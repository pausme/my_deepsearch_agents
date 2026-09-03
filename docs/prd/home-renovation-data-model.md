# 新房装修决策与预算管家数据模型设计

## 1. 设计原则

- 业务数据与 Agent 运行数据分开存储。
- 用户上传资料和生成报告必须绑定用户与会话。
- 报价单、风险点、报告章节尽量结构化，方便后续做前端展示和搜索。
- MVP 阶段可先使用 MySQL，后续再引入对象存储和向量知识库。

## 2. 核心表清单

| 表名 | 说明 |
| --- | --- |
| `renovation_session` | 装修分析会话 |
| `renovation_file` | 上传资料和生成文件 |
| `renovation_task` | 智能分析任务 |
| `renovation_report` | 分析报告主表 |
| `renovation_report_section` | 报告章节 |
| `renovation_risk_item` | 风险项 |
| `renovation_price_reference` | 装修项目参考价 |
| `renovation_material_catalog` | 材料品类和品牌档位 |

## 3. renovation_session

| 字段中文名 | Java/Python 字段名 | 数据库字段名 | 类型 | 长度/精度 | 必填 | 默认值 | 索引 | 说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 主键 | id | id | bigint | - | 是 | 自增 | 主键 | 会话 ID |
| 用户 ID | userId | user_id | bigint | - | 是 | - | 普通索引 | 所属用户 |
| 会话编号 | sessionId | session_id | varchar | 64 | 是 | - | 唯一索引 | 对外会话 ID |
| 线程编号 | threadId | thread_id | varchar | 64 | 是 | - | 普通索引 | WebSocket 和 Agent thread_id |
| 城市 | city | city | varchar | 64 | 是 | - | 普通索引 | 装修所在城市 |
| 区县 | district | district | varchar | 64 | 否 | - | 普通索引 | 城市下属区域 |
| 房屋面积 | houseArea | house_area | decimal | 10,2 | 是 | - | 无 | 平方米 |
| 房型 | roomType | room_type | varchar | 64 | 是 | - | 无 | 例如三室两厅一卫 |
| 装修阶段 | renovationStage | renovation_stage | varchar | 32 | 是 | `INITIAL` | 普通索引 | 当前阶段 |
| 最低预算 | budgetMin | budget_min | decimal | 12,2 | 否 | - | 无 | 用户预算下限 |
| 最高预算 | budgetMax | budget_max | decimal | 12,2 | 否 | - | 无 | 用户预算上限 |
| 关注重点 | priorityTags | priority_tags | varchar | 255 | 否 | - | 无 | 逗号分隔或 JSON |
| 期望入住时间 | deliveryDate | delivery_date | date | - | 否 | - | 无 | 工期判断依据 |
| 会话状态 | status | status | varchar | 32 | 是 | `ACTIVE` | 普通索引 | ACTIVE/CLOSED |
| 创建时间 | createTime | create_time | datetime | - | 是 | 当前时间 | 普通索引 | 创建时间 |
| 更新时间 | updateTime | update_time | datetime | - | 是 | 当前时间 | 无 | 更新时间 |
| 逻辑删除 | deleted | deleted | tinyint | 1 | 是 | 0 | 普通索引 | 0 未删，1 已删 |

## 4. renovation_file

| 字段中文名 | Java/Python 字段名 | 数据库字段名 | 类型 | 长度/精度 | 必填 | 默认值 | 索引 | 说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 主键 | id | id | bigint | - | 是 | 自增 | 主键 | 文件 ID |
| 用户 ID | userId | user_id | bigint | - | 是 | - | 普通索引 | 所属用户 |
| 会话编号 | sessionId | session_id | varchar | 64 | 是 | - | 普通索引 | 所属会话 |
| 文件编号 | fileId | file_id | varchar | 64 | 是 | - | 唯一索引 | 对外文件 ID |
| 原始文件名 | originalName | original_name | varchar | 255 | 是 | - | 无 | 用户上传文件名 |
| 存储文件名 | storageName | storage_name | varchar | 255 | 是 | - | 无 | 清洗后的实际文件名 |
| 文件类型 | fileType | file_type | varchar | 32 | 是 | - | 普通索引 | QUOTE/CONTRACT/HOUSE_INFO/REPORT |
| 文件后缀 | extension | extension | varchar | 16 | 是 | - | 无 | pdf/xlsx/docx 等 |
| 文件大小 | fileSize | file_size | bigint | - | 是 | 0 | 无 | 字节数 |
| 存储路径 | storagePath | storage_path | varchar | 512 | 是 | - | 无 | 服务端路径或对象存储 key |
| 解析状态 | parseStatus | parse_status | varchar | 32 | 是 | `PENDING` | 普通索引 | PENDING/SUCCESS/FAILED |
| 解析文本 | extractedText | extracted_text | mediumtext | - | 否 | - | 无 | 文件解析文本 |
| 创建时间 | createTime | create_time | datetime | - | 是 | 当前时间 | 普通索引 | 创建时间 |
| 逻辑删除 | deleted | deleted | tinyint | 1 | 是 | 0 | 普通索引 | 逻辑删除 |

## 5. renovation_task

| 字段中文名 | Java/Python 字段名 | 数据库字段名 | 类型 | 长度/精度 | 必填 | 默认值 | 索引 | 说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 主键 | id | id | bigint | - | 是 | 自增 | 主键 | 任务 ID |
| 任务编号 | taskId | task_id | varchar | 64 | 是 | - | 唯一索引 | 对外任务 ID |
| 会话编号 | sessionId | session_id | varchar | 64 | 是 | - | 普通索引 | 所属会话 |
| 用户 ID | userId | user_id | bigint | - | 是 | - | 普通索引 | 所属用户 |
| 分析类型 | analysisType | analysis_type | varchar | 32 | 是 | - | 普通索引 | 任务类型 |
| 用户问题 | query | query | text | - | 是 | - | 无 | 原始输入 |
| 任务状态 | status | status | varchar | 32 | 是 | `PENDING` | 普通索引 | PENDING/RUNNING/SUCCESS/FAILED/CANCELLED |
| 错误信息 | errorMessage | error_message | text | - | 否 | - | 无 | 异常摘要 |
| 开始时间 | startTime | start_time | datetime | - | 否 | - | 无 | 开始执行时间 |
| 结束时间 | finishTime | finish_time | datetime | - | 否 | - | 无 | 结束时间 |
| 创建时间 | createTime | create_time | datetime | - | 是 | 当前时间 | 普通索引 | 创建时间 |

## 6. renovation_report

| 字段中文名 | Java/Python 字段名 | 数据库字段名 | 类型 | 长度/精度 | 必填 | 默认值 | 索引 | 说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 主键 | id | id | bigint | - | 是 | 自增 | 主键 | 报告 ID |
| 报告编号 | reportId | report_id | varchar | 64 | 是 | - | 唯一索引 | 对外报告 ID |
| 会话编号 | sessionId | session_id | varchar | 64 | 是 | - | 普通索引 | 所属会话 |
| 任务编号 | taskId | task_id | varchar | 64 | 是 | - | 普通索引 | 来源任务 |
| 报告标题 | title | title | varchar | 128 | 是 | - | 无 | 报告标题 |
| 总结结论 | summary | summary | text | 否 | - | 无 | 一句话结论和摘要 |
| 预算健康度 | budgetScore | budget_score | int | - | 否 | - | 无 | 0-100 |
| 风险等级 | riskLevel | risk_level | varchar | 16 | 否 | - | 普通索引 | LOW/MEDIUM/HIGH |
| Markdown 路径 | markdownPath | markdown_path | varchar | 512 | 否 | - | 无 | 生成的 Markdown 文件 |
| PDF 路径 | pdfPath | pdf_path | varchar | 512 | 否 | - | 无 | 生成的 PDF 文件 |
| 报告状态 | status | status | varchar | 32 | 是 | `DRAFT` | 普通索引 | DRAFT/COMPLETED/FAILED |
| 创建时间 | createTime | create_time | datetime | - | 是 | 当前时间 | 普通索引 | 创建时间 |

## 7. renovation_risk_item

| 字段中文名 | Java/Python 字段名 | 数据库字段名 | 类型 | 长度/精度 | 必填 | 默认值 | 索引 | 说明 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 主键 | id | id | bigint | - | 是 | 自增 | 主键 | 风险项 ID |
| 报告编号 | reportId | report_id | varchar | 64 | 是 | - | 普通索引 | 所属报告 |
| 风险标题 | title | title | varchar | 128 | 是 | - | 无 | 风险名称 |
| 风险类型 | riskType | risk_type | varchar | 32 | 是 | - | 普通索引 | PRICE/MISSING_ITEM/CONTRACT/MATERIAL/SCHEDULE |
| 风险等级 | riskLevel | risk_level | varchar | 16 | 是 | `MEDIUM` | 普通索引 | LOW/MEDIUM/HIGH |
| 原始依据 | evidence | evidence | text | 否 | - | 无 | 报价单或合同原文 |
| 风险说明 | description | description | text | 是 | - | 无 | 风险解释 |
| 建议动作 | suggestion | suggestion | text | 否 | - | 无 | 用户下一步动作 |
| 创建时间 | createTime | create_time | datetime | - | 是 | 当前时间 | 普通索引 | 创建时间 |

## 8. MVP 建表优先级

P0：
- `renovation_session`
- `renovation_file`
- `renovation_task`
- `renovation_report`

P1：
- `renovation_report_section`
- `renovation_risk_item`

P2：
- `renovation_price_reference`
- `renovation_material_catalog`
