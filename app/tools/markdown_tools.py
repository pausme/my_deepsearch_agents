"""
Markdown 文件生成工具

供主智能体把最终整理后的内容写入当前会话工作目录。工具会把模型传入的
filename/path 交给 resolve_path 统一解析，避免模型直接操作真实绝对路径。

装修诊断报告使用 generate_renovation_report：固定章节模板 + 结构化输入，
保证报告结构稳定并自动附加免责声明（模板见 app/templates/renovation_report.md）。
"""

import datetime
import uuid
from pathlib import Path

try:
    from typing import Annotated
except ImportError:
    from typing_extensions import Annotated
from langchain_core.tools import tool

from app.api.context import get_session_context
from app.api.monitor import monitor
from app.utils.path_utils import resolve_path


@tool
def generate_markdown(
    content: Annotated[str, "要写入Markdown文档的文本内容"],
    filename: Annotated[str, "Markdown文档的文件名（不包含扩展名或包含.md）"],
    path: Annotated[str, "文件保存的绝对路径"] = "",
):
    """
    根据提供的文本内容生成 Markdown 文件

    :param content: 要写入 Markdown 文档的完整文本
    :param filename: 输出文件名，缺少 .md 后缀时会自动补全
    :param path: 可选保存路径；通常由运行时工作目录指令约束为相对路径
    :return: 文件生成结果说明
    """
    print(f"[MarkdownTool] 输入保存路径: {path or '当前会话目录'}")
    monitor.report_tool("Markdown文档生成工具", {"写入的文本内容": content})
    if not filename.endswith(".md"):
        filename += ".md"

    # session_dir 由 run_deep_agent 写入 ContextVar，保证文件写入当前会话工作目录
    session_dir = get_session_context()
    print(f"[MarkdownTool] 当前会话目录: {session_dir}")

    # 先把模型传入的 path/filename 合成一个逻辑路径，再交给 resolve_path 做统一清洗
    if path and path != ".":
        full_input_path = str(Path(path) / filename)
    else:
        full_input_path = filename
    full_path_str = resolve_path(full_input_path, session_dir)
    file_path = Path(full_path_str)

    parent_dir = file_path.parent

    print(
        f"[MarkdownTool] Debug: parent_dir={parent_dir}, filename={filename}, full_path={file_path}"
    )

    try:
        # 允许模型指定 session_dir 下的子目录；不存在时自动创建
        if not parent_dir.exists():
            parent_dir.mkdir(parents=True, exist_ok=True)
            print(f"[MarkdownTool] 已创建目录: {parent_dir}")

        file_path.write_text(content, encoding="utf-8")

        print(f"[MarkdownTool] 文件写入完成: {file_path}")
        return f"Markdown文件 '{file_path}' 已成功生成并保存。"
    except Exception as e:
        print(f"[MarkdownTool] 文件写入失败: {e}")
        return f"生成Markdown文件失败: {str(e)}"


@tool
def generate_renovation_report(
    one_line_conclusion: Annotated[str, "一句话结论：整体判断（预算是否合理/报价是否有明显风险）"],
    stage_assessment: Annotated[str, "当前装修阶段判断：用户处于装修流程哪个阶段、该阶段的核心任务"],
    budget_score: Annotated[int, "预算健康度评分 0-100：越接近 100 越健康"],
    budget_assessment: Annotated[str, "预算健康度解释：评分依据、预算与市场区间的对比"],
    risk_items: Annotated[str, "风险清单：Markdown 列表或表格，每条含风险等级【高/中/低】、问题、依据、建议动作；无风险时写'本次分析未发现明显风险'"],
    keep_items: Annotated[str, "必保留项：核心投入清单（如水电、防水），Markdown 列表"],
    cut_items: Annotated[str, "可删减项：预算紧张时优先调整的项目及影响，Markdown 列表；无则写'暂无'"],
    materials_advice: Annotated[str, "建议补充的材料与信息：下一步应收集的资料（如主材品牌型号、商家报价）"],
    action_list: Annotated[str, "下一步行动清单：按优先级排列的具体动作，Markdown 有序列表"],
    title: Annotated[str, "报告标题"] = "装修决策分析报告",
) -> str:
    """
    生成固定结构的装修决策分析报告（Markdown）

    报告包含固定章节：一句话结论、装修阶段判断、预算健康度评分、风险清单、
    必保留项、可删减项、建议补充材料、下一步行动清单，并自动附加免责声明。
    文件名自动使用会话编号 + 时间，保存在当前会话工作目录。
    :return: 报告生成结果说明
    """
    monitor.report_tool("装修诊断报告生成工具", {"title": title})

    session_dir = get_session_context()
    if not session_dir:
        return "错误：未找到当前会话工作目录，无法生成报告。"

    # 读取固定模板；模板缺失属于部署错误，直接报错提示而不是静默生成错误结构的报告
    template_path = Path(__file__).parents[1] / "templates" / "renovation_report.md"
    if not template_path.exists():
        return f"错误：报告模板缺失（{template_path}），请联系开发者检查部署。"
    template = template_path.read_text(encoding="utf-8")

    now = datetime.datetime.now()
    report_id = f"R{now.strftime('%Y%m%d')}{uuid.uuid4().hex[:6].upper()}"
    session_name = Path(session_dir).name.replace("session_", "")

    # 风险等级样式的固定要求放在工具层，避免模型输出风格漂移
    risk_section = risk_items.strip()
    if "本次分析未发现明显风险" not in risk_section and "|" not in risk_section:
        risk_section = risk_section.replace("【高】", "🔴【高】").replace("【中】", "🟡【中】").replace("【低】", "🟢【低】")

    content = template.format(
        report_id=report_id,
        generated_at=now.strftime("%Y-%m-%d %H:%M"),
        session_id=session_name,
        one_line_conclusion=one_line_conclusion.strip(),
        stage_assessment=stage_assessment.strip(),
        budget_score=max(0, min(100, int(budget_score))),
        budget_assessment=budget_assessment.strip(),
        risk_items=risk_section,
        keep_items=keep_items.strip(),
        cut_items=cut_items.strip(),
        materials_advice=materials_advice.strip(),
        action_list=action_list.strip(),
    )

    # 文件名使用会话编号 + 时间，避免同会话多次生成互相覆盖
    filename = f"装修诊断报告_{session_name}_{now.strftime('%H%M%S')}.md"
    file_path = Path(resolve_path(filename, session_dir))

    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
    except Exception as e:  # noqa: BLE001 - 工具层兜底，避免中断 Agent 链路
        return f"生成装修诊断报告失败: {str(e)}"

    monitor.report_file_generated(str(file_path), filename)
    return (
        f"装修诊断报告已成功生成：{filename}（报告编号 {report_id}）。"
        "如需 PDF，请调用 convert_md_to_pdf 转换该文件。"
    )


if __name__ == "__main__":
    # 本地调试入口：直接运行本文件可验证 Markdown 写入和路径解析效果
    def get_session_context():
        return "./examples/test_docs"

    test_content = "# 测试文档\n这是 Markdown 生成工具的本地测试内容"
    test_filename = "测试文件"
    test_path = "sub_dir"

    print("===== 开始测试：Markdown 文件生成 =====")
    result = generate_markdown.invoke(
        {"content": test_content, "filename": test_filename, "path": test_path}
    )

    print(f"\n调用结果：{result}")
    if "已成功生成" in result:
        file_path = Path(result.split("'")[1])
        print(f"验证结果：文件 {file_path} {'存在' if file_path.exists() else '不存在'}")
