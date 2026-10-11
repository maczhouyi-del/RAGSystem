# 安装与首次配置审计（2026-10-11）

审计基线：main `48088d2d5d28e87c390e69480d6f3cf09dbbe4de`。只读核查实际实现、Compose、权限、测试和已发布v0.2.0-beta.1；本审计不是Windows11人工安装结果。

## 当前真实流程与痛点

1. 客户端MSI/EXE不包含API/数据库；另下载同平台部署ZIP、安装Docker、解压到用户目录。README已说明，但普通用户容易把安装客户端理解成系统已就绪。
2. `RAGSystem-Setup`是PyInstaller原生命令行助手。`scripts/local_deploy.py`隐藏输出、初始化随机DB密码、只写SHA256配对哈希、私密runtime文件、启动迁移/API/三个worker/Web，检查真实ready，保留五个数据卷；不能用新UI绕过这些保护。
3. 桌面`AuthPanel.tsx`显示OS凭据库产生的哈希，用户复制到助手菜单2，再重启并回桌面连接。没有复制按钮，也没有明确连续步骤；已有安装虽不覆盖env，但用户难以判断可跳过哪些步骤。
4. 助手检查Docker/Compose版本、Linux容器、磁盘至少5GiB及8000/8080端口；没有WSL2细分。多数英文固定错误提示，`disk_space_low`等缺少专用恢复说明。CLI子进程尚无超时；普通用户可能把等待当作卡死。
5. API密钥在助手菜单5通过getpass写`.runtime-secrets.env`并限制ACL/权限；需再次启动重建容器才能被API/worker读取。Settings不接收密钥。必须保留此边界，不能把密钥放React/localStorage/角色YAML。
6. `Settings.tsx`逐角色配置provider/model/api_base/api_key_env，没有普通用户的单模型默认映射；现有`/api/providers/test`实际调用LLM，按钮写“可能收费”但没有二次确认。密钥存在不是有效，infra ready不是推理成功。
7. `FirstUseGuide.tsx`已能只读探测授权/diagnostics、自动识别空知识库、关闭偏好恢复、上传/索引/问答入口。它仍以技术架构术语展示一长列，没有集中下一步和可恢复的部署步骤。
8. 默认embedding/reranker为本地模型，首次导入会下载权重；安装基础服务正常不能证明模型加载、索引或科研质量正常。

涉及文件：`scripts/local_deploy.py`、`scripts/package_deployment.py`、`.github/workflows/desktop.yml`、`compose.yaml`、`docker/backend.Dockerfile`、`frontend/src/{FirstUseGuide,AuthPanel,Settings,main,transport}.tsx/ts`、`frontend/src-tauri/src/bridge.rs`、`frontend/src-tauri/capabilities/main.json`、`src/ragagent/api/{providers,schemas,diagnostics}.py`、`src/ragagent/providers/{config,chat,environment}.py`及现有unit/Playwright/Docker安装测试。

## 安全边界与方案选择

比较桌面启动外部程序/通用shell、部署助手本机HTTP服务、原生图形助手三种增量方案。前两种分别扩大IPC文件/执行边界或引入新监听端口及CSRF/凭据通道；此次选择Windows原生Tk图形助手，复用同一Deployment对象，不增加HTTP服务、不开放通用shell、不新增桌面IPC command/权限。Tk是Python标准库界面，随Windows原生助手打包，用户不需安装Python。

- 双击Windows助手默认图形向导；现有CLI action和`--console`兼容。macOS/Linux默认CLI保留，未验证GUI不宣称支持。
- 图形助手只提供检查、明确确认的配对/启动、隐藏输入保存key、启动后检查及停止；备份/升级/恢复/保留数据卸载继续使用成熟独立助手，文档明确入口。后台执行、固定进度消息、并发互斥、失败可重试；已有env/runtime不覆盖。
- 对Docker缺失/停止、Windows WSL未就绪、Compose旧、低磁盘、端口占用、后端未就绪给出中文原因及恢复步骤。WSL只在Windows且Docker不可用时细分，不能把可用Hyper-V部署误判为必须WSL。
- 桌面复用FirstUseGuide/AuthPanel，新增选择provider和单模型的快捷映射，保存仍走受保护的`PUT /api/providers`。高级逐角色Settings保留；已有映射仅预填，必须显式确认才覆盖。
- 所有key仅在原生助手短暂内存/私有runtime保存；前端不接收key。连接检查和推理检查拆分状态，通过现有受保护`/api/providers/test`的可选检查类型实现，旧调用默认推理保持兼容。无需新增IPC route或权限；每次外部测试明确确认费用/发送内容，不自动调用。
- 连接检查只做服务目录请求，不据此宣称可推理；失败仅静态错误码，不返回SDK响应/密钥。推理仍复用现有Provider实现，不改RAG/Research/Evidence/数据库逻辑。

## 阶段与验收

1. 本审计/方案独立提交。用户后续要求不新建分支，已将全部工作迁回现有`codex/research-product-improvement`并删除本次临时分支。
2. P0部署：Windows图形助手、中文诊断/恢复、只读已有配置识别、安全重试；离线保护测试和实际原生GUI冒烟。
3. P0模型/P1使用：快捷映射、四种状态、主动测试确认、统一步骤/下一步、复制配对哈希；后端和Playwright故障/授权/不主动收费验证。
4. 工程回归：Ruff/mypy/全部后端（真实PG）、前端check/build/Playwright/transport、Rust原生构建和Windows/macOS/Linux实际CI、原有Docker MOCK安装生命周期及新增配置持久化验证。失败保留，不用Mock冒充真实模型。
5. 文档/PR/Windows11检查表交付，记录实际CI/artifact来源。Windows11人工安装、真实key/模型/权重下载/科研效果保持NOT EXECUTED/NOT MEASURED，等待用户执行。

风险：Tk原生打包/Windows ACL需真实CI验证；Docker安装、管理员/WSL重启、网络代理/权重访问和未签名系统提示仍由用户处理；一次配对哈希复制保留，优先保持最小权限；升级不改卷/迁移，不静默重置角色配置/密钥。
