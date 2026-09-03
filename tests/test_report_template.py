"""
装修诊断报告模板测试

覆盖 PRD 开发计划 3.3 的验收标准：
- Markdown 报告包含固定章节
- 免责声明存在
- 文件名使用会话编号和时间
"""

import json
import re

from app.api.context import set_session_context, reset_session_context
from app.tools.markdown_tools import generate_renovation_report


VALID_ARGS = {
    "one_line_conclusion": "报价整体处于市场合理区间，但存在 2 处高危风险需在签约前确认。",
    "stage_assessment": "当前处于报价对比阶段，核心任务是核对报价完整性。",
    "budget_score": 72,
    "budget_assessment": "预算 15-18 万，与 89 平全包市场区间基本吻合。",
    "risk_items": "- 🔴【高】疑似重复计费：水电改造出现 2 次",
    "keep_items": "- 水电改造\n- 卫生间防水",
    "cut_items": "- 背景墙造型",
    "materials_advice": "- 索要主材品牌型号清单",
    "action_list": "1. 与商家确认重复项\n2. 补充书面增项确认流程",
}


def invoke_tool(tmp_path, **overrides):
    token = set_session_context(str(tmp_path / "session_test123"))
    try:
        args = {**VALID_ARGS, **overrides}
        return generate_renovation_report.invoke(args), tmp_path / "session_test123"
    finally:
        reset_session_context(token)


class TestRenovationReport:
    def test_fixed_sections_present(self, tmp_path):
        result, session_dir = invoke_tool(tmp_path)
        assert "已成功生成" in result
        md_file = next(session_dir.glob("*.md"))
        content = md_file.read_text(encoding="utf-8")
        for section in [
            "一句话结论",
            "当前装修阶段判断",
            "预算健康度",
            "风险清单",
            "必保留项",
            "可删减项",
            "建议补充",
            "下一步行动清单",
        ]:
            assert section in content, f"缺少固定章节：{section}"

    def test_disclaimer_present(self, tmp_path):
        _, session_dir = invoke_tool(tmp_path)
        content = next(session_dir.glob("*.md")).read_text(encoding="utf-8")
        assert "免责声明" in content
        assert "不构成法律、财务或工程验收意见" in content
        assert "不构成实际报价依据" in content or "参考区间" in content
        assert "不能替代律师或专业监理" in content

    def test_filename_uses_session_and_time(self, tmp_path):
        _, session_dir = invoke_tool(tmp_path)
        md_file = next(session_dir.glob("*.md"))
        assert md_file.name.startswith("装修诊断报告_test123_")
        assert re.search(r"装修诊断报告_test123_\d{6}\.md", md_file.name)

    def test_report_id_and_score(self, tmp_path):
        _, session_dir = invoke_tool(tmp_path)
        content = next(session_dir.glob("*.md")).read_text(encoding="utf-8")
        assert re.search(r"报告编号：R[0-9A-F]{14}", content)
        assert "72 / 100" in content

    def test_budget_score_clamped(self, tmp_path):
        result, session_dir = invoke_tool(tmp_path, budget_score=999)
        assert "已成功生成" in result
        content = next(session_dir.glob("*.md")).read_text(encoding="utf-8")
        assert "100 / 100" in content

    def test_risk_level_emoji_style(self, tmp_path):
        _, session_dir = invoke_tool(tmp_path)
        content = next(session_dir.glob("*.md")).read_text(encoding="utf-8")
        assert "🔴【高】" in content

    def test_no_absolute_path_in_result(self, tmp_path):
        # PRD 要求：向用户汇报时不允许输出文件路径
        result, _ = invoke_tool(tmp_path)
        assert str(tmp_path) not in result

    def test_missing_session_context_reported(self):
        # 未设置会话上下文时应返回明确错误，而不是抛异常
        result = generate_renovation_report.invoke({**VALID_ARGS})
        assert result.startswith("错误：未找到当前会话工作目录")
