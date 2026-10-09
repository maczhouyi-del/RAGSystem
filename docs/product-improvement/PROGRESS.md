# 科研产品改造进度

用户于 2026-10-09 授权从 TASK-01 开始，完成每项后自动串行推进，无需等待回复。
后续运行必须先读取本文件、AGENTS.md 和基线报告，再确认 Git/CI 状态。
只允许一个 TASK 修改中；任何必需测试/适用 CI 未通过都不能进入下一项。
任务状态仅使用 `NOT_STARTED / IN_PROGRESS / PASSED / BLOCKED / FAILED`。
`NOT MEASURED` / `NOT EXECUTED` 仅用于真实效果或平台测量字段，不替代任务状态。

## 当前断点

- TASK-00：**PASSED**；日志已恢复，引用 UUID 误判已修复；固定 ID 回归、负向控制、604 项完整测试及修复提交 push/PR CI、Windows/Linux Desktop 均通过。
- 起点：`a8d5c1f0ace08573c5e5787bf5eef39570405191`（fetch 后 origin/main）。
- 分支：`codex/research-product-improvement`；不直接提交 main，不 force push，不自动合并。
- TASK-01：PASSED；实现 `238403a` / 验证提交 `9e650ae` 的本地验证与最新 push/PR CI、Windows/Linux Desktop 四个 workflow 已通过；TASK-02：PASSED；本地 39 项浏览器/10 项 transport 验证及实现提交 `088e8be` 的 push/PR CI、Windows/Linux Desktop 四个 workflow 全部 SUCCESS；自动开始 TASK-03。
- [基线报告](BASELINE.md)；[实际验证记录](task-00-evidence.json)。

## 串行计划与依赖

下表列出全部任务，编号前后依赖表示用户要求的执行门禁，不表示必须把无关功能耦合进代码。
依赖若需调整，先记录原因；本轮未调整原顺序。

| TASK | 修改目标 | 前置门禁/关键依赖 | 范围与风险边界 | 计划验证 | 状态 |
| --- | --- | --- | --- | --- | --- |
| TASK-00 | 现有代码与测试基线检查 | 无 | 审查/文档及基线测试误判修复；保护业务代码与锁文件 | 完整回归、迁移、真实 CI、Windows artifact 边界 | PASSED |
| TASK-01 | 环境检查与启动诊断 | 00 | 复用 Diagnostics；不改 .env/数据库 | Windows/Linux 脚本正常与 Docker/端口/worker/auth/model 异常场景 | PASSED |
| TASK-02 | 首次使用引导界面 | 01 | 复用 AuthPanel/Settings/Diagnostics | Playwright 新用户/已有用户/断线/退出恢复 | PASSED |
| TASK-03 | 可复现科研验收框架 | 02 | 复用 Evaluation；区分 synthetic 与人工金标 | 指标/来源身份/逐例回放；无金标真实质量 NOT MEASURED | NOT_STARTED |
| TASK-04 | 文献搜索、排序和分页 | 03 | 保留旧 /api/papers；已有分页需扩展 | 至少 200 篇 fixture，搜索/筛选/稳定排序/总数/兼容 | NOT_STARTED |
| TASK-05 | 文献元数据修改 | 04 | 复用 PATCH；保护原始来源并检测陈旧编辑 | UI 保存/刷新/冲突/原 PDF 与 chunk 不变 | NOT_STARTED |
| TASK-06 | 安全删除文献后端 | 05 | 先定义 PDF/派生数据/历史证据/缓存/备份生命周期 | PG 事务、文件补偿、迟到 worker、检索排除与历史引用失效 | NOT_STARTED |
| TASK-07 | 文献删除 UI | 06 | 仅消费已验收删除协议 | Playwright 确认/取消/失败/列表与其他数据隔离 | NOT_STARTED |
| TASK-08 | 批量 PDF 导入 | 07 | 复用单篇 API/ingestion/outbox，限制并发 | 重复/失败/断网/重试/刷新/并发；上传与索引状态分离 | NOT_STARTED |
| TASK-09 | 论文分组与标签 | 08 | 后端检索范围；不复制 PDF/Embedding | 关系迁移/CRUD/删除分组不删论文/RAG 与 Research 过滤 | NOT_STARTED |
| TASK-10 | 实体标注状态可视化 | 09 | 区分未标注与不存在；严格过滤不等于全文搜索 | 部分标注语料、来源片段、状态/警示与过滤语义 | NOT_STARTED |
| TASK-11 | 实体提取与人工校正 | 10 | 保守带来源提取；费用显式、重试幂等、同名消歧 | 证据关联/校正持久化/严格过滤/重复导入；实际质量独立测量 | NOT_STARTED |
| TASK-12 | 更精确 PDF 来源定位 | 11 | 保留 stable Evidence ID；旧索引兼容；不可伪造 bbox | 文本/表格/公式 PDF、无坐标降级、迁移兼容 | NOT_STARTED |
| TASK-13 | 引用与 PDF 阅读 | 12 | 复用 source metadata/受限 bridge；新增依赖先许可证审查 | 正确论文/页/多引用/表格/缺坐标降级，Web/Desktop | NOT_STARTED |
| TASK-14 | 结构化研究报告生成 | 13；03 提供评测基础 | 扩展确定性 synthesis；保留 Reviewer、单位/实验条件边界 | 多论文/矛盾/不充分证据/重试；人工案例与 mock 分开 | NOT_STARTED |
| TASK-15 | 报告与比较结果导出 | 14；05 元数据；13 来源 | Markdown/CSV/BibTeX/引用清单，安全文件名与下载 | 旧会话/数字/条件/Evidence ID/缺字段/中文/特殊字符 | NOT_STARTED |
| TASK-16 | 模型费用、延迟与任务状态 | 15 | 复用 Run/Event/Usage；未知不为零；不主动付费刷新 | 成功/失败/取消/缺 usage/持久化/SSE/重试 | NOT_STARTED |
| TASK-17 | RAG 与 Research 对照评测 | 16；03 框架及人工金标/模型条件 | 同语料/问题/范围/配置，不预设 Research 更优 | 真实失败逐例记录；无真实资源 BLOCKED / NOT MEASURED | NOT_STARTED |
| TASK-18 | 最终安装方案与完整部署 | 17；01/02 诊断引导 | 先 ADR 比较 Docker 自动部署和完整打包；复用 MSI/NSIS CI | 实际 Windows artifact/哈希、版本/auth/升级备份卸载；人工平台单列 | NOT_STARTED |
| TASK-19 | 科研用户端到端验收 | 18；03/17 真实评测资源 | 停止新功能；A–L 全场景，工程与人工证据分开 | 全新 Win11、20 PDF、数值/比较/记忆/删除/报告/恢复/升级/跨语言 | NOT_STARTED |

## TASK-00 初次执行记录（历史，后续恢复见下节）

- 修改目标：冻结当前实现/真实 CI/测试/产品缺口与依赖，供后续任务逐项验收。
- 开始 commit：`a8d5c1f0ace08573c5e5787bf5eef39570405191`。
- 涉及文件：新增 `docs/product-improvement/BASELINE.md`、`PROGRESS.md`、`task-00-evidence.json`；追加 `docs/stage-log.md`。
- 修改说明：文档与验证证据；没有业务、数据库、接口、锁文件或工作流变更。
- 新增测试：无。TASK-00 不实现功能，不为文档制造无意义测试；重跑现有回归验证无新增失败。
- 验证命令：`uv sync --locked`、`uv run ruff format --check .`、`uv run ruff check .`、`uv run mypy src`、隔离库 Alembic upgrade/downgrade/upgrade、`uv run pytest -q --junitxml=/workspace/.rag-task00/pytest.xml`；`npm --prefix frontend ci` 及 `run lint/check/build/test:e2e/test:transport`。
- 实际结果：Python 604 passed（463 unit / 141 integration，0 skipped/failures/errors）；浏览器 32 passed；transport 10 passed；静态检查/构建/迁移 PASS；详见 evidence 和 BASELINE。
- 基准 CI：[CI 37771426122](https://github.com/maczhouyi-del/RAGSystem/actions/runs/37771426122) 与 [Desktop 37771426070](https://github.com/maczhouyi-del/RAGSystem/actions/runs/37771426070) 均 SUCCESS；已核对基准 SHA，不能代替本任务提交的 CI。
- 本任务 push [CI 37782711529](https://github.com/maczhouyi-del/RAGSystem/actions/runs/37782711529)：SUCCESS；PR [CI 37782769354](https://github.com/maczhouyi-del/RAGSystem/actions/runs/37782769354)：FAILURE（backend pytest；frontend/compose SUCCESS）。PR [Desktop 37782769337](https://github.com/maczhouyi-del/RAGSystem/actions/runs/37782769337)：SUCCESS（Windows/Linux）。push Desktop 的最终状态见 evidence；不得用其他运行的绿色覆盖失败。
- 独立基线实现 commit SHA：`d238275e3e49c392c5907bf218ffda57161b3a13`。其后仅补充本任务 CI/阻塞证据；证据提交自身 SHA 由 Git 历史及交付报告定位。
- Pull Request：[draft #1](https://github.com/maczhouyi-del/RAGSystem/pull/1)，base=main；未合并。
- 风险/限制：REST/GraphQL 后续已成功，PR 已创建。失败日志经 results-receiver.actions.githubusercontent.com 或 productionresultssa17.blob.core.windows.net 下载被代理拒绝；artifact 经 productionresultssa19.blob.core.windows.net 也被拒绝。已将这些确切域名及 api.github.com 保存到网络草稿，不能视为运行实例已应用。缺具体失败日志，不能断言 flaky、业务缺陷或文档回归。真实 provider 科研问答、人工金标质量、Windows 11 人工安装和 macOS 本机验收未执行。
- 工程状态：BLOCKED。科研质量：NOT MEASURED；Windows 11 人工操作：NOT EXECUTED。
- 恢复步骤：在环境设置应用已保存网络变更（按界面要求保存/发布），重新下载 run 37782769354 的 backend job 113329775925 日志，定位具体用例；先区分环境/原有问题再决定修复或重跑，不能盲目 rerun 洗绿。保留失败证据，核查最新证据提交及 PR 的适用 CI 后才可 PASSED。TASK-01 不得开始。

## TASK-00 阻塞恢复（2026-10-09 Asia/Shanghai）

- 本次开始 commit：`3e6259b8510a1b3d6abea26d6766779c10c2fd14`。
- 原失败日志已通过标准 REST job logs 下载；具体用例为 `test_false_local_history_and_memory_cannot_supply_scientific_answer[research]`，原运行 603 passed / 1 failed。答案正确为 120 participants，断言把引用 UUID 中的 `5009` 误判为错误人数；不是本轮文档引入的科研错误。
- 仅修复 `tests/integration/test_conversation_worker.py`，并更新本任务的三份报告/证据与 stage log；不改业务、API、数据库、锁文件或后续 TASK。
- 最小实现：fixture 使用固定 chunk UUID（包含 500），其真实 UUID5 Evidence ID 同样包含 500；核对引用 ID，然后检查剔除合法引用后的全文；分析/审查请求仅排除完整 UUID 字符串值，继续检查其余问题、事实、原文等文本；要求 payload 实际存在并携带来源 chunk。
- 新增测试覆盖：保留原 RAG/Research 参数化用例，以固定 ID 确定性覆盖误判；没有删测试或降低科学文本断言。
- 验证：固定 ID + 原断言 2 项 EXPECTED FAILURE；修复后的 worker 文件 6 passed；外部负向控制注入错误 500 人文本后两种模式均 EXPECTED FAILURE；完整 `uv sync --locked`、Ruff format/check、mypy、`uv run pytest -q --junitxml=...` PASS，604 passed（463 unit / 141 integration、0 skipped/failures，30.70s，1 upstream warning）。
- 最终实现/修复 commit：`09c29113bad0df7225e7d0f7e88b21bcd89a7de0`；其后的提交仅保存验收证据，自身 SHA 由 Git 历史定位。
- 实际 CI：push [CI 37882246737](https://github.com/maczhouyi-del/RAGSystem/actions/runs/37882246737)、[Desktop 37882246783](https://github.com/maczhouyi-del/RAGSystem/actions/runs/37882246783)；PR [CI 37882251101](https://github.com/maczhouyi-del/RAGSystem/actions/runs/37882251101)、[Desktop 37882251036](https://github.com/maczhouyi-del/RAGSystem/actions/runs/37882251036)，完整 head SHA 均与修复提交匹配，全部 SUCCESS。
- 验收状态：PASSED。历史失败保留在上节和 evidence 的 task_ci/blocker；不是靠盲目重跑解除。
- 真实科研效果仍 NOT MEASURED，Win11 人工安装仍 NOT EXECUTED；下一 TASK-01 保持 NOT_STARTED。

## 任务执行记录与后续任务计划

以下 NOT_STARTED 项均无开始 commit、无实际涉及文件、无修改、无新增测试、无已执行验证命令、
无测试结果、无 CI 链接、无最终 commit。表中的验证为计划，不能填作 PASS。
开始任一任务时，必须把这些字段替换为实际记录并列出具体文件；风险与依赖沿用上表并细化。

### TASK-01：环境检查与启动诊断

- 状态：PASSED；开始 commit：`38fec46fab33b6dd4395d93cd64fd0c4e0c099e9`；最终实现 commit：`238403a6438c1d838e7e4f99afb35c440fe1d3d2`。
- 最小实现：PowerShell/Bash 入口共用标准库 Python 只读诊断；Docker/Compose、端口、磁盘、授权、DB/Redis/三个 worker、模型配置、可选 supervisor 真实调用、可用知识库和运行时依赖分开显示，均附修复建议。
- 涉及文件：`scripts/diagnose.py/.ps1/.sh`、`scripts/test_diagnostic_launchers.py`、`src/ragagent/api/diagnostics.py`、`tests/unit/test_environment_diagnostics.py`、`tests/integration/test_api.py`、两个 CI 工作流、`README.md`、`docs/environment-diagnostics.md`、本进度/evidence/stage log。
- 新增验证：10 个离线决策场景；PG/Redis 集成验证 corpus 对 indexed/chunk/withdrawn/retracted/queued 的判定；真实 Linux API/PG/Redis/RQ smoke；Linux 合成 API 启动入口；Windows CI 执行 PowerShell 7 与 Windows PowerShell 入口。
- 实际本地结果：Ruff format/check PASS（186 文件）；mypy PASS（72 文件）；pytest 614 passed、0 skipped、1 上游 warning，30.21s；Linux launcher PASS；真实基础服务 smoke PASS，配置字节未变，模型调用 0。
- 实际 CI：实现提交 push [CI 37884515678](https://github.com/maczhouyi-del/RAGSystem/actions/runs/37884515678)、[Desktop 37884515709](https://github.com/maczhouyi-del/RAGSystem/actions/runs/37884515709) 及 PR [Desktop 37884520899](https://github.com/maczhouyi-del/RAGSystem/actions/runs/37884520899) 全部 SUCCESS；PR [CI 37884520894](https://github.com/maczhouyi-del/RAGSystem/actions/runs/37884520894) 的三个 job 和完整 SHA 上十个 check run 都 SUCCESS，但 workflow/check suite 汇总仍 in_progress/conclusion=null。保留原始差异，不猜测完成，不盲目 rerun。Windows 实际执行两种 PowerShell 和 10 个离线场景；MSI/NSIS 与 Linux 原生 smoke 成功，Win11 人工安装 NOT EXECUTED。
- 限制：诊断需要 Python 3.11+；缺少时明确提示，退出 2；授权不足显示 unknown，不能据此判定正常；worker 注册不代表工作执行成功；依赖安装不等于模型加载；未调用付费 API；真实科研质量 NOT MEASURED。
- `uv sync --locked` PASS（109 包）；[实际证据](task-01-evidence.json)。
- 验证提交：`9e650ae837011ce0298546a6409a0cfa2e4c452b`，只记录实际 CI 证据，未改业务；其 push [CI 37885297371](https://github.com/maczhouyi-del/RAGSystem/actions/runs/37885297371)、[Desktop 37885297374](https://github.com/maczhouyi-del/RAGSystem/actions/runs/37885297374)；PR [CI 37885301335](https://github.com/maczhouyi-del/RAGSystem/actions/runs/37885301335)、[Desktop 37885301369](https://github.com/maczhouyi-del/RAGSystem/actions/runs/37885301369)，全部 completed/SUCCESS、完整 SHA 与全部 job 已核对；原实现 PR 汇总差异作为历史状态保留，没有失败检查被盲目重跑。
- 工程验收 PASSED。前置门禁 00 与本任务门禁通过，按用户授权自动开始 02。

### TASK-02：首次使用引导界面

- 状态：PASSED；开始 commit：`c331848034b135181ad5fc319ddd3ddfe0bbaa0c`；最终实现 commit：`088e8be7a12b6d1f0fbbb9c33fdabe448e39ac0b`；其后的验收提交只记录证据，自身 SHA 见 Git 历史。
- 范围：只读引导复用 AuthPanel、Settings、Diagnostics、Knowledge、Tasks；不改授权系统、后端数据、记忆/会话语义；关闭偏好仅保存在浏览器本地，不包含凭据/数据 ID。
- 涉及文件：`frontend/src/FirstUseGuide.tsx`、`Diagnostics.tsx`、`main.tsx`、`style.css`、`frontend/tests/first-use.spec.ts`、`chat-fixtures.ts`，及文档/进度/证据/stage log。
- 新增测试：7 项 Playwright：空白授权→配置检查→上传→等待索引→问答；已有用户；关闭/重启保留原数据；空库关闭后重启；离线恢复；数据库/worker 故障禁止首次问答；挂起请求超时后可恢复；默认无连接测试、凭据不入 storage。
- 当前实际结果：tsc/build PASS；7 项新增 Playwright PASS（MOCK HTTP/SSE，非真实解析/模型/质量/Windows 凭据库）；完整前端结果：npm ci/lint/check/build PASS；39 项 Playwright PASS（41.5s，0 skipped）；transport 10 PASS（0 skipped）；截图已检查。CI 与完整 SHA 已核对，全部通过。
- 历史失败与修复：初次完整浏览器运行 12 failed/2 interrupted/23 not run/1 passed，原聊天夹具缺新受保护诊断路由，触发实际本机 API 的 401；补齐路由与授权模拟，保留原断言。新增超时用例初次 1 failed/38 passed，离线自动重试使刷新按钮持续 busy；取消/超时释放 busy，离线停止自动轮询并支持手动恢复，完整 39 项重跑通过。未删测试或降低断言。
- 限制：引导不安装或配置环境/密钥；远程模型/Embedding 可能收费，连接测试可选且手动；真实科研效果 NOT MEASURED、Windows 11 人工 GUI NOT EXECUTED。
- 实际 CI：push [CI 37886916945](https://github.com/maczhouyi-del/RAGSystem/actions/runs/37886916945)、[Desktop 37886916939](https://github.com/maczhouyi-del/RAGSystem/actions/runs/37886916939)；PR [CI 37886921280](https://github.com/maczhouyi-del/RAGSystem/actions/runs/37886921280)、[Desktop 37886921287](https://github.com/maczhouyi-del/RAGSystem/actions/runs/37886921287)，全部 completed/SUCCESS，完整 SHA 和所有 job 已核对；Linux 实际原生 GUI smoke 与 Windows MSI/NSIS 构建通过。
- 前置 TASK-01 和本任务门禁已通过，TASK-02 工程 PASSED；按用户授权自动开始 TASK-03。

### TASK-03：可复现科研验收框架

- 状态：NOT_STARTED；开始 commit / 最终 commit：未产生。
- 涉及文件 / 修改说明 / 新增测试：无，未执行。
- 验证命令 / 实际结果 / CI 运行链接与结论：未执行 / NOT EXECUTED / UNKNOWN。
- 修改目标、依赖、验收计划：见上表 TASK-03；前置门禁 02。
- 风险与已知限制：复用 Evaluation；区分 synthetic 与人工金标。

### TASK-04：文献搜索、排序和分页

- 状态：NOT_STARTED；开始 commit / 最终 commit：未产生。
- 涉及文件 / 修改说明 / 新增测试：无，未执行。
- 验证命令 / 实际结果 / CI 运行链接与结论：未执行 / NOT EXECUTED / UNKNOWN。
- 修改目标、依赖、验收计划：见上表 TASK-04；前置门禁 03。
- 风险与已知限制：保留旧 /api/papers；已有分页需扩展。

### TASK-05：文献元数据修改

- 状态：NOT_STARTED；开始 commit / 最终 commit：未产生。
- 涉及文件 / 修改说明 / 新增测试：无，未执行。
- 验证命令 / 实际结果 / CI 运行链接与结论：未执行 / NOT EXECUTED / UNKNOWN。
- 修改目标、依赖、验收计划：见上表 TASK-05；前置门禁 04。
- 风险与已知限制：复用 PATCH；保护原始来源并检测陈旧编辑。

### TASK-06：安全删除文献后端

- 状态：NOT_STARTED；开始 commit / 最终 commit：未产生。
- 涉及文件 / 修改说明 / 新增测试：无，未执行。
- 验证命令 / 实际结果 / CI 运行链接与结论：未执行 / NOT EXECUTED / UNKNOWN。
- 修改目标、依赖、验收计划：见上表 TASK-06；前置门禁 05。
- 风险与已知限制：先定义 PDF/派生数据/历史证据/缓存/备份生命周期。

### TASK-07：文献删除 UI

- 状态：NOT_STARTED；开始 commit / 最终 commit：未产生。
- 涉及文件 / 修改说明 / 新增测试：无，未执行。
- 验证命令 / 实际结果 / CI 运行链接与结论：未执行 / NOT EXECUTED / UNKNOWN。
- 修改目标、依赖、验收计划：见上表 TASK-07；前置门禁 06。
- 风险与已知限制：仅消费已验收删除协议。

### TASK-08：批量 PDF 导入

- 状态：NOT_STARTED；开始 commit / 最终 commit：未产生。
- 涉及文件 / 修改说明 / 新增测试：无，未执行。
- 验证命令 / 实际结果 / CI 运行链接与结论：未执行 / NOT EXECUTED / UNKNOWN。
- 修改目标、依赖、验收计划：见上表 TASK-08；前置门禁 07。
- 风险与已知限制：复用单篇 API/ingestion/outbox，限制并发。

### TASK-09：论文分组与标签

- 状态：NOT_STARTED；开始 commit / 最终 commit：未产生。
- 涉及文件 / 修改说明 / 新增测试：无，未执行。
- 验证命令 / 实际结果 / CI 运行链接与结论：未执行 / NOT EXECUTED / UNKNOWN。
- 修改目标、依赖、验收计划：见上表 TASK-09；前置门禁 08。
- 风险与已知限制：后端检索范围；不复制 PDF/Embedding。

### TASK-10：实体标注状态可视化

- 状态：NOT_STARTED；开始 commit / 最终 commit：未产生。
- 涉及文件 / 修改说明 / 新增测试：无，未执行。
- 验证命令 / 实际结果 / CI 运行链接与结论：未执行 / NOT EXECUTED / UNKNOWN。
- 修改目标、依赖、验收计划：见上表 TASK-10；前置门禁 09。
- 风险与已知限制：区分未标注与不存在；严格过滤不等于全文搜索。

### TASK-11：实体提取与人工校正

- 状态：NOT_STARTED；开始 commit / 最终 commit：未产生。
- 涉及文件 / 修改说明 / 新增测试：无，未执行。
- 验证命令 / 实际结果 / CI 运行链接与结论：未执行 / NOT EXECUTED / UNKNOWN。
- 修改目标、依赖、验收计划：见上表 TASK-11；前置门禁 10。
- 风险与已知限制：保守带来源提取；费用显式、重试幂等、同名消歧。

### TASK-12：更精确 PDF 来源定位

- 状态：NOT_STARTED；开始 commit / 最终 commit：未产生。
- 涉及文件 / 修改说明 / 新增测试：无，未执行。
- 验证命令 / 实际结果 / CI 运行链接与结论：未执行 / NOT EXECUTED / UNKNOWN。
- 修改目标、依赖、验收计划：见上表 TASK-12；前置门禁 11。
- 风险与已知限制：保留 stable Evidence ID；旧索引兼容；不可伪造 bbox。

### TASK-13：引用与 PDF 阅读

- 状态：NOT_STARTED；开始 commit / 最终 commit：未产生。
- 涉及文件 / 修改说明 / 新增测试：无，未执行。
- 验证命令 / 实际结果 / CI 运行链接与结论：未执行 / NOT EXECUTED / UNKNOWN。
- 修改目标、依赖、验收计划：见上表 TASK-13；前置门禁 12。
- 风险与已知限制：复用 source metadata/受限 bridge；新增依赖先许可证审查。

### TASK-14：结构化研究报告生成

- 状态：NOT_STARTED；开始 commit / 最终 commit：未产生。
- 涉及文件 / 修改说明 / 新增测试：无，未执行。
- 验证命令 / 实际结果 / CI 运行链接与结论：未执行 / NOT EXECUTED / UNKNOWN。
- 修改目标、依赖、验收计划：见上表 TASK-14；前置门禁 13；03 提供评测基础。
- 风险与已知限制：扩展确定性 synthesis；保留 Reviewer、单位/实验条件边界。

### TASK-15：报告与比较结果导出

- 状态：NOT_STARTED；开始 commit / 最终 commit：未产生。
- 涉及文件 / 修改说明 / 新增测试：无，未执行。
- 验证命令 / 实际结果 / CI 运行链接与结论：未执行 / NOT EXECUTED / UNKNOWN。
- 修改目标、依赖、验收计划：见上表 TASK-15；前置门禁 14；05 元数据；13 来源。
- 风险与已知限制：Markdown/CSV/BibTeX/引用清单，安全文件名与下载。

### TASK-16：模型费用、延迟与任务状态

- 状态：NOT_STARTED；开始 commit / 最终 commit：未产生。
- 涉及文件 / 修改说明 / 新增测试：无，未执行。
- 验证命令 / 实际结果 / CI 运行链接与结论：未执行 / NOT EXECUTED / UNKNOWN。
- 修改目标、依赖、验收计划：见上表 TASK-16；前置门禁 15。
- 风险与已知限制：复用 Run/Event/Usage；未知不为零；不主动付费刷新。

### TASK-17：RAG 与 Research 对照评测

- 状态：NOT_STARTED；开始 commit / 最终 commit：未产生。
- 涉及文件 / 修改说明 / 新增测试：无，未执行。
- 验证命令 / 实际结果 / CI 运行链接与结论：未执行 / NOT EXECUTED / UNKNOWN。
- 修改目标、依赖、验收计划：见上表 TASK-17；前置门禁 16；03 框架及人工金标/模型条件。
- 风险与已知限制：同语料/问题/范围/配置，不预设 Research 更优。

### TASK-18：最终安装方案与完整部署

- 状态：NOT_STARTED；开始 commit / 最终 commit：未产生。
- 涉及文件 / 修改说明 / 新增测试：无，未执行。
- 验证命令 / 实际结果 / CI 运行链接与结论：未执行 / NOT EXECUTED / UNKNOWN。
- 修改目标、依赖、验收计划：见上表 TASK-18；前置门禁 17；01/02 诊断引导。
- 风险与已知限制：先 ADR 比较 Docker 自动部署和完整打包；复用 MSI/NSIS CI。

### TASK-19：科研用户端到端验收

- 状态：NOT_STARTED；开始 commit / 最终 commit：未产生。
- 涉及文件 / 修改说明 / 新增测试：无，未执行。
- 验证命令 / 实际结果 / CI 运行链接与结论：未执行 / NOT EXECUTED / UNKNOWN。
- 修改目标、依赖、验收计划：见上表 TASK-19；前置门禁 18；03/17 真实评测资源。
- 风险与已知限制：停止新功能；A–L 全场景，工程与人工证据分开。

## 提交与继续规则

一个任务可以有独立实现提交和仅补充该任务 CI 证据的后续提交，不能混入下一 TASK。
为避免“在提交内容中写入它自身 SHA”的循环，最终实现 SHA 在后续证据提交中记录；
证据提交自身由 Git 历史定位，最后提交的 CI 仍需实际检查并在交付报告给出。

后续运行先 `git status`、fetch 并查看本分支已有 commits/PR；保留其他人的工作。
已有 TASK 不重复实现。若上次被 GitHub 权限/网络或测试阻塞，先重试该具体门禁，不能越过。
真实金标、模型授权或 Windows GUI 缺失分别记录，不能用 mock/CI 构建冒充科学/人工验收。
