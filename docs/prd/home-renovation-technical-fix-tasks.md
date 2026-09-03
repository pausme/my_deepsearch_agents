# 新房装修决策与预算管家技术问题与整改任务清单

## 1. 文档目的

本文用于记录当前技术实现与 PRD/开发计划之间的差距，方便研发按任务项继续修改。

当前整体状态：
- 后端规则层测试通过，已有 79 条测试用例。
- Python 语法编译通过。
- 前端 TypeScript 与 Vite 直接构建通过。
- 装修场景 Prompt、报价单分析、合同风险分析、上传安全、SQL 只读守卫、报告模板均已有初版实现。

当前结论：
- 已具备装修场景 MVP 技术雏形。
- 还不能作为 C 端可试用版本直接交付。
- 下一阶段重点是修复真实工具链问题、补齐端到端链路、补业务接口与持久化。

## 2. 整改任务总览

| 任务编号 | 优先级 | 任务名称 | 状态 | 涉及模块 |
| --- | --- | --- | --- | --- |
| FIX-001 | P0 | 修复合同风险工具函数同名遮蔽问题 | 已完成 | 后端工具层 |
| FIX-002 | P0 | 补充合同工具封装层测试 | 已完成 | 后端测试 |
| FIX-003 | P0 | 补齐报价单端到端分析链路测试 | 已完成 | 后端 Agent/工具/API |
| FIX-004 | P0 | 处理 pnpm build 被 build-script 审批阻塞问题 | 已完成 | 前端工程 |
| FIX-005 | P1 | 拆分装修业务接口 `/api/renovation/*` | 已完成 | 后端 API |
| FIX-006 | P1 | 增加装修会话、任务、文件、报告持久化 | 已完成 | 后端数据层 |
| FIX-007 | P1 | 增加用户归属与文件访问校验 | 已完成 | 后端安全 |
| FIX-008 | P1 | 补充报告生成到 PDF 的端到端测试 | 已完成 | 后端文件工具 |
| FIX-009 | P2 | 增加历史报告列表与详情页 | 已完成 | 前端产品页 |
| FIX-010 | P2 | 增加生产级日志与错误码规范 | 已完成 | 后端工程化 |

> 2026-09-03 整改说明：
> - FIX-006 采用 SQLite（`app/db/database.py` + `app/repository/renovation_repository.py`），
>   表与字段对齐数据模型 PRD，后续迁 MySQL 只需替换连接实现。
> - FIX-007 MVP 用 `X-User-Id` 请求头预留用户身份（默认 1），接入登录态时只需替换
>   `get_user_id` 依赖；文件下载已改为按 `file_id` 查库校验归属，不再信任前端路径。
> - FIX-009 前端新增 `HistoryPanel`：新建装修会话（表单绑定 thread_id，后续任务走
>   `/api/renovation/tasks`）、历史会话列表、报告详情（风险分级 + Markdown 渲染 + PDF 下载）。
> - FIX-008 过程中发现并修复 `convert_md_to_pdf` 返回值泄露服务端绝对路径的问题。
> - 全量测试 108 条通过（`uv run pytest`），前端 `pnpm install && pnpm build` 非交互通过。

## 3. P0 必须优先处理

### FIX-001 修复合同风险工具函数同名遮蔽问题

问题描述：
- `app/tools/contract_tools.py` 从 `app.utils.contract_rules` 导入了 `extract_contract_clauses` 和 `match_contract_risk_rules`。
- 同一文件中又定义了同名 `@tool` 函数。
- Python 名称绑定会导致工具函数体内调用到被 `@tool` 包装后的同名对象，而不是规则层纯函数。
- 当前真实调用合同工具时会报错：`TypeError 'StructuredTool' object is not callable`。

涉及文件：
- `app/tools/contract_tools.py`
- `app/utils/contract_rules.py`

建议修改：
- 导入规则层函数时使用别名。
- 示例：

```python
from app.utils.contract_rules import (
    extract_contract_clauses as extract_contract_clauses_rule,
    match_contract_risk_rules as match_contract_risk_rules_rule,
)
```

- 工具函数内部改为调用别名函数：

```python
clauses = extract_contract_clauses_rule(contract_text)
report = match_contract_risk_rules_rule(clauses, full_text=contract_text or "")
```

验收标准：
- 直接调用 `extract_contract_clauses.invoke(...)` 不报错。
- 直接调用 `match_contract_risk_rules.invoke(...)` 不报错。
- 合同风险助手可以完整执行：读取合同 -> 提取条款 -> 匹配风险。

推荐测试命令：

```bash
.venv/bin/python -m pytest tests/test_contract_rules.py -q
```

### FIX-002 补充合同工具封装层测试

问题描述：
- 当前已有 `tests/test_contract_rules.py`，主要测试规则层纯函数。
- 缺少对 `app/tools/contract_tools.py` 中 LangChain Tool 封装后的 `.invoke()` 测试。
- 因此 FIX-001 这类封装层 bug 没有被自动化测试捕获。

涉及文件：
- `tests/test_contract_tools.py`
- `app/tools/contract_tools.py`

建议新增测试：
- `parse_contract_file.invoke` 能读取 txt/md/docx 基础文本。
- `extract_contract_clauses.invoke` 能返回 JSON，且包含 `clauses`。
- `match_contract_risk_rules.invoke` 能返回 JSON，且包含 `risks`、`summary`、`disclaimer`。
- 空文本、非法 JSON、缺失文件均返回明确错误，不直接抛异常。

验收标准：
- 新增合同工具封装层测试。
- 测试能稳定复现并防止同名遮蔽回归。

推荐测试命令：

```bash
.venv/bin/python -m pytest tests/test_contract_tools.py tests/test_contract_rules.py -q
```

### FIX-003 补齐报价单端到端分析链路测试

问题描述：
- 报价单规则层和解析辅助函数已有测试。
- 但还缺少完整工具链测试：`parse_quote_file -> normalize_quote_items -> compare_quote_with_reference_price -> detect_quote_risk_items`。
- 当前无法确认 Agent 真实调用工具时，上下游 JSON 参数是否稳定兼容。

涉及文件：
- `tests/test_quote_tools_flow.py`
- `app/tools/quote_tools.py`
- `app/utils/quote_rules.py`

建议新增测试：
- 构造一份临时 Markdown/CSV/Excel 报价单。
- 设置 session context。
- 调用 `parse_quote_file.invoke`。
- 将返回值传给 `normalize_quote_items.invoke`。
- 将返回值传给 `compare_quote_with_reference_price.invoke`。
- 将返回值传给 `detect_quote_risk_items.invoke`。
- 断言最终风险项至少包含重复计费、计价含混、缺规格、价格异常、计算错误中的若干类。

验收标准：
- 工具链完整跑通。
- 上下游 JSON 入参兼容。
- 高风险项能触发 `risk_found` 事件。

推荐测试命令：

```bash
.venv/bin/python -m pytest tests/test_quote_tools_flow.py tests/test_quote_rules.py -q
```

### FIX-004 处理 pnpm build 被 build-script 审批阻塞问题

问题描述：
- 直接执行 `./node_modules/.bin/tsc -b` 通过。
- 直接执行 `./node_modules/.bin/vite build` 通过。
- 但执行 `pnpm build` 时被 pnpm 的 build-script 审批策略阻塞，错误为 `ERR_PNPM_IGNORED_BUILDS`，涉及 `esbuild`。
- 这会影响新机器、CI 或交付验收时的一键构建体验。

涉及文件：
- `frontend/package.json`
- `frontend/pnpm-lock.yaml`
- 可新增或调整 pnpm 配置文件

建议修改：
- 明确项目 pnpm build-script 策略。
- 在团队确认安全后，为 `esbuild` 配置允许执行 build script。
- 或在 README/前端文档中补充本地首次构建处理方式。
- 不建议依赖手工交互式 `pnpm approve-builds` 作为长期方案。

验收标准：
- 新环境中执行 `pnpm install && pnpm build` 可以非交互完成。
- CI 环境中前端构建不需要人工确认。

推荐测试命令：

```bash
cd frontend
pnpm install
pnpm build
```

## 4. P1 核心能力补齐

### FIX-005 拆分装修业务接口 `/api/renovation/*`

问题描述：
- 当前仍主要复用原项目接口：`/api/task`、`/api/upload`、`/api/files`、`/api/download`、`/ws/{thread_id}`。
- PRD 中定义的装修业务接口尚未落地。
- 目前缺少装修会话、分析类型、业务字段等显式 API。

涉及文件：
- `app/api/server.py`
- 可新增 `app/api/renovation_schema.py`
- 可新增 `app/api/renovation_server.py`

建议新增接口：
- `POST /api/renovation/sessions`
- `GET /api/renovation/sessions/{session_id}`
- `POST /api/renovation/tasks`
- `POST /api/renovation/tasks/{task_id}/cancel`
- `POST /api/renovation/files/upload`
- `GET /api/renovation/files`
- `GET /api/renovation/files/download`

验收标准：
- 前端可以通过装修业务接口创建会话并提交分析任务。
- 会话字段包含城市、面积、房型、预算区间、装修阶段、关注重点。
- 原通用接口可保留兼容，但新页面优先使用装修业务接口。

### FIX-006 增加装修会话、任务、文件、报告持久化

问题描述：
- 当前 `active_tasks`、WebSocket 连接、Agent 记忆主要是内存态。
- 文件归属主要靠目录结构，没有数据库记录。
- 服务重启后无法恢复历史会话、任务状态和报告记录。

涉及模块：
- 可新增 `app/db/`
- 可新增 `app/repository/`
- 可新增 `app/service/`
- 数据表见 `docs/prd/home-renovation-data-model.md`

建议新增表：
- `renovation_session`
- `renovation_file`
- `renovation_task`
- `renovation_report`
- `renovation_risk_item`

验收标准：
- 服务重启后可以查询历史会话和报告。
- 每个文件有明确归属用户、会话和文件类型。
- 每次任务有状态：PENDING/RUNNING/SUCCESS/FAILED/CANCELLED。
- 报告可保存摘要、风险等级、Markdown 路径、PDF 路径。

### FIX-007 增加用户归属与文件访问校验

问题描述：
- 当前下载和文件列表主要校验路径在 `output` 目录下。
- 还没有用户登录、用户归属、会话归属校验。
- C 端场景下，报价单、合同、户型资料均属于敏感个人资料，必须做隔离。

涉及文件：
- `app/api/server.py`
- 后续业务接口模块
- 文件持久化表

建议修改：
- 所有文件记录绑定 `user_id` 和 `session_id`。
- 下载文件时不再直接信任前端传入 path，优先使用 `file_id` 查询服务端记录。
- 查询文件前校验当前用户是否拥有该会话。
- WebSocket 连接时校验 `thread_id` 归属。

验收标准：
- 用户 A 不能下载用户 B 的文件。
- 用户 A 不能查看用户 B 的报告列表。
- 伪造 path 无法绕过文件归属校验。

### FIX-008 补充报告生成到 PDF 的端到端测试

问题描述：
- 当前报告模板测试覆盖了 Markdown 生成。
- 还缺少 Markdown 报告生成后转 PDF 的端到端测试。
- C 端交付中 PDF 下载是核心闭环，必须纳入验收。

涉及文件：
- `tests/test_report_pdf_flow.py`
- `app/tools/markdown_tools.py`
- `app/tools/pdf_tools.py`
- `app/utils/word_converter.py`

建议新增测试：
- 设置临时 session context。
- 调用 `generate_renovation_report.invoke` 生成 Markdown。
- 调用 `convert_md_to_pdf.invoke` 转换 PDF。
- 断言 PDF 文件存在且大小大于 0。
- 失败时返回明确错误。

验收标准：
- Markdown -> PDF 链路稳定。
- 生成文件仍在当前 session 目录内。
- 工具返回给用户的信息不包含服务端绝对路径。

## 5. P2 产品化与工程化

### FIX-009 增加历史报告列表与详情页

问题描述：
- 当前前端已完成装修决策管家首屏、示例任务、事件流和文件展示。
- 但还没有历史报告列表和报告详情页。
- 用户无法回看过往分析，也无法按会话管理装修资料。

涉及文件：
- `frontend/src/App.tsx`
- `frontend/src/components/*.tsx`
- `frontend/src/lib/api.ts`
- `frontend/src/types.ts`

建议新增能力：
- 历史会话列表。
- 报告详情页。
- 风险项分级展示。
- 报告下载入口。
- 按会话切换分析记录。

验收标准：
- 用户可以看到自己的历史装修分析。
- 可以打开某份报告查看风险清单。
- 可以下载历史报告 PDF。

### FIX-010 增加生产级日志与错误码规范

问题描述：
- 当前多处仍使用 `print` 输出日志。
- API 错误返回结构不统一。
- Agent 工具失败时多为字符串错误，前端难以做结构化提示。

涉及文件：
- `app/api/server.py`
- `app/api/monitor.py`
- `app/tools/*.py`

建议修改：
- 引入统一 logger。
- 定义 API 错误码。
- 统一返回结构：`code`、`message`、`data`、`trace_id`。
- monitor 事件增加 `error_code` 和 `recoverable` 字段。
- 敏感字段不进日志。

验收标准：
- 后端无明显裸 `print` 调试日志。
- API 错误结构统一。
- 前端可以根据错误码展示明确提示。

## 6. 当前验证结果

已通过：

```bash
.venv/bin/python -m pytest -q
```

结果：

```text
79 passed
```

已通过：

```bash
.venv/bin/python -m compileall app
```

已通过：

```bash
cd frontend
./node_modules/.bin/tsc -b
./node_modules/.bin/vite build
```

未完全通过：

```bash
cd frontend
pnpm build
```

原因：
- pnpm build-script 审批策略阻塞 `esbuild`，不是 TypeScript 或 Vite 代码错误。

## 7. 建议研发处理顺序

1. FIX-001：修复合同工具同名遮蔽。
2. FIX-002：补合同工具封装层测试。
3. FIX-003：补报价单工具端到端测试。
4. FIX-004：处理前端 pnpm 一键构建问题。
5. FIX-005：拆装修业务接口。
6. FIX-006：补持久化。
7. FIX-007：补用户归属和文件权限。
8. FIX-008：补报告转 PDF 端到端测试。
9. FIX-009：做历史报告页。
10. FIX-010：补日志与错误码规范。

## 8. 最小交付验收标准

完成 FIX-001 到 FIX-004 后，可认为达到“技术 Demo 可演示”标准。

完成 FIX-001 到 FIX-008 后，可认为达到“内部试用 MVP”标准。

完成 FIX-001 到 FIX-010，并补充登录态与部署文档后，可进入“小范围 C 端试用”。
