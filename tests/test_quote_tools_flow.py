"""
报价单端到端分析链路测试（FIX-003）

完整工具链验证：parse_quote_file -> normalize_quote_items ->
compare_quote_with_reference_price -> detect_quote_risk_items。
上下游之间传递的是工具的完整 JSON 返回值（模拟模型真实调用方式），
确保入参兼容，并验证高风险项触发 risk_found 事件。
"""

import json

import pytest

from app.api.context import reset_session_context, set_session_context
from app.tools.quote_tools import (
    compare_quote_with_reference_price,
    detect_quote_risk_items,
    normalize_quote_items,
    parse_quote_file,
)

# 构造一份包含 5 类风险的报价单（Markdown 表格）：
# 水电改造单价 400 虚高、瓷砖缺品牌型号、墙地砖铺贴计算错误、
# "水电 改造" 与水电改造重复、垃圾清运按批计价无数量
QUOTE_MARKDOWN = """# 装修报价单

| 序号 | 项目名称 | 单位 | 数量 | 单价 | 合价 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 水电改造 | ㎡ | 20 | 400 | 8000 | 全屋改 |
| 2 | 瓷砖 | ㎡ | 60 | 150 | 9000 | |
| 3 | 墙地砖铺贴 | ㎡ | 60 | 70 | 8000 | 人工 |
| 4 | 水电 改造 | ㎡ | 20 | 400 | 8000 | 二次布线 |
| 5 | 垃圾清运 | 批 | | 1500 | 1500 | |
| 合计 | | | | | 28800 | |
"""


@pytest.fixture
def session_dir(tmp_path):
    session = tmp_path / "session_flow"
    session.mkdir()
    token = set_session_context(str(session))
    yield session
    reset_session_context(token)


@pytest.fixture
def captured_risk_events(monkeypatch):
    """捕获 monitor.report_risk 调用，验证 risk_found 事件触发。"""
    from app.tools import quote_tools

    events = []
    monkeypatch.setattr(
        quote_tools.monitor,
        "report_risk",
        lambda level, title, description="": events.append(
            {"level": level, "title": title}
        ),
    )
    return events


def _write_markdown_quote(session_dir):
    (session_dir / "装修报价单.md").write_text(QUOTE_MARKDOWN, encoding="utf-8")


class TestQuoteToolChain:
    def test_full_chain_markdown(self, session_dir, captured_risk_events):
        _write_markdown_quote(session_dir)

        # 1. 解析：上下游传递完整 JSON 返回值（模拟模型行为）
        parsed_json = parse_quote_file.invoke({"filename": "装修报价单.md"})
        parsed = json.loads(parsed_json)
        assert parsed["item_count"] == 5
        assert parsed["stated_total"] == "28800"

        # 2. 标准化：直接把 parse 的完整 JSON 传入
        normalized_json = normalize_quote_items.invoke({"items_json": parsed_json})
        normalized = json.loads(normalized_json)
        assert normalized["normalized_count"] == 5
        categories = {item["category"] for item in normalized["normalized_items"]}
        assert "水电" in categories and "瓦工" in categories

        # 3. 参考价对比：直接把 normalize 的完整 JSON 传入
        compared_json = compare_quote_with_reference_price.invoke(
            {"items_json": normalized_json}
        )
        compared = json.loads(compared_json)
        assert compared["flagged_count"] >= 1  # 400 元/㎡ 水电明显虚高

        # 4. 风险检测：normalize JSON + parse 提取的标注总价
        report = json.loads(
            detect_quote_risk_items.invoke(
                {"items_json": normalized_json, "stated_total": parsed["stated_total"]}
            )
        )
        risk_types = {r["risk_type"] for r in report["risks"]}
        assert "DUPLICATE_ITEM" in risk_types
        assert "VAGUE_UNIT" in risk_types
        assert "MISSING_SPEC" in risk_types
        assert "PRICE_ABNORMAL" in risk_types
        assert "CALC_ERROR" in risk_types
        assert "TOTAL_MISMATCH" in risk_types  # 分项合计 28800-8000(重复)=20800 ≠ 28800

        # 5. 高风险项触发 risk_found 事件
        high_titles = [e["title"] for e in captured_risk_events if e["level"] == "HIGH"]
        assert high_titles, "HIGH 风险应触发 report_risk 事件"

    def test_full_chain_excel(self, session_dir, captured_risk_events):
        """Excel 是报价单主格式，独立验证多 sheet 解析入参兼容。"""
        import pandas as pd

        df = pd.DataFrame(
            [
                [1, "水电改造", "㎡", 20, 400, 8000, "全屋改"],
                [2, "卫生间防水", "㎡", 10, 80, 800, ""],
            ],
            columns=["序号", "项目名称", "单位", "数量", "单价", "合价", "备注"],
        )
        df.to_excel(session_dir / "报价.xlsx", index=False, sheet_name="半包报价")

        parsed_json = parse_quote_file.invoke({"filename": "报价.xlsx"})
        parsed = json.loads(parsed_json)
        assert parsed["item_count"] == 2
        assert parsed["items"][0]["name"] == "水电改造"

        normalized_json = normalize_quote_items.invoke({"items_json": parsed_json})
        report = json.loads(detect_quote_risk_items.invoke({"items_json": normalized_json}))
        assert any(r["risk_type"] == "PRICE_ABNORMAL" for r in report["risks"])

    def test_parse_missing_file_no_raise(self, session_dir):
        result = parse_quote_file.invoke({"filename": "没有这个文件.xlsx"})
        assert result.startswith("错误：")

    def test_chain_tolerates_raw_array_input(self, session_dir):
        """模型有时只传条目数组而非完整 JSON，工具需兼容。"""
        raw_array = json.dumps([{"name": "水电改造", "unit": "㎡", "quantity": "20", "unit_price": "400", "total": "8000", "note": ""}])
        normalized_json = normalize_quote_items.invoke({"items_json": raw_array})
        report = json.loads(detect_quote_risk_items.invoke({"items_json": normalized_json}))
        assert any(r["risk_type"] == "PRICE_ABNORMAL" for r in report["risks"])
