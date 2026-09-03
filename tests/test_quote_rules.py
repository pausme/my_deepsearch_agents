"""
报价单规则引擎测试

覆盖 PRD 开发计划 4.2 的验收标准：
- 至少识别 5 类报价风险（实现为 7 类）
- 风险项输出"问题、依据、影响、建议动作"结构
"""

import json

from app.utils.quote_rules import (
    compare_with_reference,
    detect_quote_risks,
    guess_category,
    normalize_quote_items,
)
from app.tools.quote_tools import (
    _extract_items_from_rows,
    _load_items,
    _parse_tabular_text,
)


class TestLoadItems:
    def test_accepts_both_wrapper_keys(self):
        # 回归：模型可能把上一个工具的完整 JSON 直接传下来，两种包装键都要兼容
        assert _load_items('{"items": [{"name": "a"}]}') == [{"name": "a"}]
        assert _load_items('{"normalized_items": [{"name": "b"}]}') == [{"name": "b"}]
        assert _load_items('[{"name": "c"}]') == [{"name": "c"}]


def make_items(*rows):
    """快捷构造标准化条目。"""
    keys = ["name", "unit", "quantity", "unit_price", "total", "note"]
    raw = [dict(zip(keys, row)) for row in rows]
    return normalize_quote_items(raw)


class TestNormalize:
    def test_category_guess(self):
        assert guess_category("水电改造") == "水电"
        assert guess_category("卫生间防水") == "防水"
        assert guess_category("墙地砖铺贴") == "瓦工"
        assert guess_category("乳胶漆滚刷") == "油漆"
        assert guess_category("神秘项目") == ""

    def test_normalize_adds_category_and_key(self):
        items = make_items(("水电改造", "㎡", "20", "120", "2400", ""))
        assert items[0]["category"] == "水电"
        assert items[0]["norm_key"] == "水电改造"

    def test_empty_name_dropped(self):
        items = make_items(("", "项", "", "", "100", ""))
        assert items == []


class TestCompareReference:
    def test_overpriced_flagged_high(self):
        items = make_items(("水电改造", "㎡", "20", "400", "8000", ""))
        rows = compare_with_reference(items)
        assert rows and rows[0]["flag"] == "high"

    def test_normal_price_ok(self):
        items = make_items(("水电改造", "㎡", "20", "100", "2000", ""))
        rows = compare_with_reference(items)
        assert rows and rows[0]["flag"] == "ok"

    def test_vague_unit_skips_area_reference(self):
        # 条目按"项"计价而参考价按"㎡"，口径不同应跳过对比
        items = make_items(("水电改造", "项", "", "", "5000", ""))
        rows = compare_with_reference(items)
        assert rows == []


class TestDetectRisks:
    def test_missing_item_detected(self):
        # 条目数足够（>=5）但只覆盖水电/瓦工/油漆，缺拆改、防水等类目
        items = make_items(
            ("拆除旧墙", "项", "1", "2000", "2000", ""),
            ("水电改造", "㎡", "20", "100", "2000", ""),
            ("墙地砖铺贴", "㎡", "60", "70", "4200", ""),
            ("乳胶漆", "㎡", "150", "40", "6000", ""),
            ("开荒保洁", "㎡", "89", "8", "712", ""),
        )
        report = detect_quote_risks(items)
        missing = [r for r in report["risks"] if r["risk_type"] == "MISSING_ITEM"]
        assert missing
        assert "防水" in missing[0]["evidence"]

    def test_small_quote_no_missing_warning(self):
        # 条目很少时不做漏项判断（可能只是单项咨询）
        items = make_items(
            ("水电改造", "㎡", "20", "100", "2000", ""),
            ("卫生间防水", "㎡", "10", "80", "800", ""),
        )
        report = detect_quote_risks(items)
        assert not any(r["risk_type"] == "MISSING_ITEM" for r in report["risks"])

    def test_duplicate_detected(self):
        items = make_items(
            ("水电改造", "㎡", "20", "100", "2000", ""),
            ("水电 改造", "㎡", "20", "100", "2000", ""),
        )
        report = detect_quote_risks(items)
        duplicates = [r for r in report["risks"] if r["risk_type"] == "DUPLICATE_ITEM"]
        assert duplicates and duplicates[0]["level"] == "HIGH"

    def test_vague_unit_detected(self):
        items = make_items(("垃圾清运", "批", "", "", "1500", ""))
        report = detect_quote_risks(items)
        assert any(r["risk_type"] == "VAGUE_UNIT" for r in report["risks"])

    def test_missing_spec_detected(self):
        items = make_items(("瓷砖", "㎡", "60", "150", "9000", ""))
        report = detect_quote_risks(items)
        assert any(r["risk_type"] == "MISSING_SPEC" for r in report["risks"])

    def test_price_abnormal_detected(self):
        items = make_items(("水电改造", "㎡", "20", "300", "6000", ""))
        comparison = compare_with_reference(items)
        report = detect_quote_risks(items, comparison=comparison)
        assert any(r["risk_type"] == "PRICE_ABNORMAL" for r in report["risks"])

    def test_calc_error_detected(self):
        items = make_items(("水电改造", "㎡", "20", "100", "3000", ""))
        report = detect_quote_risks(items)
        assert any(r["risk_type"] == "CALC_ERROR" for r in report["risks"])

    def test_total_mismatch_detected(self):
        items = make_items(
            ("水电改造", "㎡", "20", "100", "2000", ""),
            ("卫生间防水", "㎡", "10", "80", "800", ""),
        )
        report = detect_quote_risks(items, stated_total="99999")
        assert any(r["risk_type"] == "TOTAL_MISMATCH" for r in report["risks"])

    def test_risk_structure_complete(self):
        # 验收标准：输出"问题、依据、影响、建议动作"
        items = make_items(("水电改造", "㎡", "20", "400", "8000", ""))
        comparison = compare_with_reference(items)
        report = detect_quote_risks(items, comparison=comparison)
        for risk in report["risks"]:
            assert {"risk_type", "level", "title", "evidence", "description", "suggestion"} <= set(risk)

    def test_more_than_five_risk_types(self):
        # 组合条目一次触发 6 类：漏项+模糊单位+缺规格+价格异常+计算错误+总价不一致
        items = make_items(
            ("拆除旧墙", "项", "", "500", "1", ""),          # 模糊单位（项、无数量）
            ("水电改造", "㎡", "20", "100", "2000", ""),     # 正常
            ("瓷砖", "㎡", "60", "800", "48000", ""),        # 缺规格 + 单价异常偏高
            ("墙地砖铺贴", "㎡", "60", "70", "8000", ""),    # 计算错误（60×70≠8000）
            ("开荒保洁", "㎡", "89", "8", "712", ""),        # 凑足 5 条触发漏项
        )
        comparison = compare_with_reference(items)
        report = detect_quote_risks(items, comparison=comparison, stated_total="123456")
        risk_types = {r["risk_type"] for r in report["risks"]}
        assert {
            "MISSING_ITEM",
            "VAGUE_UNIT",
            "MISSING_SPEC",
            "PRICE_ABNORMAL",
            "CALC_ERROR",
            "TOTAL_MISMATCH",
        } <= risk_types

    def test_summary_counts(self):
        items = make_items(("水电改造", "㎡", "20", "100", "2000", ""))
        report = detect_quote_risks(items)
        assert report["summary"]["item_count"] == 1
        assert report["summary"]["risk_count"] == len(report["risks"])


class TestExtractFromRows:
    def test_excel_style_rows(self):
        rows = [
            ["序号", "项目名称", "单位", "数量", "单价", "合价", "备注"],
            [1, "水电改造", "㎡", 20, 100, 2000, "全改"],
            [2, "卫生间防水", "㎡", 10, 80, 800, ""],
            ["", "合计", "", "", "", 2800, ""],
        ]
        items, stated_total = _extract_items_from_rows(rows)
        assert len(items) == 2
        assert items[0]["name"] == "水电改造"
        assert items[0]["unit_price"] == "100"
        assert stated_total == "2800"

    def test_markdown_pipe_table(self):
        # 生产链路：_parse_tabular_text 先把文本转成二维行，再提取条目
        text = "| 项目名称 | 单位 | 数量 | 单价 | 合价 |\n|---|---|---|---|---|\n| 墙地砖铺贴 | ㎡ | 60 | 70 | 4200 |"
        rows = _parse_tabular_text(text)
        assert len(rows) == 2  # Markdown 分隔行被跳过
        items, _ = _extract_items_from_rows(rows)
        assert len(items) == 1
        assert items[0]["name"] == "墙地砖铺贴"
        assert items[0]["total"] == "4200"

    def test_no_header_returns_empty(self):
        items, stated_total = _extract_items_from_rows([["随便一行字"], ["另一行字"]])
        assert items == []
        assert stated_total is None
