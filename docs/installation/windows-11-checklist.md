# Windows 11 x64 首次安装人工验收清单

当前全部人工场景 **NOT EXECUTED**。Windows CI runner 原生打包/凭据库/Tk 冒烟不替代普通用户 Windows 11 安装。
填写操作系统版本、CPU、内存、磁盘、Docker/WSL 版本、构建完整 SHA、Artifact/manifest、日期和操作者。
只记录安全错误码、状态与脱敏现象，不能附 API Key、私有 env 或原始 provider 日志。
按 [首次使用指南](first-use-guide.md) 操作；真实模型请求只在用户认可费用后执行。

| 场景 | 预期与记录项 | 当前人工结果 |
| --- | --- | --- |
| 可信安装包 | 同次成功构建 MSI/EXE + ZIP、SHA256/架构正确，安全提示按政策处理 | NOT EXECUTED |
| 全新安装 | 未安装 Python/Node/Rust，无需编辑 env/Compose/YAML，五步启动成功 | NOT EXECUTED |
| Docker 缺失/停止 | 清楚提示安装/启动，修复后同按钮安全重试 | NOT EXECUTED |
| WSL/容器模式 | WSL 不可用提示官方配置；Windows containers 提示切换；可用 Hyper-V 不误报 | NOT EXECUTED |
| 端口冲突 | 8000/8080 被测试程序占用时阻止启动，不杀进程/连接陌生 API；解除后恢复 | NOT EXECUTED |
| 空间不足 | 低于 5 GiB 提示，不清理数据；另检查 Docker 虚拟磁盘 | NOT EXECUTED |
| 本机认证 | 未授权请求被拒绝；复制哈希/手动 fallback 可配对，凭据保存系统密钥库 | NOT EXECUTED |
| 私有密钥 | 遮蔽输入、保存后清空，日志/前端存储/配置/报告无明文；不自动测试 | NOT EXECUTED |
| 快捷映射 | 选择一个模型，确认后四角色保存；高级逐角色编辑保留 | NOT EXECUTED |
| 四种模型状态 | 保存/密钥存在/连接/实际推理分开；取消测试无外部请求 | NOT EXECUTED |
| 密钥无效/模型不可用 | 安全中文提示，更换后重启/刷新，主动重试；不自动消费 | NOT EXECUTED |
| 网络/目录接口失败 | 下载/服务失败有恢复说明，目录不支持不伪装推理失败/通过 | NOT EXECUTED |
| 数据库/worker 故障 | 显示尚未就绪，修复后启动恢复，不重置库/队列 | NOT EXECUTED |
| 首篇 PDF | 显示解析/索引状态；实际本地权重加载后 indexed、引用可追溯 | NOT EXECUTED |
| RAG/Research/导出 | 用户认可真实费用后两模式运行并导出，不把工程 MOCK 当科研质量 | NOT EXECUTED |
| 关闭/重启/停止 | 关闭客户端后台仍在；停止后正确显示未启动；重新启动历史/PDF/配置保留 | NOT EXECUTED |
| 已有用户升级 | 先备份，保留论文/向量/会话/密钥/自定义角色及项目五卷，不强制初始化 | NOT EXECUTED |
| 卸载/恢复 | 桌面卸载与助手 KEEP DATA 分开，不删除卷；重装后历史可用 | NOT EXECUTED |
| 安全边界 | 仅本机 API/Web、无公网 DB/Redis，IPC 不扩大，备份/报告无密钥 | NOT EXECUTED |

首次全新场景可使用单独 Windows 用户/虚拟机。异常验证仅操作明确属于验收的测试服务和测试资料；
不能为制造“全新”删除已有数据卷。备份/恢复仅在独立空项目验证，不覆盖原用户资料。
科研事实、数值、召回及 RAG/Research 对比按本地评测另记 **NOT MEASURED**，不能因安装完成改为通过。
