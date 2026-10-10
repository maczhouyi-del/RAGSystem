"""Run pinned Docling's model-free native pipeline on an actual synthetic PDF."""

import argparse
import hashlib
import json
import os
from pathlib import Path
from tempfile import mkdtemp

from pdf_fixture import write_provenance_pdf

from ragagent.ingestion.chunker import StructureChunker
from ragagent.ingestion.parser import DoclingParser


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    work = Path(mkdtemp(prefix="synthetic-pdf-", dir=args.output_dir))
    pdf = work / "source.pdf"
    write_provenance_pdf(pdf)
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    parsed = DoclingParser(native_pdf=True).parse(pdf)
    assert {e.page_start for e in parsed.elements} == {1, 2}
    text = "\n".join(e.content for e in parsed.elements)
    for phrase in [
        "Original source text on page one.",
        "Original source text on page two.",
        "Table 1",
        "91.5",
        "92.0",
        "L = x + y",
        "z = x * y",
    ]:
        assert phrase in text, phrase
    assert all(
        e.pdf_location == "available" and e.page_location == "available" for e in parsed.elements
    )
    for element in parsed.elements:
        for region in element.pdf_regions:
            assert region.source_id == element.source_id and region.bbox is not None
            assert region.bbox.page_width == 612 and region.bbox.page_height == 792
            assert region.scope == "element" and region.source_start is not None
            assert element.content[region.source_start : region.source_end]
    chunks = StructureChunker(target_tokens=32, overlap_tokens=4).chunk(parsed)
    sources = {e.source_id: e for e in parsed.elements}
    for chunk in chunks:
        for span in chunk.source_spans:
            assert (
                chunk.content[span.chunk_start : span.chunk_end]
                == sources[span.source_id].content[span.span_start : span.span_end]
            )
            assert span.pdf_regions and all(r.scope == "element" for r in span.pdf_regions)
    (work / "parsed.json").write_text(parsed.model_dump_json(indent=2), encoding="utf-8")
    (work / "chunks.json").write_text(
        json.dumps([c.model_dump() for c in chunks], indent=2), encoding="utf-8"
    )
    receipt = {
        "truth": (
            "Actual generated two-page PDF, actual pinned Docling NativePdfPipeline. "
            "SYNTHETIC ONLY / NOT A BENCHMARK / NOT MANUALLY ANNOTATED. "
            "Native pipeline has no table/formula classification or layout/OCR accuracy claim."
        ),
        "pdf_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
        "elements": len(parsed.elements),
        "chunks": len(chunks),
        "pages": 2,
        "model_calls": 0,
        "layout_models_downloaded": False,
        "artifacts": str(work),
    }
    (work / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()
