from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field, TypeAdapter, model_validator

from ragagent.domain.evaluation import GoldPaper, GoldSource, NumericTarget
from ragagent.domain.privacy import SensitiveInput, reject_credentials
from ragagent.domain.research import MetadataFilter


class EvaluationCase(SensitiveInput):
    id: str
    query: str = Field(min_length=1)
    question_type: Literal["fact", "comparison", "synthesis", "filter"]
    filters: MetadataFilter = Field(default_factory=MetadataFilter)
    relevant_chunk_ids: list[str] = Field(default_factory=list)
    relevant_paper_ids: list[str] = Field(default_factory=list)
    expected_answer: str
    expected_refusal: bool = False
    notes: str = ""
    required_aspects: list[str] = Field(default_factory=list)
    annotated_by: str | None = None
    annotated_at: str | None = None
    gold_sources: list[GoldSource] = Field(default_factory=list, max_length=100)
    reviewed_papers: list[GoldPaper] = Field(default_factory=list, max_length=1000)
    refusal_rationale: str = ""
    numeric_targets: list[NumericTarget] = Field(default_factory=list, max_length=100)
    evaluation_dimensions: list[
        Literal["cross_language", "numeric", "table", "multi_paper", "follow_up", "refusal"]
    ] = Field(default_factory=list)


class EvaluationDataset(SensitiveInput):
    dataset_id: str
    label_source: Literal["human", "synthetic", "unannotated"]
    description: str
    cases: list[EvaluationCase] = Field(min_length=1, max_length=1000)
    annotation_format: Literal["legacy", "source_v1"] = "legacy"

    @model_validator(mode="after")
    def validate_annotations(self) -> "EvaluationDataset":
        if len({c.id for c in self.cases}) != len(self.cases):
            raise ValueError("duplicate_case_ids")
        if self.label_source == "human" and any(
            not c.annotated_by or not c.annotated_at for c in self.cases
        ):
            raise ValueError("human_labels_require_annotation_provenance")
        self.validate_source_labels()
        return self

    def validate_source_labels(self) -> None:
        if self.annotation_format != "source_v1" or self.label_source == "unannotated":
            return
        for case in self.cases:
            if self.label_source == "human":
                if not case.annotated_by or not case.annotated_by.strip():
                    raise ValueError("source_gold_requires_annotator")
                try:
                    TypeAdapter(AwareDatetime).validate_python(case.annotated_at)
                except ValueError:
                    raise ValueError("source_gold_requires_aware_annotation_time") from None
            if case.expected_refusal:
                if not case.reviewed_papers or not case.refusal_rationale.strip():
                    raise ValueError("refusal_gold_requires_reviewed_scope_and_rationale")
            elif (
                not case.gold_sources
                or {source.chunk_id for source in case.gold_sources} != set(case.relevant_chunk_ids)
                or {source.paper.paper_id for source in case.gold_sources}
                != set(case.relevant_paper_ids)
            ):
                raise ValueError("source_gold_requires_all_relevance_sources")
            if (
                "numeric" in case.evaluation_dimensions
                and not case.expected_refusal
                and not case.numeric_targets
            ):
                raise ValueError("numeric_gold_requires_values_units_and_conditions")

    def runnable(self, *, allow_refusal: bool = False) -> None:
        reject_credentials(self.model_dump(mode="json"))
        self.validate_source_labels()
        if self.label_source == "unannotated" or any(
            not c.relevant_chunk_ids and not (allow_refusal and c.expected_refusal)
            for c in self.cases
        ):
            raise ValueError("dataset_requires_relevance_labels")

    def generation_runnable(self) -> None:
        self.runnable(allow_refusal=True)
        if any(
            not c.expected_answer.strip() or (not c.expected_refusal and not c.required_aspects)
            for c in self.cases
        ):
            raise ValueError("generation_eval_requires_answer_and_aspect_labels")

    @property
    def warning(self) -> str:
        if self.label_source != "human":
            return "DEMO ONLY / NOT A BENCHMARK / NOT MANUALLY ANNOTATED"
        if self.annotation_format == "legacy":
            return "User-supplied human annotations, not independently verified. " + (
                "Legacy labels lack explicit PDF/span gold; "
                "use source_v1 for auditable source labels."
            )
        return "User-supplied human annotations; not independently verified by this software."


class EvaluationRequest(SensitiveInput):
    dataset: EvaluationDataset
    resume_run_id: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    )


class CitationPair(BaseModel):
    claim_id: str
    evidence_id: str


class RAGJudgment(BaseModel):
    supported_pairs: list[CitationPair]
    supported_claim_ids: list[str]
    answered_aspects: list[str]
    refusal_supported: bool = False
    notes: list[str] = Field(default_factory=list)
