# 测试版交付后：用户本地真实科研评测

TASK-17 真实资源尚未提供，状态 BLOCKED；科研质量 NOT MEASURED。
工程中使用的 MOCK / SYNTHETIC 案例不进入科研准确率，也不能证明Research优于RAG。
本轮交付之后暂停，由用户决定论文、获准模型与预算并亲自执行，不自动产生API费用。

复用 [TASK-03现有 Evaluation 框架](../evaluation.md#auditable-scientific-gold-and-human-review)，不另建评测系统。
无需开发环境的基本路径：

1. 在Knowledge Base导入自有真实PDF，记录原文件SHA256/版本，检查解析文本、物理页、表格、公式和引用定位。扫描件与native文本解析分别标注。
2. 阅读原文人工构建问题/正确答案，用现有 `source_v1` JSON模板记录paper/chunk/span/page/quote、数值、单位和实验条件；没有人工核验不能声称金标。模板说明见evaluation文档“Source gold and human audit”。保留拒答/证据不足/多论文/跨语言等案例。
3. 在Evaluation页面上传同一数据集，分别选择RAG与Multi-Agent Research。固定论文版本、问题、检索范围/filters、embedding/reranker、角色模型/revision、judge及prompt/config。设置用户可承担的预算，先小批量。
4. 下载两次逐例results/manifest/failure artifacts。检查事实正确性、证据支持率、检索precision/recall、所有数值/单位/条件准确性；模型judge分数与人工评审分开，不把Unknown转为0或100%。
5. 记录真实延迟、Token完整性、SDK估算费用与已知账单区别。失败/取消的调用也可能收费；没有完整usage就保留Unknown/partial。
6. 用同一审查标准逐例读原PDF，保存问题ID、来源、回答、引用、人工判定与失败原因。不得事后改变金标或给其中一种方法更宽范围。比较结果允许Research更好、相同或更差。

已有离线工具同时随部署ZIP提供 `scripts/annotation_template.py` 与 `scripts/audit_evaluation.py`。
它们依赖现有运行时，可由维护者/熟悉Docker的用户在migrate容器内执行（不会调用模型）：

```text
docker compose run --rm --no-deps migrate python scripts/annotation_template.py /data/my-gold.json --count 20 --source-gold
```

上例生成未标注模板，不是金标；请通过现有API/界面导出所需原文来源并人工填写。
按[原工具说明](../evaluation.md)进行 `audit_evaluation.py template/review/case/compare`；
文件可通过Docker Desktop volumes管理或明确的本地copy操作保存，不把API密钥加入评测输出。
比较工具只接受符合既有身份约束的配对运行，拒绝不同语料/配置的假公平对照。

TASK-19科研验收需上述真实来源与人工结果齐备。Windows11/macOS本地安装与使用反馈也请单独记录，
包括OS/CPU、artifactSHA、安装/重启/配置/PDF/问答/Research/导出/升级/恢复的实际成功或失败。
