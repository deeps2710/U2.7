from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol

from .models import Plan, RiskLevel, ToolCall
from .tools import TOOL_SPECS, get_tool_spec, validate_tool_call


class LLMPlannerError(RuntimeError):
    pass


class LLMProvider(Protocol):
    def complete(self, prompt: str, timeout: float) -> str:
        ...


@dataclass(frozen=True)
class OllamaProvider:
    endpoint: str
    model: str

    def complete(self, prompt: str, timeout: float) -> str:
        payload = {
            "model": self.model,
            "stream": False,
            "format": "json",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        }
        request = urllib.request.Request(
            self.endpoint.rstrip("/") + "/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            raise LLMPlannerError(f"Ollama request failed: {exc}") from exc
        message = data.get("message") or {}
        content = message.get("content")
        if not isinstance(content, str):
            raise LLMPlannerError("Ollama response did not include message.content")
        return content


class LLMPlanner:
    def __init__(self, provider: LLMProvider, timeout: float = 8.0):
        self.provider = provider
        self.timeout = timeout

    def plan(self, utterance: str) -> Plan:
        raw = self.provider.complete(build_prompt(utterance), self.timeout)
        call, intent, confidence = parse_llm_tool_call(raw)
        validation = validate_tool_call(call)
        if not validation.valid:
            raise LLMPlannerError("; ".join(validation.errors))
        spec = get_tool_spec(call.name)
        if spec is None:
            raise LLMPlannerError(f"Unknown tool: {call.name}")
        return Plan(
            utterance=utterance,
            intent=intent or call.name,
            tool_call=call,
            risk_level=spec.risk_level,
            requires_confirmation=spec.requires_confirmation,
            source="llm",
            confidence=confidence,
        )


SYSTEM_PROMPT = """You are ULTRON 2.7's planner. Return only one JSON object. Do not execute commands."""


def build_prompt(utterance: str) -> str:
    tool_lines = []
    for name, spec in sorted(TOOL_SPECS.items()):
        required = ", ".join(spec.required) or "none"
        optional = ", ".join(spec.optional) or "none"
        tool_lines.append(f"- {name}: required={required}; optional={optional}; risk={spec.risk_level.value}")
    tools = "\n".join(tool_lines)
    return (
        "Map the user command to one allowlisted tool call.\n"
        "Return JSON in this exact shape:\n"
        '{"intent":"...", "tool_name":"...", "tool_arguments":{...}, "confidence":0.0}\n'
        "If no safe tool fits, use unsupported_request with reason.\n\n"
        f"Available tools:\n{tools}\n\n"
        f"User command: {utterance}"
    )


def parse_llm_tool_call(raw: str) -> tuple[ToolCall, str, float]:
    payload = _extract_json_object(raw)
    tool_name = payload.get("tool_name") or payload.get("name")
    arguments = payload.get("tool_arguments", payload.get("arguments", {}))
    intent = str(payload.get("intent", tool_name or ""))
    confidence = payload.get("confidence", 0.5)

    if not isinstance(tool_name, str) or not tool_name:
        raise LLMPlannerError("LLM output must include tool_name")
    if not isinstance(arguments, dict):
        raise LLMPlannerError("LLM output tool_arguments must be an object")
    if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
        confidence = 0.5
    confidence = max(0.0, min(1.0, float(confidence)))
    return ToolCall(tool_name, arguments), intent, confidence


def _extract_json_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise LLMPlannerError("LLM output was not valid JSON")
        payload = json.loads(text[start : end + 1])
    if not isinstance(payload, dict):
        raise LLMPlannerError("LLM output must be a JSON object")
    return payload


def make_ollama_planner(endpoint: str, model: str, timeout: float) -> LLMPlanner:
    return LLMPlanner(OllamaProvider(endpoint=endpoint, model=model), timeout=timeout)

