# 文献搜索、排序和分页

Knowledge Base 的「文献搜索与筛选」在服务端搜索整个文献库。填写标题、作者、
年份、会议/期刊或索引状态，选择排序后点击「搜索文献」。不同字段按 AND 组合；
标题、作者和会议/期刊按不区分大小写的字面子串匹配，`%`、`_` 不作为通配符。
「清除筛选」恢复全部文献与默认创建时间倒序。修改筛选会回到第一页；刷新保留
已提交的筛选和页码。输入框尚未提交的文字不会改变当前查询。

总数是整个筛选结果的数量，页面每次显示 50 篇。可以按创建时间或论文年份升序/
降序排列；相同值以 Paper ID 升序固定顺序，未知年份放在末尾。排序在固定集合中
稳定；不同请求之间新增或删除文献可能移动 offset 页的位置，不是冻结库的游标。
如果当前页已超出结果范围，界面回到最后有效页。查询失败保留已有结果和输入，并
显示错误，支持刷新重试。空库和筛选无匹配分别提示。

上传 PDF 与 arXiv 导入仍使用原来的入队接口；索引状态独立于人工来源状态。
应用筛选时新导入的论文可能不符合条件，后台任务提示仍显示，清除筛选可查看。

## 接口兼容

旧 `GET /api/papers?limit=50&offset=0` 仍返回 Paper 数组，分页边界保留；新增
`created_at` 字段不会移除旧字段。新接口在动态 Paper ID 路由之前声明：

```text
GET /api/papers/search?title=contrastive&author=Alice&year=2024&venue=Nature&status=indexed&sort=year&direction=desc&limit=50&offset=0
```

响应是 `{items: Paper[], total: integer, limit: integer, offset: integer}`。
总数和该页 ID 在同一条 PostgreSQL 语句快照中产生；作者用 EXISTS 筛选，多个
匹配作者不会重复文献。作者与 chunk 数量随后批量读取，非逐行 N+1 查询。

| 参数 | 校验/语义 |
| --- | --- |
| title | 1–1000 字符的非空标题子串 |
| author / venue | 1–256 字符的非空作者/会议期刊子串 |
| year | 1000–2100 整数；精确筛选 |
| status | queued / parsing / indexing / indexed / failed；索引状态 |
| sort | created_at（默认）/ year |
| direction | desc（默认）/ asc |
| limit | 1–200，默认 50 |
| offset | 0–1000000，默认 0 |

缺少的筛选字段表示不限；空字符串、控制字符、无效 UTF-8、未知字段、重复参数、
不合法枚举/范围会拒绝。与原输入边界一致，不接受可识别凭据。不要把密钥写进查询。
桌面桥仅在固定 `/api/papers/search` GET 路由解码受限查询值，允许编码后的 Unicode；
仍拒绝编码路径、任意参数、非 GET、路径穿越或远程 API 路由。旧桥路由限制保留。

## 数据库升级与验证边界

运行既有 `uv run alembic upgrade head` 应用 0007：为创建时间/年份/状态分页和
作者反向关联添加 B-tree 索引，为 lower(title/venue/author name) 添加 pg_trgm GIN
索引，支持字面子串查询。pg_trgm 是 PostgreSQL 扩展，首次创建需数据库角色具备
CREATE 权限；未添加新服务或 Python/JS/Rust 依赖。大库索引创建需维护窗口和足够
磁盘；迁移使用普通事务索引创建，不能宣称在线无锁。短子串可能走扫描，实际计划
由 PostgreSQL 选择。没有宣称真实大库延迟或吞吐已经测量。

降级至 0006 仅删除七个新增索引，保留共享 pg_trgm 扩展及所有文献。已有迁移集成
测试执行真实旧数据升级、Alembic 模型一致性检查与降级/重升。
新增集成测试创建 214 篇明确 SYNTHETIC 文献，检查服务端全库搜索、组合筛选、
Unicode/字面符号、稳定分页/总数、空结果、旧接口和三次查询的批量响应。
浏览器测试模拟 HTTP，验证筛选/页码/排序/竞态/错误恢复/原导入流程；不会冒充
实际数据库、PDF 解析或科研质量。完整结果见 product-improvement/PROGRESS.md。
