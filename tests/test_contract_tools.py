"""
合同工具封装层测试（FIX-002）

测试 app/tools/contract_tools.py 中 LangChain Tool 封装后的 .invoke() 行为，
防止工具函数与规则层函数同名遮蔽（StructuredTool object is not callable）类回归。
"""

import json

import pytest

from app.api.context import reset_session_context, set_session_context
from app.tools.contract_tools import (
    extract_contract_clauses,
    match_contract_risk_rules,
    parse_contract_file,
)

CONTRACT_TEXT = """
装修合同
一、工期 75 日历天，自开工之日起算。
二、付款方式：签订合同后、开工前支付合同总价的 60%；水电完工后支付 40%。
三、保修 1 年。
"""


@pytest.fixture
def session_dir(tmp_path):
    session = tmp_path / "session_fixture"
    session.mkdir()
    token = set_session_context(str(session))
    yield session
    reset_session_context(token)


class TestParseContractFile:
    def test_reads_txt_contract(self, session_dir):
        (session_dir / "合同.txt").write_text(CONTRACT_TEXT, encoding="utf-8")
        result = parse_contract_file.invoke({"filename": "合同.txt"})
        data = json.loads(result)
        assert data["char_count"] > 0
        assert "开工前" in data["text"]
        assert data["truncated"] is False

    def test_missing_file_returns_error_not_raise(self, session_dir):
        result = parse_contract_file.invoke({"filename": "不存在.docx"})
        assert result.startswith("错误：")

    def test_empty_file_reported(self, session_dir):
        (session_dir / "empty.txt").write_text("", encoding="utf-8")
        result = parse_contract_file.invoke({"filename": "empty.txt"})
        assert result.startswith("错误：")


class TestExtractContractClauses:
    def test_returns_clauses_json(self):
        result = extract_contract_clauses.invoke({"contract_text": CONTRACT_TEXT})
        data = json.loads(result)
        assert "clauses" in data
        clauses = data["clauses"]
        assert clauses["first_payment_percent"] == 60.0
        assert clauses["duration_days"] == 75
        assert clauses["warranty_months"] == 12

    def test_empty_text_returns_error_not_raise(self):
        result = extract_contract_clauses.invoke({"contract_text": "  "})
        assert "合同文本为空" in result


class TestMatchContractRiskRules:
    def test_returns_risks_summary_disclaimer(self):
        clauses_json = extract_contract_clauses.invoke({"contract_text": CONTRACT_TEXT})
        result = match_contract_risk_rules.invoke(
            {"clauses_json": clauses_json, "contract_text": CONTRACT_TEXT}
        )
        data = json.loads(result)
        assert {"risks", "summary", "disclaimer"} <= set(data)
        assert data["summary"]["risk_count"] == len(data["risks"])
        assert "不构成法律意见" in data["disclaimer"]
        # 60% 首付 + 无增项条款 + 保修 1 年，至少触发 3 类风险
        assert data["summary"]["risk_count"] >= 3

    def test_invalid_json_returns_error_not_raise(self):
        result = match_contract_risk_rules.invoke({"clauses_json": "not-json"})
        assert result.startswith("错误：")

    def test_bad_structure_returns_error_not_raise(self):
        result = match_contract_risk_rules.invoke({"clauses_json": "[1, 2, 3]"})
        assert result.startswith("错误：")


class TestFullChain:
    def test_parse_extract_match_chain(self, session_dir):
        """验收标准：读取合同 -> 提取条款 -> 匹配风险 完整可执行。"""
        (session_dir / "装修合同.txt").write_text(CONTRACT_TEXT, encoding="utf-8")

        parsed = json.loads(parse_contract_file.invoke({"filename": "装修合同.txt"}))
        clauses_json = extract_contract_clauses.invoke({"contract_text": parsed["text"]})
        report = json.loads(
            match_contract_risk_rules.invoke(
                {"clauses_json": clauses_json, "contract_text": parsed["text"]}
            )
        )

        assert report["summary"]["risk_count"] >= 3
        risk_types = {r["risk_type"] for r in report["risks"]}
        assert "PAYMENT" in risk_types
