# 安装故障排查

部署助手只输出固定安全代码，不回显 Docker 日志、环境变量或 provider 异常。
不要把 `docker compose config`、完整环境、Docker日志、API密钥或私有配置文件上传到公开 issue。
报告可提供版本、构建SHA、代码、服务状态和脱敏后的现象。

| 现象/代码 | 处理 |
| --- | --- |
| docker_missing | 安装 Docker Desktop 或 Engine + Compose plugin，重新打开助手。 |
| docker_not_running | 打开 Docker 并等待 Ready；Windows使用 Linux containers，按官方指导检查WSL/虚拟化。 |
| wsl_not_ready | Docker 不可用且 WSL 状态失败：按 Docker 官方指引启用虚拟化/WSL2并重启，然后重新检查；已可用的 Hyper-V/Linux Docker 不要求切换。 |
| docker_linux_containers_required | Docker 已运行但在 Windows containers 模式：在 Docker Desktop 切换到 Linux containers，重新检查。 |
| compose_too_old | 更新 Compose至≥2.24，旧版本不支持可选runtime env_file。 |
| pairing_required | 从该桌面客户端授权面板复制64位小写SHA256哈希，选择配对启动；不能填API密钥或bearer。 |
| port_conflict | 确认8000/8080被哪个程序占用，关闭自己确认的冲突服务后重试。助手不会杀进程/连接陌生API。桌面固定端口，不自动换端口。 |
| disk_space_low | 至少空出5GiB，建议20GiB以上并为模型/论文额外留空间，检查Docker虚拟磁盘。不能通过删除数据卷腾空间。 |
| deployment_failed | 在Docker Desktop检查db/redis/migrate/api/三worker服务状态；检查镜像拉取/锁定依赖下载网络。失败不删卷，再选择Start；DB迁移失败保留备份联系维护。 |
| not_ready | DB/Redis/三个worker需都运行和注册。Check不是模型推理验证。停止失败组件后由助手Start恢复，不重置数据库。 |
| active_jobs | 等待队列/运行任务完成；现有Run失败/取消状态按UI处理，再备份升级。 |
| backup_failed / backup_invalid | 不继续升级/恢复；保留原数据。检查路径/权限/空间及完整manifest的三个文件校验。 |
| restore_requires_empty | 只在新环境恢复，不能覆盖已有五类卷。不要为绕过检查删除原数据。 |
| secret_permissions | 确保部署目录当前用户可写、非共享/FAT文件系统、非symlink；遵循Windows ACL/Unix权限策略。 |
| configuration_invalid / gui_unavailable | 输入不得含换行，配对需正确哈希；图形不可用时用 --console，原数据保留。 |
| 桌面无法授权 | Windows Credential Manager/macOS Keychain/Linux Secret Service需可用。解锁用户密钥库，不用明文bearer自动降级。 |
| provider_key_missing / provider错误 | 在助手隐藏输入该provider的运行时密钥，Start更新容器；Settings选择正确provider/model/api_key_env。连接测试可能收费，不自动重试消费。 |
| provider_credential_rejected | 密钥被拒绝，不等于配置未保存。原生助手替换密钥、启动使容器读入，再刷新状态；测试须重新主动确认。 |
| provider_network_failed / provider_connection_failed | 检查服务地址、网络/组织代理及服务状态；不关闭 TLS 校验、不回显完整异常、不自动收费重试。 |
| provider_catalog_unavailable / provider_catalog_invalid | 兼容服务目录接口不支持或格式不同。连接检查不能证明推理；可主动确认单独推理测试，不能据目录结果宣称科研可用。 |
| provider_rate_limited | 按账户限流/预算恢复后主动重试，不自动重复消费。 |
| PDF解析失败 | native适用于文本PDF，扫描件需layout/OCR及其模型；检查是否加密/损坏/超过上传限制，保留源PDF，按UI安全重试。 |
| Embedding加载失败 | 检查获准的模型来源网络/空间，或按现有设置配置hosted embedding；不得随意改变维度并混用旧索引。 |
| 首次构建代理/TLS失败 | 按Docker组织代理配置设置可信CA，维护人员可用compose.cloud.yaml；不能关闭TLS校验。普通用户无需该云环境overlay。 |

桌面窗口关闭后后端继续运行，这是独立本地服务。需要暂停用助手Stop；数据仍在Docker。
CI原生构建成功不等于Windows11/macOS人工安装通过；科研答案质量仍需本地逐例人工评审。

模型四种状态独立：保存配置、密钥存在、目录连接成功、固定指令推理通过。
前三种不证明模型可实际推理，第四种也不是科研质量验收。默认本地 embedding/reranker 下载失败时，
检查获准来源、Docker 虚拟磁盘、网络和缓存权限；修复后按 UI 重试原导入，不清空数据库/模型卷。
Ollama 需另行安装与加载模型，容器 localhost 不是宿主；Docker Desktop 可使用 host.docker.internal，
Linux 宿主路由需单独配置，不开放模型/数据库到公网。
