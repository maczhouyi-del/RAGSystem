# Stage verification log

## Stage 1 — reference and architecture review

Changed: .gitignore, LICENSE, AGENTS.md, docs/reference-review.md,
docs/references/snapshot.json, docs/architecture.md, docs/stage-log.md.

Research completed before business implementation. GitHub account verified via
explicit connector link for chouytong (requested email). Shell Git credentials
belong to another account and push returned 403; use the correct GitHub connector
for all writes. Do not change or expose credentials.

Checks: Markdown/table/manual link review and JSON parse. Formatter, Ruff, mypy
and pytest are invoked but have no business source/tests to check in this
research-only stage; no test pass is claimed for absent tests.

Limitations: upstream metadata is a point-in-time observation; missing LICENSE
means no code reuse. No corpus or empirical benchmark exists yet.

## Stage 2 — data and ingestion

Changed: pyproject.toml/uv.lock, domain document contracts, SQLAlchemy normalized
models, Alembic migration/environment, parser abstraction/Docling adapter,
structure chunker, ingestion/arXiv services, settings/errors, unit/integration
tests and data-model documentation.

Checks: Ruff format/lint, strict mypy (15 source files), three unit tests;
PostgreSQL 17 + pgvector migration upgrade/downgrade/upgrade and ingestion/FTS
integration checks. Core tests download no models and use no commercial API.

Limitations: chunk token counts are reproducible lexical counts, not model
BPE counts; mathematical extraction depends on Docling recognition; arXiv
network access and actual Docling model parsing require model/network-enabled
runtime and are not asserted by fixtures. First migration freezes 384 dimensions.

## Stage 3 — retrieval, providers and evidence

Changed: typed query/filter/evidence/claim schemas; filtered DenseRetriever and
PostgreSQL FTS LexicalRetriever; RRFusion/HybridRetriever; lazy cross encoder;
independent local/LiteLLM embedding adapters; unified chat/config/mock providers;
exact-span and semantic claim verifier; evidence gate; citation parser/renderer;
provider mapping config and retrieval documentation/tests.

Checks: Ruff format/lint, strict mypy; 13 unit/integration tests on real
PostgreSQL/pgvector. All metadata filters exercised together, and absent dataset
filter returns no dense or lexical rows. Citation/spans, verifier omissions,
evidence diversity and provider secret-name validation are tested without APIs.

Limitations: semantic verification is model-based; score thresholds require
calibration on human labels. Cross-encoder/model inference needs installed model
extras and weights; integration tests intentionally use injected deterministic
embeddings/reranker to verify real SQL independently of model quality.

## Stage 4 — typed LangGraph workflows

Changed: typed RAG/MultiAgent states and updates, structured plan/subtask/analysis
contracts, current StateGraph builders, Supervisor policy, query-expansion and
revision/refusal paths, deterministic report synthesis, graph/regression tests
and agent architecture documentation.

Checks: Ruff format/lint, strict mypy; 23 tests including known-query citation
regression, real PostgreSQL graph execution with scripted LLMs, all reviewer
routes, preserved user filters, retrieval exhaustion and iteration termination.

Limitations: Supervisor task/aspect quality and semantic verdicts depend on
configured models. Unsupported contradictions force bounded revision/refusal;
supported conflicting findings can be reported with evidence. Test scripts
validate execution contracts, not scientific reasoning quality.

## Stage 5 — jobs, API, SSE and UI

Changed: API routers/contracts for upload/arXiv/library/search/RAG/research/
providers, worker/RQ queue, durable event replay, trace logging, nonsecret config
updates, runtime adapter factory and React/TypeScript/Vite UI with five pages,
validated wire contracts and citation source dialogs. Added real DB API tests.

Checks: Ruff format/lint, strict mypy (40 source files), pytest with PostgreSQL,
frontend Prettier formatting/lint, TypeScript strict check and production build.

Limitations: trusted local single-user deployment; model caches/provider keys
must be configured for inference. Worker restart/resumption is explicit via retry;
SSE events persist but automatic graph checkpoint resumption is not claimed.
Evaluation UI has no canned numbers; actual runner/API added only in stage 6.

## Stage 6 — evaluation, deployment and final verification

Changed: real retrieval/RAG/multi-agent evaluation runners and API/artifact
downloads; annotation schema, 100 unannotated forms and explicitly synthetic
pipeline dataset/corpus tool; evaluation UI metrics; Dockerfiles, Compose,
optional cloud CA overlay, environment example, Makefile and GitHub Actions;
README/evaluation/deployment documentation. Hardened ingestion ownership and
worker interruption handling, indexing progress, section descendant filters,
empty-index retrieval, all structured factual-claim verification, bounded
Supervisor replanning, nonsecret error codes and UI event reconnection.

Checks on 2026-10-03: Ruff format/lint, strict mypy (49 source files), 48 passing
pytest unit/integration/regression tests with real PostgreSQL 17/pgvector;
Alembic schema check and downgrade/upgrade round trip on the test database;
frontend Prettier, TypeScript check and production build; git diff whitespace
check. No paid APIs or model downloads are needed by these core tests.

Latest Docker images built successfully with the documented cloud CA overlay;
Compose migration/API/worker/Redis/PostgreSQL/frontend startup passed. Actual
Redis/RQ execution, sanitized provider_key_missing failure, terminal SSE replay,
empty-index search without model loading, invalid evaluation corpus references
and frontend HTTP were verified. Chromium opened all five UI pages with no
script errors. Docling/embedding/reranker packages are installed in the image;
this is not a claim that weight-backed inference or PDF model parsing ran.
The backend installs dependencies and clears caches in one layer to avoid
duplicating large model dependencies on VFS Docker builders.

Limitations: no real 100-query human-labeled benchmark, no claimed improvement
metrics, no paid provider inference or downloaded-weight inference verified in
this restricted cloud environment. Actual arXiv import and model parsing require
approved network access/caches; configured provider credentials or local models
are required for chat. Semantic evaluation remains model-based and requires
human validation. Trusted local single-user deployment, English FTS, exact
vector search and explicit retry after worker failure remain V1 boundaries.
GitHub Actions configuration is committed; local checks above do not assert a
GitHub-hosted workflow result. The six review branches are sequential PRs and
are intentionally not merged automatically.


## Independent review repairs — 2026-10-04 (Asia/Shanghai)

The user authorized implementation after the independent read-only review.
Changes were uncommitted when first verified in the `phase-6-evaluation-deployment`
checkout at baseline commit `5677745e82702bb87786fa86f741e83ddf79d2ab`. No commit,
push, pull request or merge was performed during the implementation turn.
The user subsequently authorized GitHub submission. Earlier stage entries are
historical records and do not establish acceptance of these changes.

The actual backend/migration/dependency source hash is
`fb1fa6de8ea9c6eb8ab4ad9b649abc78bef8a377589a53df08f9557ec316ca73`.
It covers 59 files: `src/**/*.py`, migration Python/Mako files, `pyproject.toml`
and `uv.lock`. The workspace reports dirty=true; the runtime reports dirty=null
because Git is unavailable in the image. Both compute the same source hash.
This identifies the tested/deployed source, not an attached source bundle, and
excludes secrets, frontend files, data and generated artifacts.

### Repairs and evidence

- Gate filtering now controls the exact evidence supplied to generation and
  verification in both workflows. Missing/low rerank scores and invalid spans
  are rejected. Unknown inline citations and missing/duplicate/unknown verdicts
  fail closed; only structured, validated citation IDs are rendered. Reviewer
  and evaluation judge receive cited exact quotes, not uncited chunk prose.
- RAG retains accepted evidence across retries. Research uses the same score
  threshold and bounded pool; changed task content cannot inherit completion
  through a reused ID. Retrieval, revision and iteration limits remain explicit.
- Run and durable dispatch intent commit together. RQ uniqueness and locked
  PostgreSQL claims prevent duplicate execution after acknowledgement loss.
  Independent API reconciliation retries dispatch and terminates expired jobs;
  Redis outages do not incorrectly declare active jobs dead. Real killed/stopped
  RQ subprocesses persist Run and owned ingestion failures. Terminal state and
  final event commit atomically; SSE drains replay pages before done.
- PDF responses are inline. Concurrent uploads deduplicate Paper/Run, shared
  authors use conflict-safe insertion, and retry/metadata changes lock and
  refresh Paper state. Readiness verifies DB, Redis and worker registration;
  liveness remains separate.
- Heading occurrence IDs and JSON structural identities prevent separator
  collisions and repeated-heading merges. Frozen migration 0001 is unchanged.
  Revision 0002 preserves legacy source links, backfills pending dispatches and
  refuses a downgrade that would lose distinct sections with identical labels.
- Hosted embedding fingerprints and transport share a frozen normalized actual
  endpoint, including OpenAI SDK/environment defaults. Supported prefixes are
  openai/cohere/cohere_chat/voyage; other prefixes fail closed, and non-OpenAI
  services require an explicit endpoint. Optional revision identity, consistent
  dotenv/runtime lookup, bounded local adapter reuse and synchronized loading
  are implemented. Retrieval author lookups are batched per search.
- Unknown charges keep totals null while exposing known subtotals and unknown
  call counts. Failed calls and malformed empty-choice responses retain usage
  accounting. Mock providers remain test-only and are not production fallback.
- Evaluation judges actual final output/status and explicit expected-refusal
  labels. Wrong refusals score zero completeness. Artifacts preserve outputs,
  source evidence, gold labels, judge input/raw decisions and per-case usage.
  Configuration, actual endpoint/revisions/timeouts and workflow budgets freeze
  at start; source and corpus hashes identify inputs. Corpus changes between
  start/end checks abort the run. Retrieval evaluation does not mutate app K.
- UI preserves raw multiword/filter separators, pages beyond 50 papers, handles
  stale requests and restored SSE connections, distinguishes unsaved settings,
  and prevents repeated evaluation submission while a request is pending.
- Added 26-requirement reconstructed v1 acceptance baseline and five repair ADRs.
  These do not claim recovery of the absent historical MASTER_SPEC. README and
  architecture/API/retrieval/deployment/evaluation documentation reflect actual
  behavior and limitations. CI includes real Redis/RQ tests, browser behavior
  tests and the Compose failure-path/SSE smoke.

### Actual checks

- Full pytest suite on Python 3.12.14: **130 passed, no skips, 2 warnings**, final
  run 25.00 seconds. Integration tests used dedicated PostgreSQL 17/pgvector
  0.8.2 and Redis 7.4.2, not SQLite. They exercised real FTS/vector/filter SQL,
  graph routing, transaction/concurrency boundaries, acknowledgement loss,
  actual RQ child exit and stop, and terminal SSE interleaving/replay.
  The warnings are RQ's Python 3.12 multi-threaded fork deprecation warnings;
  the exit/stop assertions passed.
- Migration regression: real legacy Paper/Section/Chunk/Run data upgrades from
  0001, retains section/chunk links and dispatch intent, passes `alembic check`,
  rolls back a refused lossy downgrade, and completes downgrade/base/upgrade.
  Its probe database is separate from application/test data and is removed.
- Ruff check: passed. Ruff format check: 106 files already formatted. Strict
  mypy: 53 source files, no errors. `uv lock --check`: resolved 190 packages;
  existing locked package versions were not upgraded. `git diff --check` passed.
- Frontend `npm ci`, Prettier, strict TypeScript and production build passed.
  **6 Playwright browser tests passed**, including filter submission, library
  paging, settings save gating, citation source and native EventSource reconnect.
  The HTTP fixture actually received Last-Event-ID=7; its data/provider responses
  are explicitly MOCK, not proof of model inference.
- Unit-test configuration forces LiteLLM's bundled pricing metadata so an
  isolated SDK test run does not fetch a remote cost map at import time.
  The subsequent standalone unit suite passed: **85 tests in 7.62 seconds**.
- Final backend/frontend images built with the documented cloud CA overlay.
  Backend image: `33cb43c5ec06469a3fe83f57f4ba08f54fbf5264af6d924648055bda7514637a`.
  Compose startup/readiness passed and deployed schema is 0002. Container source
  hash matches the final workspace hash above. `python scripts/smoke.py` passed
  through nginx: readiness, frontend HTTP, empty-index search, real RQ missing-key
  failure and complete terminal SSE replay. This uses no mock production model.
- This environment's VFS Docker driver exhausted disk during one intermediate
  container recreation. Only this task's stopped containers, obsolete images
  and specific build-cache records were removed; named data volumes were kept.
  Final build/start/smoke then passed. Independent test containers and the exited
  one-off migration container were cleaned up; application services remain up.

Tests used the locked core/dev environment in `/tmp/ragagent-review-venv`, with
`PYTHONDONTWRITEBYTECODE=1`, `PYTHONPATH=src:.`, dedicated TEST_DATABASE_URL and
TEST_REDIS_URL, and pytest cache disabled. Network permission for the execution
sandbox was required to allow local sockets and async thread wakeups; unit tests
made no paid calls and downloaded no model weights. Container package installation
is not weight-backed inference. These local checks do not establish a hosted
GitHub Actions result.

### Compatibility and remaining verification

- Existing hosted embedding vectors need rebuilding for the v2 fingerprint;
  default local fingerprints remain compatible. Hosted revision is an operator
  index label, not remote weight pinning. Silent remote weight replacement still
  requires explicit operator action. Previously merged section occurrences cannot
  be reconstructed from existing rows; accurate recovery requires PDF reingestion.
- Real Docling PDF/OCR/table/equation fidelity, end-to-end PDF/model indexing,
  downloaded embedding/reranker inference, real arXiv import and successful
  configured-provider inference remain **UNVERIFIED**. Semantic verification and
  generation evaluation remain model-based and need independent human validation.
- No human-annotated 100-query benchmark, improvement result, production load/
  memory measurement, hosted CI result or comprehensive dependency/model-license
  security certification is claimed. Corpus hashes compare run boundaries, not
  a locked transactional snapshot or an archived complete corpus.
- Trusted local single-user operation, English FTS, exact vector search and
  explicit retry rather than checkpoint resumption remain v1 boundaries.

### GitHub submission — 2026-10-04

The user requested publishing the validated repairs to
`phase-6-evaluation-deployment` through the linked repository owner's GitHub
account. Backend/tests, frontend/deployment/CI and documentation are separate
reviewable commits. Publishing this branch updates its existing stacked PR;
the local verification results above remain distinct from hosted CI outcomes.

### Changed files

- `.env.example`
- `.github/workflows/ci.yml`
- `README.md`
- `compose.yaml`
- `docs/MASTER_SPEC.md`
- `docs/adr/0001-structural-section-identity.md`
- `docs/adr/0002-gated-evidence-and-citation-release.md`
- `docs/adr/0003-versioned-tasks-and-bounded-evidence.md`
- `docs/adr/0004-provider-and-index-identity.md`
- `docs/adr/0005-durable-dispatch-and-terminal-events.md`
- `docs/adr/README.md`
- `docs/agents.md`
- `docs/api.md`
- `docs/architecture.md`
- `docs/data-model.md`
- `docs/deployment.md`
- `docs/evaluation.md`
- `docs/retrieval.md`
- `docs/stage-log.md`
- `evals/retrieval/annotation-template.json`
- `evals/retrieval/schema.json`
- `frontend/.gitignore`
- `frontend/.prettierignore`
- `frontend/package-lock.json`
- `frontend/package.json`
- `frontend/playwright.config.ts`
- `frontend/src/Evaluation.tsx`
- `frontend/src/Knowledge.tsx`
- `frontend/src/Settings.tsx`
- `frontend/src/Tasks.tsx`
- `frontend/src/api.ts`
- `frontend/src/components.tsx`
- `frontend/tests/ui.spec.ts`
- `migrations/env.py`
- `migrations/versions/0002_section_identity_and_job_dispatch.py`
- `pyproject.toml`
- `scripts/annotation_template.py`
- `scripts/smoke.py`
- `src/ragagent/api/app.py`
- `src/ragagent/api/dispatcher.py`
- `src/ragagent/api/evaluations.py`
- `src/ragagent/api/papers.py`
- `src/ragagent/api/providers.py`
- `src/ragagent/api/queue.py`
- `src/ragagent/api/runs.py`
- `src/ragagent/db/dispatch.py`
- `src/ragagent/db/models.py`
- `src/ragagent/domain/documents.py`
- `src/ragagent/evaluation/artifacts.py`
- `src/ragagent/evaluation/generation.py`
- `src/ragagent/evaluation/retrieval.py`
- `src/ragagent/evaluation/schema.py`
- `src/ragagent/graphs/rag.py`
- `src/ragagent/graphs/research.py`
- `src/ragagent/ingestion/chunker.py`
- `src/ragagent/ingestion/parser.py`
- `src/ragagent/ingestion/service.py`
- `src/ragagent/jobs.py`
- `src/ragagent/providers/chat.py`
- `src/ragagent/providers/config.py`
- `src/ragagent/providers/embedding.py`
- `src/ragagent/providers/environment.py`
- `src/ragagent/retrieval/evidence.py`
- `src/ragagent/retrieval/reranker.py`
- `src/ragagent/retrieval/service.py`
- `src/ragagent/runtime.py`
- `src/ragagent/settings.py`
- `src/ragagent/worker.py`
- `tests/integration/conftest.py`
- `tests/integration/test_api.py`
- `tests/integration/test_dispatch.py`
- `tests/integration/test_evaluation.py`
- `tests/integration/test_graph_execution.py`
- `tests/integration/test_ingestion.py`
- `tests/integration/test_migrations.py`
- `tests/integration/test_retrieval.py`
- `tests/integration/test_sse_race.py`
- `tests/integration/test_upload_concurrency.py`
- `tests/integration/test_worker.py`
- `tests/unit/conftest.py`
- `tests/unit/test_chunker.py`
- `tests/unit/test_embedding_endpoint.py`
- `tests/unit/test_evaluation.py`
- `tests/unit/test_generation_evaluation.py`
- `tests/unit/test_graphs.py`
- `tests/unit/test_parser.py`
- `tests/unit/test_reranker.py`
- `tests/unit/test_retrieval.py`
- `tests/unit/test_runtime_configuration.py`
- `uv.lock`


## Scientific review corrections — 2026-10-04

Baseline: `phase-6-evaluation-deployment` at
`a4495d8cbf3142c78a9159c7d87b0629be21a450`. The repair checkout is
`/workspace/RAGAgent-fixes`, local branch `fix-scientific-review`. The checks below
were completed locally before publication. The user subsequently authorized
publishing these repairs to `phase-6-evaluation-deployment` in three reviewable
commits: backend/tests, frontend and documentation. Publication does not include
merging or deployment. GitHub commit history records the published SHAs; hosted
CI outcomes remain separate from the local checks below. The earlier submission
record above describes the baseline history, not this repair pass.

### Review findings addressed

1. Provider YAML is parsed before safe model-only interpolation; secret variables
   and unresolved API templates are rejected. Host/Origin guards and preserved
   proxy Host protect local browser writes (`providers/config.py`, `api/security.py`).
2. Scientific numbers, including leading-dot decimals and Unicode exponent minus,
   remain atomic. Tables retain rows and independently located headers/captions;
   equations and unrecognized table layouts remain atomic (`ingestion/chunker.py`).
3. Every attached claim/evidence pair must receive explicit support, with missing,
   unknown and duplicated pairs failing closed (`retrieval/evidence.py`).
4. arXiv imports freeze canonical `vN`; same-byte versions remain separate.
   Migration 0003 retains unknown legacy versions and source status; both search
   channels exclude manually withdrawn/retracted sources (`ingestion/arxiv.py`,
   `worker.py`, `db/models.py`, `retrieval/service.py`, paper API/UI).
5. Reranking uses the original question/subtask; direct multi-query callers use
   all queries as fallback (`graphs/rag.py`, `graphs/research.py`, `retrieval/service.py`).
6. `python -m ragagent.reindex` atomically reembeds per paper while preserving
   chunk/citation IDs. A failed batch rolls back all changes for that paper;
   dimensions cannot silently change (`ingestion/reembed.py`, `reindex.py`).
7. Local Hub models freeze a real immutable revision before identity/loading;
   local directories hash artifacts and detect changes. Dated chat defaults and
   actual returned model/system identities are recorded (`providers/model_identity.py`).
8. Worker calls checkpoint unknown charges before dispatch and accounted usage
   afterward in a separate database transaction, without committing partial
   indexing. Reused adapters start a fresh Run ledger and release observers.
   Evaluation checkpoints per case and paid-call update, retains failure artifacts,
   resumes only compatible completed rows, and keeps prior-attempt costs separate.
   Frozen evaluation timeouts are shared by RQ and reconciliation (`worker.py`,
   `providers/chat.py`, `evaluation/*`, `jobs.py`, `api/queue.py`).
9. Hosted embedding tokens/costs join worker/evaluation totals; synchronous
   search and provider connectivity responses also return request-level usage.
   Unknown charges remain null rather than becoming zero (`providers/embedding.py`,
   `api/app.py`, `api/providers.py`).
10. Analyzer/verifier/judge inputs include exact quotes once, excluding duplicated
    main and auxiliary content (`retrieval/evidence.py:evidence_payload`).
11. Settings validate overlap versus target before jobs start (`settings.py`).

### Actual verification

- Locked Python dependencies installed with `uv sync --locked` into `.venv`;
  checks used that same environment directly, avoiding cache permission issues.
- `.venv/bin/ruff format .`, final `ruff format --check .` and `ruff check .`:
  passed, 125 Python files formatted.
- `.venv/bin/mypy src`: passed, 57 source files.
- Full `.venv/bin/pytest -q`: **271 passed**, including **60 real PostgreSQL/
  pgvector and Redis/RQ integration tests**; no skips or failures. Two existing
  RQ fork deprecation warnings occurred in process-interruption tests.
- Database migration `alembic upgrade head` reached 0003 in a disposable test
  database. Migration integration tests cover legacy upgrade, retained source
  versions and guarded downgrade.
- New/expanded tests verify numeric boundaries and source offsets, claim/citation
  support pairs, canonical versions/concurrent imports, metadata/status filters,
  multi-query reranking, model identity mocks, hosted fees and request deltas,
  atomic reembedding, rollback, paid failure/interruption checkpoints, observer
  lifetime, partial evaluation/resume and frozen timeout reconciliation.
- `npm ci`, `npm run check`, `npm run build`, `npm run lint`: passed.
  Playwright: **9 passed**, including source status/version, independent table
  context offsets and separate limitations. Browser tests use MOCK HTTP/SSE.
- `nginx:1.28.0-alpine nginx -t` with the actual nginx configuration: passed.
  `docker compose config --quiet` with synthetic example configuration: passed;
  the temporary `.env` copy was removed. No application Compose stack was started.
- `python -m ragagent.reindex --help` and `git diff --check`: passed.
- Model/provider tests use scripted mocks or an intercepted SDK transport with
  offline model/cost-map settings. Network permission was needed for local IPC,
  test PostgreSQL/Redis and Docker; no paid provider or model-weight download was
  used. Disposable test services and temporary config are not a deployment.

### Limits and required operator work

- Real Docling extraction of scientific PDFs, real embedding/reranker/model
  inference, provider billing totals, adversarial prompt resistance, human gold
  evaluation and the complete application image/deployment remain unverified.
  Passing mocks/contracts is not a scientific benchmark or release acceptance.
- The environment did not provide approved Hugging Face metadata/weight access;
  no default SHA was guessed. Cross-process reproduction requires the actual
  recorded SHA, cached weights/provider access and an annotated evaluation corpus.
- Existing local fingerprints require migration and explicit reembedding. Old
  chunks do not gain corrected numeric cuts or missing table/paragraph context
  from reembedding; rebuild from original PDFs with new relevance annotations.
  The upload API reuses matching checksums and has no in-place rechunking route;
  use a separate fresh corpus/database while retaining the original corpus.
- Source status stays unknown until manually verified. There is no automatic
  retraction feed, and old completed reports do not refresh after status edits.
- Synchronous search/provider-test usage exists in responses only; reindex
  usage exists in stdout only. Lost responses/stdout or process termination
  cannot recover those fees from the persistent worker/evaluation ledger.
- Evaluation resumes completed cases/modes, not interrupted graph internals;
  timeouts bound duration, not currency. Shared/public deployment authentication
  and backend non-root/container hardening are not implemented by this repair.

### Changed files

- `.env.example`
- `README.md`
- `config/agents.yaml`
- `docker/nginx.conf`
- `docs/adr/0006-review-corrections.md`
- `docs/adr/README.md`
- `docs/agents.md`
- `docs/api.md`
- `docs/data-model.md`
- `docs/deployment.md`
- `docs/evaluation.md`
- `docs/retrieval.md`
- `docs/stage-log.md`
- `frontend/src/Knowledge.tsx`
- `frontend/src/Tasks.tsx`
- `frontend/src/api.ts`
- `frontend/src/components.tsx`
- `frontend/tests/ui.spec.ts`
- `frontend/vite.config.ts`
- `migrations/versions/0003_paper_source_identity.py`
- `src/ragagent/api/app.py`
- `src/ragagent/api/evaluations.py`
- `src/ragagent/api/papers.py`
- `src/ragagent/api/providers.py`
- `src/ragagent/api/queue.py`
- `src/ragagent/api/schemas.py`
- `src/ragagent/api/security.py`
- `src/ragagent/db/models.py`
- `src/ragagent/domain/documents.py`
- `src/ragagent/domain/research.py`
- `src/ragagent/evaluation/artifacts.py`
- `src/ragagent/evaluation/generation.py`
- `src/ragagent/evaluation/retrieval.py`
- `src/ragagent/evaluation/schema.py`
- `src/ragagent/graphs/rag.py`
- `src/ragagent/graphs/research.py`
- `src/ragagent/graphs/state.py`
- `src/ragagent/ingestion/arxiv.py`
- `src/ragagent/ingestion/chunker.py`
- `src/ragagent/ingestion/parser.py`
- `src/ragagent/ingestion/reembed.py`
- `src/ragagent/ingestion/service.py`
- `src/ragagent/jobs.py`
- `src/ragagent/providers/chat.py`
- `src/ragagent/providers/config.py`
- `src/ragagent/providers/embedding.py`
- `src/ragagent/providers/model_identity.py`
- `src/ragagent/reindex.py`
- `src/ragagent/retrieval/evidence.py`
- `src/ragagent/retrieval/reranker.py`
- `src/ragagent/retrieval/service.py`
- `src/ragagent/settings.py`
- `src/ragagent/worker.py`
- `tests/integration/test_evaluation.py`
- `tests/integration/test_graph_execution.py`
- `tests/integration/test_migrations.py`
- `tests/integration/test_reembed.py`
- `tests/integration/test_source_identity.py`
- `tests/integration/test_usage_persistence.py`
- `tests/unit/test_api_accounting.py`
- `tests/unit/test_api_security.py`
- `tests/unit/test_arxiv_source.py`
- `tests/unit/test_chunker.py`
- `tests/unit/test_citation_pairs.py`
- `tests/unit/test_embedding_usage.py`
- `tests/unit/test_evaluation.py`
- `tests/unit/test_evaluation_accounting.py`
- `tests/unit/test_generation_evaluation.py`
- `tests/unit/test_graphs.py`
- `tests/unit/test_job_timeout.py`
- `tests/unit/test_model_identity.py`
- `tests/unit/test_multiquery_retrieval.py`
- `tests/unit/test_parser.py`
- `tests/unit/test_provider_config_security.py`
- `tests/unit/test_reranker.py`
- `tests/unit/test_retrieval.py`
- `tests/unit/test_runtime_configuration.py`


## Product upgrade: local conversations and desktop (2026-10-06)

Added formal Conversation/Message/Summary/Memory persistence, Alembic 0004,
idempotent conversation APIs, atomic worker/message terminal transitions, safe
cancellation and late-response usage accounting. Contextualization remains above
the separate evidence-first RAG/Research graphs: bounded recent context, lossy
local rolling extracts, explicit intersected filter memories and source-linked
query rewrites never become scientific Evidence.

The shared React UI now supports durable chats, Markdown/citations, folding
research details, memory management, paginated history, restart/SSE recovery and
retry/cancel. Tauri adds a scoped fixed-loopback Rust request/SSE/file bridge,
with bounded cancellation bookkeeping and native health/offline handling. The
new conversation evaluator executes actual context/graphs/retrieval/verification
and a separate judge; four dimensions and partial/resume accounting are exposed.

Final review repaired visible/submitted filter mismatch, failed draft release,
late desktop cancel capacity leakage, impossible minimum input budgets, historical
comparison-winner narrowing, credential-shaped values in context filters and
conversation evaluation payloads, and rewriting over an independently checkpointed
usage ledger. Added regressions retain the existing assertions.

### Actual validation

- `.venv/bin/ruff format --check .`, `ruff check .`, `mypy src`: passed.
- Full `pytest -q` with real PostgreSQL/pgvector and Redis/RQ: 461 passed
  (360 unit + 101 integration), 23.90 seconds; two upstream RQ fork deprecation
  warnings in deliberate real child-exit/stop tests. No skipped integration tests.
- `npm ci`, `npm run lint`, `check`, `build`: passed. System Chromium Playwright:
  26 passed (original 9 retained + 17 chat scenarios); transport tests: 8 passed.
- Cargo fmt/check/clippy with warnings denied, locked dependencies, Rust tests:
  7 passed; `npm run desktop:build`: release native binary built.
- Actual native `--check-backend`: local_backend_ready. Actual Xvfb/DBus GUI
  `--smoke-test`: desktop=true, root/loaded=true, backend-status ready, exit 0.
  Debian WebKit dependencies were extracted and relocated only in a temporary
  sysroot; system files and WebKit sandbox were not altered.
- Docker frontend/backend image builds and Compose configuration/migration/ready
  checks: passed. `python scripts/smoke.py` verifies real missing-key RQ failure,
  proxied terminal SSE, persisted conversation/message association, idempotency
  and explicit memory/history deletion. No paid inference or downloaded weights.
- A temporary 32 GB VFS validation environment filled during repeated image
  builds/container copies; test build cache/outdated test images were reclaimed
  and affected build checks rerun. No repository source or user data was deleted.

### Practical limitations

Scripted providers and synthetic corpus fixtures test the production mechanics,
not real-model scientific accuracy. Human gold datasets, genuine model inference
and measured quality/cost gains remain unverified. Windows/macOS packaging/signing,
physical operating-system IME behavior and OS PDF viewer interaction were not
tested. Context budgeting is a conservative byte estimate for rewrite input,
not an actual tokenizer reading or currency cap. Summary is lossy; deletion does
not erase backups or independent desktop PDF cache copies. Remote inference still
sends necessary text to the configured provider. The JS bundle has a size advisory.

The requested 13-part handover is in [product-upgrade-report.md](product-upgrade-report.md).

Published review branch: `feature/desktop-conversations`, stacked on
`phase-6-evaluation-deployment`. Remote backend commit
`0a4a073cbf671850986394cd72b82ced626183a5` and UI/desktop commit
`e0042c1c43c0b1f66f89a1aed5d584e1231a211a` have Git tree hashes matching the
corresponding fully tested local commits. The actual-model, real-paper native
multi-turn/restart/Research acceptance scenario remains unverified.

GitHub's backend, frontend and Compose jobs also passed on the published head.
Publication caught a Desktop workflow configuration error before any job started:
`runner.temp` is unavailable in job-level `env`. Its test-only `DATA_DIR` now uses
an isolated Linux runner's `/tmp/ragagent-desktop-data`; application code and
the verified native build are unaffected.
Actionlint 1.7.7 reproduced the original context error and passed both workflows
after this change, without further YAML/expression findings.

### Changed files

- `.dockerignore`
- `.env.example`
- `.github/workflows/desktop.yml`
- `README.md`
- `docs/adr/0007-local-conversations-and-desktop.md`
- `docs/adr/README.md`
- `docs/api.md`
- `docs/architecture.md`
- `docs/conversation-memory.md`
- `docs/data-model.md`
- `docs/deployment.md`
- `docs/evaluation.md`
- `docs/product-upgrade-report.md`
- `docs/stage-log.md`
- `evals/conversation/README.md`
- `evals/conversation/annotation-template.json`
- `evals/conversation/demo.json`
- `evals/conversation/schema.json`
- `frontend/.prettierignore`
- `frontend/package-lock.json`
- `frontend/package.json`
- `frontend/src-tauri/.gitignore`
- `frontend/src-tauri/Cargo.lock`
- `frontend/src-tauri/Cargo.toml`
- `frontend/src-tauri/build.rs`
- `frontend/src-tauri/capabilities/main.json`
- `frontend/src-tauri/icon.svg`
- `frontend/src-tauri/icons/128x128.png`
- `frontend/src-tauri/icons/128x128@2x.png`
- `frontend/src-tauri/icons/32x32.png`
- `frontend/src-tauri/icons/64x64.png`
- `frontend/src-tauri/icons/Square107x107Logo.png`
- `frontend/src-tauri/icons/Square142x142Logo.png`
- `frontend/src-tauri/icons/Square150x150Logo.png`
- `frontend/src-tauri/icons/Square284x284Logo.png`
- `frontend/src-tauri/icons/Square30x30Logo.png`
- `frontend/src-tauri/icons/Square310x310Logo.png`
- `frontend/src-tauri/icons/Square44x44Logo.png`
- `frontend/src-tauri/icons/Square71x71Logo.png`
- `frontend/src-tauri/icons/Square89x89Logo.png`
- `frontend/src-tauri/icons/StoreLogo.png`
- `frontend/src-tauri/icons/icon.icns`
- `frontend/src-tauri/icons/icon.ico`
- `frontend/src-tauri/icons/icon.png`
- `frontend/src-tauri/permissions/local-api.toml`
- `frontend/src-tauri/rust-toolchain.toml`
- `frontend/src-tauri/src/bridge.rs`
- `frontend/src-tauri/src/main.rs`
- `frontend/src-tauri/tauri.conf.json`
- `frontend/src/Evaluation.tsx`
- `frontend/src/Knowledge.tsx`
- `frontend/src/Memory.tsx`
- `frontend/src/Tasks.tsx`
- `frontend/src/api.ts`
- `frontend/src/components.tsx`
- `frontend/src/main.tsx`
- `frontend/src/style.css`
- `frontend/src/transport.ts`
- `frontend/tests/chat-fixtures.ts`
- `frontend/tests/chat.spec.ts`
- `frontend/tests/transport/transport.test.ts`
- `frontend/tests/ui.spec.ts`
- `frontend/vite.config.ts`
- `migrations/versions/0004_conversations_and_memory.py`
- `scripts/smoke.py`
- `src/ragagent/api/app.py`
- `src/ragagent/api/conversations.py`
- `src/ragagent/api/evaluations.py`
- `src/ragagent/api/queue.py`
- `src/ragagent/api/runs.py`
- `src/ragagent/conversations/context.py`
- `src/ragagent/conversations/service.py`
- `src/ragagent/db/models.py`
- `src/ragagent/domain/conversation.py`
- `src/ragagent/domain/conversation_context.py`
- `src/ragagent/evaluation/conversation.py`
- `src/ragagent/evaluation/conversation_schema.py`
- `src/ragagent/jobs.py`
- `src/ragagent/settings.py`
- `src/ragagent/worker.py`
- `tests/conftest.py`
- `tests/integration/test_conversation_evaluation.py`
- `tests/integration/test_conversation_migration.py`
- `tests/integration/test_conversation_worker.py`
- `tests/integration/test_conversations.py`
- `tests/integration/test_migrations.py`
- `tests/unit/test_conversation_context.py`
- `tests/unit/test_conversation_contracts.py`
- `tests/unit/test_conversation_evaluation.py`

## Bilingual README (2026-10-06)

Retained `README.md` as the English edition and added a complete Simplified Chinese
edition in `README.zh-CN.md`, with reciprocal language links at the top. Both
editions cover the same eight sections, commands, API examples, architecture and
scientific/data-handling limitations. Code examples and Mermaid diagrams remain
identical across editions.

Changed files: `README.md`, `README.zh-CN.md`, `docs/stage-log.md`.
Targeted checks passed: eight matching sections, seven identical fenced code
blocks, preserved original documentation links, valid relative link targets and
reciprocal language navigation; `git diff --check` passed. This is a documentation
change, so application tests were not rerun locally.

The preceding implementation head `670cc5f0ffdc873b1cfc2e91828e15f7d0a5896d`
also completed GitHub's PR-triggered CI and Desktop workflows successfully
(runs `37417995238` and `37417995251`). This does not change the recorded gaps in
real-paper/actual-model scientific acceptance or platform packaging validation.


## Engineering hardening — Phase 1 (2026-10-07 UTC)

Comparison support now checks distinct source-grounded entities and explicit
semantic claim/citation support, including comparisons within one paper. Retry
attempts keep their audit rows while superseded attempts leave subsequent context
and persisted summaries; migration 0005 preserves legacy data. Conversation
deletion commits revocation/deletion before best-effort RQ cancellation. Existing
transactional Run/Message/outbox and late-worker ownership guards remain in use.

Changed files: domain research/conversation/context contracts; database Message
model and migration 0005; conversation API/context/service; independent RAG and
Research graph/state; evidence validation; comparison, retry-context, concurrency,
delete and migration regressions; ENGINEERING_REVIEW.md and this stage log.

Actual checks: Ruff format --check (151 files), Ruff lint, mypy (64 files), full
Python tests on PostgreSQL 17.10/pgvector 0.8.2 and Redis (504 passed, 3 upstream
warnings); npm ci/lint/check/build, 8 transport tests, 26 Playwright tests; Rust
fmt/locked check/clippy -D warnings, 7 Rust tests, Linux Tauri native release build.
Canonical Compose config and frozen-dependency image build passed. Full Compose
startup failed with the managed environment's 32 GB VFS disk quota; DB/Redis health
passed, API health/ready NOT EXECUTED. Cleanup retained database volumes. Windows,
actual product GUI and actual-model scientific acceptance NOT EXECUTED. Commands,
initial evidence and remaining Phase 2–8 scope are in ENGINEERING_REVIEW.md.

The concurrent retry regression drains the real durable reconciliation path before
asserting exactly one queue submission, and repeats reconciliation to verify
idempotency. This retains the strict enqueue-count assertion when immediate
skip_locked dispatch legitimately waits for another transaction. Migration tests
resolve Alembic's current head and preserve legacy schema/data assertions.


## Engineering hardening — Phase 2 (2026-10-08 Asia/Shanghai)

Lightweight MessageSummary/RunSummary projections and the latest-50/before/after
ordinal API replace embedded full results. Single-message reconciliation handles
status updates at an unchanged ordinal; explicit legacy offset remains supported.
Conversation active IDs use one batch query. Bounded display metadata keeps only
final supported citation references, never quote/trace/draft text. Run details stay
available through GET /api/runs/{id} and are loaded on demand.

Tasks now uses history/message/composer/result components and separate message/SSE
hooks. Healthy SSE has no periodic message-history poll; reconnection/resume and
lost-final-event recovery read only new messages and active placeholders. Retry
audit attempts remain collapsible. Both English and Chinese README editions were
updated with identical behavior, along with API/data-model documentation.

Actual checks: Ruff format/lint, mypy (65 source files), 522 Python tests with real
PostgreSQL/pgvector and Redis; npm ci/lint/check/build, 8 transport tests and 28
Playwright tests (all original 26 retained); Rust fmt/check/test/clippy with locks
(8 tests), and Linux Tauri release build passed. Compose config and frontend image
build passed. Backend image rebuild/full Compose health/ready NOT EXECUTED because
the environment's proven 32 GB VFS quota left insufficient space for its 2 GB
backend image/containers. Windows and real-model scientific acceptance NOT
EXECUTED. Raw before benchmarks and the repeatable measurement script are kept
in docs/benchmarks and scripts; after measurements will follow this implementation
commit so the manifest identifies the code actually tested.

Phase 2 measurement follow-up: actual before/after fixture hashes matched for all
18 original shapes. RAG full 100 rows: 5,108,941 → 93,241 bytes; SELECT 102 → 2;
heavy Run-result SELECT 100 → 0; median 93.346 → 7.449 ms. The new latest-50,
older-page, one-row/empty incremental shapes are separately labeled. Before 270
and after 630 raw samples are committed; these measure PG/ASGI API performance
on explicit synthetic fixtures, not browser rendering or model retrieval quality.

## Engineering hardening — Phase 3 (2026-10-08 Asia/Shanghai)

Added shared durable queue routing, immutable per-Run queue names, validated
queue settings and one-workload worker CLI. Compose/cloud CA overlay now runs
independent interactive, ingestion and evaluation workers; scaling/legacy drain
instructions and both READMEs updated. `/api/queues` reports each workload;
`/api/ready` requires DB/Redis and interactive worker registration.

Changed settings/queues/jobs, RQ transport, worker, API readiness/diagnostics,
Compose/env/docs and real integration/unit tests. Real RQ/PG occupancy probe
completed interactive scripted RAG while evaluation remained running, then
released evaluation; single-trial raw result is explicitly synthetic, not a
model quality or capacity benchmark.

Ruff format/lint PASS, mypy 66 sources PASS, full Python real PG/Redis **534 passed**;
frontend npm ci/lint/check/build, **8 transport / 28 Playwright** PASS;
Rust fmt/locked check/test/clippy, **8 passed / 0 ignored**. Compose config PASS.
Backend image build/full Compose health/ready NOT EXECUTED: VFS/32 GB quota,
less than 1 GB available. Windows and real-model manual acceptance NOT EXECUTED.

Phase 3 Linux Tauri `npm run desktop:build`：PASS，实际 release 编译 1m21s；未测 Windows 或产品窗口。

## Engineering hardening — Phase 4 (2026-10-08 Asia/Shanghai)

Added deterministic bilingual standalone gate, stable relevance Top-K Selected
Memory separate from Stored Memory, all-hard-filter merging, multilingual
approximate input estimation and independent recent/summary/memory subbudgets.
A new typed `conversation_states` table (migration 0006) persists source-linked
intent/entities alongside the extractive summary. Original eligible entity
sources survive restart even after summary clipping; superseded/deleted sources
cannot be restored. Mutation/clear lifecycle invalidates derived state; Memory
panel/API expose it. Both README editions, memory/deployment/architecture/API
contracts and `.env.example` match the new behavior.

Preserved all false-history/false-memory scientific evidence assertions; made
those questions explicit pronoun follow-ups to keep testing the rewritten path
now that independent questions skip it. Source-linked state never enters
analyst/reviewer Evidence. All migrations remain incremental.

Actual 50/100 messages x English/Chinese x 100 memories probes ran both frozen
baseline and working implementation, 15 samples per case, matched shared-field
fixture hashes, source SHA-256 and raw timing/input records in docs/benchmarks.
Baseline returns explicit budget exceeded; selected/bounded current requests
construct successfully. No LLM/scientific quality measurement is inferred.

Ruff format/lint/mypy PASS; real PG/Redis Python **558 passed**, 3 upstream warnings;
npm ci/lint/check/build PASS; **8 transport / 28 Playwright** PASS;
Rust fmt/locked check/test/clippy **8 passed / 0 ignored**;
Linux Tauri release build PASS (1m23s); Compose config PASS. Local image build and
full health/ready NOT EXECUTED due VFS/32 GB quota. Phase 2 GitHub Compose checks
succeeded separately; this does not establish Phase 4 runtime success. Windows
and actual multilingual models/manual science acceptance NOT EXECUTED.

## Engineering hardening — Phase 5 (2026-10-08 Asia/Shanghai)

Added an offline licensed real-model matrix and JSON manifest schema requiring
three language directions, operator-supplied human gold/translation provenance,
consistent paper metadata and local immutable/license identities. It reuses the
existing retrieval evaluator in a unique scratch schema and cleans it afterward;
no production indexes/models are rewritten. Missing weights return Not measured
and null metrics before DB/model access. Direction metrics disclose failed counts.

Actual real-model measurement blocked: proxy CONNECT Hugging Face 403, optional
torch/sentence_transformers absent, approved human gold and weight directories
not supplied. Current/candidate/both/pretranslation 5x3 status artifact retains
null metrics and unverified candidate licenses/revisions. Defaults unchanged.
This does not complete real multilingual quality acceptance.

Ruff format/lint/mypy 68 sources PASS; real PG/Redis **566 passed**, 3 warnings;
frontend npm ci/lint/check/build, **8 transport / 28 Playwright** PASS;
Rust fmt/locked check/test/clippy **8 passed / 0 ignored**; Linux native Tauri build
PASS (1m29s); Compose config PASS. Local image build/full health/ready NOT EXECUTED
(VFS quota); Windows/real-model acceptance NOT EXECUTED for this version.

One original comparison test failed because a random UUID contained the string
500. Fixed only fixture paper/section/chunk identities, retaining every assertion;
full rerun passed. Scripted benchmark-contract tests are explicitly not real model
metrics. Changed evaluation/provider benchmark helpers, CLI, fixture/probe tests,
README editions, schema/status/usage docs and this report/log.


## Engineering Phase 6 — Local authentication and privacy (2026-10-08 Asia/Shanghai)

Changed: api/auth/app/schemas/papers, centralized privacy guards, provider config,
evaluation contracts/CLIs, native keyring/bridge, AuthPanel/transport, bilingual
README/deployment/env/CI, explicit authorized test clients and new regressions.
OS-native credentials; nonsecret verifier pairing; fail closed; all private API,
SSE/download routes authenticated; ephemeral Web HttpOnly sessions; no raw bearer
in frontend persistent storage/config. Four actual LiteLLM adapters with scripted
failure checked through real PG Run, terminal SSE and logs. Existing assertions
retained when test clients gained headers.

Actual checks: Ruff format/lint, mypy 70 sources; real PG/Redis **591 passed**
(3 upstream warnings); npm ci/lint/type/build, **8 transport + 29 Playwright**;
Rust fmt/check/test/clippy locked, **9 passed, 0 ignored**; Linux native release
build PASS (1m48s); Compose config PASS. Local Docker build/full health/ready
NOT EXECUTED (VFS/32 GB quota); remote phase-specific CI pending. Windows system
credential test is Windows-only and NOT EXECUTED locally; no actual model inference.


## Engineering Phase 7 — Windows and artifact provenance (2026-10-08 Asia/Shanghai)

Changed Windows CI/installer manifest, native build metadata/IPC, packaged backend
identity and safe no-Git fallback, aligned Python/Web/Desktop version 0.2.0,
nonroot backend and persistent writable config mount, bilingual docs and explicit
upgrade ownership/import instructions. No DB/model/config volume deletion.

Actual: Ruff format/lint/mypy 71 sources; uv lock + sync --locked; real PG/Redis
**593 passed** (3 upstream warnings); npm ci/lint/type/build, **8 transport +
29 Playwright**; Rust fmt/check/test/clippy locked **9 passed, 0 ignored**;
Compose config PASS. Local full Docker image/health/ready NOT EXECUTED (VFS quota).
Windows build is launched by publishing this phase; result/installer artifacts
need separate actual evidence. Windows 11 human installation NOT EXECUTED;
unsigned installers, no signing claim. Linux native release build PASS (1m33s).

### Phase 7 Windows CI correction (2026-10-08 Asia/Shanghai)

Actual first Windows run 37745437701 / job 113205680558 failed at Prettier:
30 tracked text files acquired CRLF on Windows checkout; all later build/test
steps were skipped, not passed. Add .gitattributes enforcing LF for auto-detected
text without weakening/ignoring formatter checks. Linux Desktop and CI/Compose
run 37745437745 on source 1f4f0a6bc0ba22f1f3880a9661ab4758e614e261 succeeded.
Installer success remains unverified until the corrected Windows job runs.

## Engineering Phase 8 — Evidence UX, diagnostics and final review (2026-10-08 Asia/Shanghai)

Changed claim/evidence optional original code-point ranges and verified fallback;
frontend Unicode-safe original slicing, automatic-evidence terminology and PDF
manual target-page guidance; protected diagnostics/build metadata; safe error
payloads/Swagger Bearer and recovery messages; native SSE 401 stops reconnecting
and prompts pairing. Fixed confirmed New Chat race by clearing old draft before
asynchronous creation, preserving newly typed input with delayed-response test.
Bilingual README maintained; final ENGINEERING_REVIEW A–L/A–K evidence recorded.
CI extends config PUT smoke and lossless old root-owned volume owner migration.

Actual: Ruff format/lint/mypy 72 sources; real PG/Redis **604 passed** (3 upstream
warnings); npm ci/lint/type/build, **10 transport + 32 Playwright**; Rust fmt/locked
check/test/clippy **9 passed, 0 ignored**; Linux Tauri release build **PASS (1m48s)**;
Compose config PASS. Local Docker image/full health/ready NOT EXECUTED (VFS quota);
phase-specific remote results are separate. No real-model quality/gold made up.
Windows 11 human installation/chat/restart/uninstall NOT EXECUTED, signing absent.
Windows CI OS Credential Manager test passed; installer build pending at this record.

Remote af1d2cad CI backend/Compose passed; one frontend test failed in async New Chat
because new draft could be cleared. This phase fixes production behavior and adds
deterministic slow-response regression; original assertions/timeouts retained.


### Final remote implementation evidence (2026-10-08 Asia/Shanghai)

Head f803d824432108cfd4bc4c4771b6764b96010cda / tree
8246aad106e5d648b258f81a78c378935a829e5b: CI 37747840466 backend/frontend/Compose
all success, including nonroot config writes and lossless application volume
owner migration followed by real ready/smoke. Desktop 37747840471 Linux window/
loopback smoke and Windows MSI/NSIS build/upload all success. Windows 10 Rust tests
passed (0 ignored), including real OS Credential Manager round trip.

Downloaded artifact 11536936513 and independently recalculated ZIP and both
MSI/NSIS file sizes/SHA-256; all match generated manifest/GitHub digest. Raw evidence
in docs/validation/windows-artifacts-f803d824.json. Actual PR checkout merge commit
a1737fcfeeb05a2b81c80c7d6f3ed91403cbb5bf has identical source tree to head, verified
using Git; provenance records actual checkout. This is CI build evidence only;
Windows 11 human install/chat/restart/uninstall and real-model quality remain
NOT EXECUTED/Not measured. Evidence-only documentation follow-up changes no code.

### Repository migration preparation (2026-10-08 Asia/Shanghai)

Source: chouytong/RAGAgent `fix/engineering-hardening`, commit
df75bdd011fe81a18c58609792e1a9a3536f5969, tree
3299629a66baafbe23cddf6bcc2461b2acc727e8. Completed the shallow clone into
its full 29-commit ancestry; Git object integrity check passed. Prepared a
separate migration copy for maczhouyi-del/RAGSystem with `main` as
the final-code branch. Preserved original authors, commits, license and historical
CI/artifact evidence; changed only both README clone instructions and this log.
No runtime code, configuration, lockfile or workflow changes; no deployment.

The owner created and supplied the empty public target repository RAGSystem;
its default branch is `main`. At preparation time, account metadata reported
push/admin permissions, but actual Git pushes returned 403 and a contents-API write returned
`Resource not accessible by integration`. The target account's GitHub App
installation list was empty. No remote write had succeeded; the target was empty
pending effective integration authorization. The original repository and its
main/engineering branch heads were read and remained unchanged. Verification
at that stage covered Git history/tree integrity and documentation consistency;
remote equality still required a successful transfer. No new application test,
CI success or completed migration was claimed in that preparation record.

### Repository migration completed (2026-10-08 19:37 Asia/Shanghai)

After the owner installed/authorized the GitHub App for maczhouyi-del, Git push
to RAGSystem/main succeeded. Initial published commit
3796cf0e06d2dcaef242b08d124878d28b74eef9 / tree
3fcf7b6cfc354c835f2c76b981c8ecbe628dacab was independently cloned from GitHub.
Full Git integrity checks passed; all 29 original source commits, IDs, authors,
messages and ancestry were preserved in native Git history. Remote commit/tree
matched the prepared local copy. Runtime code, configuration, dependency locks
and workflows match source df75bdd exactly; only bilingual README clone links
and this migration log differ. This completion record is a documentation-only
follow-up; English and Simplified Chinese README editions are retained.

The original chouytong/RAGAgent repository remains unchanged: remote main
616d93b9124de353206bd25766d7031c28c4a92d and fix/engineering-hardening
df75bdd011fe81a18c58609792e1a9a3536f5969 were rechecked. No PR was merged and
no deployment was performed. New-repository CI 37771216180 and Desktop
37771216216 were triggered and were still running at this record; their success
is not claimed. Historical CI/installers remain linked to the original runs.


## Product improvement TASK-00 — baseline audit (2026-10-08 Asia/Shanghai)

Started from fetched RAGSystem/main a8d5c1f0ace08573c5e5787bf5eef39570405191
on codex/research-product-improvement. Documentation/evidence only; no business,
test, dependency, migration or workflow changes. Added
`docs/product-improvement/BASELINE.md`, `PROGRESS.md`, `task-00-evidence.json`
and this stage entry. All TASK-01–19 remain NOT_STARTED.

Fresh locked install, Ruff format/check, mypy (72 sources), isolated migration
upgrade/downgrade/upgrade and pytest: 604 passed (463 unit, 141 integration;
zero skipped/failures/errors), one upstream Alembic warning. Frontend npm ci,
lint/check/build passed; Playwright 32 and transport 10 passed. Database is
dedicated test ragagent, separate from application ragagent_dev; Redis tests
use DB 15. No application data downgrade/reset.

Live public GitHub summaries for baseline SHA confirm CI 37771426122
(backend/frontend/compose) and Desktop 37771426070 (Windows/Linux) SUCCESS.
Current Windows artifact 11547938987 exists, unsigned; GitHub-reported archive
digest recorded, not independently downloaded/rehashed in this task. Real
Windows 11 installation and paid-model scientific QA NOT EXECUTED; scientific
quality and multilingual/RAG-vs-Research gains NOT MEASURED. No new tests were
needed for a documentation-only audit. TASK-00 commit CI remains pending until
recorded in the new progress/evidence files.

TASK-00 CI follow-up: baseline commit d238275e3e49c392c5907bf218ffda57161b3a13
pushed; draft PR https://github.com/maczhouyi-del/RAGSystem/pull/1 created.
Push CI 37782711529 SUCCESS; PR CI 37782769354 backend pytest FAILURE,
frontend/compose SUCCESS; PR Desktop 37782769337 Windows/Linux SUCCESS.
Exact failed test UNKNOWN: gh run log and REST job-log downloads denied by
results-receiver.actions.githubusercontent.com / productionresultssa17.blob.core.windows.net.
Required domains saved in environment draft; runtime access not established.
No speculative flaky-test attribution, no blind rerun, no test/source changes.
TASK-00 BLOCKED pending log access and diagnosis; TASK-01 remains NOT_STARTED.


### TASK-00 baseline test false positive recovery (2026-10-09 Asia/Shanghai)

Original PR CI logs are now retrievable. The sole failure in run 37782769354
was test_false_local_history_and_memory_cannot_supply_scientific_answer[research]:
correct 120-participant prose, but the citation UUID contained 5009 and triggered
the whole-string 500 exclusion. Analyst/reviewer serialized IDs had the same risk.
Changed only tests/integration/test_conversation_worker.py and the TASK-00
BASELINE/PROGRESS/evidence files plus this log. No runtime, API, schema or lock change.
A fixed chunk/Evidence UUID containing 500 reproduces both modes' old failures;
updated assertions validate citation identity and retain scientific-text exclusion.
Worker file: 6 passed. Negative-control leaked scientific text: 2 intentional
failures, confirming both guards remain effective. Full locked sync, Ruff format/check,
mypy: PASS; pytest 604 passed (463 unit / 141 integration, zero skipped), 1 upstream
warning, 30.70s. Fix-commit CI pending; TASK-00 IN_PROGRESS, TASK-01 NOT_STARTED.

TASK-00 recovery accepted: fix 09c29113bad0df7225e7d0f7e88b21bcd89a7de0.
Push CI 37882246737 and Desktop 37882246783; PR CI 37882251101 and Desktop
37882251036 all completed SUCCESS, exact head SHA verified via GitHub REST.
TASK-00 PASSED; TASK-01 remains NOT_STARTED. This evidence-only follow-up
preserves the earlier 603-pass/1-failure log diagnosis and the deterministic
red/green and negative-control checks. Scientific quality NOT MEASURED;
Windows 11 manual installation NOT EXECUTED. No production or dependency changes.

## TASK-01 环境检查与启动诊断（2026-10-09）

- 修改：跨平台只读脚本、标准库诊断/离线测试/可执行平台 smoke、既有 diagnostics 的知识库与依赖状态、Windows/Linux CI 步骤、README/诊断说明/进度和证据。没有 .env、数据库迁移、依赖锁或模型下载修改。
- 验证：Ruff format/check、mypy 72 文件通过；614 项 pytest（0 skipped）通过；Linux 合成 launcher 与真实 API/PG/Redis/三个 RQ worker 诊断通过；配置哈希未变，模型调用为 0。完整记录见 task-01-evidence.json。
- 待办：本任务 push/PR CI 与 Windows 两种 PowerShell 实际执行；不能在此门禁前开始 TASK-02。缺主机 Python/授权时给出具体恢复建议；真实科研质量和 Win11 人工安装未测。

- TASK-01 平台验证：`238403a6438c1d838e7e4f99afb35c440fe1d3d2` 的全部十个 CI check run 和四个 workflow 的全部 job SUCCESS；Windows 两种 PowerShell、MSI/NSIS 及 Linux 原生 smoke 均成功；uv locked sync 109 包通过。PR CI run 37884520894 汇总仍 in_progress，与已结束成功的三个 job 不一致；如实保留状态，不重新运行洗绿，暂不开始 TASK-02。证据提交仅记录实际验证与差异。

- TASK-01 最终验收：验证提交 `9e650ae837011ce0298546a6409a0cfa2e4c452b` 的 push CI 37885297371 / Desktop 37885297374、PR CI 37885301335 / Desktop 37885301369 四个 workflow 全部 completed/SUCCESS，SHA 和全部 job 已匹配。原实现 PR 汇总未结束的观察保留，不猜测其状态，没有失败检查被重跑。TASK-01 工程 PASSED；自动开始 TASK-02。验收提交只保存证据。

## TASK-02 首次使用引导（2026-10-09）

- 修改：新 FirstUseGuide 读取连接/授权/Diagnostics；复用 AuthPanel、Settings、Knowledge 与 RAG；main 集成、响应式步骤 CSS、Diagnostics corpus 展示、授权后的旧聊天夹具与 7 项新 Playwright、首次使用文档/进度/证据。没有后端、Rust、迁移、依赖锁或记忆/会话协议修改。
- 实际验证：npm ci/lint/check/build、39 项 Playwright（0 skipped、41.5s）、10 项 transport（0 skipped）通过；合成 UI 截图已检查。测试明确 MOCK HTTP/SSE；未执行真实 PDF 解析、付费 API、科研质量、Win11 人工操作。
- 保留失败：旧 fixture 缺诊断路由造成 12 项聊天失败，补齐模拟后原断言通过；超时场景 1 failed/38 passed，修复取消/超时 busy 与离线自动轮询，完整重跑 39 pass。详见 task-02-evidence.json，没有删测试或降低断言。
- CI 待对应提交的实际检查；用户已授权通过后自动开始 TASK-03。

- TASK-02 验收：实现 `088e8be7a12b6d1f0fbbb9c33fdabe448e39ac0b` 的 push CI 37886916945 / Desktop 37886916939、PR CI 37886921280 / Desktop 37886921287 四个 workflow 全部 completed/SUCCESS，完整 SHA 与所有 job 已匹配。39 项浏览器/10 transport 本地通过、Linux 原生 GUI smoke 和 Windows MSI/NSIS CI 通过；工程 PASSED。真实科研质量/Win11 人工 GUI 仍未测，按授权自动开始 TASK-03。

## TASK-03 可复现科研验收框架（2026-10-09）

- 修改：复用 Evaluation；新增 domain 金标/审核契约、source_v1 验证、真实 corpus 来源核验、数值 Decimal PostgreSQL JSON 入队、legacy hash 兼容、adapter 分类及离线逐例检查/人工审核/配对比较；新增脚本与 31 项测试、文档/进度/证据。未改依赖锁、迁移、前端或 Rust bridge。
- 验证：Ruff format/check、mypy 74 文件 PASS；645 pytest（496 unit / 149 integration、0 skipped、30.80s）PASS，1 项已有 Alembic warning；四个 audit CLI 和七份未标注 source_v1 表单 PASS。来源测试使用真实 PG；输出审核/比较是 SYNTHETIC ONLY，不代表科研表现。
- 保留失败：首轮新增 fixture Claim.statement 与真实 text 契约不符导致 16 failed/93 passed，修正 fixture 后完整回归 PASS，没有删除断言。
- 边界：物理 PDF 页/语义支持必须人工检查；未知费用为空；原失败保留，未审核不记零；无真实金标/模型请求/Win11 人工 GUI；科学质量 NOT MEASURED。实际实现 CI 待核对，通过前不进入 TASK-04。

- TASK-03 验收：实现 `b77c04157a03309484b6a62a7071b5add14b893b` 的 push CI 37890505110 / Desktop 37890505103、PR CI 37890510399 / Desktop 37890510395 全部 completed/SUCCESS，完整 SHA 和全部 job 已匹配。645 项本地测试、Windows MSI/NSIS 与 Linux 原生 smoke 通过；工程 PASSED，科学质量 NOT MEASURED；自动开始 TASK-04。后续仅文档提交保存证据。

## TASK-04 文献搜索、排序和分页（2026-10-09）

- 修改：domain 搜索参数、兼容旧数组的 /api/papers/search 与按页批量 response、created_at 字段、db 七个索引及 0007/pg_trgm 迁移、Knowledge 筛选/总数/排序/分页、Web/受限 Rust Unicode 查询、214 篇 PG/浏览器/transport/bridge 测试、README/使用文档/进度/证据。未改依赖锁、PDF、Embedding 或科学检索协议。
- 实际验证：Ruff format/check、mypy 75、npm ci/lint/check/build PASS；672 pytest（496 unit / 176 integration，0 skipped，36.44s）、43 Playwright（49.7s，0 skipped）和 11 transport PASS；真实迁移升级/降级/重升及 Alembic check PASS；官方校验下载的 rustfmt 1.90 format/check PASS；三种 GIN access path EXPLAIN 可用，仅强制索引可用性，不是性能测量；截图已检查。
- 保留失败：初次浏览器 2 failed/41 passed（新 select 可访问名称不明确），补 aria-label 后完整回归通过；mypy column 变量复用类型冲突，改为 sort_column 后通过。未删断言。
- 限制：跨请求集合变化会移动 offset；大库普通索引迁移需维护窗口/磁盘/扩展权限；共享 pg_trgm 降级保留；实际大库性能/科研质量 NOT MEASURED，Win11 人工 GUI NOT EXECUTED。本提交 Rust 编译/原生 smoke/安装包由实际 CI 验证，待通过前不进入 TASK-05。

- TASK-04 验收：`5e59f1bd8851da0551b2c5b31bb004b93bc6fc9f` 的 push CI 37892156284 / Desktop 37892156271、PR CI 37892160891 / Desktop 37892160910 四个 workflow 全部 completed/SUCCESS，完整 SHA 与所有 job 已核对；Rust check/test/clippy、Windows MSI/NSIS、Linux 原生 GUI smoke PASS。uv locked sync 109 包 PASS；本任务工程 PASSED，自动进入 TASK-05；科研质量/真实大库性能/Win11 人工 GUI 未测。TASK-03 文档验收提交 bdefa45 的四个 workflow 同样已全部 SUCCESS。

## TASK-05 文献元数据修改（2026-10-09）

- 修改：domain 初始来源契约、Paper 原始元数据/乐观版本/人工维护字段、0008 迁移与有损降级保护、既有 PATCH 原子版本核对和只更新变更字段、上传/Atom 字段捕获、独立编辑窗口/来源展示/失败草稿保留/冲突重载、PG/API/来源/迁移/浏览器覆盖和文档/进度/证据。未改依赖锁、Rust bridge、原始 PDF、chunk/section/vector 或模型调用流程。
- 实际验证：uv locked sync 109、Ruff format/check、mypy 75、npm ci/lint/check/build PASS；687 pytest（496 unit / 191 integration、0 skipped、39.59s）、47 Playwright（0 skipped、47.4s）和 11 transport PASS；真实迁移/模型检查/有损降级拒绝与回滚 PASS；截图已检查。两个真实 PG session 同版本编辑仅一个成功，另一个 409。
- 修正记录：初次 mypy 持久化字典需 domain 验证；两段长 SQL 字面量拆行；显式未知 origin 存为 JSON null 的只读探针揭示错误降级阻塞，改 none_as_null=True 并加入 SQL NULL 断言，完整回归通过。没有删断言。
- 边界：旧来源未知，不伪造官方值；upload 源为用户输入，Atom 测试响应是 scripted，不是联网验真；旧无版本 PATCH 不具备陈旧意图保护，新 UI 全部带版本；数据保护降级不能绕过。科学质量/Win11 人工 GUI/付费模型未测。实际实现 CI 待核对，TASK-06 未开始。TASK-04 仅验收文档 736d3a7 的四个 workflow 已全部 completed/SUCCESS。

- TASK-05 验收：`5c288748342f2c782c934c5c1deb36687903e1e4` 的 push CI 37894376600 / Desktop 37894376697、PR CI 37894379794 / Desktop 37894379810 四个 workflow 全部 completed/SUCCESS，完整 SHA 与所有 job 已核对；Windows MSI/NSIS 与 Linux 原生 GUI smoke PASS。687 后端/47 浏览器/11 transport 本地 PASS；工程 PASSED，按授权自动进入 TASK-06；真实科学质量/Win11 人工 GUI 未测。

## TASK-06 安全文献删除后端（2026-10-09 Asia/Shanghai）

- 开始：`ec4fc99c1a5ddf0c20c033fd2a5408c51183f29f`；此前 TASK-05 文档验收提交的 push CI 37895505460 / Desktop 37895505473、PR CI 37895509178 / Desktop 37895509171 全部 completed/SUCCESS，完整 head 匹配。
- 改动：domain 删除确认/预览/状态契约；0009 tombstone/file manifest/Run 清理账本及有损降级保护；DELETE 事务去除 Paper 与级联 PDF 派生数据/向量/Evidence/实体 occurrence，关联孤立作者/实体子类型删除，共享数据保留；Run/outbox ingestion 队列异步清理，明确幂等/失败新 Run 重试；受管路径/摘要/no-follow 文件清理；历史 Run/事件/消息来源脱敏和当前引用验证失效，正文/真实历史状态保留；模型等待后的解析/Embedding/重排/arXiv/事件/最终输出/评测文件保护；评测实际来源 ID checkpoint；GET/PATCH/retry 410 与导出禁止。未改前端、Rust、锁文件，未引入新队列或模型调用。
- 验证：新增 15 unit / 15 integration；真实 PostgreSQL 和 Redis queued/started RQ job stop、短事务迟到 barriers、共享/孤立元数据与另一论文/会话保留、确认/版本冲突无写入、注入事务失败全部回滚、部分文件失败与新 Run 重试、受管替换/越界/符号链接不误删、历史引用/原文/金标脱敏、导出之外用户文件保留、非空删除账本有损 downgrade 拒绝。最终 717 passed（511 unit / 206 integration，0 skipped/failures，48.34s，1 上游 warning）；Ruff/mypy 82/Alembic check/uv locked 109/npm ci/lint/check/build PASS。
- 初次完整 11 failed / 706 passed：终态保护新读取触发过期属性自动 flush，修复 no_autoflush 范围；既有单位/PG 替身需支持新增 scalar/scalars/constructor keyword，保持原断言；受影响 66 passed/1 failed 时剩余评测构造替身未收 keyword，修正后最终全绿。专项首次 SSE fixture 使用独立连接被外层 TRUNCATE 锁阻塞，终止该测试进程并改测试依赖共享连接；随后错误路由比较 request_id、fixture 注册、description 缺字段均修正。没有靠删除断言或盲目重跑洗绿。
- 影响：数据库提交后当前知识库立即不可见，清理状态独立；停止消息最终消费不保证同步，但已撤销 worker DB 所有权，RQ callback 不覆盖 cancelled。文件已清理不随 DB rollback 恢复，缺文件可幂等继续。实际 checkpoint 追踪可识别金标之外来源，旧消息即使缺 Run 也有当前来源失效标记。
- 限制：全历史脱敏扫描会暂停来源发布，未测大库延迟；当前 POSIX 文件描述符后端，Windows 桌面通过 Docker/Linux，原生 Win Python 未支持；历史回答/用户问题/摘要可能留有论文事实或引用正文，独立桌面 documents 缓存、外部阅读器/下载/备份/同步/provider 留存需人工管理，恢复旧备份须再应用删除记录。科研质量与人工 Win11 GUI 未测。TASK-07 实现引用可用性显示和删除确认 UI，本任务无前端改动。
- 状态：IN_PROGRESS；实际 GitHub CI 待推送和核对，不能提前 PASSED。
- 独立实现：`da9ba0d24404ca7a72d1712bf32bca03c18caacc` 已推送；push CI 37914217426 / Desktop 37914219092、PR CI 37914222359 / Desktop 37914222404 真实运行，head SHA 匹配；backend/frontend/compose SUCCESS，Desktop 待最终验收。
- 云实例更新：运行的任务自有旧服务无进行中作业；应用库保留一条 failed Run/零论文，schema 0006→0009 无损升级，重启 API/三个 worker/web 后公共 health/ready 成功。没有触发模型请求；读取独立进程私有 runtime token 被拒，改用公共检查，不声称额外受保护本地 smoke 已执行；本地 TestClient 和实际 CI 的受保护 API 验证仍成立。
- TASK-06 验收：`da9ba0d24404ca7a72d1712bf32bca03c18caacc` 的 push CI 37914217426 / Desktop 37914219092、PR CI 37914222359 / Desktop 37914222404 全部 completed/SUCCESS，完整 SHA 和十个实际 job 已核对；Rust/Windows MSI/NSIS/Linux 原生 GUI smoke PASS。717 后端本地 PASS，工程 PASSED；保存验收后自动执行 TASK-07。真实科研质量/Win11 人工 GUI 未测。
- 后续协议接入检查发现 TASK-06 消息失效 metadata 更新遗漏 updated_at，会允许客户端将迟到的旧快照覆盖新失效状态。TASK-07 尚无代码变更，先补修 TASK-06：消息根级 unavailable 标记兼容无 presentation 历史，时间戳严格推进（兼容回退时钟）。PG 原用例增加有/无 Run 时间推进断言，新增无 presentation/回退时钟来源变更的 API 断言，正文和历史执行状态仍保留；前端未改。原 717 全量补修回归 PASS（40.13s），新用例加入后再次全量待最终记录/CI；工程状态临时 IN_PROGRESS，不能提前继续 TASK-07。
- 原验收文档提交 `769e10026379da246283fadb5e88b113d6d2aa78` 的 push CI 37914979351 / Desktop 37914979320、PR CI 37914987178 / Desktop 37914987240 全部 completed/SUCCESS、完整 SHA 匹配；此事实不代替补修提交的门禁。
- 消息协议补修最终本地验证：718 passed（511 unit / 207 integration，0 skipped/failures，43.27s，1 上游 warning），Ruff format/check / mypy 82 PASS。无 schema/锁/前端变更；补修提交待核对四个实际 workflow。

- TASK-06 CI 恢复：补修 `c1f1e3a6024cdec0202ad5266125027d76fa17d1` 的 PR CI 37916026331/backend 113772289585 是真实 FAILURE（1 failed/717 passed），push CI 37916020890、push Desktop 37916020892、PR Desktop 37916026190 SUCCESS，其余九个 job 均成功。官方 gh --log-failed 已取得具体日志；未重跑抹去失败。既有会话评测扫描引用 UUID 数字导致记忆隔离假失败；新增五个确定性控制，原代码 1 failed/4 passed，修复只排除当前来源的引用标记，正文/未知或畸形引用/裸 UUID 仍检查、原始输出保留。真实 PG RAG/Research 固定 chunk 得到含 500 Evidence UUID，两模式确认当前证据身份且正文无 500。必要 CI 恢复修改 evaluation/conversation 与对应单位/PG/检索 fixture；无前端/schema/锁变更。专项 87 passed，最终全量 723 passed（516 unit/207 integration，0 skipped/failed，42.17s），Ruff format/check 和 mypy 82 PASS；状态仍 IN_PROGRESS，等待新实现实际 CI，TASK-07 尚未开始。

- TASK-06 最终补修验收：`f8640d091d895dd7c19ecd230f21bedbf4b12f48` 的 push CI 37917294006 / Desktop 37917294017、PR CI 37917298835 / Desktop 37917299180 四个实际 workflow 全部 completed/SUCCESS；四个完整 head SHA 与十个 job 核对。后端/前端/Compose、Rust check/test/clippy、实际 Windows MSI/NSIS、Linux GUI smoke PASS。723 本地后端测试 PASS；先前 c1f1e3 的 PR failure 仍保留。TASK-06 工程 PASSED，记录验收后按用户授权自动进入 TASK-07；科学质量 NOT MEASURED、Win11 人工 GUI NOT EXECUTED。

## TASK-07 文献删除 UI（2026-10-09 Asia/Shanghai）

- 开始 commit：f00374859eb629a445e55102cf3c71e978b742e6；TASK-06 恢复 f8640d0 与仅验收文档 f003748 四个精确 SHA workflow/十个 job 均 completed/SUCCESS；f003748 runs 37917954357/37917954320/37917961856/37917961675。
- 修改：Knowledge 删除按钮与中央 native modal，只读最新元数据/范围版本核对、明确副本 ACK、取消/Escape 零写入/提交中防重复；已移除与清理完成分离、可见页面五秒只读状态、安全失败指导/显式 queued/failed/cancelled 清理重试、未知结果对账不重放；最近二十 UUID 只读提示恢复，不保存凭据/原文/请求/任务。历史根级/presentation/Run/Evidence 来源失效显示、非交互失效引用/他文献 PDF 保留，逐引用 fresh Run、版本取消旧详情/缓存/事件与旧引用窗口；返回窗口最多五十显示引用消息核对。Rust 仅四个固定 UUID 协议白名单与正负控制，transport DELETE 确认体与 POST 空对象保持；文档/进度/证据。无后端/迁移/依赖/锁变更。
- 新增 14 Playwright、1 transport、1 Rust 路由控制，覆盖预览失败/取消/ACK/冲突/失联提交对账/未提交失败/清理失败新 Run/重载只读/其他文献会话/缓存失效/真实 request abort/迟到旧消息页完成/旧无 presentation 消息/提交中保护/状态服务失败。原缓存测试改为仅打开单个 Run 的每次 fresh 读取，不移除科学断言。
- 实际验证：npm ci/lint/check/build PASS，最终 61 Playwright PASS（0 fail/skip，58.9s）、12 transport PASS；已校验官方 Rust 1.90 rustfmt/--check PASS。先专项 13 PASS、完整 58 PASS、扩展专项 14 PASS/完整 61 PASS，截图揭示长内容 footer 需滚动，改固定可见操作区并加 viewport 断言后最终 61 PASS；没有靠跳过或重跑失败洗绿。CLI prettier 首次错误 cwd 不匹配文件，修正 cwd 后 lint 全量 PASS。
- 限制：浏览器是明确 MOCK HTTP 契约，真实检索/DB/RQ/文件保护由 TASK-06 实际验证；存储禁用/清空/换客户端/超过二十时不保证提示自动恢复，服务器账本不受影响；不周期性全历史同步；独立缓存/备份与历史正文需自行管理。本地 Cargo 未安装，实际 native 编译/测试/clippy/安装包/smoke 必须由新提交 CI 证明。科研质量 NOT MEASURED、人工 Win11 GUI NOT EXECUTED。
- 状态：IN_PROGRESS；实现尚未提交、实际 CI NOT EXECUTED。TASK-08 NOT_STARTED。

- TASK-07 验收：`d7807ef695faf525100ee9489fea5c15e0267df1` 的 push CI 37919686500 / Desktop 37919686626、PR CI 37919693641 / Desktop 37919693605 全部 completed/SUCCESS；完整 head SHA、四个 workflow、十个 job 已核对。实际 backend/frontend/Compose、Rust format/check/test/clippy、Windows MSI/NSIS 和 Linux native GUI smoke PASS。最终本地 61 browser/12 transport PASS；TASK-07 工程 PASSED，验收记录后自动进入 TASK-08。浏览器是 MOCK HTTP；科学质量 NOT MEASURED、Win11 人工 GUI NOT EXECUTED。

## TASK-08 批量 PDF 导入（2026-10-09）

- 修改：domain/API 回执、详情最新 Run 指针和 pending Run 重试复用；PdfImports/Knowledge/API/error/style，9 项 MOCK 浏览器与真实 PG 并发/回执断言，旧单篇 fixture，文档/进度/证据。无依赖锁、迁移、Rust 或新任务系统修改。
- 验证：uv locked sync 109 包，Ruff format/check、mypy 82、npm ci/lint/check/build PASS；724 pytest（516 unit /208 integration，0 skipped，67.72s），70 browser（0 skipped，报告 1.2m）/12 transport PASS；截图 PASS。真实 PostgreSQL，未使用 SQLite。
- 修复：14 全响应比较失败来自 list/detail 新指针差异，统一详情 fixture 并核对真实回执 ID，保留完整字段保护断言；恢复行 generation undefined/0 导致 1 browser 失败，统一默认值后完整 PASS。平台认证短暂 401，后续 API/Git 读取恢复，无凭据提取或绕代理。
- 边界：浏览器 scripted 完成不证明模型/解析质量；历史查询性能、峰值内存、科研质量 NOT MEASURED，Win11 人工 GUI NOT EXECUTED。TASK-08 实现 CI 待实际提交检查，TASK-09 NOT_STARTED。

- TASK-08 验收：`b8a4d3bc4b06323528af085c096354c8c9a77d37` 的 push CI 37922681767 / Desktop 37922681780、PR CI 37922686606 / Desktop 37922686602 四个 workflow 和十个 job 全部 completed/SUCCESS，完整 SHA 核对；实际 Windows MSI/NSIS、Rust format/check/test/clippy、Linux GUI smoke PASS。云环境加载新代码、API/Web/三 worker ready，保留开发数据、无模型请求。工程 PASSED，自动进入 TASK-09；科研质量和 Win11 人工验收仍未测。

## TASK-09 论文分组与标签（2026-10-09）

- 修改：domain 组织契约/UUID 范围，PaperCollection/Member 与 0010 迁移、目录/关系 API，论文列表及 dense/lexical scope；Collections/Knowledge/FilterEditor/API 显式方法、Rust 受限路由/查询，真实 PG/图/浏览器/transport/bridge 覆盖与文档/证据。无依赖锁或第二任务系统修改，不复制 PDF/vector/Evidence。
- 验证：locked sync 109、Ruff format/check、mypy 84、npm ci/lint/check/build、官方 rustfmt、真实升级/模型 check/有损降级拒绝/重升 PASS；749 pytest（525 unit /224 PG、0 skipped、63.65s）、82 browser（报告 1.2m、0 skipped）/13 transport PASS；最终截图检查。
- 保留失败：首轮 browser 5/6、第二轮 3/8；pending checkbox 与旧发送 locator 修正，实际 api bodyless PUT/DELETE 被改 GET 的错误修复，服务器读回确认断言保留。Ruff SQL 长行/局部导入组修复。没有跳过或移除测试。
- 边界：当前检索快照成员范围，名称版本不冻结关联数；大库性能/真实模型科研质量未测，Win11 人工 GUI 未执行；MOCK HTTP 不证明真实科研表现。本任务实际 CI 待提交；TASK-10 未开始。

- TASK-09 验收：48e89dd8fa24d4e458d188292fd5ab660252e370 的 push CI 37925725221 / Desktop 37925725238、PR CI 37925731577 / Desktop 37925731446 四个实际 workflow/十个 job completed/SUCCESS，完整 SHA 核对。Rust/Windows MSI/NSIS/Linux GUI smoke PASS；749 后端、82 MOCK 浏览器、13 transport 本地 PASS。工程 PASSED，自动进入 TASK-10。TASK-17 真实评测资源经用户确认未备妥，科学质量和 Win11 人工验收仍未测。

## TASK-10 实体标注状态可视化（2026-10-09）

- 开始：626f7886a63c08fc47e188274f95923c2262714f，前置四个精确 SHA workflow/十个 job SUCCESS。0011 审阅覆盖/原文摘要、五状态/历史链接不自动 completed；分页实体与原文来源读、共享过滤谓词范围计数与零匹配/部分覆盖说明；固定 native 路由，不调用模型、不启动抽取、不修改源文献/证据或新建队列。
- 验证：Ruff/mypy 86/locked sync 109/npm ci/lint/check/build/官方 rustfmt PASS；真实 PG 专项 17、迁移 2、删除恢复专项 9 PASS；完整 browser 91（MOCK HTTP，1.3m）/transport 14 PASS，截图已查看。最终 Python 增加删除回归正在验证，实际 CI 待提交。
- 失败保留：新导航定位与旧 preview 端口占用已修复；旧会话 fixture 未模拟覆盖查询导致真实 401 授权切换，修正 MOCK 并保留全部科学/过滤断言；新增删除 fixture 提交后刷新已删除 ORM Chunk，先保留 IDs，专项 PASS。格式/SQL 行长/类型注解修正，没有跳过测试。状态与严格条件不可满足不是实体科学不存在证明。
- 当前状态 IN_PROGRESS；TASK-11 未开始。真实模型抽取质量、真实科研质量/人工 Win11 GUI 未测量，用户确认 TASK-17 真实资源未备妥。

- TASK-10 最终本地后端：768 passed（534 unit /234 integration、0 skipped/failed、54.90s），Ruff format/check 与 mypy 86 PASS；退役来源 410 和审阅 CASCADE 实际验证。最终前端 91 MOCK browser/14 transport PASS，构建/格式/type PASS，官方 rustfmt PASS。状态 IN_PROGRESS，等待新实现四个实际 workflow/十个 job 门禁。

- TASK-10 验收：57bb3b5c979e5cf90264ed9ae8b2ad7a1022e7a0 的 push CI 37930288053 / Desktop 37930288107、PR CI 37930293477 / Desktop 37930293482 四个实际 workflow/十个 job completed/SUCCESS、完整 SHA 与实际 native 步骤核对。768 后端/91 MOCK browser/14 transport 本地 PASS；实际 Windows MSI/NSIS/Linux GUI smoke PASS。工程 PASSED，自动进入 TASK-11。真实科研/模型抽取质量和 Win11 人工验收仍未测；用户确认 TASK-17 真实资源未备妥。

## TASK-11 实体提取与人工校正（2026-10-09）

- 开始 09233791235a586592942d28b7c281a2f838c461；TASK-10 实现 57bb3b5 四个精确 SHA workflow/十个 job 全部 SUCCESS。采用本地来源标签规则产生候选、精确跨度和人工确认；严格链接仅在确认后写入，不全局改名其他论文，复用 Run/outbox/ingestion 队列，零模型 API 调用。分析中，功能和验证尚未实现；实际模型质量 NOT MEASURED。

- TASK-11 后端初稿：0012 候选/版本/精确来源/待审阅，offline extractor 协议与 worker 分批来源锁/既有 Run 路由，确认/拒绝/校正/明确全类型审阅及 legacy source 校验；前端/native 尚未实现。单位 15 PASS、真实 PG 专项 8 PASS，mypy 91/后端 Ruff 初步 PASS，非完整验收。首轮 worker 2 FAIL 因过期属性导致待终态自动 flush，发布前 refresh 修复后 2 PASS；扩展 6 PASS/2 FAIL 是 fixture 未提交导致 API rollback 移除未提交来源，正确持久化测试准备后 8 PASS。原文/Embedding/Evidence 不修改，来源同名校正不全局改名、源删除取消 annotation Run，无模型调用。

- TASK-11 完整后端：797 passed（549 unit /248 PG、0 skipped/failed、116.39s），真实两个连接并发只创建一个 Run/outbox 与实际 Redis/RQ worker 零模型执行；原文 Unicode 跨度、别名分别确认、严格 dense/lexical、局部旧链接移除/审阅重复安全、退役取消/级联/迟到保护和 0012 兼容迁移 PASS。前端初次完整88 PASS/7 FAIL：旧 summary 匹配嵌套面板六项、删除说明新增实体提取一项，修正具体定位/说明并保留原行为断言。专项模拟事件3/1后用 mouseup4 PASS；专项命令目录笔误记录并校正。当前完整浏览器复验及实际 CI 未完成，IN_PROGRESS。

- TASK-11 最终本地：797 后端（549 unit /248 real PG、0 skipped/failed）、95 MOCK browser（1.4m、0 skipped/failed）/15 transport 全部 PASS。实际 Redis/RQ worker 与两个独立数据库连接并发、0012 迁移兼容/有损降级拒绝/重升/模型 check PASS；Ruff/mypy91/locked sync/npm ci/lint/check/build/官方 rustfmt PASS。独立提交后须四个精确 SHA workflow/十个 job SUCCESS；科研模型质量仍 NOT MEASURED。

- TASK-11 验收：25f4ff06398638cf179ba7727b4a9ee48a5fe237 的 push CI 37940255984 / Desktop 37940255892、PR CI 37940261144 / Desktop 37940261151 四个 workflow/十个 job completed/SUCCESS、完整 SHA 和实际 native 步骤已核对。797 后端/95 MOCK browser/15 transport 本地 PASS；实际 Windows MSI/NSIS/Linux GUI PASS。云 schema0012、API/Web/三 worker ready，旧开发 Run 保留，无付费/模型调用。工程 PASSED，自动进入 TASK-12；真实模型抽取质量及科研质量 NOT MEASURED，Win11 人工验收 NOT EXECUTED。

## TASK-12 更精确 PDF 来源定位（2026-10-09）

- 开始1e505d4；前置TASK-11精确实现SHA四个workflow/十个job全部SUCCESS。检查Docling锁定上游的provenance/bbox/charspan语义，计划兼容保存Element→Chunk→Evidence原始区域和缺失降级，Evidence ID不变。调研中，尚未实现与验证；不调用付费模型。

- TASK-12 本地后端：824 passed（573 unit/251 PG、0 skipped/failed，75.53s），新增24 unit/3 PG；保持稳定 Evidence ID 与真实向量/全文过滤隔离。Ruff/mypy92/locked sync/Alembic check0012/npm ci/lint/check/build/transport15/官方 rustfmt PASS。实际生成两页 PDF，锁定 Docling NativePdfPipeline 产出12来源元素/3块，0模型调用、未下载模型，PDF原页已渲染检查。几何只为元素导航提示；旧 JSON/无 provenance 有效文本仍可读。完整浏览器和精确实现 CI 待完成，状态 IN_PROGRESS；上游许可证/坐标语义/wheel SHA256 已核对，真实布局/OCR/科研质量 NOT MEASURED。

- TASK-12 完整前端：97 MOCK browser PASS（1.4m），含2个旧 Run 可选坐标损坏回归。修复前正确定位的2个负向控制均失败，修复后全量成功；原始错误定位运行单独保留，不作产品缺陷证据。静态检查/构建/15 transport PASS，待精确实现 SHA CI。

- TASK-12 初始实现3449f8e 的 push CI37945304885：823 passed/1 failed（Research比较追问）。原 fixture把整个证据JSON中的500当错误人数；新PDF provenance SHA256随机含500而误判。固定含500的两个论文digest使RAG/Research原断言均确定性失败，修正只排除经64hex校验的pdf_sha256，保留所有其他科学/元数据字段，生产digest仍完整保留。相关15 integration PASS；独立负向控制确认错误500原文/标题与伪造digest被拒绝。完整后端正在重跑，不重跑旧失败CI洗绿，TASK-13门禁保持关闭。

- TASK-12 修正后完整后端824 passed，0 skipped/failed，67.78s；Ruff/mypy92/locked sync PASS，前端实现未变，既有97 browser/15 transport结果继续适用。初始四个 workflow已completed：push CI1失败、其余3 SUCCESS，9/10 job成功，原生步骤实际成功；全部保留，修正提交将重新触发完整门禁。

- TASK-12 验收：c55c15867ab5e3647ace294527ab28dade0c7cdc push CI37946282912 / Desktop37946282951、PR CI37946292019 / Desktop37946292211四个 workflow/十个 job completed/SUCCESS，完整SHA与native实际步骤已核对。824后端/97 MOCK browser/15 transport本地PASS，真实生成两页PDF来源链验证成功、0模型调用。原失败及固定含500 digest复现/科学错误负向控制保留；旧开发Run及schema0012不变。工程PASSED，自动进入TASK-13；实际布局/OCR/科研质量NOT MEASURED，Win11人工NOT EXECUTED。

## TASK-13 引用与 PDF 阅读（2026-10-09）

- 开始于TASK-12验收提交3cc1c70，前置c55c158四个实现workflow/十个job全部SUCCESS。决定复用受限外部PDF阅读路径，无新PDF解析/worker依赖，不降低CSP或文件/远程WebView/API安全边界。可靠原文支持跨度在原文面板标记；元素框仅为页候选，不作逐字PDF高亮。状态IN_PROGRESS，验证尚未执行。

- TASK-13 实现与本地：831后端（576 unit/255 PG、0 skipped/failed、198s）PASS，新增3 unit/4 PG，包括真实原PDF字节/摘要/论文路由读取；33专项 browser/15专项Python PASS，新增10 browser与1transport。锁定安装/Ruff/mypy92/npm ci/lint/check/build/16transport/官方rustfmt PASS。页可用性贯通引用/实体面板与列表，未知页不假装p.1；多来源/表格辅助页独立、原文Unicode支持跨度核对后标记，受限Desktop/Web路径复用，无新依赖/CSP权限变化。首次全量106browser PASS/1旧p.6–6文案断言FAIL，改成真实p.6后重跑完整回归；初始类型/ORM字段拼写错误及修正保留。工程IN_PROGRESS，CI待产生，科研/布局正确率NOT MEASURED，Win11系统阅读器人工NOT EXECUTED。

- TASK-13 最终前端：107 MOCK browser PASS（1.5m、0 failed/skipped）、16 transport PASS，npm lint/check/build成功。原表格页码标签断言按p.6修正，原文/来源/版本/辅助页检查保留。最终截图已检查，上方原始PDF入口可见，表格原文数字不变；实际系统阅读器人工操作仍NOT EXECUTED。待精确实现CI门禁。

- TASK-13 验收（2026-10-10 Asia/Shanghai）：dd023de01cf22a2b020df1891b4e781813302665 push CI37950083681 / Desktop37950083661、PR CI37950089001 / Desktop37950089060四个 workflow/十个 job completed/SUCCESS，完整SHA及实际native步骤已核对。831后端/107 MOCK browser/16 transport本地PASS，真实PG/API原PDF与页可用性验证PASS。云schema0012、API/Web/三worker ready，原有开发Run保留、0实际模型调用。工程PASSED，自动进入TASK-14；系统阅读器Win11人工操作NOT EXECUTED，科研/布局识别质量NOT MEASURED。

## TASK-14 结构化科研报告（2026-10-10 Asia/Shanghai）

- 开始2c0e798，TASK-13精确SHA四个workflow/十个job全部SUCCESS。扩展现有AnalysisResult及Reviewer语义校验，不增加自由生成Agent；报告字段只引用Claim，原文字面值必须在该来源引文中，缺失与明确未报告区分。旧图20 PASS，初稿mypy5个局部变量复用类型错误已修复；完整回归及实现CI待执行，状态IN_PROGRESS。

- TASK-14 首次完整：857 PASS/1 FAIL（116.48s），旧RAG记忆隔离测试把随机PDF摘要中的500当人数。固定摘要500+61零使两模式旧断言均确定性FAIL；共享测试oracle只剔除已校验64hex源摘要和来源ID字段的完整UUID，保留原文/问题/Claim/普通元数据与非来源digest，原摘要在生产payload保留。新增11个负向/身份控制；57专项PASS。初步新报告22unit/2PG与旧图共44PASS；新增3报告边界测试；109全量MOCK browser/16transport PASS，截图已检查。初次浏览器JSON模块缺import attribute导致0test启动失败，修复后2专项执行PASS；报告表格连续行格式审查修正，无断言删除。完整后端复验及实现CI待完成，IN_PROGRESS。

- TASK-14 最终本地：869 passed（612 unit/257 real PG，0 skipped/failed）、109 MOCK browser/16 transport、locked sync/Ruff/mypy94/npm ci/lint/check/build/官方rustfmt PASS；新增38后端与2浏览器，旧数值/过滤/Reviewer失败重试/记忆隔离保留。实际科研模型与人工金标仍未执行，等待独立实现精确SHA CI。

- TASK-14 工程验收：63dddba45edea005d3997626c71e0bc320c63470 push CI38018734225 / Desktop38018734359、PR CI38018737804 / Desktop38018737776 四个workflow/十个job completed/SUCCESS，完整SHA及实际native步骤已核对。869后端（612 unit/257 PG）、109 MOCK browser/16 transport PASS；云schema0012、API/Web/三worker ready、旧开发Run保留、0模型调用。工程PASSED，自动进入TASK-15。实际论文人工案例/Win11人工操作NOT EXECUTED，科研质量NOT MEASURED，用户已确认资源未备妥。
