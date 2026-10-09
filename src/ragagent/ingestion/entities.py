"""Original conservative source-label rules. No weights, SDK or model calls."""

import re
from typing import Protocol, cast
from uuid import NAMESPACE_URL, uuid5

from pydantic import ValidationError

from ragagent.domain.entities import EntityKind, EntityProposal


class EntityExtractor(Protocol):
    """Local no-network factories only; models require a separate budget/usage workflow."""

    version: str

    def extract(self, content: str) -> list[EntityProposal]: ...


class SourceLabelExtractor:
    version = "source-labels-v1"
    # Explicit typed labels or an adjacent dataset/method/metric noun.
    # Names remain proposals: no broad semantic or scientific-role inference.
    # Quotes allow multiword/Unicode names; bare identifiers must start uppercase.
    pattern = re.compile(
        r"\b(?P<kind>(?i:Dataset|Method|Metric))\s*[:=]\s*"
        r'(?:"(?P<quoted>[^"\n]{1,256})"|(?P<bare>[A-Z](?:[A-Za-z0-9_.+-]{0,62}[A-Za-z0-9])?)(?![\w+-]|\.[A-Za-z0-9]))'
        r"(?:\s*\((?P<alias>[A-Z][A-Za-z0-9_.+-]{1,63})\))?"
    )

    adjacent = re.compile(
        r"\b(?P<bare>[A-Z](?:[A-Za-z0-9_.+-]{0,62}[A-Za-z0-9])?)"
        r"(?![\w+-]|\.[A-Za-z0-9])\s+(?P<kind>dataset|method|metric)\b"
    )
    generic_names = {
        "The",
        "This",
        "That",
        "Our",
        "Your",
        "Their",
        "A",
        "An",
        "Each",
        "Training",
        "Validation",
        "Test",
        "Public",
        "Original",
        "Same",
        "New",
        "Proposed",
    }

    def extract(self, content: str) -> list[EntityProposal]:
        results: list[EntityProposal] = []
        matches = sorted(
            [*self.pattern.finditer(content), *self.adjacent.finditer(content)],
            key=lambda match: match.start(),
        )
        seen: set[tuple[int, int, str]] = set()
        for match in matches:
            if len(results) >= 100:
                break
            captured_values = match.groupdict()
            field = "quoted" if captured_values.get("quoted") is not None else "bare"
            alias = captured_values.get("alias")
            group = (
                str(uuid5(NAMESPACE_URL, f"source-alias:{match.start()}:{match.group(0)}"))
                if alias
                else None
            )
            # Bare multiword text is ambiguous: do not keep just its first word.
            tail = content[match.end() : match.end() + 1]
            if (
                match.re is self.pattern
                and not alias
                and field == "bare"
                and tail
                and tail in " \t"
            ):
                rest = content[match.end() :].lstrip(" \t")
                if rest and rest[0].isalpha():
                    continue
            captures = [field, "alias"] if alias else [field]
            if len(results) + len(captures) > 100:
                break
            for captured in captures:
                name = match.group(captured)
                if name is None or name != name.strip() or name in self.generic_names:
                    continue
                identity = (match.start(captured), match.end(captured), match.group("kind").lower())
                if identity in seen:
                    continue
                seen.add(identity)
                try:
                    results.append(
                        EntityProposal(
                            name=name,
                            entity_type=cast(EntityKind, match.group("kind").lower()),
                            span_start=match.start(captured),
                            span_end=match.end(captured),
                            alias_group=group,
                        )
                    )
                except ValidationError:
                    # Recognizable credentials and malformed candidates never persist.
                    continue
        return results
