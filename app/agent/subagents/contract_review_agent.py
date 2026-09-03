"""
合同风险子智能体配置模块

将 app/prompt/prompts.yml 中的 contract 配置与合同读取、条款提取、风险规则匹配工具
组装成 DeepAgents 可识别的字典式子智能体。主智能体在用户上传合同并要求分析时，
会根据 description 把任务分派给它。
"""

from app.agent.prompts import sub_agents_content
from app.tools.contract_tools import (
    extract_contract_clauses,
    match_contract_risk_rules,
    parse_contract_file,
)

# 合同助手的工作链路固定为：读取全文 -> 提取条款 -> 规则匹配
contract_review_agent = {
    "name": sub_agents_content["contract"]["name"],
    "description": sub_agents_content["contract"]["description"],
    "system_prompt": sub_agents_content["contract"]["system_prompt"],
    "tools": [parse_contract_file, extract_contract_clauses, match_contract_risk_rules],
}
