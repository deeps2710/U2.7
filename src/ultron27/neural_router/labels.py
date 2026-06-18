from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


HEADS = ("route", "intent", "tool_name", "risk_level", "requires_confirmation")


@dataclass(frozen=True)
class LabelMaps:
    values: dict[str, list[str]]

    @classmethod
    def from_rows(cls, rows: Iterable[dict[str, Any]]) -> "LabelMaps":
        buckets: dict[str, set[str]] = {head: set() for head in HEADS}
        for row in rows:
            for head in HEADS:
                buckets[head].add(normalize_label(head, row.get(head)))
        return cls({head: sorted(values) for head, values in buckets.items()})

    def encode(self, head: str, value: Any) -> int:
        labels = self.values[head]
        normalized = normalize_label(head, value)
        try:
            return labels.index(normalized)
        except ValueError:
            return 0

    def decode(self, head: str, index: int) -> str:
        labels = self.values[head]
        if index < 0 or index >= len(labels):
            return labels[0] if labels else ""
        return labels[index]

    def num_classes(self) -> dict[str, int]:
        return {head: len(self.values[head]) for head in HEADS}

    def to_dict(self) -> dict[str, list[str]]:
        return {head: list(self.values[head]) for head in HEADS}

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "LabelMaps":
        return cls({head: [str(item) for item in payload.get(head, [])] for head in HEADS})

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "LabelMaps":
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))


def normalize_label(head: str, value: Any) -> str:
    if head == "requires_confirmation":
        return "true" if bool(value) and str(value).lower() != "false" else "false"
    text = str(value if value is not None else "").strip()
    return text or "unknown"
