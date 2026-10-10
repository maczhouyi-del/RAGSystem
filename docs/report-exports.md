# 报告导出

已发布的 RAG/Research 消息下选择格式并点击“导出当前结果”。不会创建 Run、触发模型、
重新检索或改变原报告。旧记录缺少 Run 正文时使用该 Run 的已保存 Assistant 消息，
只用于此次导出，不重写数据库。运行中、失败或取消的草稿不能导出为结果。

四个固定产物通过已授权的 `/api/runs/{UUID}/exports/{filename}` 读取：

| 文件 | 内容与边界 |
| --- | --- |
| report.md | 持久化报告正文的 UTF-8 原文，科学数字不换算、不重写。退役来源增加历史不可验证提示。 |
| comparison.csv | UTF-8 BOM、标准 CSV 引号和 CRLF；各实验行的方法/数据集/受试者/条件/指标/结果/单位/划分、字段状态、Claim/Evidence IDs 独立保留。 |
| references.bib | 仅导出已引用 Evidence 的冻结论文元数据；标题/作者/年份/venue/arXiv 有值才使用，未存 DOI 明确缺失，不把 venue 猜成期刊；使用保守 @misc。 |
| citations.json | Run、执行/验证状态、Evidence/Paper/Chunk/Section IDs、位置、冻结元数据和来源状态。没有 Evidence 记录的历史标记明确未知，不虚构来源。 |

没有结构化字段的旧报告保留原 Claim 和 legacy_report 正文；字段标为证据不足，
不会从旧散文猜单位或实验条件。引用快照标为 snapshot_only，不证明原始 PDF 当前仍存在；
有来源删除记录时标为 unavailable，全局验证标为 historical_unverifiable。
原文、支持跨度与科学数值不会在导出时重新生成。已发布的拒答可保存，不能把未通过的
Analyst 草稿或其 limitations 转入比较表。导出无当前验证信息的旧结果显示 legacy_review_unknown。

CSV 单元格保留原文字/换行/引用。可能成为电子表格公式的非数值字符串加单引号作为保护；
纯数字如 -0.3、+91.5、0.89、-1e-3 和百分数字面值不改动，科学数字不取浮点/舍入。
BibTeX 保留 Unicode，转义大括号、反斜线和 LaTeX 特殊字符，作者姓名按字面保护；
缺失作者、年份、venue 与 DOI 用注释标记。Evidence ID 保留在每个条目的注释中。

## 文件与授权边界

Web 使用同源授权请求与 Blob 下载，建议文件名只由固定前缀、校验的 Run UUID 和格式组成，
不采用论文标题或远程 Content-Disposition 作为路径。浏览器会按其下载设置保存，界面只说明
“下载已发起”，不能声称已写入用户磁盘。

Desktop 使用专门的 save_export 命令，只接受四个固定 Run UUID 路由，网络仍由
原有受限 Rust 客户端/系统凭据管理；没有 renderer 目录、任意 URL 或内容写入参数。
保存位置由系统 download_dir 提供，文件名加入随机 UUID，create_new 防覆盖；
Unix 文件权限 0600。UTF-8/JSON/8 MiB 限制在原生保存前检查，写入失败清除本次文件。
保存回执只给文件名和 Downloads，不暴露凭据或通用文件系统能力。
所有导出 GET 不缓存，nosniff、attachment，后端只读生成且不写任意目录。

## 验证

DEMO ONLY / NOT A BENCHMARK / NOT MANUALLY ANNOTATED。
Python 检查共享浏览器 fixture 确为实际确定性导出字节；浏览器实际下载四种文件并逐字节比较，
验证恶意建议文件名、失败恢复、旧会话与 MOCK Desktop 保存回执。
真实 PostgreSQL/API 验证结果/事件不修改、旧消息回退、来源退役、授权、状态和路径边界。
原生 Rust 用真实临时文件检查 Unicode/数字、重复保存不覆盖和无效路径/格式失败。
实际 Windows/Linux 原生编译和测试须以本任务精确提交 CI 记录为准。
MOCK 回执不能代替 Win11 人工 Downloads 保存/打开检查，真实科研质量仍 NOT MEASURED。
