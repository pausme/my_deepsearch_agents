"""
报价单规则引擎（纯函数，可独立测试）

对报价单条目做标准化和风险检测，不依赖 LLM：
- normalize_quote_items：条目归类、字段清洗
- compare_with_reference：单价与参考价区间对比
- detect_quote_risks：漏项/重复/模糊单位/缺规格/价格异常/计算错误/总价对不上

工具层（app/tools/quote_tools.py）负责文件解析和 monitor 埋点，
本模块只处理内存中的结构化条目，输入输出均为 dict/list/str。
"""

import re
from decimal import Decimal, InvalidOperation

from app.data.renovation_reference import (
    CATEGORY_KEYWORDS,
    COMMON_CATEGORIES,
    MAIN_MATERIAL_KEYWORDS,
    REFERENCE_PRICES,
    RISK_TYPE_CALC_ERROR,
    RISK_TYPE_DUPLICATE,
    RISK_TYPE_MISSING,
    RISK_TYPE_MISSING_SPEC,
    RISK_TYPE_PRICE_ABNORMAL,
    RISK_TYPE_TOTAL_MISMATCH,
    RISK_TYPE_VAGUE_UNIT,
    VAGUE_UNITS,
    CITY_LEVEL_NOTE,
)

# 条目名称清洗：去空格、全角转半角、去标点差异，用于重复项识别
_FULL_TO_HALF = str.maketrans("０１２３４５６７８９ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ（）：；，", "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz():;,")


def _to_number(value) -> Decimal | None:
    """把条目字段转成 Decimal；无法解析时返回 None。"""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    text = str(value).strip().replace(",", "").replace("￥", "").replace("元", "")
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _clean_name(name: str) -> str:
    """条目名称归一：全角转半角、去空白和常见分隔符，用于重复项识别。"""
    text = str(name or "").translate(_FULL_TO_HALF)
    return re.sub(r"[\s（）()：:；;，,、\-—_/\\]+", "", text)


def guess_category(name: str, note: str = "") -> str:
    """根据条目名称和备注关键词猜测所属施工类目；未命中返回空字符串。"""
    text = f"{name} {note}"
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            return category
    return ""


def _has_spec_hint(item: dict) -> bool:
    """判断条目是否带品牌/型号/规格信息（ASCII 数字字母组合或明确品牌字样）。"""
    text = f"{item.get('name', '')} {item.get('note', '')} {item.get('brand_spec', '')}"
    if item.get("brand_spec"):
        return True
    # 规格常见写法：600*600、DN25、4平方、A+、E0 级等
    if re.search(r"\d+(\.\d+)?\s*[*×xX]\s*\d+", text):
        return True
    if re.search(r"[A-Za-z0-9]{2,}", str(text).translate(_FULL_TO_HALF)):
        return True
    return False


def normalize_quote_items(items: list[dict]) -> list[dict]:
    """
    标准化报价条目

    输入条目允许的字段：name/unit/quantity/unit_price/total/note（解析层产出）
    输出条目固定字段：name/unit/quantity/unit_price/total/note/category/norm_key
    category 为猜测的施工类目（可能为空），norm_key 用于重复项识别
    """
    normalized = []
    for item in items:
        name = str(item.get("name", "") or "").strip()
        if not name:
            continue

        unit = str(item.get("unit", "") or "").strip()
        note = str(item.get("note", "") or "").strip()
        category = guess_category(name, note)

        normalized.append(
            {
                "name": name,
                "unit": unit,
                "quantity": str(_to_number(item.get("quantity")) or ""),
                "unit_price": str(_to_number(item.get("unit_price")) or ""),
                "total": str(_to_number(item.get("total")) or ""),
                "note": note,
                "category": category,
                "norm_key": _clean_name(name),
            }
        )
    return normalized


def compare_with_reference(items: list[dict]) -> list[dict]:
    """
    条目单价与内置参考价区间对比

    返回对比结果列表（仅含有参考价且解析出单价的条目）：
    {name, category, unit_price, reference_low, reference_high, price_unit, flag, note}
    flag: ok / high / low
    """
    results = []
    for item in items:
        category = item.get("category", "")
        # 先精确匹配"瓦工-找平"这类子类目，再退回主类目
        reference = REFERENCE_PRICES.get(category)
        if reference is None and "-" in category:
            reference = REFERENCE_PRICES.get(category.split("-")[0])
        if reference is None:
            # 主材类目按主材关键词匹配
            for material, material_ref in REFERENCE_PRICES.items():
                if material in item.get("name", ""):
                    reference = material_ref
                    category = material
                    break
        if reference is None:
            continue

        unit_price = _to_number(item.get("unit_price"))
        if unit_price is None:
            continue

        # 计价口径不一致时跳过对比：条目按项/批/套计价，而参考价按面积口径，没有可比性
        item_unit = (item.get("unit") or "").strip()
        if item_unit in VAGUE_UNITS and "㎡" in reference["price_unit"]:
            continue

        low = Decimal(str(reference["low"]))
        high = Decimal(str(reference["high"]))
        # 参考区间按施工口径给出；单价明显越界才标记，区间内浮动属正常
        if unit_price > high * Decimal("1.5"):
            flag = "high"
        elif unit_price < low * Decimal("0.5"):
            flag = "low"
        else:
            flag = "ok"

        results.append(
            {
                "name": item.get("name", ""),
                "category": category,
                "unit_price": float(unit_price),
                "reference_low": reference["low"],
                "reference_high": reference["high"],
                "price_unit": reference["price_unit"],
                "flag": flag,
                "note": reference["note"],
            }
        )
    return results


def _risk(risk_type: str, level: str, title: str, evidence: str, description: str, suggestion: str) -> dict:
    """构造统一结构的风险项（与 PRD renovation_risk_item 字段对齐）。"""
    return {
        "risk_type": risk_type,
        "level": level,
        "title": title,
        "evidence": evidence,
        "description": description,
        "suggestion": suggestion,
    }


def detect_quote_risks(
    items: list[dict],
    comparison: list[dict] | None = None,
    stated_total=None,
) -> dict:
    """
    报价单风险检测主入口

    :param items: normalize_quote_items 输出的标准化条目
    :param comparison: compare_with_reference 输出的价格对比结果
    :param stated_total: 报价单上标注的合计金额（解析层提取，可能为 None）
    :return: {"risks": [...], "summary": {...}, "price_note": str}
    """
    risks: list[dict] = []

    # 1. 疑似漏项：条目数足够多（>=5）时，检查常见类目覆盖情况
    if len(items) >= 5:
        present_categories = {item["category"] for item in items if item.get("category")}
        missing = [
            f"{cat}（{desc}）"
            for cat, desc in COMMON_CATEGORIES.items()
            if cat not in present_categories
        ]
        if missing:
            risks.append(
                _risk(
                    RISK_TYPE_MISSING,
                    "MEDIUM",
                    f"疑似漏项：未见{'、'.join(missing[:4])}{'等' if len(missing) > 4 else ''}类目",
                    f"报价单共 {len(items)} 条，未覆盖类目：{'、'.join(missing)}",
                    "常见装修流程包含拆改、水电、防水、瓦工、木作、油漆、安装、保洁清运等环节，"
                    "缺失类目可能是后期增项的主要来源。",
                    "向商家确认缺失项目是包含在总价中、由其他方式施工，还是后续增项；要求书面写明。",
                )
            )

    # 2. 疑似重复计费：归一后同名条目出现多次
    seen: dict[str, list[dict]] = {}
    for item in items:
        seen.setdefault(item["norm_key"], []).append(item)
    for norm_key, group in seen.items():
        if len(group) > 1:
            names = "；".join(f"{g['name']}({g['total'] or '价待确认'})" for g in group)
            risks.append(
                _risk(
                    RISK_TYPE_DUPLICATE,
                    "HIGH",
                    f"疑似重复计费：{group[0]['name']} 出现 {len(group)} 次",
                    names,
                    "同一项目分行出现且各自计价，可能是分区域报价，也可能是重复收费。",
                    "要求商家说明多次出现的原委；如为不同区域施工，应合并标注区域和数量。",
                )
            )

    # 3. 模糊计价单位：单位为 项/批/套 等，且缺少数量
    for item in items:
        if item["unit"] in VAGUE_UNITS and not item["quantity"]:
            risks.append(
                _risk(
                    RISK_TYPE_VAGUE_UNIT,
                    "MEDIUM",
                    f"计价单位含混：{item['name']}（单位：{item['unit']}）",
                    f"{item['name']}，单位“{item['unit']}”，未填写数量",
                    "按“项/批/套”计价且无数量拆解时，实际工程量与计价基准难以核对，容易成为增项入口。",
                    "要求商家补充计量方式和工程量拆解（例如按面积、延米或点位数），并写入报价单。",
                )
            )

    # 4. 缺品牌/型号/规格：主材关键词条目无规格信息
    for item in items:
        name = item["name"]
        if any(keyword in name for keyword in MAIN_MATERIAL_KEYWORDS) and not _has_spec_hint(item):
            risks.append(
                _risk(
                    RISK_TYPE_MISSING_SPEC,
                    "MEDIUM",
                    f"主材信息不完整：{name}",
                    f"{name}，未标注品牌/型号/规格（备注：{item['note'] or '无'}）",
                    "主材缺少品牌型号时，施工阶段可能被以次充好或签约后要求加钱升级。",
                    "要求报价单补充主材的品牌、型号、规格和等级，并约定更换需业主书面确认。",
                )
            )

    # 5. 单价异常：与参考价区间对比
    for row in comparison or []:
        if row.get("flag") == "high":
            risks.append(
                _risk(
                    RISK_TYPE_PRICE_ABNORMAL,
                    "HIGH",
                    f"单价明显高于参考区间：{row['name']}",
                    f"报价 {row['unit_price']} 元，参考区间 {row['reference_low']}-{row['reference_high']} "
                    f"{row['price_unit']}（{row['note']}）",
                    "该单价超出常见市场区间较多，可能包含高端工艺/材料，也可能存在虚高。",
                    "要求商家解释单价构成（材料档次、工艺标准），并对比 2-3 家其他报价。",
                )
            )
        elif row.get("flag") == "low":
            risks.append(
                _risk(
                    RISK_TYPE_PRICE_ABNORMAL,
                    "MEDIUM",
                    f"单价明显低于参考区间：{row['name']}",
                    f"报价 {row['unit_price']} 元，参考区间 {row['reference_low']}-{row['reference_high']} "
                    f"{row['price_unit']}（{row['note']}）",
                    "明显低价可能意味着材料档次下调、工艺缩水，或以低价签约后靠增项找回。",
                    "确认低价对应的具体材料和工艺标准，并写入合同附件。",
                )
            )

    # 6. 计算错误：数量×单价与合价不一致
    for item in items:
        quantity = _to_number(item.get("quantity"))
        unit_price = _to_number(item.get("unit_price"))
        total = _to_number(item.get("total"))
        if quantity is None or unit_price is None or total is None:
            continue
        if total == 0:
            continue
        expected = quantity * unit_price
        if abs(expected - total) / abs(total) > Decimal("0.02"):
            risks.append(
                _risk(
                    RISK_TYPE_CALC_ERROR,
                    "MEDIUM",
                    f"金额计算不一致：{item['name']}",
                    f"{quantity} × {unit_price} = {expected}，报价合价为 {total}",
                    "数量乘单价与合价不一致，可能是优惠折让，也可能是录入错误或隐性加价。",
                    "要求商家解释差异原因，修正报价单后再核对总价。",
                )
            )

    # 7. 合计对不上：条目合计与报价单标注总价不一致
    stated = _to_number(stated_total)
    if stated and items:
        item_sum = sum(
            (t for t in (_to_number(i.get("total")) for i in items) if t is not None),
            Decimal("0"),
        )
        if item_sum and abs(item_sum - stated) / abs(stated) > Decimal("0.02"):
            risks.append(
                _risk(
                    RISK_TYPE_TOTAL_MISMATCH,
                    "HIGH",
                    "条目合计与报价总价不一致",
                    f"分项合计 {item_sum} 元，报价单标注总价 {stated} 元",
                    "总价与分项不一致时，签约价和实际结算价可能存在差距，也可能存在未列明的收费项。",
                    "要求商家提供总价构成说明，列明管理费、税金、损耗等所有收费项。",
                )
            )

    level_counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for risk in risks:
        level_counts[risk["level"]] = level_counts.get(risk["level"], 0) + 1

    return {
        "risks": risks,
        "summary": {
            "item_count": len(items),
            "risk_count": len(risks),
            **level_counts,
        },
        "price_note": CITY_LEVEL_NOTE,
    }
