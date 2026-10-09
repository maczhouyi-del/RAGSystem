# PDF 来源位置与兼容性

TASK-12 检查的是来源链：Docling Element → Chunk 原文 → Evidence/Citation。
字符跨度是 Python Unicode code-point 区间 `[start,end)`，并非 PDF 文件字节偏移。
Evidence ID 继续使用 `UUID5("chunk:{chunk_id}:0:{len(content)}")`，不加入坐标、来源 ID
或解析版本。旧索引不重写原文、不重新分块、不改变已有 Chunk/Evidence ID。
论文仍携带冻结 arXiv 版本；新 Evidence 的 `paper.pdf_sha256` 记录原始 PDF 摘要。

新增可选数据：

- `pdf_regions`：原始 source_id、原始页码、可验证区域、Docling 原始 charspan。
- bbox 保留 `left/top/right/bottom`、页宽高、`TOPLEFT/BOTTOMLEFT` 和 `page_units`。
  不把未知坐标系猜成某个原点，不用渲染像素冒充 PDF 页单位。
- `scope=element`：区域属于解析元素。即使 charspan 可映射到原文，这个区域也不能
  冒充某条科研结论或单个字符的精确高亮框。
- `source_start/end`：仅在 charspan 有序、落在相同原文且 Docling text/orig 一致时保存。
  Markdown 表格的生成字符与 PDF 字符没有可靠逐字映射，始终不填此精确映射。
- `pdf_location=available/partial/unavailable`：由通过验证的区域计算，不能由输入声明伪造。
- `page_location`：无可靠 provenance 的文字仍保存，但页码明确 unavailable；既有数值字段的
  兼容占位值不能用作实际第一页位置。旧索引原有已保存页码可读，坐标默认 unavailable。

边界框须数值有限、非退化、方向符合原点、落在可靠页宽高内；缺失、零框、越界、未知原点
或无页尺寸时保存明确原因，不拒绝整段有效文字。损坏的可选历史位置同样降级。
文本块只携带与其原始跨度相交的来源区域；无法逐字映射的多页表格保留全部候选页区域，
不猜测某一行属于某个框。表头和表注继续使用独立 `SourceContext`，公式继续保持原子块。
原文、表头、表注、公式和 source_id 的关系独立于坐标可用性。

持久化使用现有 Chunk JSON metadata，增加 `source_location_version=1`、`pdf_regions`
和 `page_location`；现有 `source_spans/source_context` 增量包含位置数据。
不需要数据库 DDL 或有损回填。旧 Run/Evidence JSON 缺字段仍按默认值读取。
检索、支持跨度及引用验证不以坐标存在为前提，旧文本证据继续有效。
坐标不传入模型提示，保持科研文本验证和导航信息的用途独立。
来源退役会清除相关历史原文、辅助来源及位置字段，位置状态变为 unavailable。

上游依据是仓库锁定的 Docling slim 2.133.0 和 docling-core 2.99.0，已检查 wheel
SHA256 和 MIT LICENSE。PdfBox/ProvenanceItem/PageItem 的坐标、页尺寸、charspan 定义
来自这些实际版本；没有复制外部实现。布局/OCR/模型权重许可证及真实识别质量须另外核验。

可复现的真实 PDF 检查：

```bash
export UV_PROJECT_ENVIRONMENT="$(mktemp -d)/venv"
uv sync --locked --extra parsing
uv run --locked --extra parsing python scripts/verify_pdf_provenance.py \
  --output-dir /tmp/ragagent-pdf-proof
```

脚本生成自有两页 PDF，含正文、表格行、表题及公式，并使用实际
`DoclingParser(native_pdf=True)` / Docling NativePdfPipeline 读取 PDF。
HF/Transformers 离线开关开启，管线不加载布局、OCR、表格或其他模型。
产出实际 PDF、parsed/chunk JSON、摘要和验证回执；只在唯一临时子目录写入，不覆盖已有文件。
原生管线没有语义表格/公式分类；本检查证明这些可见文字、页码、元素区域和分块原文关系，
不证明自动版面分类正确率。结构化表格/表头/表注/公式另有合成契约和真实 PostgreSQL 回归。

当前实际结果：两页、12 个来源元素、3 个块，0 模型调用；原始 PDF SHA256
`9f4e298964b136c23447bc9b72b7220ccd4f2762998a4843486197c62fd17bff`。
样本是 **SYNTHETIC ONLY / NOT A BENCHMARK / NOT MANUALLY ANNOTATED**。
标准 Docling 布局/OCR 的真实识别质量、科研效果及真实扫描论文位置正确率均 NOT MEASURED。
默认应用解析管线保持现有标准 Docling 行为；原生模式是明确选择的验证/降级能力。
TASK-13 在这些契约之上提供阅读与定位说明，缺坐标不得伪装精确高亮。
