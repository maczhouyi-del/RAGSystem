# TASK-18 / TASK-19 工程测试版交付

版本 **0.2.0，未签名测试构建**。安装产物构建 SHA：
`817dd43a4c4d8f525f5173d48474357ff6814d9c`。
交付的是 **客户端安装包 + 同平台部署 ZIP**；必须安装 Docker Desktop（Windows/macOS），或 Docker Engine + Compose ≥2.24（Linux）。不需要主机 Python、Node.js 或 Rust。首次后端构建需要互联网。不是正式 Release。

## 下载

登录 GitHub 后下载下列 Actions Artifact，解压外层下载包。
其中 `frontend/src-tauri/target/release/bundle` 提供客户端安装器，`deployment-dist` 提供部署 ZIP。
Windows MSI 与 EXE 任选一个；必须同时解压并运行同一 Artifact 内的部署助手。

| 平台 | 客户端 | 下载完整 Artifact |
| --- | --- | --- |
| Windows x64 | .msi, .exe | [下载](https://github.com/maczhouyi-del/RAGSystem/actions/runs/38052578187/artifacts/11670216639) |
| macOS Apple Silicon | .dmg | [下载](https://github.com/maczhouyi-del/RAGSystem/actions/runs/38052578187/artifacts/11670570823) |
| macOS Intel | .dmg | [下载](https://github.com/maczhouyi-del/RAGSystem/actions/runs/38052578187/artifacts/11670500993) |
| Linux x64 | .AppImage, .deb | [下载](https://github.com/maczhouyi-del/RAGSystem/actions/runs/38052578187/artifacts/11669907075) |

上述 Artifact 当前未过期，GitHub 记录的过期时间为 **2027-01-08 12:36:28 UTC**。过期后需重新构建并重新核验，不能复用本表校验值。

[完整安装与首次使用指南](../installation/README.md) · [数据、备份、升级和卸载](../installation/data-and-upgrades.md) · [故障排查](../installation/troubleshooting.md) · [交付后本地真实评测](../installation/local-evaluation.md)

## 实际 SHA256

以下针对解压后的单个文件；GitHub 外层 Artifact ZIP 有独立 digest，不应与这些值混用。
独立验证 [Push 38053611108](https://github.com/maczhouyi-del/RAGSystem/actions/runs/38053611108) 和 [PR 38053615245](https://github.com/maczhouyi-del/RAGSystem/actions/runs/38053615245) 均 SUCCESS。
它们通过官方 download-artifact 下载全部实际包、复算安装器与部署 ZIP，并核对 ZIP 内每个文件、版本、构建 SHA、平台及敏感文件排除；两份报告完全一致。
云工作区直接 Blob 下载受策略限制，实际下载与复算在 GitHub Actions 执行；没有宣称在本机运行四个平台安装器。
[机器可读复算报告](task-19-installer-verification.json) · [验证报告 Artifact](https://github.com/maczhouyi-del/RAGSystem/actions/runs/38053611108/artifacts/11669723430)

| 平台/文件 | 字节数 | SHA256 |
| --- | ---: | --- |
| Linux x64 / `Scientific RAGAgent_0.2.0_amd64.AppImage` | 81738232 | `cee1ae62b7648f7153afe0930e984729aa1fc109c98359ff05af563bcc7ec812` |
| Linux x64 / `Scientific RAGAgent_0.2.0_amd64.deb` | 3036652 | `4c279a6f8582f0843674436ac2ab8fee858923014cdbef31524325579b8a6e81` |
| Linux x64 / `RAGSystem-deployment-linux-x86_64.zip` | 21167663 | `5f6b4b2424834dced98380ebffb0c25f68e7a9d7558066745e8c0c65654171cb` |
| macOS Apple Silicon / `Scientific RAGAgent_0.2.0_aarch64.dmg` | 2688394 | `802afe00f614c61584f8ded0f64eb48fa254ce953d0d5e8aea9c4c3c376313d6` |
| macOS Apple Silicon / `RAGSystem-deployment-macos-aarch64.zip` | 8671855 | `a6335b4aa3a1c7ea8abe6fdda8c5382dba3f08fa3762e47c3ff5c8254206d1b6` |
| macOS Intel / `Scientific RAGAgent_0.2.0_x64.dmg` | 2859058 | `849d18ef472c31532460d7fa05b42a4384031d0159d94b0c6df480466d8522e5` |
| macOS Intel / `RAGSystem-deployment-macos-x86_64.zip` | 9197933 | `ffd3b4e6ad1f5d6fc25197d98035a39eae3f3a12e117b509dcce64d5d8e166d1` |
| Windows x64 / `Scientific RAGAgent_0.2.0_x64_en-US.msi` | 3407872 | `e4b5deb0f83cdf937db065689fd499dcf54636fc9589eb3c00e905faf0a31329` |
| Windows x64 / `Scientific RAGAgent_0.2.0_x64-setup.exe` | 2368154 | `f0d031b77ba0c46c77e9c5474f6fd719d7595193932005b1f8d6ed7a2783f44d` |
| Windows x64 / `RAGSystem-deployment-windows-x86_64.zip` | 9468064 | `24ac55f4a15cdc19b22a50a324efdc1a194198db878dc17a986c650bd83fdb84` |

Windows PowerShell：`Get-FileHash -Algorithm SHA256 "文件完整路径"`；macOS：`shasum -a 256 "文件路径"`；Linux：`sha256sum "文件路径"`。核对后按系统或组织策略处理未签名提示。

## 工程证据及边界

TASK-16 PASSED：原实现 f2423e5 与 b20f4f7 仅三份文档不同；b20 四工作流十 job 全通过。原 Rust 下载超时 attempt1 保留 FAILURE；原 Linux job 定向重跑 attempt2 的新 job114203551683已实际通过 Rust/fmt/check/test/clippy/GUI。

TASK-18 PASSED：上述实际安装构建 SHA 的 [Push CI](https://github.com/maczhouyi-del/RAGSystem/actions/runs/38052578129)、[PR CI](https://github.com/maczhouyi-del/RAGSystem/actions/runs/38052582203)、[Push Desktop](https://github.com/maczhouyi-del/RAGSystem/actions/runs/38052578187)、[PR Desktop](https://github.com/maczhouyi-del/RAGSystem/actions/runs/38052582202) 全部 SUCCESS，14/14 适用 job 成功。

- 后端982测试（705 unit、277真实PostgreSQL）、124 Playwright、19 transport，零失败/跳过；Ruff、mypy、前端构建、Rust fmt/check/test/clippy通过。
- 真实 Docker 工程：空数据库迁移、API/Redis/三个worker/Web启动、私密配置保存、桌面和Web独立配对、真实Docling Native两页PDF导入/index/字节身份、MOCK RAG/Research、四类报告导出。
- 故障和数据：缺Docker、占用端口、DB/worker失败恢复、备份时停写、停止/重启后的配置与历史保留、独立空项目还原、升级迁移、卸载/重装保留全部五个卷；不静默删除论文/索引/会话/配置。
- 原生CI：Windows x64 MSI/NSIS、Credential Manager；macOS ARM64/Intel分别原生DMG和Keychain；Linux x64 deb/AppImage及实际GUI/loopback。四平台助手和桌面二进制实际运行身份检查，不以交叉编译推断CPU。
- 安装生命周期验证使用 **MOCK 聊天/Embedding/reranker**，PDF解析器是真实Docling Native。没有实际付费模型调用，不衡量真实科研质量。

TASK-19 工程 **PASSED**：实现 e18ffc1 的四个标准工作流14 job与两项独立产物验证作业均SUCCESS，16/16；[完整证据](task-19-evidence.json)。人工/科研部分保持如下状态，不混入自动化工程结论。

| 项目 | 实际状态 |
| --- | --- |
| 真实Windows11用户手动安装 | NOT EXECUTED |
| 真实macOS ARM64/Intel用户手动安装及Docker后端 | NOT EXECUTED |
| Linux用户手动安装/Secret Service完整使用 | NOT EXECUTED |
| Windows ARM64、Linux ARM64、非Ubuntu24.04发行版 | NOT EXECUTED |
| 扫描件OCR/复杂表格公式/真实Embedding和重排推理 | NOT EXECUTED |
| 真实论文事实、数值、检索质量、人工评审、RAG与Research对照 | NOT MEASURED / NOT EXECUTED |

测试版未签名/notarize；macOS Gatekeeper、Windows SmartScreen、WebView2及Linux FUSE/Keyring限制见安装指南。升级助手不做数据库大版本自动升级。已有排队任务会在worker启动后继续，用户模型费用须自行管理。
API密钥只从私密运行时文件注入；报告、备份、安装产物不包含API密钥。备份仍含论文/配置/历史，应私密保存；还原拒绝覆盖已有项目数据卷。卸载程序与删除用户数据是两回事，助手只移除容器，默认保留数据。

TASK-17及TASK-19科研部分资源BLOCKED。交付后暂停，等待用户用自己的论文和获准API本地测试；不会自动开展真实科研评测，也不宣称Research优于RAG。不合并main、不发布正式Release。
