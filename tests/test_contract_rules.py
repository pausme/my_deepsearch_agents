"""
合同规则引擎测试

覆盖 PRD 开发计划 4.3 的验收标准：
- 识别付款过度前置、工期责任不清、增项确认缺失等风险
- 输出明确免责声明
"""

from app.utils.contract_rules import extract_contract_clauses, match_contract_risk_rules

GOOD_CONTRACT = """
第一条 工程概况
甲方将位于杭州市滨江区的新房装修工程发包给乙方，建筑面积 89 平方米。
第二条 工期
本工程工期 75 日历天，自开工之日起算。
第三条 合同价款
合同总价 158000 元，包含全包施工及辅料。
第四条 付款方式
签订合同后、开工前支付合同总价的 30%，计 47400 元；
水电工程验收合格后支付合同总价的 30%；
瓦工木工完工后支付合同总价的 30%；
竣工验收合格后支付合同总价的 10% 尾款。
第五条 工程变更
任何增项必须经双方书面签字确认后方可施工，增项价格按附件清单执行。
第六条 材料
乙方提供的主材品牌型号见附件，如需材料替换或代用，必须经甲方书面同意。
第七条 违约责任
乙方延期竣工的，每延期一日按合同总价的千分之二支付违约金。
第八条 保修
本工程整体保修 2 年，防水工程保修 5 年。
第九条 争议解决
因本合同发生争议，双方协商不成的，向工程所在地人民法院提起诉讼。
"""

BAD_CONTRACT = """
装修合同
甲方：张三 乙方：某装饰公司
一、合同总价 120000 元。
二、付款方式：签订合同后、开工前支付合同总价的 60%；剩余 40% 在水电完工后支付。
三、乙方使用的材料如遇缺货可以更换为同等材料。
"""


class TestExtract:
    def test_payment_terms_extracted(self):
        clauses = extract_contract_clauses(GOOD_CONTRACT)
        assert clauses["first_payment_percent"] == 30.0
        assert clauses["final_payment_percent"] == 10.0
        assert len(clauses["payment_terms"]) == 4

    def test_duration_extracted(self):
        clauses = extract_contract_clauses(GOOD_CONTRACT)
        assert clauses["duration_days"] == 75

    def test_warranty_extracted(self):
        clauses = extract_contract_clauses(GOOD_CONTRACT)
        assert clauses["warranty_months"] == 60  # 防水 5 年取最大值

    def test_flags(self):
        clauses = extract_contract_clauses(GOOD_CONTRACT)
        assert clauses["has_increase_item_clause"] is True
        assert clauses["increase_written_confirm"] is True
        assert clauses["has_material_replacement_clause"] is True
        assert clauses["material_confirm_required"] is True
        assert clauses["has_delay_penalty"] is True
        assert clauses["has_breach_clause"] is True

    def test_bad_contract_flags(self):
        clauses = extract_contract_clauses(BAD_CONTRACT)
        assert clauses["first_payment_percent"] == 60.0
        assert clauses["duration_days"] is None
        assert clauses["warranty_months"] is None
        assert clauses["has_increase_item_clause"] is False


class TestRiskRules:
    def test_good_contract_few_risks(self):
        clauses = extract_contract_clauses(GOOD_CONTRACT)
        report = match_contract_risk_rules(clauses, full_text=GOOD_CONTRACT)
        risk_types = {r["risk_type"] for r in report["risks"]}
        # 规范合同不应触发付款前置、增项确认缺失、保修缺失等高风险
        assert "PAYMENT" not in risk_types or all(
            r["level"] != "HIGH" for r in report["risks"] if r["risk_type"] == "PAYMENT"
        )
        assert "CONTRACT" not in risk_types  # 增项已约定书面确认
        assert "WARRANTY" not in risk_types  # 保修 2+5 年
        assert report["disclaimer"]

    def test_high_first_payment(self):
        clauses = extract_contract_clauses(BAD_CONTRACT)
        report = match_contract_risk_rules(clauses, full_text=BAD_CONTRACT)
        payment_risks = [r for r in report["risks"] if r["risk_type"] == "PAYMENT"]
        assert any(r["level"] == "HIGH" and "首期" in r["title"] for r in payment_risks)

    def test_pre_completion_too_high(self):
        # 坏合同竣工前累计 100%，应触发累计过高风险
        clauses = extract_contract_clauses(BAD_CONTRACT)
        report = match_contract_risk_rules(clauses, full_text=BAD_CONTRACT)
        assert any("累计付款" in r["title"] for r in report["risks"])

    def test_missing_schedule_warranty_breach(self):
        clauses = extract_contract_clauses(BAD_CONTRACT)
        report = match_contract_risk_rules(clauses, full_text=BAD_CONTRACT)
        risk_types = {r["risk_type"] for r in report["risks"]}
        assert "SCHEDULE" in risk_types  # 无工期
        assert "WARRANTY" in risk_types  # 无保修
        assert "BREACH" in risk_types  # 无违约条款

    def test_material_replacement_without_confirm(self):
        clauses = extract_contract_clauses(BAD_CONTRACT)
        report = match_contract_risk_rules(clauses, full_text=BAD_CONTRACT)
        assert any(r["risk_type"] == "MATERIAL" for r in report["risks"])

    def test_no_payment_terms_at_all(self):
        clauses = extract_contract_clauses("本合同只约定了工程范围为全包装修。")
        report = match_contract_risk_rules(clauses)
        assert any("未找到付款节点条款" in r["title"] for r in report["risks"])

    def test_risk_structure_and_disclaimer(self):
        clauses = extract_contract_clauses(BAD_CONTRACT)
        report = match_contract_risk_rules(clauses, full_text=BAD_CONTRACT)
        for risk in report["risks"]:
            assert {"risk_type", "level", "title", "evidence", "description", "suggestion"} <= set(risk)
        assert "不构成法律意见" in report["disclaimer"]
        assert report["summary"]["risk_count"] == len(report["risks"])
