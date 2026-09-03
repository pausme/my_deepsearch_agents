"""
报告生成到 PDF 端到端测试（FIX-008）

覆盖 C 端交付核心闭环：generate_renovation_report 生成 Markdown ->
convert_md_to_pdf 转换 PDF。验收标准：
- PDF 文件存在且大小大于 0
- 生成文件仍在当前 session 目录内
- 工具返回给用户的信息不包含服务端绝对路径
- 失败时返回明确错误，不抛异常
"""

import json

from app.api.context import reset_session_context, set_session_context
from app.tools.markdown_tools import generate_renovation_report
from app.tools.pdf_tools import convert_md_to_pdf

VALID_ARGS = {
    "one_line_conclusion": "报价整体处于市场合理区间，但存在高危风险需签约前确认。",
    "stage_assessment": "当前处于报价对比阶段。",
    "budget_score": 72,
    "budget_assessment": "预算与市场区间基本吻合。",
    "risk_items": "- 【高】疑似重复计费：水电改造出现 2 次",
    "keep_items": "- 水电改造\n- 卫生间防水",
    "cut_items": "- 背景墙造型",
    "materials_advice": "- 索要主材品牌型号清单",
    "action_list": "1. 与商家确认重复项",
}


def test_markdown_to_pdf_flow(tmp_path):
    session_dir = tmp_path / "session_pdfflow"
    session_dir.mkdir()
    token = set_session_context(str(session_dir))
    try:
        # 1. 生成 Markdown 报告
        md_result = generate_renovation_report.invoke({**VALID_ARGS})
        assert "已成功生成" in md_result
        assert str(tmp_path) not in md_result, "返回信息不应包含服务端绝对路径"

        md_files = list(session_dir.glob("装修诊断报告_*.md"))
        assert len(md_files) == 1
        md_file = md_files[0]

        # 2. 转换为 PDF
        pdf_result = convert_md_to_pdf.invoke({"md_filename": md_file.name})
        assert "成功转换" in pdf_result
        assert str(tmp_path) not in pdf_result, "返回信息不应包含服务端绝对路径"

        # 3. PDF 存在、非空、且留在会话目录内
        pdf_file = md_file.with_suffix(".pdf")
        assert pdf_file.exists()
        assert pdf_file.stat().st_size > 0
        assert pdf_file.parent == session_dir
    finally:
        reset_session_context(token)


def test_pdf_with_custom_filename(tmp_path):
    session_dir = tmp_path / "session_pdfflow2"
    session_dir.mkdir()
    token = set_session_context(str(session_dir))
    try:
        generate_renovation_report.invoke({**VALID_ARGS})
        result = convert_md_to_pdf.invoke(
            {
                "md_filename": [f.name for f in session_dir.glob("*.md")][0],
                "pdf_filename": "给设计师看.pdf",
            }
        )
        assert "成功转换" in result
        assert (session_dir / "给设计师看.pdf").exists()
    finally:
        reset_session_context(token)


def test_convert_missing_file_returns_error(tmp_path):
    session_dir = tmp_path / "session_pdfflow3"
    session_dir.mkdir()
    token = set_session_context(str(session_dir))
    try:
        result = convert_md_to_pdf.invoke({"md_filename": "不存在的报告.md"})
        assert result.startswith("错误：")
    finally:
        reset_session_context(token)


def test_pdf_conversion_without_session_context():
    # 无会话上下文时 resolve_path 会按进程目录解析，找不到文件应返回明确错误
    result = convert_md_to_pdf.invoke({"md_filename": "完全不存在.md"})
    assert "错误" in result or "转换失败" in result
