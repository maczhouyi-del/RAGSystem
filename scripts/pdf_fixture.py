"""Generate an owned, two-page PDF with text, table rows and a formula; DEMO ONLY."""

from pathlib import Path


def write_provenance_pdf(path: Path) -> None:
    pages = [
        [
            "SYNTHETIC ONLY - NOT A BENCHMARK",
            "Methods",
            "Original source text on page one.",
            "Table 1: DEMO scores (%)",
            "Method     Dataset     Score (%)",
            "Alpha      DEMOSET     91.5",
            "Formula: L = x + y",
        ],
        [
            "SYNTHETIC ONLY - NOT A BENCHMARK",
            "Table 1 continued",
            "Beta       DEMOSET     92.0",
            "Original source text on page two.",
            "Formula: z = x * y",
        ],
    ]
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [4 0 R 6 0 R] /Count 2 >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    for i, lines in enumerate(pages):
        content = "BT /F1 12 Tf 16 TL 50 750 Td\n"
        for index, line in enumerate(lines):
            escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            content += ("T*\n" if index else "") + f"({escaped}) Tj\n"
        stream = (content + "ET\n").encode("ascii")
        objects.append(
            (
                "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                "/Resources << /Font << /F1 3 0 R >> >> "
                f"/Contents {5 + i * 2} 0 R >>"
            ).encode()
        )
        objects.append(f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"endstream")
    result = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(result))
        result.extend(f"{i} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = len(result)
    result.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        result.extend(f"{offset:010d} 00000 n \n".encode())
    result.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    path.write_bytes(result)
