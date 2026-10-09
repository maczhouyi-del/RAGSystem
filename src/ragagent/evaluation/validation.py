from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ragagent.db.models import Chunk, Paper
from ragagent.domain.evaluation import GoldPaper
from ragagent.errors import EvaluationError
from ragagent.evaluation.schema import EvaluationDataset


def validate_references(dataset: EvaluationDataset, session: Session) -> None:
    chunks = sorted({cid for case in dataset.cases for cid in case.relevant_chunk_ids})
    papers = sorted({pid for case in dataset.cases for pid in case.relevant_paper_ids})
    for ids, column in [(chunks, Chunk.id), (papers, Paper.id)]:
        known: set[str] = set()
        for start in range(0, len(ids), 1000):
            known.update(
                session.scalars(select(column).where(column.in_(ids[start : start + 1000])))
            )
        if known != set(ids):
            raise EvaluationError("dataset_references_unknown_chunks_or_papers")

    labels = [label for case in dataset.cases for label in case.reviewed_papers] + [
        source.paper for case in dataset.cases for source in case.gold_sources
    ]
    source_ids = sorted({source.chunk_id for case in dataset.cases for source in case.gold_sources})
    paper_ids = sorted({label.paper_id for label in labels})
    paper_rows: dict[str, Any] = {}
    chunk_rows: dict[str, Any] = {}
    for start in range(0, len(paper_ids), 1000):
        statement = select(
            Paper.id, Paper.sha256, Paper.arxiv_family_id, Paper.arxiv_version
        ).where(Paper.id.in_(paper_ids[start : start + 1000]))
        paper_rows.update((row.id, row) for row in session.execute(statement))
    for start in range(0, len(source_ids), 1000):
        statement_chunks = select(
            Chunk.id, Chunk.paper_id, Chunk.page_start, Chunk.page_end, Chunk.content
        ).where(Chunk.id.in_(source_ids[start : start + 1000]))
        chunk_rows.update((row.id, row) for row in session.execute(statement_chunks))

    def validate_paper(label: GoldPaper) -> None:
        paper = paper_rows.get(label.paper_id)
        if paper is None or paper.sha256 != label.pdf_sha256:
            raise EvaluationError("gold_pdf_identity_mismatch")
        if (
            label.arxiv_family_id is not None
            and label.arxiv_family_id != paper.arxiv_family_id
            or label.arxiv_version is not None
            and label.arxiv_version != paper.arxiv_version
        ):
            raise EvaluationError("gold_paper_version_mismatch")

    for case in dataset.cases:
        for label in case.reviewed_papers:
            validate_paper(label)
        for source in case.gold_sources:
            validate_paper(source.paper)
            chunk = chunk_rows.get(source.chunk_id)
            if chunk is None or chunk.paper_id != source.paper.paper_id:
                raise EvaluationError("gold_chunk_paper_mismatch")
            if (
                source.page_start < chunk.page_start
                or source.page_end > chunk.page_end
                or chunk.content[source.span_start : source.span_end] != source.quote
            ):
                raise EvaluationError("gold_quote_or_page_mismatch")
