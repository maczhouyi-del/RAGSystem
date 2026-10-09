# 环境检查与启动诊断

在下载的 RAGSystem 项目目录打开终端。诊断需要 Python 3.11+（项目 `.venv` 也可），
不需要安装项目依赖。Windows 若缺少 Python，脚本会提示安装并返回 2；
安装时选择添加 Python 到 PATH，然后重新打开终端。

Windows PowerShell：

```powershell
powershell -NoProfile -File .\scripts\diagnose.ps1
powershell -NoProfile -File .\scripts\diagnose.ps1 -Json
```

Linux：

```bash
./scripts/diagnose.sh
./scripts/diagnose.sh --json
```

若 Windows 的组织策略禁止脚本执行，遵循组织策略；可直接运行
`python scripts/diagnose.py --json`，无需修改系统执行策略。
非默认端口使用 Windows `-Port 8001 -WebPort 8081` 或 Linux `--port 8001 --web-port 8081`。
只连接本机 127.0.0.1；不会把授权发送到远端或跟随重定向。

## 如何理解报告

- `backend unavailable`：后端没启动、端口不匹配或响应不符合健康接口。
  使用 Docker 时，在项目目录运行 `docker compose up --build`。
- `backend_port occupied`：端口已被占用。后端同时 available 时通常正常；
  不可达时检查 Windows `Get-NetTCPConnection -LocalPort 8000` 或 Linux `ss -ltnp`，
  确认进程后处理冲突。脚本不终止任何进程。
- `database unavailable`：后端可达但数据库不可用。检查 `docker compose ps db` 和连接配置，
  不要删除数据卷。`redis unavailable` 类似地检查 Redis。
- `worker_* unavailable`：对应队列没有已注册 worker。启动建议中指定的服务。
  注册状态不等于真实任务能成功；诊断不执行任务。
- `local_auth not_initialized`：在桌面 Connection authorization 完成本机配对。
- `diagnostic_access unknown`：受保护诊断不可读取，不可推断数据库、worker 或模型正常。
  在已授权的 Settings → Diagnostics 查看，或通过当前进程环境
  `RAGAGENT_DIAGNOSTIC_TOKEN`（也兼容已有 `LOCAL_AUTH_TOKEN`）提供合法本机配对凭据。
  不要把凭据写到命令行参数、报告或聊天记录；脚本不读取 `.env`。
- `models not_configured`：四个聊天角色至少一个配置或运行时凭据缺失。
  在 Settings 配置服务商/模型，按[部署说明](deployment.md)配置运行时密钥。
- `models configured` 与 `inference_supervisor not_tested`：配置存在，但真实调用尚未验证。
  `/api/ready`、Docker 健康状态都不能证明模型推理正常。
- `corpus empty`：当前没有 indexed、有 chunk、未标为撤回/撤稿的论文。上传 PDF，
  等待 ingestion worker 索引完成。这个计数不证明嵌入模型、索引兼容性或科研答案质量。

`infrastructure available` 仅表示 API、授权后的数据库/Redis 与三个队列 worker 注册可用。
Docker 与 Compose 是 Docker 部署的前置条件；本地部署可以没有 Docker。
后端同时检查 Docling 和本地模型 Python 包是否安装；不导入或下载模型，
安装状态不代表模型权重、加载或解析能成功。缺包时按报告重建镜像或安装可选依赖。
磁盘 5 GiB 是提醒阈值，模型下载和论文储存还需要额外空间。
每项检查都有具体建议。退出码：0=基础服务可观察且可用，1=需处理/未知，2=诊断依赖或参数错误。

## 可选的真实模型验证

仅在愿意承担服务商费用时运行 Windows `-TestModel` 或 Linux `--test-model`。
脚本调用已有 `/api/providers/test`，只验证 supervisor 角色的一次小型请求；
`succeeded` 只在该请求实际成功时出现，失败为 `failed`。这不验证其他角色、Embedding、
Reranker、端到端问答或科研质量。默认命令绝不调用此接口。

脚本不修改配置，不安装依赖，不删除/重置数据库，不回显服务响应、Docker 日志或密钥。
测试包含离线独立异常场景，以及 Windows/Linux 启动入口对合成 API 的真实执行；
合成调用测试不能作为真实模型成功的证据。
