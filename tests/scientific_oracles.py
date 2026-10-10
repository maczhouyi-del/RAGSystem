"""Keep scientific text observable while excluding validated source identities."""

import json
import re
from typing import Any

_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_IDENTITIES = {
    "paper_id",
    "paper_ids",
    "chunk_id",
    "section_id",
    "evidence_id",
    "evidence_ids",
    "claim_id",
}


def scientific_payload_text(value: Any) -> str:
    def copy(item: Any, key: str = "") -> Any:
        if isinstance(item, list):
            return [copy(child, key) for child in item]
        if isinstance(item, dict):
            result = {}
            for name, child in item.items():
                if key == "paper" and name == "pdf_sha256":
                    assert child is None or (
                        isinstance(child, str) and re.fullmatch(r"[0-9a-f]{64}", child)
                    )
                    continue
                result[name] = copy(child, name)
            return result
        if key in _IDENTITIES and isinstance(item, str) and _UUID.fullmatch(item):
            return ""
        return item

    return json.dumps(copy(value))
