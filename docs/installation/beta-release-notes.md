# Scientific RAGAgent 0.2.0 Beta 1

测试版 / Pre-release。应用内部版本0.2.0；这是工程测试交付，真实科研质量 **NOT MEASURED**。

## 下载与安装

Windows11 x64：下载 MSI 或 EXE（二选一）以及 `RAGSystem-deployment-windows-x86_64.zip`。
macOS：按CPU选择aarch64（Apple Silicon）或x64（Intel）DMG与对应部署ZIP。
Linux x64（Ubuntu24.04）：选择deb或AppImage与Linux部署ZIP。

**桌面安装包是客户端，必须配合对应部署ZIP，并安装Docker。** Windows/macOS使用Docker Desktop；Linux使用Docker Engine + Compose ≥2.24。
不需要主机Python、Node.js、Rust或Git；首次后端构建需要互联网。建议16GB内存、20GB以上可用磁盘，模型/论文另需空间。

核对 `SHA256SUMS.txt`；`release-manifest.json`列出实际构建SHA、平台、版本、各安装器与部署ZIP的校验值。
Release文件名把空格改为下划线，文件字节不变；各ZIP中的原始manifest仍可独立核验。
`installation-guides.zip`包含中英文README及完整安装、数据管理、故障排查和本地评测说明。

[完整安装/首次配置指南](https://github.com/maczhouyi-del/RAGSystem/blob/main/docs/installation/README.md) ·
[备份/升级/还原/卸载](https://github.com/maczhouyi-del/RAGSystem/blob/main/docs/installation/data-and-upgrades.md) ·
[故障排查](https://github.com/maczhouyi-del/RAGSystem/blob/main/docs/installation/troubleshooting.md)

安装客户端，部署ZIP解压到长期保留的用户可写目录；打开桌面“本机授权”复制配对哈希；
运行RAGSystem-Setup，选择2配对并启动，等待数据库迁移、API、Redis、三个worker和Web检查成功。
通过助手隐藏输入保存API密钥，在Settings配置各角色模型，导入PDF并等待indexed后进行RAG/Research问答或导出报告。
使用自己的模型API可能收费，真实评测由用户自行发起；本轮发布不自动调用真实模型。

## 工程证据

发布流程要求同一 main SHA 的Push CI（backend/frontend/Compose）与四个平台原生Desktop job全部SUCCESS。
随后独立下载实际安装产物，核对全部安装器/部署ZIP/ZIP成员的SHA256、平台、版本和构建SHA，
上传后还核对GitHub服务端digest与文件大小，成功后才将草稿转为公开Pre-release。
构建workflow与源SHA追加在本说明末尾，服务器/用户机器不同环境不混用结果。

现有工程回归覆盖982backend（含277真实PostgreSQL）、124Playwright、19transport、Rust fmt/check/test/clippy与原生凭据库。
完整Docker工程覆盖全新部署、真实Docling Native PDF解析/index、MOCK RAG/Research与四类导出、
DB/worker失败恢复、重启持久化、停写备份、空项目还原和卸载/重装保留全部五个数据卷。
历史失败及修正保留于[工程证据](https://github.com/maczhouyi-del/RAGSystem/blob/main/docs/product-improvement/task-19-evidence.json)，不声称失败attempt本身通过。

## 已知限制与数据保护

- 未代码签名、未macOS notarize。按系统/组织策略处理安全提示，不关闭全局安全保护。
- Windows11、macOS双架构、Linux用户人工安装均 **NOT EXECUTED**；原生CI成功不等于人工安装通过。
- Windows/Linux ARM64、其他Linux发行版以及macOS上的Docker后端人工验证 **NOT EXECUTED**。
- 安装工程使用 **MOCK模型**、真实Docling Native文本PDF；真实聊天/embedding/reranker、OCR/复杂版面和科研质量没有因此得到验证。
- TASK-17与TASK-19科研部分 **BLOCKED / NOT MEASURED / NOT EXECUTED**。不宣称Research优于RAG。
- API密钥只保存到私密运行时文件，配对凭据使用OS密钥库；不要加入日志、报告或备份。
- 关闭桌面不会自动停后端；用助手停止。卸载只移除程序/容器，保留数据库、论文、索引、历史、配置与模型卷。
- 升级先备份，不覆盖私有runtime文件；只支持PostgreSQL17内升级，不自动迁移数据库主版本。
- 启动worker可能继续用户已有排队任务并产生此前授权的模型费用。

发布后等待用户本地测试反馈，不自动进行真实科研评测。
