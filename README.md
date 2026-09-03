<div align='center'>
  <h1 style="margin-top: 15px;">新房装修决策与预算管家</h1>
  <h4><b>renovation-decision-agent</b>（基于 deepsearch-agents 二次开发）</h4>
  <p><em>面向首次装修业主的对话式多智能体决策助手：上传报价单和合同，系统自动识别漏项、重复计费、付款前置等风险，并输出可下载的装修诊断报告（Markdown / PDF）</em></p>
</div>

<div align='center'>

![AI](https://img.shields.io/badge/AI-Multi--Agent-00c853?style=flat)
![DeepAgents](https://img.shields.io/badge/DeepAgents-0.5.7-1C3C3C.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-WebSocket-009688.svg?logo=fastapi&logoColor=white)
![Tests](https://img.shields.io/badge/tests-79%20passed-brightgreen.svg)

</div>

> **项目来源**：本项目基于 [didilili/deepsearch-agents](https://github.com/didilili/deepsearch-agents)（「深度研搜」对话式多智能体研究系统）二次开发而来，保留了其 DeepAgents 主从智能体架构、FastAPI + WebSocket 实时推送和 React 前端的完整工程骨架，将业务场景从"通用深度研搜"改造为"装修消费决策"。原项目配套系统教程 [ai-agents-from-zero](https://github.com/didilili/ai-agents-from-zero)，想系统学习 DeepAgents 强烈建议先看原项目。本项目的 PRD 与设计文档见 [docs/prd/](docs/prd/)。

## 📖 项目介绍

装修是典型的低频高消决策：信息分散在平台内容、商家报价、合同条款和邻居经验里，最容易踩坑的不是"选哪个品牌"，而是**预算失控、项目漏项、工期拖延、材料替代和增项争议**。

用户需要的不是一个搜索框，而是一份能直接拿去和家人、设计师、工长沟通的决策材料。本项目让用户：

1. 上传报价单、合同、清单等资料（Excel / PDF / Word / Markdown）；
2. 用自然语言发起分析（"帮我分析这份报价单有没有漏项、重复收费和明显偏贵的地方"）；
3. 实时观看多智能体的分析过程（哪个助手在跑、调了什么工具、发现了什么风险）；
4. 拿到结构化风险清单 + 一份固定结构的装修诊断报告，可下载 Markdown / PDF。

## ✨ 核心功能

- **一主五从的多智能体架构**（Orchestrator-Workers）
  - 主智能体：装修决策顾问，负责核对信息完整性、分派任务、汇总结论、生成报告
  - 网络资料助手（Tavily）：查材料价格行情、装修流程、城市政策、避坑经验
  - 报价单分析助手：解析报价单，识别 7 类风险——疑似漏项、重复计费、计价单位含混、主材缺品牌型号、单价偏离参考区间、数量×单价≠合价、分项合计≠总价
  - 合同风险助手：提取付款节点/工期/保修/增项/材料替换条款，规则匹配 10 类风险——首付过度前置、竣工前累计付款过高、尾款约束不足、增项无书面确认、保修低于国家标准等
  - RAGFlow 知识库助手：查施工规范、材料选购标准、合同模板
- **规则引擎 + 模型判断双层分析**：确定性风险（计算错误、重复项、单位含混）由纯函数规则引擎保证稳定可测；业务解释、追问清单、删减建议由模型补充
- **固定结构诊断报告**：一句话结论 / 阶段判断 / 预算健康度评分 / 风险清单 / 必保留项 / 可删减项 / 建议补充材料 / 行动清单，自动附加免责声明和报告编号
- **上传安全加固**：文件名清洗防路径穿越、后缀白名单、单文件 20MB 限制
- **SQL 只读守卫**：仅放行 SELECT/SHOW，表名白名单，自动 LIMIT，杜绝模型执行危险 SQL
- **执行过程实时可观察**：工具调用、助手调度、高危风险发现（`risk_found` 事件）、报告生成、取消和异常全部经 WebSocket 推送前端
- **会话级隔离**：`thread_id` 一钥三用（会话记忆 / 文件目录 / WebSocket 路由），ContextVar 让深层工具拿到会话上下文
- **79 个单元测试**：覆盖上传安全、SQL 守卫、报价规则、合同规则、报告模板

## 🏗️ 系统架构

```text
用户任务 / 上传资料
  -> FastAPI 接口接收（任务、取消、上传、文件、WebSocket）
  -> run_deep_agent 创建会话目录并写入上下文
  -> 装修决策主智能体（规划、核对信息、汇总、生成报告）
       ├─ 网络资料助手   ── internet_search
       ├─ 数据库查询助手 ── list_sql_tables / get_table_data / execute_sql_query（只读守卫）
       ├─ 报价单分析助手 ── parse_quote_file / normalize / compare_price / detect_risks
       ├─ 合同风险助手   ── parse_contract_file / extract_clauses / match_risk_rules
       └─ RAGFlow 助手   ── get_assistant_list / create_ask_delete
  -> generate_renovation_report 固定模板报告 + convert_md_to_pdf
  -> monitor 按 thread_id 定向推送 WebSocket 事件
  -> 前端展示事件流、风险、结论和文件下载
```

### 智能体与工具

| 归属 | 能力 | 工具 |
| --- | --- | --- |
| 主智能体 | 任务规划、助手调度、结果汇总、报告交付 | `generate_renovation_report`、`generate_markdown`、`convert_md_to_pdf`、`read_file_content` |
| 网络资料助手 | 查公开装修资料、价格行情、避坑经验 | `internet_search` |
| 数据库查询助手 | 查结构化业务数据（只读） | `list_sql_tables`、`get_table_data`、`execute_sql_query` |
| 报价单分析助手 | 报价单解析、参考价对比、7 类风险初筛 | `parse_quote_file`、`normalize_quote_items`、`compare_quote_with_reference_price`、`detect_quote_risk_items` |
| 合同风险助手 | 条款提取、10 类规则风险匹配 | `parse_contract_file`、`extract_contract_clauses`、`match_contract_risk_rules` |
| RAGFlow 助手 | 查内部施工规范、合同模板 | `get_assistant_list`、`create_ask_delete` |

## 🛠️ 技术栈

| 模块 | 技术 | 作用 |
| --- | --- | --- |
| 智能体框架 | DeepAgents | 主从智能体组装与调度 |
| 图与检查点 | LangGraph | 底层运行时和 `InMemorySaver` 会话检查点 |
| 模型接入 | OpenAI 兼容接口 | `.env` 中 `OPENAI_BASE_URL` / `OPENAI_API_KEY` / `LLM_QWEN_MAX` |
| 网络搜索 | Tavily | 公开资料检索 |
| 结构化数据 | MySQL / mysql-connector-python | 业务数据查询（只读守卫） |
| 私有知识库 | RAGFlow / ragflow-sdk | 内部文档问答 |
| 文件处理 | pypdf / python-docx / pandas / openpyxl / ReportLab | 报价单与合同解析、报告生成与 PDF 转换 |
| 后端接口 | FastAPI / Uvicorn / WebSocket | 任务、取消、上传、文件、实时推送 |
| 前端 | React / Vite / Ant Design | 对话式分析界面、事件流、附件上传、文件下载 |
| 依赖与测试 | uv / pytest | Python 依赖管理、79 个单元测试 |

## 📁 项目结构

```text
renovation-decision-agent/
├── app/
│   ├── agent/
│   │   ├── subagents/              # 五个子智能体（网络/数据库/报价单/合同/RAGFlow）
│   │   ├── llm.py                  # OpenAI 兼容模型初始化
│   │   ├── main_agent.py           # 主智能体组装与 run_deep_agent 执行入口
│   │   └── prompts.py              # 读取 app/prompt/prompts.yml
│   ├── api/
│   │   ├── context.py              # ContextVar 保存 thread_id 和 session_dir
│   │   ├── monitor.py              # 事件推送（tool_start/assistant_call/risk_found/...）
│   │   └── server.py               # FastAPI 任务、上传、文件、下载、WebSocket 接口
│   ├── data/
│   │   └── renovation_reference.py # 装修参考价区间、类目清单（MVP 内置，后续迁 MySQL）
│   ├── prompt/
│   │   └── prompts.yml             # 主智能体和五个子智能体提示词配置
│   ├── ragflow/                    # RAGFlow 配置和基础调用示例
│   ├── templates/
│   │   └── renovation_report.md    # 诊断报告固定模板（8 章节 + 免责声明）
│   ├── tools/                      # Tavily/MySQL/RAGFlow/报价单/合同/文件读取/报告工具
│   ├── utils/                      # 纯函数规则引擎：quote_rules / contract_rules / sql_guard / upload_security
│   ├── output/                     # 运行时生成：每个会话的报告产物
│   └── updated/                    # 运行时生成：用户上传文件的会话暂存目录
├── docs/
│   ├── prd/                        # 本项目 PRD：产品/数据模型/接口/Agent 工具/开发计划
│   └── knowledge_base/             # RAGFlow 知识库示例 PDF（待补充装修资料）
├── docker/                         # 本地 MySQL 教学环境
├── frontend/                       # React + Vite 前端（装修决策管家）
├── tests/                          # pytest 单元测试（上传安全/SQL/报价/合同/报告模板）
├── .env.example                    # 环境变量示例
└── pyproject.toml                  # Python 依赖与 pytest 配置
```

## 🚀 快速开始

### 1. 准备环境

- Python `3.12`、`uv`、Node.js + `pnpm`、Docker
- 可用的大模型 API Key（OpenAI 兼容接口）
- Tavily API Key
- RAGFlow 服务与 API Key（可选，不接入时报价/合同/搜索/数据库链路均可独立运行）

### 2. 克隆与安装

```bash
git clone git@github.com:pausme/my_deepsearch_agents.git
cd my_deepsearch_agents
uv sync
```

### 3. 配置环境变量

```bash
cp .env.example .env
```

```bash
# LLM 配置
OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
OPENAI_API_KEY=你的大模型_API_KEY
LLM_QWEN_MAX=qwen-max

# Tavily 配置
TAVILY_API_KEY=你的_TAVILY_API_KEY

# RAGFlow 配置（可选）
RAGFLOW_API_URL=http://your-ragflow-host
RAGFLOW_API_KEY=ragflow-your-api-key

# MySQL 配置
MYSQL_USER=root
MYSQL_PASSWORD=root
MYSQL_DATABASE=deepsearch_db
MYSQL_HOST=localhost
MYSQL_PORT=3307
MYSQL_CHARSET=utf8mb4
MYSQL_COLLATION=utf8mb4_unicode_ci
MYSQL_SQL_MODE=TRADITIONAL
```

### 4. 启动 MySQL（数据库链路需要）

```bash
docker compose -f docker/docker-compose.yaml up -d
```

### 5. 启动后端

```bash
uv run uvicorn app.api.server:app --host 0.0.0.0 --port 8000 --reload
```

| 接口 | 说明 |
| --- | --- |
| `POST /api/task` | 启动一次后台分析任务 |
| `POST /api/task/{thread_id}/cancel` | 取消指定会话任务 |
| `POST /api/upload` | 上传装修资料（报价单/合同/清单，白名单格式，单文件 ≤20MB） |
| `GET /api/files` | 列出当前会话输出目录中的生成文件 |
| `GET /api/download` | 下载输出目录中的文件（含路径穿越防护） |
| `WebSocket /ws/{thread_id}` | 推送工具调用、助手调度、风险发现、结果和异常事件 |

### 6. 启动前端

```bash
cd frontend
pnpm install
pnpm dev
```

默认连接 `http://localhost:8000`（API）和 `ws://localhost:8000`（WebSocket），可在 `frontend/.env.local` 中用 `VITE_API_BASE_URL` / `VITE_WS_BASE_URL` 修改。

### 7. 跑几个示例任务

```text
（先上传报价单）帮我分析这份报价单有没有漏项、重复收费和明显偏贵的地方。
```

```text
（先上传合同）检查这份装修合同的付款节点、工期、增项和保修条款有没有风险。
```

```text
我家在杭州，89 平三室两厅，预算 15-18 万全包，请给我一份首次诊断，并生成 PDF 报告。
```

## 🧪 运行测试

```bash
uv run pytest
```

覆盖上传文件安全（路径穿越/白名单/大小限制）、SQL 只读守卫（危险语句/白名单/LIMIT）、报价单规则引擎（7 类风险）、合同规则引擎（10 类风险）、报告模板（固定章节/免责声明/文件命名）。

## 📚 开发路线

基于 [docs/prd/home-renovation-development-plan.md](docs/prd/home-renovation-development-plan.md) 的版本规划：

| 版本 | 目标 | 状态 |
| --- | --- | --- |
| V0.1 场景化 MVP | Prompt 改造、上传安全、报告模板、前端文案 | ✅ 已完成 |
| 报价单/合同分析助手 | 规则引擎 + 子智能体 + 结构化风险输出 | ✅ 已完成 |
| V0.3 数据持久化 | 会话、文件、任务、报告、风险项（SQLite，字段对齐 PRD，可迁 MySQL） | ✅ 已完成 |
| V0.4 前端产品化 | 装修会话表单、历史报告页、风险分级展示 | ✅ 已完成（报告分享/家人协作待做） |
| V1.0 可试用版本 | 权限（已预留 X-User-Id）、部署文档、错误码全量覆盖 | 🚧 进行中 |

整改任务明细见 [docs/prd/home-renovation-technical-fix-tasks.md](docs/prd/home-renovation-technical-fix-tasks.md)。

其他待办：参考价数据迁入 MySQL（`renovation_price_reference`）、装修知识库接入 RAGFlow、参考价城市系数、登录态接入。

## ⚠️ 能力边界与免责声明

- 本项目提供装修决策辅助，**不构成法律、财务或工程验收意见**；合同风险分析不能替代律师或专业监理审查。
- 所有价格为参考区间（内置参考价按二线城市综合口径），实际价格受城市、材料档次、工艺和施工难度影响。
- 报价单与合同分析为"规则初筛 + 模型解释"的辅助结论，关键决策请以专业人士复核为准。
- 工程层面仍为学习型项目边界：无用户体系、无任务队列、会话记忆为进程内存（`InMemorySaver`），生产化能力见开发路线。

## 🙏 致谢

- [didilili/deepsearch-agents](https://github.com/didilili/deepsearch-agents)：本项目的上游基座，提供了多智能体架构、工具分层和前后端闭环的完整教学实现
- [ai-agents-from-zero](https://github.com/didilili/ai-agents-from-zero)：上游配套的系统教程，DeepAgents 从入门到项目闭环
