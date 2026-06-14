from __future__ import annotations

import json
import re
import string
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable

from .models import Plan, RiskLevel, ToolCall
from .tools import get_tool_spec


DEFAULT_DATASET_PATH = Path("data/jarvis_dataset_v2/jarvis_laptop_commands_synthetic_v2.jsonl")


@dataclass(frozen=True)
class DatasetExample:
    utterance: str
    intent: str
    tool_call: ToolCall
    risk_level: RiskLevel
    requires_confirmation: bool


class DatasetPlanner:
    def __init__(self, examples: Iterable[DatasetExample] = ()):
        self.examples = list(examples)
        self._by_normalized = {normalize_text(example.utterance): example for example in self.examples}

    @classmethod
    def from_jsonl(cls, path: Path = DEFAULT_DATASET_PATH) -> "DatasetPlanner":
        if not path.exists():
            return cls()

        examples: list[DatasetExample] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            examples.append(
                DatasetExample(
                    utterance=row["utterance"],
                    intent=row["intent"],
                    tool_call=ToolCall(row["tool_name"], row.get("tool_arguments") or {}),
                    risk_level=RiskLevel(row["risk_level"]),
                    requires_confirmation=bool(row["requires_confirmation"]),
                )
            )
        return cls(examples)

    def plan(self, utterance: str) -> Plan:
        normalized = normalize_text(utterance)
        exact = self._by_normalized.get(normalized)
        if exact is not None:
            return self._to_plan(utterance, exact, "dataset_exact", 1.0)

        deterministic = regex_plan(utterance)
        if deterministic.source == "regex":
            return deterministic

        fuzzy = self._nearest(normalized)
        if fuzzy is not None:
            example, confidence = fuzzy
            return self._to_plan(utterance, example, "dataset_fuzzy", confidence)

        return deterministic

    def _nearest(self, normalized: str) -> tuple[DatasetExample, float] | None:
        best: tuple[DatasetExample, float] | None = None
        for key, example in self._by_normalized.items():
            ratio = SequenceMatcher(None, normalized, key).ratio()
            if best is None or ratio > best[1]:
                best = (example, ratio)
        if best and best[1] >= 0.82:
            return best
        return None

    @staticmethod
    def _to_plan(utterance: str, example: DatasetExample, source: str, confidence: float) -> Plan:
        return Plan(
            utterance=utterance,
            intent=example.intent,
            tool_call=example.tool_call,
            risk_level=example.risk_level,
            requires_confirmation=example.requires_confirmation,
            source=source,
            confidence=confidence,
        )


def normalize_text(text: str) -> str:
    table = str.maketrans("", "", string.punctuation)
    return " ".join(text.lower().translate(table).split())


def regex_plan(utterance: str) -> Plan:
    text = normalize_text(utterance)

    volume_match = re.search(r"\b(?:volume|sound)\b.*?\b(\d{1,3})\b", text)
    if volume_match:
        level = clamp(int(volume_match.group(1)), 0, 100)
        return _plan_from_tool(utterance, "set_volume", "set_system_volume", {"level": level}, "regex", 0.76)

    brightness_match = re.search(r"\b(?:brightness|screen)\b.*?\b(\d{1,3})\b", text)
    if brightness_match:
        level = clamp(int(brightness_match.group(1)), 0, 100)
        return _plan_from_tool(utterance, "set_brightness", "set_screen_brightness", {"level": level}, "regex", 0.74)

    if "mute" in text:
        return _plan_from_tool(utterance, "mute_volume", "mute_system_volume", {"mute": True}, "regex", 0.72)

    note_match = re.search(r"\b(?:create|make|write)\s+(?:a\s+)?note\s+(?:called\s+|named\s+)?(.+)", text)
    if note_match:
        title = note_match.group(1).strip()
        return _plan_from_tool(utterance, "create_note", "create_note", {"title": title, "content": ""}, "regex", 0.70)

    reminder_match = re.search(r"\bremind\s+me\s+to\s+(.+?)\s+(?:at|on|in)\s+(.+)", text)
    if reminder_match:
        return _plan_from_tool(
            utterance,
            "set_reminder",
            "set_reminder",
            {"task": reminder_match.group(1).strip(), "time": reminder_match.group(2).strip()},
            "regex",
            0.70,
        )

    timer_match = re.search(r"\b(?:start|set)\s+(?:a\s+)?timer\s+(?:for\s+)?(.+)", text)
    if timer_match:
        return _plan_from_tool(utterance, "start_timer", "start_timer", {"duration": timer_match.group(1).strip()}, "regex", 0.70)

    if "screenshot" in text:
        return _plan_from_tool(utterance, "take_screenshot", "take_screenshot", {}, "regex", 0.70)

    copy_match = re.search(r"\bcopy\s+(.+)\s+to\s+(?:the\s+)?clipboard", text)
    if copy_match:
        return _plan_from_tool(utterance, "copy_clipboard", "copy_to_clipboard", {"text": copy_match.group(1).strip()}, "regex", 0.68)

    if "read clipboard" in text or "show clipboard" in text:
        return _plan_from_tool(utterance, "read_clipboard", "read_clipboard", {}, "regex", 0.68)

    open_folder_match = re.search(r"\bopen\s+(?:folder\s+)?(?:my\s+)?(downloads|documents|desktop|pictures|music|videos)\b", text)
    if open_folder_match:
        return _plan_from_tool(utterance, "open_folder", "open_folder", {"folder": open_folder_match.group(1).title()}, "regex", 0.70)

    open_app_match = re.search(r"\bopen\s+([a-z0-9 ._-]+)$", text)
    if open_app_match:
        app = open_app_match.group(1).strip()
        return _plan_from_tool(utterance, "open_app", "open_application", {"app": app}, "regex", 0.68)

    search_match = re.search(r"\b(?:find|search|look for)\s+(.+)", text)
    if search_match:
        query = search_match.group(1).strip()
        return _plan_from_tool(utterance, "search_files", "search_files", {"query": query}, "regex", 0.64)

    delete_match = re.search(r"\bdelete\s+(.+)", text)
    if delete_match:
        file_name = delete_match.group(1).strip()
        return _plan_from_tool(utterance, "delete_file", "delete_file", {"file_name": file_name}, "regex", 0.63)

    return _plan_from_tool(
        utterance,
        "unsupported_request",
        "unsupported_request",
        {"reason": "No safe tool matched this command."},
        "fallback",
        0.0,
    )


def _plan_from_tool(
    utterance: str,
    intent: str,
    tool_name: str,
    arguments: dict[str, Any],
    source: str,
    confidence: float,
) -> Plan:
    spec = get_tool_spec(tool_name)
    risk_level = spec.risk_level if spec else RiskLevel.BLOCKED
    requires_confirmation = spec.requires_confirmation if spec else True
    return Plan(utterance, intent, ToolCall(tool_name, arguments), risk_level, requires_confirmation, source, confidence)


def clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))
