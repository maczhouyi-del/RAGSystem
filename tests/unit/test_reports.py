"""DEMO ONLY / NOT A BENCHMARK / NOT MANUALLY ANNOTATED."""

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from ragagent.domain.reports import FIELD_LABELS, ReportField, StudyObservation
from ragagent.domain.research import (
    CitationValidation,
    Claim,
    ClaimEvidencePair,
    ClaimVerdict,
    SearchResult,
    VerificationResponse,
)
from ragagent.graphs.reports import binding_errors, synthesize_report
from ragagent.graphs.research import build_research
from ragagent.graphs.state import AnalysisResult, MultiAgentState
from ragagent.providers.chat import MockProvider
from ragagent.retrieval.evidence import parse_citations
from tests.unit.helpers import evidence
from tests.unit.test_graphs import plan


def report_demo():
    texts = [
        "Alpha uses contrastive training on DemoSet; accuracy 91.5 %; test split; "
        "single GPU. Participant demographics are not reported. Improvement observed.",
        "Beta uses baseline training on DemoSet; accuracy 0.89 fraction; validation split; "
        "CPU. No improvement observed.",
    ]
    sources = []
    facts = []
    rows = []
    for i, text in enumerate(texts):
        source = evidence(f"chunk-{i}", f"00000000-0000-0000-0000-00000000000{i + 1}", f"paper-{i}")
        source.content = source.quote = text
        source.span_end = len(text)
        source.paper.title = ("DEMO Alpha", "DEMO Beta")[i]
        sources.append(source)
        values = {
            "method": ("contrastive training", "baseline training")[i],
            "dataset": "DemoSet",
            "metric": "accuracy",
            "result": ("91.5", "0.89")[i],
            "unit": ("%", "fraction")[i],
            "split": ("test split", "validation split")[i],
            "conditions": ("single GPU", "CPU")[i],
        }
        fields = {}
        for name, literal in values.items():
            cid = f"{i}-{name}"
            facts.append(
                Claim(claim_id=cid, text=literal, aspect=name, evidence_ids=[source.evidence_id])
            )
            fields[name] = ReportField(state="reported", claim_ids=[cid], source_literal=literal)
        if i == 0:
            cid = "0-participants"
            facts.append(
                Claim(
                    claim_id=cid,
                    text="Participant demographics are not reported.",
                    aspect="participants",
                    evidence_ids=[source.evidence_id],
                )
            )
            fields["participants"] = ReportField(
                state="explicit_not_reported",
                claim_ids=[cid],
                source_literal="Participant demographics are not reported.",
            )
        facts.append(
            Claim(
                claim_id=f"{i}-finding",
                text=("Improvement observed.", "No improvement observed.")[i],
                aspect="finding",
                evidence_ids=[source.evidence_id],
            )
        )
        rows.append(
            StudyObservation(
                row_id=f"experiment-{i}", paper_id=source.paper.paper_id, fields=fields
            )
        )
    validation = CitationValidation(
        valid=True,
        report_bindings_verified=True,
        verdicts=[
            ClaimVerdict(claim_id=c.claim_id, supported=True, reason="MOCK exact source")
            for c in facts
        ],
        supported_pairs=[
            ClaimEvidencePair(claim_id=c.claim_id, evidence_id=e)
            for c in facts
            for e in c.evidence_ids
        ],
    )
    return facts, sources, rows, validation


def demo_report():
    facts, sources, rows, validation = report_demo()
    return synthesize_report(
        "Compare DEMO experiments",
        facts,
        sources,
        validation,
        rows,
        {"findings": [c for c in facts if c.aspect == "finding"]},
    )


def test_multisource_report_keeps_conditions_numbers_disputes_and_provenance():
    report = demo_report()
    facts, sources, _, _ = report_demo()
    assert len(report.sections) == 10 and len(report.rows) == 2
    assert {c.claim_id for c in facts} == {cid for s in report.sections for cid in s.claim_ids}
    assert set(parse_citations(report.markdown)) == {e.evidence_id for e in sources}
    assert "91.5" in report.markdown and "0.89" in report.markdown
    assert (
        "Improvement observed." in report.markdown and "No improvement observed." in report.markdown
    )
    assert all(
        any(label + "：原文字段不同" in n for n in report.comparability)
        for label in ["单位", "数据划分", "实验条件"]
    )
    assert report.comparison_status == "not_directly_comparable"
    assert report.rows[0].fields["participants"].state == "explicit_not_reported"
    assert "原文明确未报告" in report.rows[0].fields["participants"].text
    assert report.rows[1].fields["participants"].state == "evidence_insufficient"
    assert "不代表原文未报告" in report.rows[1].fields["participants"].text
    assert all(set(row.fields) == set(FIELD_LABELS) for row in report.rows)


@pytest.mark.parametrize(
    "mutation, error",
    [
        ("wrong_paper", "report_cross_source_or_invalid_evidence"),
        ("unknown_claim", "report_unknown_claim"),
        ("invent_literal", "report_literal_not_in_cited_quote"),
        ("duplicate_row", "report_unknown_paper_or_duplicate_row"),
        ("uncited_paper", "report_unknown_paper_or_duplicate_row"),
    ],
)
def test_invalid_report_bindings_refuse(mutation, error):
    facts, sources, rows, validation = report_demo()
    if mutation == "wrong_paper":
        rows[0].paper_id = rows[1].paper_id
    elif mutation == "unknown_claim":
        rows[0].fields["method"].claim_ids = ["memory-fact"]
    elif mutation == "invent_literal":
        rows[0].fields["result"].source_literal = "99.99"
    elif mutation == "duplicate_row":
        rows.append(rows[0])
    else:
        extra = evidence(paper="uncited-paper")
        sources.append(extra)
        rows.append(StudyObservation(row_id="uncited", paper_id=extra.paper.paper_id))
    assert error in binding_errors(rows, facts, sources)
    with pytest.raises(ValueError, match="report_requires_verified"):
        synthesize_report("question", facts, sources, validation, rows, {})


@pytest.mark.parametrize(
    "field",
    [
        {"state": "reported"},
        {"state": "explicit_not_reported", "claim_ids": ["c"]},
        {"state": "evidence_insufficient", "claim_ids": ["c"]},
        {"state": "evidence_insufficient", "source_literal": "memory"},
        {"state": "reported", "claim_ids": ["c", "c"]},
    ],
)
def test_field_schema_cannot_hide_unverified_prose(field):
    with pytest.raises(ValidationError):
        ReportField.model_validate(field)


@pytest.mark.parametrize(
    "mutation", ["rejected", "missing_pair", "unsupported", "bindings_unverified"]
)
def test_deterministic_synthesis_requires_complete_current_review(mutation):
    facts, sources, rows, validation = report_demo()
    if mutation == "rejected":
        validation.valid = False
    elif mutation == "missing_pair":
        validation.supported_pairs.pop()
    elif mutation == "unsupported":
        validation.verdicts[0].supported = False
    else:
        validation.report_bindings_verified = False
    with pytest.raises(ValueError, match="report_requires_verified"):
        synthesize_report("question", facts, sources, validation, rows, {})


def test_legacy_claims_remain_readable_without_inventing_experiment_columns():
    facts, sources, _, validation = report_demo()
    report = synthesize_report("q", facts, sources, validation, [], {})
    assert all(
        f.state == "evidence_insufficient" for row in report.rows for f in row.fields.values()
    )
    assert "91.5" in report.markdown and "原文明确未报告" not in report.markdown
    assert report.sections[2].claim_ids == ["0-method", "1-method"]


def test_matching_literals_never_establish_fair_comparison():
    _, _, rows, _ = report_demo()
    report = demo_report()
    # Dataset and metric match in the fixture, but no equivalence or ranking follows.
    assert rows[0].fields["dataset"].source_literal == rows[1].fields["dataset"].source_literal
    assert any("相同字段或文字不能证明实验等价" in x for x in report.comparability)


def test_several_experiments_in_one_paper_are_not_merged():
    facts, sources, rows, validation = report_demo()
    sources[1].paper = sources[0].paper
    rows[1].paper_id = rows[0].paper_id
    report = synthesize_report("q", facts, sources, validation, rows, {})
    assert len(report.paper_ids) == 1 and len(report.rows) == 2
    assert report.rows[0].fields["result"].source_literal == "91.5"
    assert report.rows[1].fields["result"].source_literal == "0.89"
    assert (
        report.rows[0].fields["split"].source_literal
        != report.rows[1].fields["split"].source_literal
    )


def test_partially_extracted_paper_still_has_visible_field_gaps():
    facts, sources, rows, validation = report_demo()
    report = synthesize_report("q", facts, sources, validation, rows[:1], {})
    assert len(report.rows) == 2
    assert report.rows[1].paper_id == sources[1].paper.paper_id
    assert all(f.state == "evidence_insufficient" for f in report.rows[1].fields.values())


def test_original_omission_is_not_reported_as_a_different_experimental_value():
    facts, sources, rows, validation = report_demo()
    rows[0].fields["unit"] = rows[0].fields["participants"]
    report = synthesize_report("q", facts, sources, validation, rows, {})
    assert not any("单位：原文字段不同" in note for note in report.comparability)
    assert any("单位：缺少完整可验证字段" in note for note in report.comparability)


def test_question_and_metadata_cannot_inject_citations_or_report_headings():
    facts, sources, rows, validation = report_demo()
    fake = "[E:00000000-0000-0000-0000-000000000099]"
    sources[0].paper.title = "DEMO | 中文\n# fake " + fake
    report = synthesize_report("# fake " + fake, facts, sources, validation, rows, {})
    assert fake not in report.markdown
    assert set(parse_citations(report.markdown)) == {e.evidence_id for e in sources}
    assert "\\|" in report.markdown and "中文" in report.markdown


@pytest.mark.parametrize("reject_binding", [False, True])
async def test_graph_reviewer_controls_binding_retry_without_extra_retrieval(reject_binding):
    facts, sources, rows, _ = report_demo()
    # Use the existing plan's required aspect while retaining typed field roles.
    for fact in facts:
        fact.aspect = "method"
    analysis = AnalysisResult(
        claims=facts, observations=rows, limitations=["MOCK unverified 9999 finding"]
    )

    class Search:
        calls = 0

        async def search(self, plan, rerank=True):
            self.calls += 1
            return SearchResult(dense=[], lexical=[], fused=[], evidence=sources)

    response = VerificationResponse(
        verdicts=[ClaimVerdict(claim_id=c.claim_id, supported=True, reason="MOCK") for c in facts],
        supported_pairs=[
            ClaimEvidencePair(claim_id=c.claim_id, evidence_id=e)
            for c in facts
            for e in c.evidence_ids
        ],
        question_answered=True,
        report_bindings_verified=True,
    )
    search = Search()

    class CaptureReviewer(MockProvider):
        payloads: list[dict[str, Any]]

        def __init__(self, responses):
            super().__init__(responses)
            self.payloads = []

        async def complete(self, instruction, payload, schema):
            self.payloads.append(payload)
            return await super().complete(instruction, payload, schema)

    reviewer = CaptureReviewer(
        [response.model_copy(update={"report_bindings_verified": False}), response]
        if reject_binding
        else [response]
    )
    graph = build_research(
        search,
        MockProvider([plan()]),
        MockProvider([]),
        MockProvider([analysis, analysis] if reject_binding else [analysis]),
        reviewer,
    )
    state = MultiAgentState.model_validate(
        await graph.ainvoke(MultiAgentState(research_question="method?"))
    )
    assert state.status == "completed" and state.structured_report
    assert state.revision_count == int(reject_binding) and search.calls == 1
    assert "9999" not in state.draft_report and state.analysis_results[0].limitations
    assert state.draft_report == state.structured_report.markdown
    assert reviewer.payloads[0]["report_observations"] == [o.model_dump() for o in rows]
    assert all("content" not in e for e in reviewer.payloads[0]["evidence"])


async def test_graph_failed_bindings_do_not_publish_after_retry_exhaustion():
    facts, sources, rows, _ = report_demo()
    for fact in facts:
        fact.aspect = "method"

    class Search:
        async def search(self, plan, rerank=True):
            return SearchResult(dense=[], lexical=[], fused=[], evidence=sources)

    review = VerificationResponse(
        question_answered=True,
        verdicts=[ClaimVerdict(claim_id=c.claim_id, supported=True, reason="MOCK") for c in facts],
        supported_pairs=[
            ClaimEvidencePair(claim_id=c.claim_id, evidence_id=e)
            for c in facts
            for e in c.evidence_ids
        ],
    )
    state = MultiAgentState.model_validate(
        await build_research(
            Search(),
            MockProvider([plan()]),
            MockProvider([]),
            MockProvider([AnalysisResult(claims=facts, observations=rows)]),
            MockProvider([review]),
            max_revisions=0,
        ).ainvoke(MultiAgentState(research_question="method?"))
    )
    assert state.status == "insufficient_evidence" and state.structured_report is None
    assert "91.5" not in state.draft_report and not parse_citations(state.draft_report)


def test_browser_demo_fixture_matches_real_deterministic_output():
    path = Path(__file__).parents[1] / "fixtures" / "report-demo.json"
    assert json.loads(path.read_text()) == demo_report().model_dump()
