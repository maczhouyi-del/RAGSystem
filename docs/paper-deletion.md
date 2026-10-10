# 从当前知识库删除论文

TASK-06 后端协议；独立副本并不等于当前知识库。验收状态见产品改造进度。

预览返回论文 ID、元数据版本、派生数据与待停止任务数量、清理范围和保留副本说明。
DELETE 必须提交同一论文 ID、预览版本、`scope=current_library`、
`acknowledge_retained_copies=true`。版本冲突 409，缺确认 422；预览与取消没有写操作。

数据库提交是生效点：Paper、作者链接、section、chunk 内的向量、实体链接/关系和 Evidence
一同删除；共享作者/实体保留，关联后无任何引用的作者/实体及子类型删除。
持久化删除账本只保留来源 ID、文件清单/摘要、
取消任务 ID 与清理状态，不保存标题或证据原文。现有 Run/outbox/RQ ingestion 队列负责清理，
没有第二套任务队列。重复删除返回同一账本；失败重试创建新清理 Run，不能恢复 Paper。

PostgreSQL 事务级读写 advisory lock 将删除与来源发布串行化。解析/Embedding/模型调用结束后，
worker 先核对 Run 所有权与来源是否存在，才能写索引、事件、最终回答或评测文件。
相关未完成导入在同一删除事务撤销；Redis 停止指令随后执行，即使 Redis 故障也不能迟到复活。
尚未解析版本的同家族 arXiv 导入也撤销；其他已知版本和其他论文的任务保留。
用户后续主动重新导入产生新 Paper ID，旧引用仍不可用。

删除事务会扫描现有 Run、事件、消息元数据以发现历史来源；此期间来源发布等待事务结束。
这是完整历史脱敏的工程取舍，尚未测量大规模历史库的延迟。其他不涉及来源的会话正文不会删除。
worker 的检索使用短事务持久化 Evidence，随后释放 FK/advisory lock，再进入下一次模型调用。
普通检索 API 仍由路由提交事务；重排结束后再次按实际数据库来源筛选所有候选与证据。

历史 Run 的结构化来源 quote/content/source_context/source_spans、金标原文及相关事件脱敏，
标记 `source_availability=unavailable`、`source_unavailable_reason=source_deleted`。
消息 metadata 根级同样标记失效，兼容没有 compact presentation 的旧消息；来源更新推进
Message.updated_at（即使时钟回退也单调增加），让客户端丢弃迟到的旧快照，不能复活已失效引用。
历史作业状态保留真实执行结果，当前 `citation_validation.valid` 失效，相关支持关系移除；
会话消息与回答正文保留，并加来源不可用提示。因此回答正文、用户问题、会话摘要仍可能含原文
或论文事实，本接口不承诺全部文字抹除。其他来源的结构化原文保持不变。
包含被删来源的受管评测导出立即禁止下载，后台仅清理该 Run 的固定结果文件。
评测 checkpoint 在受保护文件写入的同一事务登记实际来源 ID，因此金标之外的检索来源也可发现。
TASK-07 负责将后端失效标记显示在旧回答与引用界面。

原始 PDF、`.parsed.json` 仅按数据库登记的受管路径清理，拒绝符号链接、越界、摘要不符
或未登记路径；其他 Paper 正使用的文件保留。评测仅允许 UUID Run 目录下固定四个结果/临时文件，
不递归删除目录、不 glob 用户文件。部分文件成功后失败可继续重试；缺文件视为幂等成功。
数据库已移除而清理失败时新检索仍不可见，账本保留安全错误码并可对账。

独立副本：桌面 `app_cache_dir/documents`、操作系统 PDF 阅读器、已下载的导出、用户另存 PDF、
备份/同步副本、外部模型服务的留存。本 API 无权定位或清除这些副本。用户需关闭占用程序、
清理桌面缓存及明确选择自己的文件，并按备份保留策略过期/重建备份；恢复旧备份会恢复旧知识库，
必须再应用删除账本后才开放检索。不得宣称所有副本已删除，不清理共享模型权重或其他会话。

后端当前使用 POSIX 目录描述符清理；Windows 桌面通过 Docker/Linux 后端使用此协议。
原生 Windows Python 文件清理未经支持/验收，不应据桌面 MSI 构建成功推断其可用。

## API 与对账

- `GET /api/papers/{id}/deletion-preview`：只读预览。
- `DELETE /api/papers/{id}`：确认请求，202 返回 `library_removed=true`、`cleanup_run_id`、
  `cleanup_status`、安全错误码、`retained_copies` 和 `retained_managed_files`。
- `GET /api/papers/{id}/deletion`：即使 Paper 已消失仍可读取账本状态。
- `POST /api/papers/{id}/deletion/retry`：queued/running/completed 幂等返回当前任务，
  failed/cancelled 创建新的清理 Run/outbox。恢复 Redis 后 queued 派发也可再次尝试。

删除 ID 的 Paper/PDF/chunks GET、元数据 PATCH、导入重试返回 410 `source_deleted`；
普通未知 ID 继续兼容 404（旧 chunks 的未知 ID 空数组语义保留）。来源历史下载被禁止后，
已打开/下载的文件仍属于独立副本。0009 禁止非空账本降级，不能遗忘来源不可用记录。

文件清理失败时先查看安全码和数据库 `paper_deletions.files` 清单：
`cleanup_queue_unavailable` 恢复 Redis 后重试；`cleanup_file_unavailable/cleanup_unsafe_path`
检查受管目录权限或符号链接；`cleanup_file_changed` 表示路径现有文件与登记摘要不符，
需人工确认并另存替换文件，再恢复登记文件或人工移除该受管路径后重试。不能更新摘要来强行删替换文件。
`unmanaged_path/shared_by_other_paper` 是明确保留，不属于清理失败；API 不回传原始磁盘路径。

部分清理成功后数据库回滚不会恢复已移除文件；重试将缺文件视为已清理，继续向前对账。
运行中 Redis stop 指令无同步完成保证，但数据库已撤销所有权，不能再发布来源；
实际停止和 callback 不覆盖 cancelled 历史状态已通过真实 RQ worker 验证。

检查计划：真实 PostgreSQL 原子性/撤销/共享数据与新检索隔离；真实 Redis 队列取消/失败重试；
受管文件缺失、部分失败、替换/符号链接/共享路径；迟到解析/Embedding/检索/事件/评测写入；
历史脱敏、当前验证失效和另一论文/会话保留。测试仅合成资料，不代表真实科研质量。
