# Evaluation and annotation

No benchmark improvements or human-annotated dataset are bundled. Synthetic
fixtures check pipeline behavior only: **DEMO ONLY / NOT A BENCHMARK / NOT
MANUALLY ANNOTATED**. A human must supply real queries, relevance labels and
expected answers before making research-quality comparisons.

Generate 100 unannotated forms:

```bash
python scripts/annotation_template.py my-annotations.json --count 100
```

A ready-made unannotated 100-row template and JSON schema are in
`evals/retrieval/`. Get exact corpus IDs from `/api/papers/{id}/chunks`. Read the
PDF and each chunk; enter question type, filters, relevant chunk/paper IDs,
expected answer, required aspects, notes and annotator/time. Change label_source
to human only after actual human annotation. The software records that declaration
as user supplied; it does not independently certify who labeled the data.
Unannotated data and nonexistent labeled corpus IDs are rejected. Retrieval
evaluation requires nonempty relevant chunk labels for every case. Generation
cases require a nonempty `expected_answer` and, unless `expected_refusal=true`,
nonempty `required_aspects` and relevance labels. An expected-refusal case can
omit relevant chunks/aspects; that flag must be supplied by the annotator rather
than inferred from a model refusing.

Optional pipeline corpus:

```bash
docker compose exec api python scripts/seed_demo.py
```

This appends one clearly labeled synthetic paper and uses real configured
embeddings (may incur charges with a hosted embedding backend). It generates an
original PDF and structured text, without pretending it came from a publisher.
Use `evals/retrieval/demo.json`. It is not sufficient for performance conclusions.

## Retrieval

POST `/api/evaluations/retrieval` with `{dataset: <dataset JSON>}`. Separate runs
measure dense, lexical, hybrid and hybrid_rerank. Each mode has its own actual
elapsed latency including embedding/inference for that mode; cold-cache ordering
can influence measurements. Warm up and repeat on a fixed corpus before comparing.

- Recall@1/5/10: retrieved relevant unique chunks / all relevant chunks.
- Precision@5: relevant chunks in first five / 5, including short result lists.
- MRR@10: reciprocal rank of first relevant result within ten, or zero.
- nDCG@10: binary relevance DCG divided by ideal DCG for known relevance.
- latency_ms: wall-clock execution time, never a copied number.

Dense/lexical/fused rankings are retained. Evaluation uses rerank K ≥ 10,
recorded separately from application evidence K. Chunk IDs and labels must refer
to the same index snapshot; changing chunking requires relabeling.

## RAG and multi-agent

POST `/api/evaluations/rag` or `/api/evaluations/multi-agent` with the same dataset.
The configured reviewer mapping is instantiated as a separate judge. Judgments
are **MODEL_BASED**, not human ground truth. Artifacts record judge provider,
model, full prompt, version and hash. Using the same model family for reviewer
and judge can create correlated errors; independent human review is needed for
scientific conclusions.

The manifest also freezes workflow retry, revision, iteration and evidence
budgets, plus each actual chat adapter's request timeout (null if unavailable).
Changes to environment settings during a run do not rewrite this provenance.

Citation precision is supported predicted claim/evidence pairs divided by all
predicted pairs. Citation recall is verified cited gold chunks divided by labeled
gold chunks; this is a reference-coverage measure, not a unique minimal-citation
estimate. Citation completeness is claims with a supported citation divided by
all released claims. Unsupported claim rate uses judge-supported claim IDs.
Answer/report completeness is fully answered required aspects divided by labeled
required aspects. Generation evaluation rejects missing required-aspect labels
on ordinary cases; it does not silently fill them or award a perfect score.
Undefined citation ratios produce null. Explicit refusals have no released
factual claims, and an unexpected refusal has answer completeness 0 even if the
judge asserts that an aspect was answered.

The judge receives the actual final answer/report, workflow status, claims,
exact evidence, expected answer/aspects and explicit expected-refusal flag.
Its evidence payload includes only released claims' cited IDs with valid exact
spans, their quotes and source metadata; full chunk content, retrieval scores
and uncited pool records are excluded from the semantic judgment. Full evidence
is retained separately in the artifact for human inspection.
`refusal_correctness` is defined for expected-refusal cases and actual refusals;
otherwise it is null. To score 1, the case must expect refusal, the workflow
must end in `insufficient_evidence`, release no claims, produce a nonempty actual
refusal, and receive the judge's `refusal_supported` verdict. Expected-refusal
answer completeness uses the same score. This is still a
**MODEL_BASED** determination, not human verification that a refusal was warranted.

Multi-agent also records verified workflow completion, retry/revision count,
workflow latency, per-provider prompt/completion tokens and cost when the SDK
knows prices. Hosted embedding calls are included in workflow token/cost totals,
not only chat calls; the separately instantiated judge remains excluded from
workflow totals. If any call's cost is unknown, the total is null; usage separately
records `known_cost` and `unknown_cost_calls`. Failed API calls may be billed
without returning usage, so they make cost incomplete. Worker usage snapshots
persist before dispatch and after response, including in-flight unknown charges
and returned provider model/system identities where available. Failure does not
turn already paid calls into zero cost. Judge latency/usage is separate from the
workflow. Retrieval-round counters do not count every expanded SQL query.

## Partial results and explicit resumption

Runners write an initial artifact and checkpoint after each completed or failed
case (each case/mode for retrieval ablation), instead of waiting for the whole
dataset. Paid-call usage updates also trigger artifact checkpoints before dispatch
and after accounting, preserving the worker's database usage observer. A case
failure records a safe error code and failure stage and does not
erase earlier successful cases; generation artifacts retain available workflow
output/evidence even when judging fails. Summary metrics include only cases with
`evaluation_status=completed`, with evaluated/failed/pending counts displayed.
An artifact with errors is `partial` or `failed`, not a completed benchmark.
Both JSON and Markdown downloads are available when the Run is terminal,
including `Run.status=failed`.

A killed process may leave pending cases and `corpus_verification=pending` in
its last checkpoint. That checkpoint remains usable for inspection, while the
Run records interruption and available usage; it must not be reported as a fully
verified evaluation. The in-progress case is not checkpoint-resumed internally.

Submit the same endpoint and dataset again with the previous terminal Run ID:

```json
{
  "dataset": {"...": "the same complete, annotated dataset object"},
  "resume_run_id": "00000000-0000-0000-0000-000000000000"
}
```

Replace the illustrative dataset object and UUID with the real values. Resumption
creates a new Run and retains only successful case checkpoints; failed/pending
cases execute again. Kind, canonical dataset hash, source hash, instantiated
adapter model configuration, workflow/retrieval/judge configuration and available
corpus snapshot must match.
Missing artifacts, a nonterminal/wrong-kind prior Run, unavailable corpus identity
or a previously failed corpus verification rejects resumption. A source/configuration
change requires a fresh evaluation rather than combining incompatible results.

Artifacts label usage `usage_scope=current_attempt`. Current totals describe
only newly executed work; retained rows use `attempt_scope=resumed` and keep their
original case usage. `previous_attempt_usage` preserves the earlier attempts'
usage/status/timestamps as a history chain, including failure costs. Do not sum
retained row costs into the new attempt again; account for all paid attempts using
that history plus current-attempt usage. This distinguishes saved outputs from
newly billed work rather than presenting a resumed batch as one fresh run.
On resumption, prior persisted Run usage supplements the artifact's latest usage
when available; that history entry records `usage_source=persisted_run` (otherwise
`artifact`). This retains paid-call accounting even if a case never reached its
result checkpoint. Completed case rows determine which work can be skipped;
usage snapshots alone do not certify case completion.

This durable accounting applies to queued worker Runs/evaluation. Synchronous
search/provider tests return `current_request` usage in responses only, and the
reindex CLI prints `current_attempt_cumulative` snapshots only. They do not
create persistent billing Runs; lost responses/stdout or process termination
cannot recover those costs from evaluation artifacts.

The evaluation RQ timeout is `EVALUATION_TIMEOUT_SECONDS` (default 7200,
1800–86400), frozen at dispatch and shared with reconciliation. Ordinary jobs
remain 1800 seconds; queued jobs expire after 1800 seconds and running jobs have
120 seconds grace. Timeout bounds execution duration, not currency spending.

## Artifacts and reproducibility

Each run writes `data/evaluations/{run_id}/results.json` and `results.md`, downloadable
from the evaluation API. They include Git commit, canonical dataset hash,
timestamp, label source/warnings, model configuration, retrieval configuration,
per-query outputs/rankings, actual latency and summary. Generation results retain
`actual_output`, `evidence`, `gold_labels`, `judge_input` and raw `judgment` as well
as released claims, status and metrics. Evidence snapshots carry source metadata,
exact text/offsets and scores so a download can be inspected independently.
New source snapshots include arXiv family/version, source status and independent
table context offsets. Unknown version/status remains explicit rather than being
inferred from a PDF checksum or successful indexing.

The manifest also freezes `source_hash`, `source_dirty`, `source_file_count`
and `source_hash_scope` at run start. The hash identifies the actual allowlisted
Python/Mako source under `src`/`migrations`, `pyproject.toml` and `uv.lock`,
including uncommitted changes; `.env`, corpus data and other secret/runtime files
are excluded. `source_dirty` is null when Git status cannot be inspected. The
hash is an identity/check value, not a bundled copy of the source; retain the
matching checkout or archive separately to reproduce it.

Provider configuration is captured from the actual instantiated adapters before
execution; changing the settings file during a run does not relabel that run.
Adapters without introspectable configuration are explicitly marked unavailable.
Retrieval provenance records the actual embedding/reranker revisions and the
embedder's frozen normalized API base; local adapters record no hosted base.
Local Hub revisions resolve to immutable SHAs before inference, and directory
models record their artifact hash. Configure the recorded SHA for later processes:
resolving an omitted revision only freezes the current adapter, not every future
run. Default chat mappings use a dated model name; response model identities and
system fingerprints are recorded when the provider supplies them. Temperature 0
and frozen identities do not guarantee deterministic remote model output.
Fallback configuration without instantiated adapters is labeled
`configuration_available=false`, with unavailable values null.
For PostgreSQL-backed retrieval, the indexed corpus and metadata/vector/entity
inputs are hashed at the start and checked again at the end; a detected change
rejects the evaluation. This boundary check does not lock the corpus throughout
the run. Test search ports without a corpus session mark that hash unavailable
and retain evidence snapshot hashes instead. Keys are never recorded.
Mounting the clone's read-only `.git` directory lets containers identify the
commit; source archives must supply a real `GIT_COMMIT` value.

CI checks metrics against hand-calculated fixtures and executes real PostgreSQL
ablations without paid APIs/model downloads. These are correctness tests; they
are not evidence of retrieval improvement on research literature.

## Auditable scientific gold and human review

The existing Evaluation UI and endpoints also accept `annotation_format=source_v1`.
Legacy datasets remain accepted, with a warning that they lack explicit PDF/span
gold. Adding empty default fields preserves unchanged legacy dataset hashes;
adding substantive labels changes the hash. Generate empty forms, never a claimed
human benchmark:

```bash
uv run python scripts/annotation_template.py my-gold.json --count 7 --source-gold
```

The generated `label_source` remains `unannotated` and cannot run. A human must
read original papers and fill the forms before declaring `human`. Cover English
and Chinese cross-language queries, single-paper facts, numeric/table questions,
multi-paper comparison, conversation follow-ups and warranted refusals. Keep the
existing `question_type` values; use `evaluation_dimensions` to mark
`cross_language`, `numeric`, `table`, `multi_paper`, `follow_up` and `refusal`.
Follow-up execution uses the existing conversation dataset and ordered turns;
the dimension alone does not create conversation context.

For each non-refusal case, `gold_sources` must cover exactly all labeled relevant
chunk and paper IDs. Each source contains:

- `paper`: `paper_id`, lowercase original `pdf_sha256`, optional known
  `arxiv_family_id`/`arxiv_version`, and positive, unique `reviewed_pages`.
- `chunk_id`, inclusive `page_start`/`page_end`, zero-based Python character
  `span_start`/exclusive `span_end`, and the exact nonblank `quote`.

Get chunk IDs/text from `/api/papers/{id}/chunks`; obtain the original PDF hash
with `sha256sum original.pdf` or PowerShell `Get-FileHash original.pdf -Algorithm
SHA256` (normalize to lowercase). Record versions only when known; a checksum
does not establish a publisher/arXiv version. API submission and worker execution
check stored PDF identity/version, chunk-to-paper association, exact text span
and containment within indexed page ranges. The software does not independently
certify a physical PDF page when an indexed chunk spans several pages: the human
must inspect the PDF and declare the precise reviewed pages. Retain the originals
and the matching index separately.

Expected-refusal cases need `reviewed_papers` with the same paper identities/page
declarations and a nonblank `refusal_rationale` describing the reviewed scope.
Absence of relevant chunks alone does not demonstrate warranted refusal. All
human cases need a nonblank annotator and timezone-aware annotation timestamp.
Numeric cases additionally need `numeric_targets`: name, decimal `value` as a
JSON string, explicit `unit` (use `dimensionless` where appropriate), and nonblank
experimental `conditions` keys/values. The API preserves decimal precision when
queuing to JSONB. Correctness requires all values, units and conditions, rather
than matching a digit somewhere in an answer.

Download an existing run's `results.json` using Evaluation, then inspect/review
it without another model call:

```bash
uv run python scripts/audit_evaluation.py template --results results.json --output review.json
# A human edits only review fields, keeping observations and artifact identity intact.
uv run python scripts/audit_evaluation.py review --results results.json --review review.json --output human-assessment.json
uv run python scripts/audit_evaluation.py case --results results.json --scope generation --id q001 --output failure-case.json
uv run python scripts/audit_evaluation.py compare --results before.json --after after.json --output comparison.json
```

Scopes are `generation`, `retrieval/MODE`, or `conversation/CONVERSATION_ID`;
the `id` is the query/turn ID. Case inspection retains actual output, evidence,
gold, failure stage/code, metrics and usage and is labeled
`OFFLINE_INSPECTION_NO_MODEL_CALL`. Actual inference replay uses the explicit
resumption procedure above and can incur charges. A code/configuration change
requires a fresh evaluation.

Review templates start with every case unreviewed, all verdicts unset. For an
inspected case supply `reviewed=true`, `reviewed_by`, timezone-aware `reviewed_at`,
notes, verified `supported_pairs` and fully `supported_claim_ids`; numeric/refusal
verdicts are optional booleans only for applicable labeled cases. Verified pairs
must refer to released claim/citation IDs and structurally exact evidence.
The reviewer must read that evidence to assess semantic support. A changed
artifact, edited frozen observation, unknown pair or unsupported claim rejects
the assessment. These are user-supplied reviews, not independently certified
annotation quality.

| Human metric | Denominator and interpretation |
| --- | --- |
| Citation precision | Verified claim/evidence pairs / all released predicted pairs |
| Citation coverage | Released claims with a verified pair / all released claims |
| Claim support accuracy | Fully human-supported claims / all released claims |
| Numeric accuracy | Human all-values/units/conditions verdict, only with numeric gold |
| Refusal accuracy | Human verdict for expected or actual refusal; true additionally requires expected refusal, insufficient-evidence status, no claims and a nonempty refusal |

Undefined ratios and unreviewed cases stay null. Summary reports macro means of
reviewed cases with a separate count for each metric; no reviewed cases yields
an empty summary. Original failure statuses remain visible. Existing automated
model judgments remain separate from these human metrics.

Comparison requires identical dataset/label source, known corpus hash, actual
model, judge, retrieval and workflow configurations, and known source hashes.
Source hashes may differ for a before/after code comparison. Added derived adapter
classification does not change configuration identity. Only matching completed
case IDs contribute metric deltas; failures/missing cases and both manifests stay
in the output. Unknown costs stay null. A paired-success mean cannot conceal
failure counts or establish gains over a different successful cohort.

Chat adapters are explicitly classified as `SCRIPTED`, `PROVIDER_ADAPTER` or
`UNKNOWN_ADAPTER`; scripted, synthetic and unknown execution cannot claim real
scientific quality. Real quality is **NOT MEASURED** in this repository. To measure
it, supply licensed original PDFs and stable corpus/model revisions, actual human
gold across the requested dimensions, authorized model access/budget and human
inspection of actual generated answers. No fabricated human dataset or research
accuracy is bundled.

## Conversational RAG and Research

POST `/api/evaluations/conversation` with `{dataset, resume_run_id?}` queues the
production conversation evaluator. Cases have `mode=rag|research`, explicit
dimensions, optional seed messages/structured memories and ordered labeled turns.
Each turn reuses the Context Builder, extractive rolling summary, configured
retriever contextualization, the independent existing graph, current retrieval,
citation validation and a separately instantiated model-based judge. Conversation
history never becomes an EvidenceRecord or relevance label.

The dataset schema/examples are in [evals/conversation](../evals/conversation/README.md).
Existing expected-answer, required-aspect, corpus-relevance and human-annotation
validation remains mandatory. Expected-refusal cases must be labeled explicitly.
Additional labels include `expected_context_terms`, `forbidden_answer_fragments`
and `expects_summary`. Dimension declarations require relevant labels rather than
silently scoring unlabeled cases. Synthetic examples/templates remain **DEMO ONLY /
NOT A BENCHMARK / NOT MANUALLY ANNOTATED** and require real corpus IDs/annotations
before research-quality comparisons.

After checking the labels against the current corpus and configuring providers,
wrap a dataset file in the API request and submit it from the repository root:

```bash
python - <<'PY'
import json
from pathlib import Path
dataset = json.loads(Path("my-conversations.json").read_text())
Path("conversation-request.json").write_text(json.dumps({"dataset": dataset}))
PY
curl -H 'Content-Type: application/json' --data-binary @conversation-request.json \
  http://localhost:8000/api/evaluations/conversation
curl -N http://localhost:8000/api/runs/RUN_ID/events
curl -o conversation-results.json \
  http://localhost:8000/api/evaluations/RUN_ID/results.json
```

Replace `RUN_ID` with the returned Run UUID and download after it becomes terminal.
The Evaluation UI supports the same conversation dataset/API. These operations
invoke configured models and may incur charges; they do not create user chat
Conversation records. Keep dataset/request/artifact files private when they contain
private source text or seed history.

| Dimension | Recorded checks and metrics |
|---|---|
| `context_resolution` | `resolution_accuracy`: all labeled expected terms occur in the contextualized query, case-insensitively; `context_budget_compliance`: rewrite input estimate stays within its configured budget. This is a labeled text check, not a complete semantic parser score. |
| `evidence_grounding` | Existing citation precision/recall/completeness, answer completeness, unsupported-claim and refusal metrics over the actual released answer/current evidence; semantic judgment remains MODEL_BASED. |
| `memory_isolation` | No forbidden historical answer fragments, exact paper/chunk/span provenance, evidence matching current-turn retrieval, context IDs absent from evidence, and a grounded complete answer (or explicitly labeled correct refusal). Empty ordinary answers cannot earn success. |
| `long_summary` | For summary-labeled turns, summary was used, expected context terms remain resolved, budget is respected and the answer is grounded/complete; also records summary-used rate. |

Per-turn artifacts retain original/contextualized queries, used context IDs,
summary/version, enforced filters, current retrieval plans, structural checks,
actual output/evidence/judge input and actual latency/usage. The manifest freezes
context settings/version, rewrite-role prompt/hash, instantiated provider identities
and source/configuration/corpus identities alongside existing evaluation provenance.
Rewrite calls count as retriever usage; hosted embeddings count in workflow usage;
the independent judge remains separately charged. Unknown or interrupted call fees
make complete totals unknown.

Checkpoints occur at context/usage/turn/case boundaries. A turn failure stops its
conversation case so later turns do not inherit an incoherent partial dialogue;
other cases continue. Summary metrics include only fully completed conversations
and report completed/failed/pending counts. Dimension coverage/counts and missing
dimensions are visible; a dataset exercising one dimension does not establish
coverage of all four. Within successful cases, labeled turn metrics are averaged;
undefined values remain null rather than becoming perfect scores.

Explicit resume skips only fully completed conversation cases. A failed or
interrupted conversation reruns as a whole, including its earlier turns, because
their history affects later turns. Source/dataset/model/context/prompt/corpus
identities must match, and previous-attempt usage remains separate. This is not
intra-conversation graph checkpoint restoration or a claim that repeated inference
will be deterministic.

Term-presence and forbidden-fragment checks can miss paraphrases, irrelevant text
or subtle reference errors. Model-based judgment can be wrong or correlated with
the graph reviewer. Synthetic/provider-scripted regression tests establish routing,
budget and evidence separation contracts; they do not establish real scientific
chat quality. Real PDFs, fixed model revisions, human-labeled conversation cases,
remote-provider compatibility and long-history quality need separate runs. Actual
execution results are recorded in the stage log, without invented benchmark gains.
