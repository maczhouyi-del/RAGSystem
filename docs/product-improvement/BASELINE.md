# TASK-00：现有代码与测试基线

核查日期：2026-10-08（Asia/Shanghai）。本报告只审查现状，不实现 TASK-01 或后续功能。
任务状态、提交及后续依赖以 [PROGRESS.md](PROGRESS.md) 为准；机器可读验证记录见
[task-00-evidence.json](task-00-evidence.json)。

## 1. 基准与范围

- 仓库：`maczhouyi-del/RAGSystem`；已执行 `git fetch origin main`。
- 最新 main / 开始提交：`a8d5c1f0ace08573c5e5787bf5eef39570405191`。
- 基准 tree：`7099b234b7ff06c0eaf038569ecf511d100bb6b4`。
- 开发分支：`codex/research-product-improvement`，从 origin/main 创建；开始时工作区干净，未发现同名本地或远端分支。
- 初次基线提交只新增基线、进度、验证记录并追加 stage log；恢复阶段仅修复已有集成测试的 UUID 误判（见第 9 节）。业务、依赖、锁文件、迁移、CI 与用户配置均未修改。
- 已阅读 README 两个语言版本、部署/架构/检索/评测/会话文档、ENGINEERING_REVIEW.md、product-upgrade-report.md、stage-log.md、现有工作流及下列实现。

历史报告来自不同提交，不能把其中的 461/504/566 等测试数、旧分支状态或历史安装包视为当前 main 的验收结果。部署文档仍有旧仓库、旧开发分支及合并前措辞；本轮记录这一文档缺口，不顺带改造部署流程。

## 2. 当前实现与产品缺口

| 领域 | 当前代码事实与依据 | 尚缺或不应宣称完成的能力 |
| --- | --- | --- |
| RAG | `src/ragagent/graphs/rag.py:build_rag` 使用 StateGraph：plan → retrieve → answer → verify，有界 expand/refuse；用户过滤器受约束，rerank 使用原问题。 | 工程测试证明路径与约束；未证明真实论文回答准确率。 |
| Research | `graphs/research.py:build_research` 保留 supervisor/retriever/analysis/synthesis/reviewer；限制检索、修订、迭代、证据池；重规划按完整 task 内容判断完成状态。 | synthesis 当前是标题加确定性 `render_claims` 拼接，未提供用户要求的完整章节、实验条件/单位比较结构。TASK-14 应扩展此节点，保留发布门禁。 |
| Evidence | `retrieval/evidence.py`、`domain/research.py`：chunk/span 稳定 ID、原文区间校验、每个 claim/evidence pair 的语义审查、aspect/comparison coverage、确定性引用；失败不能发布已验证回答。 | Reviewer 是模型检查，不等于人工科学审查。自动通过不证明原论文或结论真实。 |
| 检索 | `retrieval/service.py`、`filters.py`：pgvector 精确 dense + PostgreSQL English FTS + RRF + reranker；两路 SQL 都施加过滤；排除 withdrawn/retracted；embedding fingerprint 隔离。 | English FTS 及默认模型跨语言质量未测。数据集/方法/指标严格过滤依赖 ChunkEntity，上传索引不等于已标注。 |
| Knowledge | `api/papers.py`、`frontend/src/Knowledge.tsx`：单 PDF、arXiv、去重、任务、来源版本/状态、原 PDF、chunk、retry；已有 limit/offset 服务端分页，UI 每页 50 条并多取一条判断下一页。 | 没有论文列表标题/作者搜索、年份/venue/status 组合筛选、总数；仅 created_at 降序，没有唯一键 tie-break。不得把 TASK-04 描述成从零增加分页。 |
| 元数据 | `api/papers.py:update_metadata` 已有标题、作者、年份、venue、source_status PATCH 和行锁；arXiv 版本不在可编辑字段中。UI 可编辑来源状态。 | 普通元数据编辑 UI、用户/原始字段来源展示和防止陈旧编辑覆盖的冲突协议尚需 TASK-05；数据库行锁本身不是乐观版本冲突检测。 |
| 删除/导入/组织 | 当前没有 paper DELETE 路由；已有单文件 ingestion Run、durable dispatch 和重复请求防护。 | 安全删除生命周期、迟到 worker 防护与历史引用失效、批量上传队列、分组/标签未实现；不可仅复用会话删除逻辑删除论文。 |
| 实体 | `api/papers.py:annotate` 按 name/type 建立 Entity 和 ChunkEntity，验证 chunk 属于 paper；重复关联避免重复插入。 | 无自动实体抽取队列、标注完成度、人工确认/来源置信状态或同名实体消歧流程。无标注不能解释成论文中不存在某实体。 |
| PDF 来源 | `ingestion/parser.py` 读取 Docling prov 页码、self_ref、章节 ancestry 和 caption refs；`domain/documents.py`/chunker 保留 SourceSpan、独立 SourceContext 和字符偏移。 | 当前 DTO 不保留 bbox。文本偏移指解析后的 Element/Chunk Unicode 文本，不是 PDF 字节/版面坐标；无 prov 项被跳过。真实复杂 PDF 解析保真度未验收。 |
| 引用阅读 | `frontend/src/components.tsx:Citations` 对原文 code-point span 核查/展示，显示论文/页/章节与辅助表格上下文；Web PDF 带目标页，Desktop 走受限本地资源桥与系统阅读器。 | 系统阅读器可能不按页定位，无可靠 bbox 精确高亮；不能把文本片段高亮宣称为 PDF 版面高亮。 |
| Memory/多轮 | `conversations/context.py`、`service.py`、`api/conversations.py`：近期消息、确定性有损摘要、显式 Memory Top-K、结构化硬过滤交集、持久 intent/entity state；独立问题跳过改写；有效 retry lineage 排除被替代回答。`Memory.tsx` 可查看/增删显式记忆。 | 历史/摘要/记忆仅理解意图，不进入本轮科学 Evidence。清记忆保留消息，后续可以重建摘要；不等于遗忘全部历史。真实代词解析/错误历史抗干扰率未测。 |
| 持久任务 | `jobs.py`、`db/dispatch.py`、`worker.py`、`api/runs.py`：Run+dispatch 事务、幂等 claim、终态/event 事务、SSE replay、取消撤销执行权与迟到写保护；interactive/ingestion/evaluation 三队列。 | 不是任意图节点断点恢复；共享 CPU/RAM 仍竞争。取消不能撤回已发出的远程计费调用。 |
| Evaluation | `evaluation/{schema,metrics,retrieval,generation,conversation,multilingual,artifacts}.py`：人工来源字段、synthetic/unannotated 区分、逐例输出/原文/标签/judge、失败 checkpoint/resume、source/corpus/model/config identity，复用既有 Run/worker。 | TASK-03 是扩展统一科研验收覆盖与人工逐项核查，不是另造框架；复杂数值准确率、人工 claim 支持率、真实跨语言/比较与公平 RAG/Research 对照未完成测量。 |
| 成本/状态 | `providers/chat.py:Usage`、worker 持久化：prompt/completion、known_cost、unknown_cost_calls、in-flight、返回 model/fingerprint；未知总费用为 null；失败/取消仍保留已知 usage。 | chat ResultPanel 展示状态、重试、事件、计划/reviewer/context，尚无完整直观的费用/阶段耗时面板；同步 search/provider test 与 reindex 不属于持久 Run 账单。 |
| 导出 | Evaluation 已能下载 JSON/Markdown artifact，含逐例结果和证据。 | 不能等同于普通 Research/旧会话 Markdown、比较 CSV、论文 BibTeX 与引用清单产品导出。 |
| 首次使用 | 现有 AuthPanel、Settings、Diagnostics 及后端 `/api/diagnostics` 可复用；诊断明确 inference/connectivity/model_loading 为 not_tested，不主动推理。 | 缺少跨平台外部环境诊断脚本与分步骤首次使用引导。TASK-01/02 不应重写授权或把配置存在当调用成功。 |

## 3. 安装包、依赖与 readiness 边界

Tauri `tauri.conf.json` 打包 React dist 和 Rust 桌面 shell，没有 Python sidecar/backend/database/model bundle。Rust bridge 固定 `127.0.0.1:8000`，限制路径、方法、重定向、代理和本地资源；授权凭据由 OS credential store 管理。Windows workflow 真正执行 MSI/NSIS 构建和上传，但产物为 unsigned。

非开发者第一次使用仍需：独立安装/启动 Docker Engine/Desktop 与 Compose v2、取得项目部署配置、先配对 Desktop 并把非密钥 hash 配置到后端、启动 PostgreSQL/pgvector、Redis、迁移、API、三个 worker 及 Web；实际问答另需配置 chat provider/本地模型，以及可用的 parsing/embedding/reranker 模型资源和已索引语料。构建桌面源码另需 Node、Rust 和 OS WebView 开发依赖。Windows 运行依赖 WebView2；macOS 兼容配置存在，但目前没有 macOS CI job 或本轮实际运行证据。

| 检查 | 实际含义 | 不代表什么 |
| --- | --- | --- |
| `/api/health` | API 进程能回应 `ok` | 不检查 DB/Redis/worker/auth/model |
| `/api/ready` | 已初始化本机授权 verifier，DB SELECT 1、Redis ping、interactive worker 注册存在 | 不执行推理，不检查所有模型，不要求 ingestion/evaluation worker，也不证明知识库有可用论文 |
| `/api/queues` | 三类队列 pending/worker 数 | 不证明 worker 能完成任何真实模型任务 |
| `/api/diagnostics` | 授权后的 infrastructure/configuration 快照 | provider key 存在不等于有效，inference 明确 not_tested |
| 成功科研问答 | 真实解析/索引/检索/chat/reviewer 对有许可论文完成回答，并人工核查 | 本轮 NOT EXECUTED；科学质量 NOT MEASURED |

本轮只检查变量名称/是否存在：默认 OpenAI/Anthropic/DeepSeek key 未注入，无已提供人工金标/批准模型目录；项目 venv 没安装可选 docling/torch/sentence_transformers。未调用付费模型、未下载权重、未绕过许可证或网络策略。基础设施 smoke 的 `provider_key_missing` 是有意验证失败路径，不是成功推理。

## 4. 版本、锁定与迁移

- Python/Web/Desktop 产品版本均 0.2.0；Python 声明 `>=3.11,<3.14`，CI 使用 uv 0.12.19 / Python 3.11；本机 Python 3.11.16。
- `uv.lock` 覆盖核心/dev/可选依赖；本轮 `uv sync --locked` 安装 109 个核心/dev 包，无锁文件变化。可选 parsing 为 Docling 2.133.0，models 为 torch 2.8.0/torchvision 0.23.0 与 sentence-transformers 5.x，Linux CPU index。
- `frontend/package-lock.json` 和 `frontend/src-tauri/Cargo.lock` 已提交。CI Node 22，本机 Node 24.19.0/npm 11.9.0；本轮没有把本机 Node 24 结果冒充 Node 22 结果。Rust toolchain 1.90.0；Tauri 2.12.1。
- Compose/CI pgvector image `0.8.2-pg17`，Redis `7.4.2-alpine`；本机实际 PostgreSQL 17.10、pgvector 0.8.2、Redis 7.4.2。
- 单链迁移：0001 normalized papers/evidence → 0002 section identity/dispatch → 0003 paper source identity → 0004 conversations/memory → 0005 retry lineage → 0006 conversation intent state。
- 在专用、可丢弃测试 DB `ragagent` 上执行 upgrade head → downgrade base → upgrade head，最后 head=0006。应用 DB 为独立 `ragagent_dev`；没有对应用数据执行 downgrade/truncate。既有迁移、旧数据/重试/会话测试属于本轮 141 项集成测试。

## 5. 实际验证与测试真实性

本轮在未修改业务代码的基准上重新执行，不仅沿用上一轮环境安装结果。

| 验证 | 实际命令 | 本轮结果 |
| --- | --- | --- |
| 锁定安装 | `uv sync --locked` | PASS |
| Python 格式/静态 | `uv run ruff format --check .`、`uv run ruff check .`、`uv run mypy src` | PASS；180 格式文件、72 source files |
| 数据库往返 | `uv run alembic upgrade head`、`uv run alembic downgrade base`、`uv run alembic upgrade head` | PASS；专用测试库 |
| Python 完整回归 | `uv run pytest -q --junitxml=/workspace/.rag-task00/pytest.xml` | 604 passed：463 unit + 141 integration；0 failed/errors/skipped；53.57s |
| 前端安装/静态/构建 | `npm --prefix frontend ci`、`run lint`、`run check`、`run build` | PASS |
| 浏览器 | `npm --prefix frontend run test:e2e` | 32 passed，36.9s；系统 Chromium，2 workers，HTTP/SSE mock scenarios |
| 传输 | `npm --prefix frontend run test:transport` | 10 passed；0 failed/skipped |
| 当前运行服务 | GET `/api/ready` 经 Vite proxy | HTTP 200，status=ready；不是模型成功 |
| 同会话准备阶段 live smoke | `.venv/bin/python /workspace/.rag-onboarding/start.py --smoke`，内部 `scripts/smoke.py` | 此前已 PASS，代码 SHA 相同：empty search、真实 RQ 缺 key 失败、proxied SSE、持久 conversation/idempotency/memory 删除；本轮没有重跑此 launcher |
| Compose 镜像/启动 | 本轮本机未构建；见下节同一基准 SHA 的真实 GitHub CI compose job | 远端 SUCCESS；不能称为本轮本机 Compose 验证 |
| 桌面 Rust/GUI/安装包 | 本轮本机 NOT EXECUTED；见同一基准 SHA 的真实 Desktop workflow | 远端 Windows/Linux SUCCESS；Windows 11 人工安装 NOT EXECUTED |

本机测试环境：`UV_CACHE_DIR=/workspace/.cache/uv`、`UV_PYTHON_INSTALL_DIR=/workspace/.local/python`；DATABASE_URL/TEST_DATABASE_URL 指向隔离测试库，TEST_REDIS_URL 指向 DB 15；应用使用 Redis DB 0。浏览器设置 `PLAYWRIGHT_CHROMIUM_EXECUTABLE=/usr/bin/chromium` 和外部 `PLAYWRIGHT_OUTPUT_DIR`，避免污染仓库。

实际 warnings：Alembic 未指定 path_separator 的弃用提示；Vite bundle >500 kB 及 Zod PURE 注释提示。均未改断言、删测试或改依赖绕过。

真实性边界：`tests/integration/test_graph_execution.py` 使用真实 PostgreSQL HybridRetriever，但 Embedding/Reranker/Chat 为 fixture/MockProvider；conversation/evaluation 测试也包含 scripted reviewer/judge；`tests/unit/test_parser.py` 替换 Docling 模块并输入结构化 fixture，不是真实 OCR。已有浏览器测试主要拦截 API/SSE。没有收集覆盖率百分比，不能从用例数推导全覆盖。

## 6. 当前基准的真实 GitHub CI

已访问当前仓库的公开 Actions 列表及每个 run summary，核对完整提交链接、状态和 job；不是引用旧仓库历史报告推测。

| 工作流 | 基准提交 | 运行链接 | 实际观察 |
| --- | --- | --- | --- |
| CI | a8d5c1f0ace08573c5e5787bf5eef39570405191 | [37771426122](https://github.com/maczhouyi-del/RAGSystem/actions/runs/37771426122) | Success；backend/frontend/compose 全部成功 |
| Desktop | 同上 | [37771426070](https://github.com/maczhouyi-del/RAGSystem/actions/runs/37771426070) | Success；windows-desktop/linux-desktop 全部成功 |

Desktop 当前基准 artifact `11547938987`：`scientific-ragagent-windows-unsigned-a8d5c1f0ace08573c5e5787bf5eef39570405191`；页面大小 5.22 MB，GitHub 显示 archive digest `65dd9bf49806e01184bafc86c5bc3c1aa52a3c2e8b33e8267d310b5fd2c6413d`。本轮尝试下载此 archive，但其存储目的地 productionresultssa19.blob.core.windows.net 被代理拒绝；没有完成下载，也没有重新计算 MSI/NSIS 逐文件哈希。旧文件 `docs/validation/windows-artifacts-f803d824.json` 属于原仓库旧 commit，不能充当新 artifact 的独立校验。

工作流内容核查：CI backend 含真实 PG/Redis、migration roundtrip 和 pytest；frontend 含 Playwright；compose 含构建/ready/smoke/旧卷 ownership 验证。Desktop Windows 含 locked check/test/clippy、OS credential store、真实 MSI/NSIS；Linux 含 native build、loopback 和 Xvfb 窗口 smoke。当前没有真实 Windows 11 用户安装/科研流程验收。

最初 `gh api .../actions/runs` 返回代理 CONNECT 403；先使用公开 github.com 页面读取真实 run 状态，并保存只追加 api.github.com 的环境网络草稿。后续实际 REST/GraphQL 请求已成功，重新核对了基准 jobs/steps，并创建草稿 PR #1。可用性以成功请求为证，不以草稿保存推断。artifact 的独立存储目的地仍被拒绝。新 TASK-00 提交必须另查 CI，不能沿用 main 的绿色状态；结果记录在 PROGRESS/evidence。

## 7. 科研质量与后续验收边界

当前 Evaluation 已有 Recall@1/5/10、Precision@5、MRR@10、nDCG@10，以及 model-based citation/claim/aspect/refusal 指标、workflow/judge 分离的耗时和 usage、失败/resume 记录。`evals/*/demo.json` 是 synthetic，annotation-template 是未标注模板；human 标志及 annotator/date 只是提交者声明，不自动认证金标质量。

`docs/benchmarks/multilingual-status.json` 及 multilingual.md 保留 en→en、zh→en、zh→zh 与不同模型组合的空指标。实际跨语言召回、复杂表格/数值准确率、跨论文可比性、错误历史抗干扰、真实 RAG vs Research 效益：**NOT MEASURED**。已有 messages/context/queue 工程 benchmark 是历史合成 fixture 的 API/构造/占用测量，本轮未重测，不是科研质量/模型端到端性能。

后续外部条件：经许可且可本地保存/处理的论文、人工核对的逐问金标（版本/页/正确证据）、批准的模型权重与身份/许可证、可用 provider 或本地推理服务及费用授权、真实 Windows 10/11 x64 和 macOS 验证环境。不能因这些条件缺失阻止独立工程框架工作，也不能解除 TASK-17/19 的真实验收门禁。

完整串行任务顺序与依赖见 PROGRESS.md。本轮没有调整用户顺序，没有实现任何后续 TASK。

## 8. TASK-00 初次提交门禁结果（历史）

基线文档提交 `d238275e3e49c392c5907bf218ffda57161b3a13` 已推送，
草稿 [PR #1](https://github.com/maczhouyi-del/RAGSystem/pull/1) 已创建。
同一 head 的 push CI 37782711529 SUCCESS；PR CI 37782769354 的 backend
在 `uv run pytest -q` 步骤 FAILURE，frontend/compose SUCCESS；PR Desktop
37782769337 Windows/Linux SUCCESS。静态检查及 migration 步骤在失败的 backend
job 中也通过。精确 job/step 结果保存在 task-00-evidence.json。

日志读取经 gh run view 和标准 REST job logs endpoint 均被存储域名代理拒绝，
公开 step log 返回 404，因此具体失败用例及原因 UNKNOWN。文档之外的源码与
基准 Git diff 为空；这不能直接证明失败是偶发或环境原因。未修改测试、跳过
用例或盲目重跑。TASK-00 为 BLOCKED，不能开始 TASK-01。恢复前置为应用已保存
网络域名变更并取得失败日志。此结论不抹去本机 604 项通过和远端失败的差异。

## 9. 基线测试误判恢复（2026-10-09 Asia/Shanghai）

失败日志现在已可下载。run 37782769354 的唯一失败是
`test_false_local_history_and_memory_cannot_supply_scientific_answer[research]`：
答案含正确的 120 participants，但引用 UUID `85d8-a4c5-5009-b422-19530dd16509`
含字符串 500，命中了全字符串断言。原运行实际为 603 passed / 1 failed。
因此已确认既有测试对随机标识符的误判；该失败不证明错误历史被当作科学事实。

为解除基线门禁，只调整现有测试文件与本任务记录。固定 source chunk 和真实
UUID5 Evidence ID 均含 500，在 RAG/Research 中原断言各稳定失败；修复后仍
要求正确 120 人、正确证据引用和来源 chunk，错误数字不能出现在非引用正文或
分析/审查请求的科学文本中。完整 UUID 字符串值与科学文本分开检查。
外部负向控制向分析请求注入错误 500 人文本，两模式仍按预期断言失败。
修复后 worker 文件 6 passed，完整 Python 604 passed，Ruff/mypy/锁定安装 PASS。
只改变测试，无业务、数据模型、API 或依赖修改；新增语义检查范围没有变成
允许错误人数。修复提交 `09c29113bad0df7225e7d0f7e88b21bcd89a7de0` 的 push/PR CI 和 Desktop 已核对全部 SUCCESS：CI 37882246737 / 37882251101，Desktop 37882246783 / 37882251036。TASK-00 为 PASSED；旧失败保留作为诊断证据，TASK-01 未开始。
