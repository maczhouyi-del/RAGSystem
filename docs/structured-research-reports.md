# 结构化科研报告

Research 使用已有 Supervisor → Retriever → Analyst → Reviewer 和确定性报告节点。
完成状态的 `draft_report` 为最终 Markdown，`structured_report` 同时保存版本 1 的章节、
逐来源实验行、字段状态、Claim/Evidence IDs 与可比性限制，供后续导出。
旧 Run 不需迁移；没有实验字段的旧 Claim 仍按已验证类别组织，不从散文猜字段。

报告依次组织研究问题、文献范围、方法、数据集/受试者、实验条件、结果、
发现/争议、可比性限制、证据缺口和参考来源。研究问题明确为用户意图，不能充当事实证据；
范围只说明已引用的来源，不声称穷尽文献。引用元数据不经过第二次模型生成。
所有科学内容来自原来的 Claim 文本，使用原 Evidence ID，可打开逐来源原文。
未验证的 Analyst limitations 只保留在既有独立面板，不能进入已验证报告正文。

## 字段和发布门禁

Analyst 可返回 `observations`，每行明确 `paper_id` 和实验 `row_id`。字段固定为
method/dataset/participants/conditions/metric/result/unit/split，只引用已有 `claim_ids`。
可选 `source_literal` 必须是该字段所引来源 quote 的逐字子串；它用于差异识别，不能提供新事实。
同一论文多个实验保持不同行；跨论文综合论断可进发现章节，不能冒充单篇实验字段。

- `reported`：存在已验证 Claim，科学数字保持原样。
- `explicit_not_reported`：存在引用、原文字面语句和通过 Reviewer 的明确未报告论断。
- `evidence_insufficient`：本次未检索到可验证字段，不意味着原文没有报告；不得附带事实或字面值。

来源/Claim 不存在、错配来源、重复行、伪造字面值由确定性检查拒绝。
Reviewer 在原有逐 Claim/支持对/问题覆盖校验之外，核查字段角色、实验归属、
指标定义、单位、数据划分、实验条件，以及明确遗漏与检索遗漏的区别。
提供实验字段时必须返回 `report_bindings_verified=true`；缺失或 false 进入既有有界修订。
当前 Reviewer 未通过不能发布最终报告，耗尽重试返回证据不足，不保留可误认为最终正文的草稿。
来源删除仍保留历史正文，但撤销当前验证、清除原始 quote/新字面值并标记不可用。

## 实验可比性

比较表保存各行单位、数据划分和实验设置，不换算、不静默合并，不作公平排名。
不同 `reported` 字段的原文字面值会显示差异警示；明确未报告/缺失不能当成另一个实际实验值。
字段缺失或字面值缺失明确说明无法确认可比性。即使文字相同，也不证明实验等价。
系统采取保守的 `not_directly_comparable` 状态；真正的公平比较需研究人员核查完整设置。

## 验证边界

`tests/fixtures/report-demo.json` 来自实际确定性节点，Python 校验与浏览器共享该产物。
自有双来源模拟例包含 91.5 % / 0.89 fraction、test / validation、GPU / CPU、相反发现、
明确人口信息未报告和另一来源检索缺失，逐项检查数字、章节、条件、来源和缺口。
标记为 **DEMO ONLY / NOT A BENCHMARK / NOT MANUALLY ANNOTATED**。
真实 PostgreSQL 测试核查限定来源检索、当前 Reviewer 门禁与删除后的历史状态。
这些验证不构成真实论文人工金标或真实模型的科研质量测量；用户已确认资源尚未备妥。
真实科研人工案例验收、质量指标和 Win11 人工操作分别保持 NOT EXECUTED / NOT MEASURED。
