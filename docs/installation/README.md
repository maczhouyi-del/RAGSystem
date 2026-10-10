# 本地测试版安装与使用

这套交付由**桌面安装包 + 对应平台的部署 ZIP**组成。桌面安装包本身只有客户端。
必须安装 Docker Desktop（Windows/macOS），或 Docker Engine + Compose v2（Linux），
并由部署助手启动 PostgreSQL/pgvector、Redis、API、三个 worker 和 Web。
不需要在个人电脑安装 Python、Node.js 或 Rust，也不宣称完全免依赖或离线一键安装。

版本：0.2.0 测试构建；具体构建 SHA、SHA256、实际 CI 与 Artifact 链接见
[交付验证记录](../product-improvement/task-18-delivery.md)。同一套客户端和部署 ZIP 应来自同一个 Artifact。
测试版未代码签名/notarization。不要自动忽略来源不明的系统安全提示。
GitHub Actions Artifact 下载通常需要登录 GitHub，保留期有限；这是 CI 测试交付，不是正式 Release。

建议 16GB 内存、至少 20GB 可用磁盘（模型/论文另需空间）。首次构建需要互联网，
下载容器和依赖通常需 10–30 分钟，实际取决于网络/CPU；启动时不调用付费模型。
默认 API 与 Web 仅绑定本机 8000/8080；数据库/Redis 没有发布主机端口。
不要把这些端口转发到公网。

## Windows 11（优先）

1. 从对应 GitHub Actions Artifact 下载并解压。核对 SHA256（PowerShell：`Get-FileHash 文件路径 -Algorithm SHA256`），与交付记录/manifest 一致。
2. 按 Docker 官方 [Windows 安装指南](https://docs.docker.com/desktop/setup/install/windows-install/) 安装 Docker Desktop，按官方引导启用 WSL2/虚拟化并完成要求的重启。注意 Docker Desktop 许可证/订阅条款。启动 Docker Desktop，确认 Linux containers 可用。
3. 双击 `.msi` 或 NSIS `.exe` 安装 Scientific RAGAgent。二者选一个即可。测试构建未签名，确认 GitHub 仓库、构建 SHA 和校验值后按系统/组织策略处理提示。WebView2 Runtime 若缺失，按安装器/Microsoft 官方引导安装。
4. 把 `RAGSystem-deployment-windows-x86_64.zip` 中的 `RAGSystem` 文件夹解压到长期保留、当前用户可写的位置，例如 `C:\Users\你的用户名\RAGSystem`。不要放在 Program Files 或临时下载缓存中。不要遗漏隐藏的 `.env.example`。
5. 启动桌面程序，打开 **Connection authorization / 本机授权**，复制显示的 SHA256 配对哈希。它不是 API 密钥，实际 bearer 只保存在 Windows Credential Manager。
6. 双击该文件夹的 `RAGSystem-Setup.exe`，选择 **2 配对并启动**，粘贴哈希。助手检查 Docker/Compose、端口、空间，构建锁定依赖镜像，启动 DB/Redis，执行 Alembic 初始化，再启动 API、三个 worker 与 Web。等待 PASS，不要关闭启动中的控制台。
7. 回到桌面首次使用引导，打开 Settings 的诊断，确认 DB/Redis 与三个 worker 可用；再按下面的使用流程配置模型。

以后只需启动 Docker Desktop，打开部署助手选择 **3 启动**，再打开桌面程序。
关闭桌面窗口不会自动停止后端；选择 **4 停止**可以停止后台服务，数据保留。
电脑重启后先等待 Docker，再选择启动。助手固定使用 `scientific-ragagent` 项目，避免无意换一套数据卷。

## macOS（Apple Silicon 与 Intel）

分别使用 `macos-aarch64` 和 `macos-x86_64` Artifact，不能互换或以交叉编译推断兼容。
按 [Docker 官方 macOS 指南](https://docs.docker.com/desktop/setup/install/mac-install/) 安装对应 CPU 的 Docker Desktop。
打开对应 `.dmg`，把应用拖到 Applications。部署 ZIP 解压到长期可写用户目录。
在 Terminal 进入该目录，运行 `./RAGSystem-Setup`，按同样的配对/启动菜单操作；这不需要开发工具链。
若下载解压工具未保留可执行权限，可对助手执行一次 `chmod +x RAGSystem-Setup`。

CI 构建为 unsigned、未 notarize；Gatekeeper 可能拦截应用或助手。只对已核对来源与校验值的产物，
按 macOS Privacy & Security / Open Anyway 和组织政策处理。不要关闭 Gatekeeper 或删除整个系统的安全限制。
配对凭据使用 macOS Keychain；被拒绝时解锁/允许本应用访问，不把 bearer 复制到配置文件。
实际 CI runner 架构与测试结果见验证记录；真实 macOS 人工安装为 NOT EXECUTED，Docker 后端在该平台的人工验证也为 NOT EXECUTED。

## Linux 与 Web

Linux x86_64 桌面包面向 Ubuntu 24.04：选择 `.deb` 使用系统软件安装器安装，或运行 `.AppImage`。
AppImage 可能需要发行版 FUSE2 兼容组件；Debian 包依赖 WebKitGTK4.1/GTK 等系统库。
桌面配对需要用户会话的 Secret Service（例如 GNOME Keyring）和 D-Bus，须解锁密钥环；
没有密钥环时会明确拒绝授权，不能使用明文 bearer 作为自动降级。

按 [Docker Engine](https://docs.docker.com/engine/install/) 安装 Engine + Compose plugin ≥2.24，
当前用户需能访问 Docker daemon（该权限具有很高系统权限，遵循系统管理员策略）。
解压 Linux 部署 ZIP，Terminal 中运行 `./RAGSystem-Setup`，按同样菜单操作。
原生助手在 Ubuntu24.04 构建，更老 glibc/其他发行版、Linux ARM64 **NOT EXECUTED**。
Web 用户在部署助手选择 **9 Web配对**：用密码管理器生成43–128字符的随机凭据（仅A–Z/a–z/0–9/下划线/短横线），隐藏输入并保存在自己的密码管理器；助手只保存SHA256，不保存或回显bearer，也不修改已有桌面配对。
启动后浏览器访问 `http://127.0.0.1:8080`，本机授权中输入此Web凭据。
浏览器授权保存在HttpOnly/SameSite=strict会话，后端重启/退出/过期后需重新授权；不要把凭据写入报告、命令行参数或前端持久化存储。

## 首次配置和使用

1. 部署助手选择 **5 API密钥**，输入对应运行时变量名（例如 `OPENAI_API_KEY`），隐藏输入密钥。密钥只保存到 `.runtime-secrets.env`，Windows 仅当前用户 ACL，Unix0600。不要截图、发送、加入 Git、日志或备份。旧版在 `.env` 配置的 runtime key 继续兼容，不会自动迁移或删除。
2. 再选择 **3 启动**以更新容器运行时环境。在桌面 Settings 配置各角色的 provider/model 与 `api_key_env`，例如 OpenAI / 模型名 / `OPENAI_API_KEY`。配置只记录环境变量名。四个聊天角色都需要获准使用的模型和密钥；可选连接测试/问答/Research 可能收费，由用户自行发起。
3. 默认本地 embedding 与 reranker 首次使用会下载各自模型权重，需要互联网/空间；依照已有许可证说明。配置存在、服务 ready 不代表模型加载/调用成功。也可按现有 Settings/部署文档配置获准的 hosted embedding；维度/模型身份需与索引一致，不能静默混用旧向量。
4. 新助手生成环境默认 `PDF_PARSER_MODE=native`，使用 Docling 的文本型 PDF 无权重解析。扫描件/OCR、复杂表格/公式结构应切换 `layout` 并重启，再自行确认模型下载和解析结果。旧部署未设置该字段仍保留原 layout 默认。native 模式不宣称扫描件或复杂版面准确率。
5. 打开 Knowledge Base，选择 PDF，可多选。观察上传与解析/Embedding/索引分别显示的状态；必须 indexed 后才可检索。失败用现有重试功能，不重复点击或删除数据卷“修复”。
6. 进入 RAG，选择论文/分组/标签范围后提问。Research 提供 Multi-Agent 研究入口；查看证据引用、定位和 Reviewer 结果。未报告或证据不足应保持对应状态，不把模型输出当作原文事实。
7. 在结果中查看“模型、用量与耗时”，缺失用量/账单显示 Unknown；SDK 估算不是服务商账单。在导出入口保存 Markdown/CSV/BibTeX/引用清单。
8. 退出桌面再打开、停止服务再启动后，已导入论文/索引、会话与配置保留。实际科研效果需用户以自己的论文逐例核查，目前 NOT MEASURED。

[数据、备份、升级与卸载](data-and-upgrades.md) · [安装故障排查](troubleshooting.md) · [交付后本地真实评测](local-evaluation.md)
