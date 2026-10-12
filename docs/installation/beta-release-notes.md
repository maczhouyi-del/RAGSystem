# Scientific RAGAgent 0.2.0 Beta 2

测试版 / Pre-release，应用内部版本 **0.2.0**。新版提供 Windows 五步图形部署助手、首次模型配置与连续步骤引导。
旧 beta1 保留，不覆盖旧文件或 tag。真实科研质量 **NOT MEASURED**。

## 安装入口

完整安装指南直接写在本次发布源码的 README：
[简体中文 README](https://github.com/maczhouyi-del/RAGSystem/blob/RELEASE_SOURCE_SHA/README.zh-CN.md#下载安装与首次使用) ·
[English README](https://github.com/maczhouyi-del/RAGSystem/blob/RELEASE_SOURCE_SHA/README.md#download-install-and-first-use)。
Release 附件 `installation-guides.zip` 也包含中英文 README、详细恢复/升级说明、实际证据和第三方许可证。

在 Assets 下载同平台的**桌面安装包 + 部署 ZIP**：Windows11 x64 选 MSI/EXE之一，
macOS 按 Apple Silicon/Intel 选 DMG，Linux x64 选 deb/AppImage。另下载 `SHA256SUMS.txt` 和 `release-manifest.json` 核对。
公开安装包无需 Actions Artifact 登录。文件名空格替换为下划线，字节不变。

**Docker 仍必需**：Windows/macOS 需 Docker Desktop，Linux 需 Docker Engine + Compose ≥2.24。
建议16GB内存、20GB以上空闲空间及模型/论文额外空间，首次构建需互联网。
无需主机Python、Node.js、Rust、Git，无需手改env/Compose/Agent YAML。

Windows：安装客户端、解压部署ZIP到个人长期可写目录，双击RAGSystem-Setup.exe，
跟随检查→复制桌面配对哈希→原生遮蔽输入密钥→确认启动/恢复→回桌面模型配置五步。
Settings确认一次服务商/聊天模型即可生成四角色默认映射，高级逐角色配置保留。
配置保存、密钥存在、目录连接与固定指令推理四种状态分开；连接/推理都必须主动确认，可能产生费用。
随后导入第一篇PDF，等indexed，选择RAG/Research提问并检查引用、按需导出。
macOS/Linux保留原生控制台助手，Web保持独立配对路径；备份/升级/保留数据卸载可用 --console。

## 工程证据与发布核验

本次发布针对所选可信仓库分支的同一完整SHA，要求Push CI三个job及Desktop四个原生job实际成功。
发布作业再次从GitHubActions下载四平台真实安装产物，独立重算六安装器、四部署ZIP及所有成员的SHA256，
核对版本、平台、源码SHA，检查没有用户env/密钥/测试文件；上传后核查全部GitHub服务端digest和大小，才公开Pre-release。
PR CI/Desktop结果和发布结果分别记录，不能用工程MOCK推断科研性能。

已完成的改造实现验证：1010后端（含真实PostgreSQL/Redis）、131Playwright MOCK、19transport；
Windows/macOS双架构各19 Rust、Linux18 Rust，fmt/check/clippy、原生凭据库、实际安装器与助手CPU/版本检查。
Windows打包Tk五页、遮蔽输入、忙碌/错误/重试冒烟通过；完整Docker覆盖真实Native PDF解析/索引、
四角色配置/私有密钥存在、MOCK RAG/Research/四导出、DB/worker恢复、备份、重启持久化、迁移和卸载重装保留五卷。
原780/69构建的Windows GUI断言失败曾被PowerShell后续命令掩盖为绿灯，原日志保留；修正控件计数与逐命令退出码后才通过。
[原安装体验验收及失败证据](https://github.com/maczhouyi-del/RAGSystem/blob/RELEASE_SOURCE_SHA/docs/installation/first-use-evidence.json)。
本次实际发布源码及Desktop运行追加在本说明末尾；release-manifest和SHA256SUMS是本次包的校验依据。

## 限制与数据安全

- 未签名/未macOS notarize，遵守系统/组织安全策略，不关闭全局保护。
- Windows11/macOS/Linux人工安装、真实用户模型/密钥/权重下载 **NOT EXECUTED**；自动化runner不替代人工安装。
- Windows/Linux ARM64、其他Linux发行版、用户Ollama/扫描PDF的OCR/复杂版面未因此验证。
- TASK-17及TASK-19科研质量 **BLOCKED / NOT MEASURED**，不声称Research一定优于RAG。
- API Key只经原生私有runtime/ACL，不进入前端存储/日志/报告/备份；配对凭据在OS密钥库。
- 关闭桌面后台仍运行；助手停止保留数据。卸载程序/容器保留论文/索引/历史/角色/密钥和五卷。
- 升级先备份，保留私有env和项目名，不静默删卷/重置；仅支持既有PostgreSQL17内迁移。
- 启动worker可能继续既有排队任务及用户此前授权的模型费用；本次发布不主动发起收费模型调用。

按README在本地安装后反馈体验；真实科研评测由用户使用自己的论文与获准模型/预算自行开展。
