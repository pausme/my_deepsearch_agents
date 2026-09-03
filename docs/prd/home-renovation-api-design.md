# 新房装修决策与预算管家接口清单

## 1. 接口设计原则

- 保留当前项目的对话式任务接口，优先扩展业务参数和任务类型。
- 长耗时分析仍采用异步任务 + WebSocket 推送。
- 上传文件、报告生成、文件下载继续按会话隔离。
- C 端用户所有接口必须支持登录态，MVP 可先预留 `user_id`，后续接入真实认证。

## 2. 核心接口清单

| 接口名称 | 请求方式 | 接口路径 | 功能说明 | 请求参数 | 返回结果 | 权限要求 | 业务规则 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 创建装修会话 | POST | `/api/renovation/sessions` | 创建一次装修分析会话 | 城市、面积、房型、预算、装修阶段、关注重点 | session_id、thread_id | 登录用户 | 同一用户可创建多个会话 |
| 获取会话详情 | GET | `/api/renovation/sessions/{session_id}` | 查看会话基础信息、状态和最近结果 | session_id | 会话详情 | 本人 | 只能访问自己的会话 |
| 提交装修分析任务 | POST | `/api/renovation/tasks` | 发起一次智能分析 | session_id、query、analysis_type | task_id、thread_id、status | 本人 | 同一会话同时只允许一个运行中任务 |
| 取消分析任务 | POST | `/api/renovation/tasks/{task_id}/cancel` | 取消运行中的智能分析 | task_id | status | 本人 | 已完成任务不可取消 |
| 上传装修资料 | POST | `/api/renovation/files/upload` | 上传报价单、合同、清单、户型说明等资料 | session_id、files、file_type | 文件列表 | 本人 | 限制文件格式和大小 |
| 获取资料列表 | GET | `/api/renovation/files` | 查询会话内上传资料和生成报告 | session_id、category | 文件列表 | 本人 | 只返回当前会话文件 |
| 下载文件 | GET | `/api/renovation/files/download` | 下载用户上传文件或生成报告 | file_id | 文件流 | 本人 | 校验文件归属和路径边界 |
| 删除文件 | DELETE | `/api/renovation/files/{file_id}` | 删除错误上传资料 | file_id | 删除结果 | 本人 | 运行中任务引用的文件不可删除 |
| 获取分析报告 | GET | `/api/renovation/reports/{report_id}` | 查看结构化报告内容 | report_id | 报告详情 | 本人 | 报告必须归属当前用户 |
| 生成 PDF 报告 | POST | `/api/renovation/reports/{report_id}/pdf` | 将分析报告转成 PDF | report_id | 文件信息 | 本人 | 报告状态为 completed 才可转换 |
| WebSocket 事件流 | WS | `/ws/renovation/{thread_id}` | 推送分析过程、工具调用、最终结果 | thread_id | 实时事件 | 本人 | 连接时校验 thread_id 归属 |

## 3. 分析任务类型

| 类型 | 英文值 | 说明 |
| --- | --- | --- |
| 首次诊断 | `INITIAL_DIAGNOSIS` | 根据用户基础信息生成装修建议 |
| 报价单分析 | `QUOTE_REVIEW` | 分析报价单漏项、重复项、虚高项 |
| 合同风险分析 | `CONTRACT_REVIEW` | 分析合同条款风险 |
| 材料选择建议 | `MATERIAL_ADVICE` | 根据预算和关注重点推荐材料选择策略 |
| 预算优化 | `BUDGET_OPTIMIZATION` | 给出删减项和保留项 |
| 完整报告 | `FULL_REPORT` | 聚合多来源信息生成完整报告 |

## 4. 关键请求对象

### 4.1 创建装修会话

```json
{
  "city": "杭州",
  "district": "滨江区",
  "house_area": 89.5,
  "room_type": "三室两厅一卫",
  "renovation_stage": "QUOTE_REVIEW",
  "budget_min": 120000,
  "budget_max": 180000,
  "priority_tags": ["省钱", "环保", "耐用"],
  "delivery_date": "2026-12-31"
}
```

### 4.2 提交装修分析任务

```json
{
  "session_id": "session_xxx",
  "analysis_type": "QUOTE_REVIEW",
  "query": "帮我分析这份报价单有没有漏项、重复收费和明显偏贵的地方"
}
```

## 5. WebSocket 事件

| 事件 | 说明 | data 示例 |
| --- | --- | --- |
| `session_created` | 会话工作目录创建完成 | `{"path": "/app/output/session_xxx"}` |
| `require_more_info` | 需要用户补充资料 | `{"fields": ["城市", "面积"]}` |
| `tool_start` | 开始调用工具 | `{"tool_name": "装修价格检索工具"}` |
| `assistant_call` | 调用子智能体 | `{"assistant_name": "报价单分析助手"}` |
| `risk_found` | 发现风险点 | `{"level": "high", "title": "水电项目漏项"}` |
| `report_generated` | 报告生成完成 | `{"report_id": "report_xxx"}` |
| `task_result` | 任务完成 | `{"result": "分析结论"}` |
| `task_cancelled` | 任务取消 | `{}` |
| `error` | 任务异常 | `{"message": "错误说明"}` |

## 6. MVP 接口优先级

P0：
- 创建装修会话
- 提交装修分析任务
- 上传装修资料
- 获取资料列表
- 下载文件
- WebSocket 事件流

P1：
- 获取会话详情
- 获取分析报告
- 生成 PDF 报告
- 取消分析任务

P2：
- 删除文件
- 历史会话列表
- 报告分享链接
- 家人协作查看
