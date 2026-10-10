# 任务模型、用量与耗时

聊天每条 Assistant 的「模型、用量与耗时」及 Evaluation 当前任务提供按需统计。展开后读取本机持久化 Run/Usage/Event，不调用模型，不刷新服务商账单；关面板或切换任务会取消读取。活动任务每5秒读取一次，最多60次；网络/格式错误后暂停，支持手动刷新。终态不持续轮询，取消后可手动查看迟到费用补记。历史消息不同时加载全部 Run。

`GET /api/runs/{UUID}/metrics` 需要既有本机授权，响应 no-store；仅投影 accounting 和 event timing，不加载、返回科学正文、原文引文、API endpoint、凭据或原始错误。Desktop 固定 GET 路径，不允许 query、重定向、远程 URL 或写方法，保留现有受限 bridge 与 CSP。

## 用量与费用含义

- 配置模型冻结在每次执行的适配器 Usage 中；返回模型来自实际 SDK 响应。未产生记录的历史任务显示 Unknown，不以当前 Settings 反推旧模型。展示 chat、embedding、reranker 和 evaluation judge；judge 单列，属于整个评测 Run 的统计。
- SDK 明确报告的非负整数 Token 累计到已知部分，报告调用次数用来判断完整性。明确报告0显示0，缺失/bool/负数/异常格式不计作已知0。失败和未完成调用会使总量不完整；旧记录正数仅作已知子总量，旧默认0仍为 Unknown。本地 embedding/reranker 没有 Token 测量，不能编造计数。
- LiteLLM `completion_cost` 是 **SDK 美元估算**，不是服务商精确账单。未知价格、失败和在途请求保留未知，部分金额不当完整总费用。旧金额没有 basis 时显示来源 Unknown。仅已确认的 SDK 估算参加顶部已知估算汇总；本地调用收费可为0，但不包含硬件、电力成本。
- **精确服务商账单始终 Unknown**：目前没有导入服务商账单的接口。本任务没有新增实际推理或付费验价调用。
- Usage 保留原数值接口，增量补入 configured_model/cost_basis/prompt_token_reports/completion_token_reports。Evaluation 的每次执行差值保留这些字段，产物增加 token_totals_complete/cost_basis/exact_provider_bill；既有 Token 总数字段是已知计数汇总，不保证完整。历史账单与重试不能混入当前尝试。
- 取消/失败后，只能补齐已经在 dispatch 前 checkpoint 的调用；不许增加调用数或恢复终态任务。用户重试可能额外计费。复用现有数据库所有权保护，不新增 billing 服务/队列。

## 时间与状态

总耗时使用 Run.created_at 至当前读取或终态 Event 的时间，含排队；执行耗时需实际 started 与结束事件。缺事件、不合理倒序显示 Unknown，历史任务不会推断不存在的阶段计时。

新 graph 完成更新后，用单调时钟记录 `execution_timing` 的节点区间：包含调度/状态处理，不声称纯模型推理时间。重试的同名阶段累加完成区间，缺少任一区间计时则该阶段总量 Unknown；当前未完成阶段尚未计入。计时放入 Event，不进入科学 State/Reviewer 模型 payload。队列时长和总耗时可能不同于完成节点区间之和。

统计显示对应 Run UUID、模式、持久化状态、安全失败原因和本轮重试提示。重试仍受现有会话/来源条件限制；统计刷新不改变 SSE 或重试状态。

## 验证边界

SDK/HTTP/IPC 浏览器夹具为 MOCK，DEMO ONLY / NOT A BENCHMARK / NOT MANUALLY ANNOTATED。真实 PostgreSQL 验证了状态、只读投影、取消后费用补记与新调用拒绝。构建与原生路径测试走现有 CI；Windows11人工安装/真实模型账单/科研效果不以这些测试替代。
