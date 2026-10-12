# Windows 原生部署：第一阶段结果与停止决定

日期：2026-10-13（Asia/Shanghai）。**结论：NO-GO，暂停第二、三阶段生产实现。**

目标仍是无 Docker/WSL 的单 EXE 安装。实际原型证明原生数据库和 Garnet 基础操作可以运行，
但当前生产使用的 RQ Worker 不能在 Windows 执行任务，选定 PostgreSQL 分发的中文路径也失败。
不能把基础命令通过等同于完整科研系统可安装使用。尚不能交付免 Docker `RAGSystem-Setup.exe`。
按本次用户的第一阶段门禁和“停止高风险变更”要求，交付审计、真实原型、证据与后续设计。
这不是证明所有 Windows 原生方案永远不可行；是当前固定版本方案未达到安全实施条件。

## 实际环境、版本与证据

- 审计基线 `376b73e8fb7ed1b90bec5bbadb80fe7e52f92dd4`。
- 原型实现 `11e933bef82f1f71408447465c7dcd6a4d846157`，分支 `codex/windows-native-runtime`。
- [Draft PR #4](https://github.com/maczhouyi-del/RAGSystem/pull/4)，堆叠于已有 research 分支；不合并 main。
- GitHub `windows-2025` x64 开发 runner；有 Python、MSVC、PostgreSQL 等预装工具。
  测试过程不调用 Docker/WSL，但这不是没有开发环境的干净 Windows 11 人工安装验证。
- PostgreSQL **17.11**，复制 runner 的原有分发到新建隔离目录，未改原安装/服务/数据库。
- pgvector **0.8.2**，官方 commit `cab9da72c04353f143bb06b42ab70a403daac64a`，MSVC/nmake 实际编译。
- Garnet **2.2.1** 官方 win-x64 ready-to-run ZIP，使用 net8.0 原生入口；RQ **2.12.0**。
- 测试数据是 **SYNTHETIC ONLY / NOT A BENCHMARK**。付费模型调用 **0**；科研效果 **NOT MEASURED**。

| 运行 | 实际结论 | 报告与来源 | 可下载报告 Artifact |
| --- | --- | --- | --- |
| [Push 38282856636](https://github.com/maczhouyi-del/RAGSystem/actions/runs/38282856636) | FAILURE / NO_GO_PRODUCTION | [原报告](evidence/push-native-report.json)、[来源](evidence/push-native-origin.json) | [11762440579](https://github.com/maczhouyi-del/RAGSystem/actions/runs/38282856636/artifacts/11762440579) |
| [PR 38282864644](https://github.com/maczhouyi-del/RAGSystem/actions/runs/38282864644) | FAILURE / NO_GO_PRODUCTION | [原报告](evidence/pr-native-report.json)、[来源](evidence/pr-native-origin.json) | [11761887687](https://github.com/maczhouyi-del/RAGSystem/actions/runs/38282864644/artifacts/11761887687) |

PR 实际 checkout 为测试合并 SHA `4f3e2bc98c9e88a1b32b412ed470c7012b339106`；Push 为上述实现 SHA。
仓库中的 JSON 是从完整运行日志中提取的原型输出；来源记录包含日志 SHA256、Artifact 服务端 ZIP digest。
未独立重新下载这两个 Artifact，不把服务端 digest 称为本地重算值。
这两个失败门禁保留，不重跑业务失败来取得绿色结果。后续文档提交不改变原型代码证据。

## 实际原型结果

| 项目 | 结果与范围 |
| --- | --- |
| PG ASCII 程序/数据目录 | PASS：17.11 + 编译 vector 0.8.2，现有 Alembic head 初始化迁移 |
| 向量、FTS、trigram、锁 | PASS：真实 vector 距离查询、TSVECTOR、pg_trgm、两连接 SKIP LOCKED，使用合成夹具 |
| 数据库持久/恢复 | PASS：pg_dump/独立空库 pg_restore；immediate stop 后原库与恢复库重新启动，夹具行数保留 |
| PG 中文/空格程序目录 | FAIL：原安装 pg_config 正常，同源复制到含中文/空格目录后退出 1 |
| PG 中文/空格数据目录 | FAIL：ASCII 程序 initdb 指向该数据目录退出 1；另起 ASCII 数据夹具通过，未覆盖或转写失败 |
| Garnet 认证与接口 | PASS：真实 socket，127.0.0.1/密码；未授权 PING 拒绝，Lua SET、BLMOVE、WATCH/MULTI/EXEC 基本操作成功 |
| 真实 RQ 入队与排队取消 | PASS：三个独立命名队列各入一个真实 RQ job，unique=True 路径成功，排队 job cancel 后状态 canceled |
| 队列持久化 | PASS：COMMITAOF，结束原生服务后从磁盘重启，三个队列各保留原 job ID；不是所有崩溃时序的持久性证明 |
| 现有原版 Worker 执行 | **FAIL**：真实子进程尝试消费首个 job，未完成；私有日志匹配 `os.fork` 不存在，报告 `OS_FORK_UNAVAILABLE` |
| SpawnWorker | **NOT EXECUTED**：源码将连接 kwargs（含密码）拼进 `python -c` 命令；还依赖 os.setpgrp/Unix监控与解释器入口，不安全执行 |
| 三 Worker、重试、超时、运行中停止/恢复 | **NOT EXECUTED**：任务执行前提失败；不能以三个队列入队或一次 Lua 命令代替这些验证 |
| 原生完整 PDF→RAG/Research/报告 | **NOT EXECUTED**：原生 Worker 前提失败；旧 Docker 路径的回归单独报告 |
| pgvector 构建文件 | 实际 postgres.exe/initdb.exe/vector.dll SHA256 分别记录在两份报告；不同 runner 构建的 vector.dll 哈希不同，不声明可重复二进制构建 |

中文路径结果来自该英文 Windows Server runner 与选定 PG 分发，未判定所有中文 Windows 11 必然失败。
ASCII 回退仅为技术诊断，不是产品自动改写用户数据路径，也不是中文账户验收成功。

## 安全和数据保护

原型只创建自身拥有的新目录、新 PGDATA、空数据库、命名测试队列和随机回环端口。
未操作原有用户论文、配置、Docker volumes；未连接已有数据库，不删除已有安装。
PG 密码通过受限 pwfile/子进程环境传入；Garnet 密码在受限 JSON；Worker 连接 URL 在环境内，均不在 argv。
复用已有 `private_write` Windows ACL 机制；这里只使用每次随机的测试密码，没有用户 API Key。
PG/Garnet 均绑定回环；没有新增 Tauri IPC、shell 权限或授权豁免。
Artifact 仅上传安全 JSON；私有日志、密码文件、DB、dump 不上传。诊断只输出固定错误码和经过密钥过滤的启动错误。
这些是原型边界，不是生产安装/卸载、Defender、普通用户 ACL 与所有崩溃报告的完整安全验收。

## 失败历史保留

| 实现/运行 | 事实与处理 |
| --- | --- |
| 364d67b / Push38276890932 | job 创建前 workflow context 无效，0 job；改为分配 runner 后设置目录，不算原生业务失败 |
| 5a08b4f / Push38277315499、PR38277320980 | 拷贝后的 pg_config 失败，未执行 DB/队列；增加原分发对照 |
| 83b7a96 / Push38277820366、PR38277828064 | 原 PG17.11 通过、中文路径副本失败；分离 ASCII 程序和中文数据测试，不隐藏原失败 |
| fddfa14 / Push38278515817、PR38278523098 | 控制进程管道等待，主动取消；没有完整功能报告，不能认定通过。改用 DEVNULL、连接/查询/进程超时与即时阶段输出 |
| 2aaa48b / Push38280530370、PR38280536993 | ASCII PG 实测通过，中文路径失败；Garnet 启动失败，RQ 未执行 |
| 33b2de1 / Push38281342937、PR38281400324 | Garnet 启动退出 0 但不 ready；实际源码捕获异常只打印 message，退出 0 不是健康证明 |
| 319ad07 / Push38282305607、PR38282312505 | 明确错误：LogDir 需启用 StorageTier。修正原型配置，不称为 Redis 兼容性缺陷 |
| 11e933b / Push38282856636、PR38282864644 | 修正启动后，Garnet 基础/RQ 入队通过，真实原版 Worker fork 失败；最终核心 NO-GO |
| 旧路径 Desktop38278515731 | attempt1 Intel macOS bundle_dmg.sh 失败，根因未确认；仅失败 job 重跑，attempt2 SUCCESS；原失败保留 |

详细逐阶段记录在 [stage-log](../stage-log.md)。原型准备和诊断改动是为取得证据，没有弱化生产队列或科研断言。

## 已有路径兼容性回归

精确原型提交的 **Push/PR CI + Push/PR Desktop 四工作流，14/14适用job全部 SUCCESS**。
实际完整日志已读取，job/步骤结果与日志SHA256记录在 [legacy-regression.json](evidence/legacy-regression.json)。

| 回归项目 | 实际结果 |
| --- | --- |
| 后端 | 1010 PASS，含真实PostgreSQL/pgvector集成；0 skipped |
| 前端 | 131 Playwright PASS（MOCK）；lint/check/build PASS |
| transport | 19 PASS；四原生平台实际运行 |
| Tauri/Rust | Windows/macOS两架构各19、Linux18测试PASS；fmt/check/clippy PASS；真实Credential Manager/Keychain |
| 桌面构建 | 实际MSI/NSIS、两macOS DMG、Linux deb/AppImage及助手CPU/版本检查PASS；Windows packaged GUI自动冒烟PASS |
| 旧Docker部署 | 真实PG/Redis/Docling PDF导入与索引；MOCK RAG/Research/四导出、配置/密钥存在性、worker/DB恢复、备份/空库恢复、重启迁移与卷保留PASS |
| 本地静态检查 | Ruff format/check、mypy97files、原型help、JSON解析、diff check PASS |

具体运行：Push CI38282856644、PR CI38282864651、Push Desktop38282856676、PR Desktop38282864770。
验收记录提交只改README/报告；上述实现SHA与PR测试合并SHA保留，不能把新记录SHA当成旧二进制来源。
不要将已通过的 Docker/Mock 回归转换为原生模式或真实模型验收。

## 未执行的产品验收与仍需手动的步骤

| 用户要求 | 状态 / 原因 |
| --- | --- |
| 干净 Windows11，仅 EXE/GUI，无 Docker/WSL/开发工具 | **NOT EXECUTED**：原生安装器尚未实现，runner 不是该环境 |
| 冻结 API/三 worker、PDF native DLL/资源完整性 | **NOT EXECUTED**：先过 workhorse 门禁，不能仅打包 Python 宣称通过 |
| 原生图形向导、首次论文与真实引用问答 | **NOT EXECUTED**：第二/三阶段暂停；已有 beta2 向导仍是 Docker 路径 |
| 原生模型密钥、付费推理、模型下载/离线失败 | **NOT EXECUTED**，科研 **NOT MEASURED**；不自动调用收费服务 |
| 中文 Windows、非管理员账户、Defender、低配电脑 | **NOT EXECUTED**；原型中文路径已 FAIL，但不是这些环境人工结果 |
| 原生端口/磁盘/权限失败、休眠/唤醒、关闭进行中任务 | **NOT EXECUTED**；仅原型超时与特定启动失败有证据，无产品 GUI 恢复验收 |
| 原生安装中断、升级、重复安装/卸载保留数据 | **NOT EXECUTED**；不宣称无损升级，不执行自动清理 |
| Docker 数据迁往原生 | **NOT EXECUTED / 不自动迁移**：需要备份、一致性、互斥、中断恢复和空目标回滚独立设计 |

本阶段交付的是开发者可复现原型，复现需要 Windows 开发依赖，不能作为普通用户的安装指引。
普通用户现有可下载版仍为 [beta2](https://github.com/maczhouyi-del/RAGSystem/releases/tag/v0.2.0-beta.2)，
按 [README](../../README.zh-CN.md) 手动安装 Docker、下载部署包、配对并填写模型配置；它不满足本次免 Docker 目标。
没有把该路径当作本次替代实现或新的原生 Release。

## 安全后续方案（先验证，后生产）

1. **RQ Windows workhorse 单独实验**：保留 RQ/SQL 持久调度与业务 job，调查上游受支持的 Windows worker。
   若没有安全实现，只在原型分支设计专用 workhorse 入口/受限 secret 环境或私有 pipe，
   不生成带密码的 `-c` 命令，不 monkeypatch fork/禁用超时，不以 SimpleWorker 替代。
   Windows Job Object 必须能拥有并结束本次子进程；检查 frozen exe 入口、心跳、registry、杀进程回调及 SIGALRM 替代机制。
   用真实 Garnet/真实 RQ 对三 Worker 并发、unique 重复提交、跨队列隔离、异常退出/reconcile、重试/超时、
   queued/active cancel、重启中断恢复、DB claim 进行完整验证。仅基本任务通过还不足 GO。
2. **PG Windows 分发闭环**：固定可重分发 PG17 来源、完整许可证/第三方 notice 和 DLL 依赖清单；
   排查 Unicode failure 的具体组件/locale，测试中文/空格用户目录与普通账户。
   如采用独立 ASCII 存储路径，必须形成明确安装/ACL/备份/数据位置设计并实际验证，不能静默移动已有论文/库。
   验证最低 Windows11/VC runtime/无开发 PATH 环境、PG patch 更新、扩展升级、备份与失败回滚。
3. **Garnet 可交付性**：基础接口不是全 Redis 兼容。固定 release源码与资源许可证、native Lua/.NET/VC 依赖，
   真实多进程一致性、AOF 丢电/磁盘满/损坏恢复、auth 与最小权限、升级测试过后，才能选择为生产运行时。
4. **前述全部 GO 后**：API/worker onedir 打包保留现有业务入口，验证 Docling/native wheels、embedding/reranker 缓存；
   Rust 最小 lifecycle 命令、受控后台进程与 NSIS 多资源安装；图形化服务进度/错误重试/首次配置/PDF入口。
   安装与用户数据分离，保留原认证/私有密钥机制；所有下载需版本/签名或固定 SHA256与用户确认。
   旧 Docker/Web/macOS/Linux 模式继续独立；数据迁移不作为自动升级副作用。
5. 最后在真正无依赖 Windows11 上完成用户列出的 P0/P1 安装、实功能与异常恢复矩阵，
   再讨论单 EXE Release。没有这些证据前，本任务整体状态保持 **BLOCKED / NO-GO**。
