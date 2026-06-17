from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from .audit import append_audit_record
from .knowledge import KnowledgeBase, looks_sensitive
from .models import PolicyDecision, RiskLevel, ToolCall, ValidationResult
from .runtime import UltronAssistant


SkillHandler = Callable[["SkillRegistry", dict[str, Any], bool], dict[str, Any]]


@dataclass(frozen=True)
class SkillSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    risk_level: RiskLevel
    examples: tuple[str, ...] = ()

    def public(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["risk_level"] = self.risk_level.value
        return payload


@dataclass
class SkillRegistry:
    assistant: UltronAssistant
    knowledge: KnowledgeBase
    handlers: dict[str, SkillHandler] = field(default_factory=dict)
    specs: dict[str, SkillSpec] = field(default_factory=dict)

    @classmethod
    def with_builtins(cls, assistant: UltronAssistant, knowledge: KnowledgeBase) -> "SkillRegistry":
        registry = cls(assistant=assistant, knowledge=knowledge)
        registry.register(
            SkillSpec(
                name="notes",
                description="Create or append a local note through the safe notes tool.",
                input_schema={
                    "required": {"action": {"type": "string", "enum": ["create", "append"]}, "title": {"type": "string"}},
                    "optional": {"content": {"type": "string"}},
                },
                risk_level=RiskLevel.LOW,
                examples=("Create note project ideas", "Append a reminder to note project ideas"),
            ),
            _notes_skill,
        )
        registry.register(
            SkillSpec(
                name="reminders",
                description="Save a reminder through the safe reminder tool.",
                input_schema={"required": {"task": {"type": "string"}, "time": {"type": "string"}}, "optional": {}},
                risk_level=RiskLevel.LOW,
                examples=("Remind me to test voice mode at 6 pm",),
            ),
            _reminders_skill,
        )
        registry.register(
            SkillSpec(
                name="file_search",
                description="Search files inside configured safe roots.",
                input_schema={
                    "required": {"query": {"type": "string"}},
                    "optional": {"file_type": {"type": "string"}, "folder": {"type": "string"}},
                },
                risk_level=RiskLevel.LOW,
                examples=("Find files about phase 12",),
            ),
            _file_search_skill,
        )
        registry.register(
            SkillSpec(
                name="project_summary",
                description="Summarize matching local project knowledge without executing actions.",
                input_schema={"required": {"query": {"type": "string"}}, "optional": {"limit": {"type": "integer"}}},
                risk_level=RiskLevel.LOW,
                examples=("Summarize phase 12 knowledge",),
            ),
            _project_summary_skill,
        )
        registry.register(
            SkillSpec(
                name="daily_planning",
                description="Draft a daily plan from explicit priorities, recent memory, and searchable local knowledge.",
                input_schema={"required": {}, "optional": {"date": {"type": "string"}, "priorities": {"type": "string"}}},
                risk_level=RiskLevel.LOW,
                examples=("Plan today around testing voice mode",),
            ),
            _daily_planning_skill,
        )
        return registry

    def register(self, spec: SkillSpec, handler: SkillHandler) -> None:
        self.specs[spec.name] = spec
        self.handlers[spec.name] = handler

    def list(self) -> list[dict[str, Any]]:
        return [self.specs[name].public() for name in sorted(self.specs)]

    def run(self, name: str, payload: dict[str, Any], *, confirmed: bool = False) -> dict[str, Any]:
        spec = self.specs.get(name)
        if spec is None:
            result = {"status": "unknown_skill", "message": f"Unknown skill: {name}"}
            self._audit(name, payload, ValidationResult(False, ("Unknown skill",)), None, result)
            return result

        validation = validate_skill_input(spec, payload)
        policy = decide_skill(spec, validation, confirmed=confirmed)
        if not validation.valid:
            result = {"status": "blocked", "message": "; ".join(validation.errors)}
        elif policy.action == "confirm":
            result = {"status": "confirmation_required", "message": policy.reason}
        elif policy.action == "block":
            result = {"status": "blocked", "message": policy.reason}
        else:
            result = self.handlers[name](self, payload, confirmed)

        response = {
            "status": result.get("status", "ok"),
            "skill": spec.public(),
            "input": payload,
            "validation": asdict(validation),
            "policy": asdict(policy),
            "result": result,
        }
        self._audit(name, payload, validation, policy, result)
        return response

    def _audit(
        self,
        name: str,
        payload: dict[str, Any],
        validation: ValidationResult,
        policy: PolicyDecision | None,
        result: dict[str, Any],
    ) -> None:
        if not self.assistant.settings.write_audit:
            return
        append_audit_record(
            {
                "record_type": "skill_run",
                "skill_name": name,
                "input": payload,
                "validation": asdict(validation),
                "policy": asdict(policy) if policy else None,
                "result": result,
            },
            self.assistant.settings.audit_log,
        )


def validate_skill_input(spec: SkillSpec, payload: dict[str, Any]) -> ValidationResult:
    errors: list[str] = []
    required = spec.input_schema.get("required", {})
    optional = spec.input_schema.get("optional", {})
    allowed = set(required) | set(optional)

    for key in required:
        if key not in payload:
            errors.append(f"Missing required input: {key}")
    extra = set(payload) - allowed
    if extra:
        errors.append(f"Unexpected inputs: {', '.join(sorted(extra))}")

    for key, rule in {**required, **optional}.items():
        if key not in payload:
            continue
        value = payload[key]
        expected = rule.get("type")
        if expected == "string" and not isinstance(value, str):
            errors.append(f"{key} must be a string")
        elif expected == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
            errors.append(f"{key} must be an integer")
        elif expected == "boolean" and not isinstance(value, bool):
            errors.append(f"{key} must be a boolean")
        if isinstance(value, str) and looks_sensitive(value):
            errors.append(f"{key} appears to contain sensitive content")
        choices = rule.get("enum")
        if choices and value not in choices:
            errors.append(f"{key} must be one of: {', '.join(choices)}")

    return ValidationResult(not errors, tuple(errors))


def decide_skill(spec: SkillSpec, validation: ValidationResult, *, confirmed: bool = False) -> PolicyDecision:
    permission_level = _permission_level(spec.risk_level)
    if not validation.valid:
        return PolicyDecision("block", "; ".join(validation.errors), RiskLevel.BLOCKED, True, "blocked")
    if spec.risk_level in {RiskLevel.MEDIUM, RiskLevel.HIGH} and not confirmed:
        return PolicyDecision("confirm", f"{spec.risk_level.value.capitalize()}-risk skill requires confirmation.", spec.risk_level, True, permission_level)
    if spec.risk_level == RiskLevel.BLOCKED:
        return PolicyDecision("block", "This skill is blocked.", spec.risk_level, True, "blocked")
    return PolicyDecision("allow", f"{spec.risk_level.value.capitalize()}-risk skill can run.", spec.risk_level, False, permission_level)


def _permission_level(risk_level: RiskLevel) -> str:
    if risk_level == RiskLevel.LOW:
        return "low_risk_allowed"
    if risk_level == RiskLevel.MEDIUM:
        return "medium_risk_confirmation"
    if risk_level == RiskLevel.HIGH:
        return "high_risk_confirmation"
    if risk_level == RiskLevel.BLOCKED:
        return "blocked"
    return "no_execution"


def _notes_skill(registry: SkillRegistry, payload: dict[str, Any], confirmed: bool) -> dict[str, Any]:
    action = str(payload["action"])
    title = str(payload["title"])
    content = str(payload.get("content", ""))
    if action == "append":
        call = ToolCall("append_to_note", {"title": title, "content": content})
    else:
        call = ToolCall("create_note", {"title": title, "content": content})
    runtime = registry.assistant.handle_tool_call(
        f"skill notes {action} {title}",
        call,
        intent="skill_notes",
        confirmed=confirmed,
    )
    return {"status": runtime["result"]["status"], "message": runtime["result"]["message"], "runtime": runtime}


def _reminders_skill(registry: SkillRegistry, payload: dict[str, Any], confirmed: bool) -> dict[str, Any]:
    call = ToolCall("set_reminder", {"task": str(payload["task"]), "time": str(payload["time"])})
    runtime = registry.assistant.handle_tool_call("skill reminders set", call, intent="skill_reminders", confirmed=confirmed)
    return {"status": runtime["result"]["status"], "message": runtime["result"]["message"], "runtime": runtime}


def _file_search_skill(registry: SkillRegistry, payload: dict[str, Any], confirmed: bool) -> dict[str, Any]:
    arguments = {"query": str(payload["query"])}
    if payload.get("file_type"):
        arguments["file_type"] = str(payload["file_type"])
    if payload.get("folder"):
        arguments["folder"] = str(payload["folder"])
    runtime = registry.assistant.handle_tool_call("skill file search", ToolCall("search_files", arguments), intent="skill_file_search", confirmed=confirmed)
    return {"status": runtime["result"]["status"], "message": runtime["result"]["message"], "runtime": runtime}


def _project_summary_skill(registry: SkillRegistry, payload: dict[str, Any], confirmed: bool) -> dict[str, Any]:
    query = str(payload["query"])
    limit = int(payload.get("limit", 5))
    search = registry.knowledge.search(query, limit=limit)
    matches = search.get("matches", [])
    if not matches:
        return {"status": "ok", "message": f"No local knowledge matched: {query}", "matches": []}
    bullets = [f"{item['title']}: {item['snippet']}" for item in matches]
    return {"status": "ok", "message": f"Found {len(matches)} knowledge match(es) for {query}.", "summary": bullets, "matches": matches}


def _daily_planning_skill(registry: SkillRegistry, payload: dict[str, Any], confirmed: bool) -> dict[str, Any]:
    date = str(payload.get("date") or "today")
    priorities = str(payload.get("priorities") or "").strip()
    memory_items = registry.assistant.settings.workspace / ".ultron" / "memory.json"
    knowledge_matches = registry.knowledge.search(priorities, limit=3).get("matches", []) if priorities else []
    plan = [
        f"Review top priorities for {date}.",
        "Run safe tasks through ULTRON tools only after validation and policy checks.",
        "Capture any completed work as non-sensitive notes or memory.",
    ]
    if priorities:
        plan.insert(1, f"Focus block: {priorities}.")
    if knowledge_matches:
        plan.append(f"Use {len(knowledge_matches)} local knowledge match(es) as context, not as execution authority.")
    return {
        "status": "ok",
        "message": f"Drafted a daily plan for {date}.",
        "plan": plan,
        "memory_path": str(memory_items),
        "knowledge_matches": knowledge_matches,
    }
