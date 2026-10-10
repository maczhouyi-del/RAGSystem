"""Real PostgreSQL source/filters; scripted models, DEMO ONLY, not a benchmark."""

import pytest
from sqlalchemy.orm import Session

from ragagent.deletion.history import SourceIds, redact
from ragagent.domain.reports import ReportField, StudyObservation
from ragagent.domain.research import (
    Claim,
    ClaimEvidencePair,
    ClaimVerdict,
    MetadataFilter,
    QueryPlan,
    VerificationResponse,
)
from ragagent.graphs.research import build_research
from ragagent.graphs.state import AnalysisResult, MultiAgentState, ResearchPlan, SubTask
from ragagent.providers.chat import MockProvider
from ragagent.retrieval.service import HybridRetriever
from tests.integration.test_retrieval import Embedder, FixtureReranker, populate


@pytest.mark.integration
@pytest.mark.parametrize("bindings_verified", [True, False])
async def test_pg_research_report_respects_source_scope_and_current_review(
    empty_db: Session, bindings_verified: bool
):
    pid, cid = populate(empty_db)
    filters = MetadataFilter(paper_ids=[pid])
    retrieval = HybridRetriever(empty_db, Embedder(), FixtureReranker())
    actual = await retrieval.search(QueryPlan(queries=["contrastive training"], filters=filters))
    item = actual.evidence[0]
    analysis = AnalysisResult(
        claims=[
            Claim(
                claim_id="method", text=item.quote, aspect="method", evidence_ids=[item.evidence_id]
            )
        ],
        observations=[
            StudyObservation(
                row_id="experiment",
                paper_id=pid,
                fields={
                    "method": ReportField(
                        state="reported",
                        claim_ids=["method"],
                        source_literal="Contrastive training",
                    )
                },
            )
        ],
    )
    review = VerificationResponse(
        question_answered=True,
        report_bindings_verified=bindings_verified,
        verdicts=[ClaimVerdict(claim_id="method", supported=True, reason="MOCK source")],
        supported_pairs=[ClaimEvidencePair(claim_id="method", evidence_id=item.evidence_id)],
    )
    plan = ResearchPlan(
        objective="method",
        required_aspects=["method"],
        subtasks=[
            SubTask(
                task_id="t", question="method?", aspect="method", queries=["contrastive training"]
            )
        ],
    )
    state = MultiAgentState.model_validate(
        await build_research(
            retrieval,
            MockProvider([plan]),
            MockProvider([]),
            MockProvider([analysis]),
            MockProvider([review]),
            max_revisions=0,
        ).ainvoke(MultiAgentState(research_question="method?", filters=filters))
    )
    assert {e.paper.paper_id for e in state.evidence_pool} == {pid}
    assert {e.chunk_id for e in state.evidence_pool} == {cid}
    if not bindings_verified:
        assert state.status == "insufficient_evidence" and state.structured_report is None
        assert item.quote not in state.draft_report
        return
    assert state.status == "completed" and state.structured_report
    report = state.structured_report
    assert report.paper_ids == [pid] and report.evidence_ids == [item.evidence_id]
    assert report.rows[0].fields["method"].text.startswith(item.quote)
    assert report.rows[0].fields["dataset"].state == "evidence_insufficient"
    historical = redact(
        state.model_dump(), SourceIds(papers={pid}, chunks={cid}, evidence={item.evidence_id})
    )
    assert historical["draft_report"] == state.draft_report
    assert historical["source_availability"] == "unavailable"
    assert not historical["review_result"]["validation"]["valid"]
    assert historical["structured_report"]["source_availability"] == "unavailable"
    assert historical["structured_report"]["rows"][0]["fields"]["method"]["source_literal"] is None
    assert (
        historical["analysis_results"][0]["observations"][0]["fields"]["method"]["source_literal"]
        is None
    )
    assert historical["evidence_pool"][0]["quote"] == ""
