"""
装修合同规则引擎（纯函数，可独立测试）

从合同文本中提取关键条款（付款节点、工期、保修、增项、材料替换、违约），
并用规则做风险初筛。规则为启发式，输出必须搭配"仅供参考"提示使用；
合同文本表达多样，规则未覆盖的情况交由子智能体的模型判断补充。
"""

import re
from decimal import Decimal

# 合同风险类型英文值（与 PRD renovation_risk_item.risk_type 对齐）
RISK_TYPE_PAYMENT = "PAYMENT"        # 付款节点风险
RISK_TYPE_SCHEDULE = "SCHEDULE"      # 工期风险
RISK_TYPE_CONTRACT = "CONTRACT"      # 增项/变更流程风险
RISK_TYPE_MATERIAL = "MATERIAL"      # 材料替换风险
RISK_TYPE_WARRANTY = "WARRANTY"      # 保修责任风险
RISK_TYPE_BREACH = "BREACH"          # 违约责任风险

# 住宅装修合同行业常见分期：首付 30% 左右，尾款 5% 左右
FIRST_PAYMENT_SAFE_RATIO = Decimal("0.35")   # 开工前付款超过该比例提示风险
FINAL_PAYMENT_MIN_RATIO = Decimal("0.05")    # 尾款低于该比例提示约束力不足
MIN_WARRANTY_MONTHS = 24                     # 国家规定住宅装修最低保修期 2 年
MIN_DURATION_DAYS = 20                       # 常规 89㎡ 以下装修合理工期下限参考


def _risk(risk_type: str, level: str, title: str, evidence: str, description: str, suggestion: str) -> dict:
    """构造统一结构的风险项。"""
    return {
        "risk_type": risk_type,
        "level": level,
        "title": title,
        "evidence": evidence,
        "description": description,
        "suggestion": suggestion,
    }


def _find_context(text: str, pattern: str, window: int = 60) -> list[str]:
    """找到 pattern 命中位置并带上下文原文，作为风险依据。"""
    evidences = []
    for match in re.finditer(pattern, text):
        start = max(0, match.start() - window)
        end = min(len(text), match.end() + window)
        snippet = re.sub(r"\s+", " ", text[start:end]).strip()
        evidences.append(snippet)
        if len(evidences) >= 5:
            break
    return evidences


def extract_contract_clauses(text: str) -> dict:
    """
    从合同全文提取关键条款要素

    :param text: 合同全文文本
    :return: 条款要素 dict（供 match_contract_risk_rules 消费，也可直接给模型阅读）
    """
    # 付款条款：找带百分比的行，通常出现在"付款方式/付款节点"章节
    payment_terms: list[dict] = []
    for line in text.splitlines():
        line_clean = line.strip()
        if not line_clean or not re.search(r"付款|支付|款", line_clean):
            continue
        percents = [Decimal(p) for p in re.findall(r"(\d{1,3}(?:\.\d+)?)\s*%", line_clean)]
        if percents:
            payment_terms.append(
                {
                    "text": re.sub(r"\s+", " ", line_clean)[:200],
                    "percents": [float(p) for p in percents],
                }
            )

    # 开工前（首期）付款比例：命中 开工前/签订后/首付/预付 的条款中的最大百分比
    first_payment_percent = None
    for term in payment_terms:
        if re.search(r"开工前|开工之日起|签订.{0,10}(后|之日起)|首付|预付|第一期", term["text"]):
            candidate = max(Decimal(str(p)) for p in term["percents"])
            if first_payment_percent is None or candidate > first_payment_percent:
                first_payment_percent = candidate

    # 竣工验收前累计付款：按条款行累加（同一行出现多个百分比视为多笔，求和），
    # 尾款行（命中"竣工验收/尾款/保修后/质保金"）不计入累计；
    # 注意"水电验收合格后"这类中期节点不算尾款
    pre_completion_percent = None
    final_payment_percent = None
    running = Decimal("0")
    for term in payment_terms:
        unique_percents = {Decimal(str(p)) for p in term["percents"]}
        if re.search(r"尾款|竣工验收(合格)?后|保修(期满)?后|质保金", term["text"]):
            candidate = max(unique_percents)
            if final_payment_percent is None or candidate > final_payment_percent:
                final_payment_percent = candidate
            continue
        running += sum(unique_percents, Decimal("0"))
    if running > 0:
        pre_completion_percent = running

    # 工期：开/竣工日之间或"XX 日历天/工作日"
    duration_days = None
    duration_text = None
    for match in re.finditer(r"工期.{0,30}?(\d{1,4})\s*(日历天|个工作日|天|日)", text):
        duration_days = int(match.group(1))
        duration_text = re.sub(r"\s+", " ", match.group(0))
        break

    has_delay_penalty = bool(re.search(r"(延期|逾期|延误).{0,40}(违约|赔偿|每日|每天|千分之|万分之)", text))

    # 保修：保修/质保 + 年/月
    warranty_months = None
    warranty_text = None
    for match in re.finditer(r"(保修|质保)[^。；\n]{0,40}?(\d{1,2})\s*(年|个月)", text):
        value = int(match.group(2))
        months = value * 12 if match.group(3) == "年" else value
        if warranty_months is None or months > warranty_months:
            warranty_months = months
            warranty_text = re.sub(r"\s+", " ", match.group(0))

    # 增项与变更流程
    has_increase_item_clause = bool(re.search(r"增项|增加项目|工程变更|项目变更|加项", text))
    increase_written_confirm = bool(
        re.search(r"增项[^。；\n]{0,60}(书面|签字|签名|确认单|变更单|双方确认)", text, re.S)
        or re.search(r"(书面|签字|变更单)[^。；\n]{0,60}增项", text, re.S)
    )

    # 材料替换/代用是否约定业主确认
    has_material_replacement_clause = bool(re.search(r"(材料|主材|辅材)[^。；\n]{0,30}(替换|代用|更换|变更|代替)", text))
    material_confirm_required = bool(
        re.search(r"(替换|代用|更换|变更|代替)[^。；\n]{0,50}(甲方|业主|发包方|同意|确认|认可)", text)
    )

    has_breach_clause = bool(re.search(r"违约", text))
    has_dispute_clause = bool(re.search(r"(争议|纠纷).{0,30}(仲裁|诉讼|人民法院)", text, re.S))
    has_total_price_clause = bool(re.search(r"(合同总价|总价|工程造价|合同价款)[^。；\n]{0,40}(\d|元)", text))

    return {
        "payment_terms": payment_terms,
        "first_payment_percent": float(first_payment_percent) if first_payment_percent is not None else None,
        "pre_completion_percent": float(pre_completion_percent) if pre_completion_percent is not None else None,
        "final_payment_percent": float(final_payment_percent) if final_payment_percent is not None else None,
        "duration_days": duration_days,
        "duration_text": duration_text,
        "has_delay_penalty": has_delay_penalty,
        "warranty_months": warranty_months,
        "warranty_text": warranty_text,
        "has_increase_item_clause": has_increase_item_clause,
        "increase_written_confirm": increase_written_confirm,
        "has_material_replacement_clause": has_material_replacement_clause,
        "material_confirm_required": material_confirm_required,
        "has_breach_clause": has_breach_clause,
        "has_dispute_clause": has_dispute_clause,
        "has_total_price_clause": has_total_price_clause,
    }


def match_contract_risk_rules(clauses: dict, full_text: str = "") -> dict:
    """
    合同条款风险匹配

    :param clauses: extract_contract_clauses 的输出
    :param full_text: 合同原文（用于给风险项附上原文依据）
    :return: {"risks": [...], "summary": {...}, "disclaimer": str}
    """
    risks: list[dict] = []
    first = clauses.get("first_payment_percent")
    pre_completion = clauses.get("pre_completion_percent")
    final = clauses.get("final_payment_percent")

    # 1. 付款过度前置
    if first is not None and Decimal(str(first)) > FIRST_PAYMENT_SAFE_RATIO * 100:
        risks.append(
            _risk(
                RISK_TYPE_PAYMENT,
                "HIGH",
                f"首期付款比例过高（{first}%）",
                _find_context(full_text, r"开工前|首付|预付|第一期") or "合同付款条款",
                "开工前付款比例明显超过行业常见的 30% 左右，施工缺乏资金约束，"
                "一旦出现争议业主较为被动。",
                "争取首期付款降到 30% 以内，或约定首期款分期支付；比例调整写入补充协议。",
            )
        )

    # 2. 竣工验收前累计付款过高（>=95% 意味着验收环节没有任何保留款项；
    #    行业常见的 30/30/30/10 节奏竣工前为 90%，不触发）
    if pre_completion is not None and Decimal(str(pre_completion)) >= Decimal("95"):
        risks.append(
            _risk(
                RISK_TYPE_PAYMENT,
                "HIGH",
                f"竣工验收前累计付款约 {pre_completion}%，验收环节无保留款",
                "付款条款分期累计",
                "竣工验收前支付全部或接近全部款项，施工质量和工期完全失去资金约束，"
                "一旦验收争议业主没有任何抓手。",
                "把至少 5%-10% 的款项调整到竣工验收合格后支付。",
            )
        )

    # 3. 尾款比例过低
    if final is not None and Decimal(str(final)) < FINAL_PAYMENT_MIN_RATIO * 100:
        risks.append(
            _risk(
                RISK_TYPE_PAYMENT,
                "MEDIUM",
                f"尾款比例仅 {final}%，约束力不足",
                "付款条款中的尾款约定",
                "尾款是对施工质量最重要的保留手段，比例过低时整改阶段缺乏抓手。",
                "争取尾款不低于 5%，并明确尾款支付以验收合格和保修责任履行为前提。",
            )
        )

    # 4. 未找到付款条款
    if not clauses.get("payment_terms"):
        risks.append(
            _risk(
                RISK_TYPE_PAYMENT,
                "HIGH",
                "未找到付款节点条款",
                "全文未识别出带百分比的付款约定",
                "付款节奏没有书面约定，付款时点完全依赖口头沟通，极易产生纠纷。",
                "要求在合同中写明每个阶段的付款比例和支付条件。",
            )
        )

    # 5. 工期缺失或过短
    duration_days = clauses.get("duration_days")
    if duration_days is None:
        risks.append(
            _risk(
                RISK_TYPE_SCHEDULE,
                "MEDIUM",
                "未找到工期约定",
                "全文未识别出工期天数表述",
                "没有书面工期就没有延期认定的依据，工期拖延时无法主张责任。",
                "补充约定开工日、竣工日和总日历天数，并写入延期违约条款。",
            )
        )
    elif duration_days < MIN_DURATION_DAYS:
        risks.append(
            _risk(
                RISK_TYPE_SCHEDULE,
                "LOW",
                f"工期仅 {duration_days} 天，明显偏短",
                clauses.get("duration_text") or "工期条款",
                "工期过短可能意味着工艺压缩（例如基层未干透就进行下道工序），影响质量。",
                "确认工期是否包含养护时间；必要时按工序拆解工期表。",
            )
        )

    # 6. 有工期但无延期违约条款
    if duration_days is not None and not clauses.get("has_delay_penalty"):
        risks.append(
            _risk(
                RISK_TYPE_SCHEDULE,
                "MEDIUM",
                "有工期约定但未找到延期违约责任",
                "未识别出延期/逾期违约金表述",
                "只约定工期不约定延期责任，工期条款基本没有约束力。",
                "补充约定延期违约金（常见为合同价的千分之一到千分之五每天）。",
            )
        )

    # 7. 增项无书面确认流程
    if clauses.get("has_increase_item_clause") and not clauses.get("increase_written_confirm"):
        risks.append(
            _risk(
                RISK_TYPE_CONTRACT,
                "HIGH",
                "增项条款未约定书面确认流程",
                _find_context(full_text, r"增项|工程变更|项目变更") or "增项相关条款",
                "增项只有口头确认时，结算金额可能远超签约价，这是装修超支的最常见原因。",
                "约定：任何增项必须双方书面签字确认并附价格清单后方可施工。",
            )
        )

    # 8. 材料替换未要求业主确认
    if clauses.get("has_material_replacement_clause") and not clauses.get("material_confirm_required"):
        risks.append(
            _risk(
                RISK_TYPE_MATERIAL,
                "MEDIUM",
                "材料替换条款未要求业主确认",
                _find_context(full_text, r"(材料|主材)[^。；\n]{0,30}(替换|代用|更换|变更|代替)") or "材料相关条款",
                "允许施工方自行替换材料而不需确认时，实际用材可能低于报价承诺。",
                "约定材料品牌型号变更必须经业主书面同意，否则按报价品牌供货或补差价。",
            )
        )

    # 9. 保修缺失或不足
    warranty_months = clauses.get("warranty_months")
    if warranty_months is None:
        risks.append(
            _risk(
                RISK_TYPE_WARRANTY,
                "MEDIUM",
                "未找到保修条款",
                "全文未识别出保修/质保年限",
                "国家规定住宅装修最低保修期为 2 年（防水工程 5 年），缺少书面保修约定无法主张售后责任。",
                "补充保修条款：写明保修范围、年限（整体不低于 2 年、防水不低于 5 年）和响应时限。",
            )
        )
    elif warranty_months < MIN_WARRANTY_MONTHS:
        risks.append(
            _risk(
                RISK_TYPE_WARRANTY,
                "MEDIUM",
                f"保修期 {warranty_months} 个月，低于国家最低标准",
                clauses.get("warranty_text") or "保修条款",
                "《住宅室内装饰装修管理办法》规定最低保修期 2 年，防水工程 5 年，低于该标准的条款无效。",
                "要求按国家规定修改保修期，并单独注明防水工程保修 5 年。",
            )
        )

    # 10. 违约责任缺失
    if not clauses.get("has_breach_clause"):
        risks.append(
            _risk(
                RISK_TYPE_BREACH,
                "MEDIUM",
                "未找到违约责任条款",
                "全文未出现违约相关表述",
                "双方违约责任没有约定时，出现纠纷只能事后协商，维权成本高。",
                "补充双向违约责任条款，包括延期、质量问题、付款拖欠的处理方式。",
            )
        )

    level_counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for risk in risks:
        level_counts[risk["level"]] = level_counts.get(risk["level"], 0) + 1

    return {
        "risks": risks,
        "summary": {"risk_count": len(risks), **level_counts},
        "disclaimer": (
            "以上为基于常见装修合同风险的初筛结果，仅供参考，不构成法律意见；"
            "签约前建议请律师或专业监理复核合同全文。"
        ),
    }
