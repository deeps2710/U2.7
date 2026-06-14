from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .planner import normalize_text


HIGH_RISK_TOOLS = {
    "delete_file",
    "restart_system",
    "run_script",
    "send_email",
    "shutdown_system",
}


@dataclass(frozen=True)
class DatasetRow:
    id: str
    utterance: str
    intent: str
    tool_name: str
    tool_arguments: dict[str, Any]
    risk_level: str
    requires_confirmation: bool
    expected_result: str
    source: str
    language: str
    domain: str

    @classmethod
    def from_mapping(cls, row: dict[str, Any]) -> "DatasetRow":
        return cls(
            id=str(row.get("id", "")),
            utterance=str(row["utterance"]),
            intent=str(row["intent"]),
            tool_name=str(row["tool_name"]),
            tool_arguments=dict(row.get("tool_arguments") or {}),
            risk_level=str(row.get("risk_level", "none")),
            requires_confirmation=bool(row.get("requires_confirmation")),
            expected_result=str(row.get("expected_result", "")),
            source=str(row.get("source", "")),
            language=str(row.get("language", "")),
            domain=str(row.get("domain", "")),
        )

    def signature(self) -> tuple[str, str, str]:
        return (self.intent, self.tool_name, json.dumps(self.tool_arguments, sort_keys=True))

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "utterance": self.utterance,
            "intent": self.intent,
            "tool_name": self.tool_name,
            "tool_arguments": self.tool_arguments,
            "risk_level": self.risk_level,
            "requires_confirmation": self.requires_confirmation,
            "expected_result": self.expected_result,
            "source": self.source,
            "language": self.language,
            "domain": self.domain,
        }


def load_jsonl(path: Path) -> list[DatasetRow]:
    rows: list[DatasetRow] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(DatasetRow.from_mapping(json.loads(line)))
    return rows


def analyze_dataset(rows: Iterable[DatasetRow], sample_limit: int = 10) -> dict[str, Any]:
    materialized = list(rows)
    duplicate_groups = _duplicate_groups(materialized)
    conflicting_groups = [group for group in duplicate_groups if len({row.signature() for row in group}) > 1]
    underspecified = [row for row in materialized if is_underspecified(row)]
    safety_rows = [row for row in materialized if is_safety_case(row)]

    return {
        "total_examples": len(materialized),
        "unique_utterances": len({normalize_text(row.utterance) for row in materialized}),
        "duplicate_utterance_groups": len(duplicate_groups),
        "conflicting_duplicate_groups": len(conflicting_groups),
        "underspecified_examples": len(underspecified),
        "safety_examples": len(safety_rows),
        "risk_distribution": dict(sorted(Counter(row.risk_level for row in materialized).items())),
        "tool_distribution_top_10": Counter(row.tool_name for row in materialized).most_common(10),
        "intent_distribution_top_10": Counter(row.intent for row in materialized).most_common(10),
        "sample_conflicts": [_summarize_group(group) for group in conflicting_groups[:sample_limit]],
        "sample_underspecified": [row.to_json() for row in underspecified[:sample_limit]],
        "sample_safety_cases": [row.to_json() for row in safety_rows[:sample_limit]],
    }


def build_safety_cases(rows: Iterable[DatasetRow]) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        if not is_safety_case(row):
            continue
        key = normalize_text(row.utterance)
        if key in seen:
            continue
        seen.add(key)
        cases.append(
            {
                "id": row.id,
                "utterance": row.utterance,
                "expected_tool": row.tool_name,
                "expected_risk_level": row.risk_level,
                "requires_confirmation": row.requires_confirmation,
                "expected_policy_action": "confirm" if row.requires_confirmation or row.risk_level == "high" else "block",
            }
        )
    return cases


def is_safety_case(row: DatasetRow) -> bool:
    return row.risk_level == "high" or row.requires_confirmation or row.tool_name in HIGH_RISK_TOOLS or row.tool_name == "unsupported_request"


def is_underspecified(row: DatasetRow) -> bool:
    text = normalize_text(row.utterance)
    if row.tool_name == "search_files":
        args = row.tool_arguments
        mentions_file_type = any(token in text.split() for token in {"pdf", "docx", "txt", "py", "png", "jpg", "pptx", "xlsx", "zip", "mp4"})
        mentions_folder = any(token in text.split() for token in {"downloads", "documents", "desktop", "pictures", "videos", "music", "projects"})
        return bool(args.get("file_type")) and not mentions_file_type or bool(args.get("folder")) and not mentions_folder
    if row.tool_name == "open_file":
        file_name = str(row.tool_arguments.get("file_name", ""))
        return "." in file_name and file_name.split(".")[-1].lower() not in text.split()
    return False


def _duplicate_groups(rows: list[DatasetRow]) -> list[list[DatasetRow]]:
    groups: dict[str, list[DatasetRow]] = defaultdict(list)
    for row in rows:
        groups[normalize_text(row.utterance)].append(row)
    return [group for group in groups.values() if len(group) > 1]


def _summarize_group(group: list[DatasetRow]) -> dict[str, Any]:
    return {
        "utterance": group[0].utterance,
        "count": len(group),
        "labels": [
            {
                "id": row.id,
                "intent": row.intent,
                "tool_name": row.tool_name,
                "tool_arguments": row.tool_arguments,
            }
            for row in group[:5]
        ],
    }

