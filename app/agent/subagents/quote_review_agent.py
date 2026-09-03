"""
报价单分析子智能体配置模块

将 app/prompt/prompts.yml 中的 quote 配置与报价单解析、参考价对比、风险检测工具
组装成 DeepAgents 可识别的字典式子智能体。主智能体在用户上传报价单并要求分析时，
会根据 description 把任务分派给它。
"""

from app.agent.prompts import sub_agents_content
from app.tools.quote_tools import (
    compare_quote_with_reference_price,
    detect_quote_risk_items,
    normalize_quote_items,
    parse_quote_file,
)

# 报价单助手的工作链路固定为：解析 -> 标准化 -> 参考价对比 -> 风险检测
# tools 列表顺序即模型被约束的工作顺序
quote_review_agent = {
    "name": sub_agents_content["quote"]["name"],
    "description": sub_agents_content["quote"]["description"],
    "system_prompt": sub_agents_content["quote"]["system_prompt"],
    "tools": [
        parse_quote_file,
        normalize_quote_items,
        compare_quote_with_reference_price,
        detect_quote_risk_items,
    ],
}
