from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .planner import DatasetPlanner


def evaluate_dataset(planner: DatasetPlanner, dataset_path: Path, limit: int | None = None) -> dict[str, Any]:
    total = 0
    tool_matches = 0
    argument_matches = 0
    confirmation_matches = 0
    intent_matches = 0
    misses: list[dict[str, Any]] = []

    for line in dataset_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        plan = planner.plan(row["utterance"])
        total += 1
        expected_args = row.get("tool_arguments") or {}

        tool_ok = plan.tool_call.name == row["tool_name"]
        args_ok = plan.tool_call.arguments == expected_args
        confirm_ok = plan.requires_confirmation == bool(row["requires_confirmation"])
        intent_ok = plan.intent == row["intent"]

        tool_matches += int(tool_ok)
        argument_matches += int(args_ok)
        confirmation_matches += int(confirm_ok)
        intent_matches += int(intent_ok)

        if len(misses) < 10 and not (tool_ok and args_ok and confirm_ok and intent_ok):
            misses.append(
                {
                    "utterance": row["utterance"],
                    "expected_tool": row["tool_name"],
                    "actual_tool": plan.tool_call.name,
                    "expected_arguments": expected_args,
                    "actual_arguments": plan.tool_call.arguments,
                }
            )

        if limit is not None and total >= limit:
            break

    return {
        "total": total,
        "intent_accuracy": _ratio(intent_matches, total),
        "tool_accuracy": _ratio(tool_matches, total),
        "argument_exact_match": _ratio(argument_matches, total),
        "confirmation_accuracy": _ratio(confirmation_matches, total),
        "sample_misses": misses,
    }


def _ratio(count: int, total: int) -> float:
    return round(count / total, 4) if total else 0.0

