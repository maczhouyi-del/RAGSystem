# 安装与首次配置工程交付（2026-10-11）

工程状态 **PASSED**；PR [#3](https://github.com/maczhouyi-del/RAGSystem/pull/3)，复用现有 `codex/research-product-improvement`。
已验收实现/以下产物源码 SHA：`479872cec0742aefbf9d3922954854dc49d07233`；应用版本 **0.2.0**。
本记录随后仅补文档/许可，不把文档提交的 SHA 当成下表二进制来源。已发布 beta1 不包含新图形助手。

## 已完成的体验改进

- Windows 双击原生五步向导：条件检查、配对、遮蔽密钥、启动迁移/全后台、开始使用；既有配置识别、错误说明与安全重试。
- 服务商/单模型确认生成四角色默认映射，保留高级设置；配置保存、密钥存在、目录连接和实际推理分开显示。
- 快捷及高级模型测试都需明确确认，目录请求也提示可能费用；不在载入/保存/刷新时测试，不把密钥送前端。
- 桌面步骤进度/下一步、配对哈希复制 fallback、首篇 PDF/索引/问答入口；保留 Diagnostics、Knowledge Base、CLI 与 Web。

## 实际工程验证

| 工作流 | 适用 job | 结果 |
| --- | --- | --- |
| [push CI](https://github.com/maczhouyi-del/RAGSystem/actions/runs/38150671378) | 3 | SUCCESS |
| [pull_request CI](https://github.com/maczhouyi-del/RAGSystem/actions/runs/38150674289) | 3 | SUCCESS |
| [push Desktop](https://github.com/maczhouyi-del/RAGSystem/actions/runs/38150671420) | 4 | SUCCESS |
| [pull_request Desktop](https://github.com/maczhouyi-del/RAGSystem/actions/runs/38150674286) | 4 | SUCCESS |

全部14 job通过。实际日志核查：1010后端（真实PG/Redis，0失败/跳过）、131浏览器MOCK、19transport；
Windows/macOS两架构各19 Rust、Linux18 Rust；原生凭据库、fmt/check/clippy、实际安装器/原生助手/CPU版本身份通过。
Windows打包Tk实际五页/遮蔽输入/忙碌/错误/安全重试通过，是自动化runner验证。
真实Docker执行：数据库迁移、三个worker、Native PDF解析/索引、四角色保存和私有密钥存在、
**MOCK** RAG/Research及四导出、DB/worker故障恢复、备份/重启/历史配置持久化、卸载/重装保留五卷。

历史失败保留：780974b Push/PR 与69d1d8d Push 的 Windows GUI 断言实际失败，但 PowerShell 后续成功命令掩盖退出码，
作业汇总错误地为SUCCESS。这些GUI结果不被认定为通过；修正控件类型识别并逐条传播退出码后，479872c实际GUI日志PASS。
本地初次浏览器目录配置错误及可访问名称失败也保留，修复后重跑通过，未删除断言。

## 下载已验收构建

Artifact需登录GitHub，保留期限见[JSON证据](first-use-evidence.json)。每个Artifact包含同构建客户端、部署ZIP、manifest和ZIP校验文件。
请使用本表同一来源，不能拿原beta或此前817构建哈希验证新文件。

| 平台 | 下载 | 自动原生结果 | 人工安装 |
| --- | --- | --- | --- |
| linux-x86_64 | [Artifact 11706935126](https://github.com/maczhouyi-del/RAGSystem/actions/runs/38150671420/artifacts/11706935126) | PASS | NOT EXECUTED |
| macos-x86_64 | [Artifact 11706678795](https://github.com/maczhouyi-del/RAGSystem/actions/runs/38150671420/artifacts/11706678795) | PASS | NOT EXECUTED |
| macos-aarch64 | [Artifact 11706274691](https://github.com/maczhouyi-del/RAGSystem/actions/runs/38150671420/artifacts/11706274691) | PASS | NOT EXECUTED |
| windows-x86_64 | [Artifact 11706219974](https://github.com/maczhouyi-del/RAGSystem/actions/runs/38150671420/artifacts/11706219974) | PASS | NOT EXECUTED |

以下 SHA256 来自实际成功的生产CI构建/文件哈希步骤；未声称云环境重新下载独立复核或跨OS执行安装器。

| 平台 / 文件 | 字节 | SHA256 |
| --- | --- | --- |
| windows-x86_64 / `msi\Scientific RAGAgent_0.2.0_x64_en-US.msi` | 3411968 | `9499706b137678d27595f9780f4e3ff8cf547deaa1db6e9ac47940d53b7308cb` |
| windows-x86_64 / `nsis\Scientific RAGAgent_0.2.0_x64-setup.exe` | 2372723 | `62912bc99baf939284b2ccb6d3a986dd3ed0af33dc1da723cd9c6a846b8b8fe5` |
| windows-x86_64 / `RAGSystem-deployment-windows-x86_64.zip` | 12629553 | `4d3cd2dd17b8f9fd9e79f7ae74b326eefdcb665e6f814e659d091448a7e77fcd` |
| linux-x86_64 / `RAGSystem-deployment-linux-x86_64.zip` | 25594741 | `784a85a826b9f9e9462ca25666c979a3550343ab7cd1ce0a2fa110ede7239e07` |
| linux-x86_64 / `appimage/Scientific RAGAgent_0.2.0_amd64.AppImage` | 81742328 | `2aa7cf81a33e05685c5159bb56ff1ab860b558d56902cb561381d8af73b5bed9` |
| linux-x86_64 / `deb/Scientific RAGAgent_0.2.0_amd64.deb` | 3039344 | `b196795b33d9aa6a55f3662805d0310b9ab9a1adf6aa51f8e3ad3831b3960bae` |
| macos-x86_64 / `RAGSystem-deployment-macos-x86_64.zip` | 11792365 | `19b5247310597fcb6c9679cc387ec623250ad9bd72b86ea7e391c36529cbecac` |
| macos-x86_64 / `dmg/Scientific RAGAgent_0.2.0_x64.dmg` | 2863404 | `dd6ab28fef1ee6a7bbf33b18261c26d5db855aceab73ccfb0ed715f0a72256ad` |
| macos-aarch64 / `RAGSystem-deployment-macos-aarch64.zip` | 11131373 | `ded7a12f2898d71fed64f4cba61bbb6f63b83bb7782c1a0d8d1abe9f23718158` |
| macos-aarch64 / `dmg/Scientific RAGAgent_0.2.0_aarch64.dmg` | 2692721 | `5e09f97c32bf43b937297128991ba60219c0cad66eb415ba9df30aacb7bd2bfd` |

## 尚未人工验证与用户步骤

Windows11实际MSI/EXE安装、Docker/WSL重启、系统提示、中文路径/DPI、真实用户升级/卸载；
macOS/Linux人工安装、本地Ollama加载、真实密钥/模型推理与实际权重网络下载均 **NOT EXECUTED**。
[Windows11检查表](windows-11-checklist.md)逐场景填写；科研事实/数值/证据/检索/对照评测 **NOT MEASURED**。

用户仍需下载安装Docker并完成官方前置条件，核对并解压客户端/部署ZIP，复制一次配对哈希，在原生窗口输入密钥，
选择账户可用模型并自行确认付费测试。备份/升级/空环境恢复/保留数据卸载仍从 `--console` 菜单操作，
无需手改env/Agent YAML或执行Python/Node/Rust/Compose开发命令。

## 已知限制与后续

未签名/未notarize；Docker和网络仍必需，助手不自动安装Docker或强杀冲突程序；磁盘探针只覆盖部署盘，Docker虚拟盘需另查。
独立助手与桌面仍是两个窗口，保留一次配对复制以维持最小IPC权限；Windows使用console打包保留CLI兼容。
macOS/Linux继续原生控制台助手，新模型/步骤UI兼容Web。Ollama需额外模型/宿主路由配置，扫描PDF/OCR可能另需下载。
升级不覆盖私有env/角色或删除卷；密钥不包含在备份。请按[完整指南](first-use-guide.md)、
[备份/升级/卸载](data-and-upgrades.md)及[故障排查](troubleshooting.md)操作。
建议先完成Windows11人工清单，再反馈安装体验；真实科研评测复用现有TASK-03工具，用户认可论文/模型/预算后自行开展。
此任务交付PR/CI测试产物，不新建分支，不自动合并main/发布新Release或运行付费科研评测。
