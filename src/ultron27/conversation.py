from __future__ import annotations

import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from .audit import append_audit_record
from .brain import TaskPlan, TaskState, TaskStep, UltronBrain, format_memory
from .models import ToolCall


ASSISTANT_TONE = (
    "Calm, concise, respectful, and slightly futuristic. "
    "ULTRON should sound like a capable personal assistant, not a command parser."
)


@dataclass(frozen=True)
class RoutedIntent:
    kind: str
    understood: str
    response: str = ""
    key: str = ""
    value: str = ""
    query: str = ""
    enabled: bool | None = None


@dataclass
class ConversationTurn:
    turn_id: str
    user_input: str
    understood: str
    route: str
    response: str
    task: dict[str, Any] | None = None
    needs_confirmation: bool = False
    memory_events: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class FastIntentRouter:
    """Classifies low-latency chat and memory intents before invoking the planner."""

    def route(self, text: str) -> RoutedIntent:
        understood = cleanup_user_text(text)
        lowered = understood.lower()
        if not understood:
            return RoutedIntent("empty", understood, "I did not receive anything clear. Try again when ready.")

        memory_toggle = self._memory_toggle(lowered)
        if memory_toggle is not None:
            response = "Memory is now on." if memory_toggle else "Memory is now off. I will avoid learning new preferences until you turn it back on."
            return RoutedIntent("memory_toggle", understood, response, enabled=memory_toggle)

        show_memory = lowered in {"/memory", "memory", "show memory", "show my memory", "what do you remember", "what do you remember about me"}
        if show_memory:
            return RoutedIntent("memory_show", understood)

        forget_query = self._forget_query(understood)
        if forget_query:
            return RoutedIntent("memory_forget", understood, key=forget_query, query=forget_query)

        memory_fact = self._memory_fact(understood)
        if memory_fact:
            key, value, kind = memory_fact
            return RoutedIntent("memory_remember", understood, key=key, value=value, query=kind)

        chat_response = self._chat_response(lowered)
        if chat_response:
            return RoutedIntent("chat", understood, chat_response)

        return RoutedIntent("command", understood)

    def _memory_toggle(self, lowered: str) -> bool | None:
        if lowered in {"turn memory on", "enable memory", "memory on", "start memory", "remember things again"}:
            return True
        if lowered in {"turn memory off", "disable memory", "memory off", "stop memory", "do not remember things"}:
            return False
        return None

    def _forget_query(self, text: str) -> str:
        lowered = text.lower()
        if lowered.startswith("/forget "):
            return text[8:].strip()
        match = re.match(r"^(?:forget|remove memory|delete memory)\s+(?:that\s+)?(?P<query>.+)$", text, flags=re.IGNORECASE)
        return match.group("query").strip() if match else ""

    def _memory_fact(self, text: str) -> tuple[str, str, str] | None:
        patterns = [
            (r"^(?:please\s+)?remember\s+that\s+(?P<value>.+)$", "fact"),
            (r"^my\s+preferred\s+response\s+style\s+is\s+(?P<value>.+)$", "preference"),
            (r"^i\s+prefer\s+(?P<value>.+)$", "preference"),
            (r"^call\s+(?P<key>[\w .-]{2,40})\s+(?P<value>[\w .-]{2,80})$", "alias"),
        ]
        for pattern, kind in patterns:
            match = re.match(pattern, text, flags=re.IGNORECASE)
            if not match:
                continue
            if kind == "alias":
                raw_key = match.group("key")
                value = clean_memory_value(match.group("value"))
                return f"alias:{slugify(raw_key)}", value, kind
            value = clean_memory_value(match.group("value"))
            key = "preferred_response_style" if kind == "preference" and "response" in text.lower() else f"{kind}:{slugify(value)[:44]}"
            return key, value, kind
        return None

    def _chat_response(self, lowered: str) -> str:
        normalized = lowered.strip(" .!?")
        if normalized in {"hi", "hello", "hey", "hello ultron", "hey ultron", "ultron"}:
            return "At your service. Tell me what you need and I will handle the safe steps."
        if normalized in {"thanks", "thank you", "thanks ultron", "thank you ultron"}:
            return "Always. I will keep things clear and quick."
        if normalized in {"how are you", "how are you ultron"}:
            return "Online and steady. Ready when you are."
        if normalized in {"who are you", "what are you"}:
            return "I am ULTRON 2.7, your local assistant for chat, planning, voice, and safe laptop tasks."
        if re.search(r"\b(what can you do|help|commands)\b", lowered):
            return "I can chat, create notes, search files, set reminders, open safe apps, search the web, play music, and pause before risky actions."
        return ""


class ConversationManager:
    def __init__(self, brain: UltronBrain):
        self.brain = brain
        self.router = FastIntentRouter()
        self.turns: list[ConversationTurn] = []
        self.memory_enabled = self._load_memory_enabled()
        self._command_counts: dict[str, int] = {}

    def handle(self, text: str, *, confirmed: bool = False, mode: str = "do") -> dict[str, Any]:
        if mode == "plan":
            task = self.brain.plan(cleanup_user_text(text))
            turn = self._turn(text, task.original_goal, "plan", task.summary, task=task.to_dict())
            return self._payload(turn)

        routed = self.router.route(text)
        memory_events: list[str] = []
        task: TaskPlan | None = None
        response = routed.response

        if routed.kind == "command":
            task = self.brain.execute(routed.understood, confirmed=confirmed)
            response = task.summary
            memory_events.extend(self._learn_from_task(routed.understood, task))
        elif routed.kind == "memory_show":
            response = self._memory_summary()
            task = self._assistant_reply_task(routed.understood, response)
        elif routed.kind == "memory_forget":
            removed = self.brain.memory.forget(routed.query)
            response = f"Forgot {removed} matching memory item(s)." if removed else "I did not find a matching memory item."
            memory_events.append(f"forgot:{removed}")
            task = self._assistant_reply_task(routed.understood, response)
        elif routed.kind == "memory_toggle":
            self.memory_enabled = bool(routed.enabled)
            self.brain.memory.remember("memory_enabled", str(self.memory_enabled).lower(), kind="control")
            memory_events.append(f"memory_enabled:{self.memory_enabled}")
            task = self._assistant_reply_task(routed.understood, response)
        elif routed.kind == "memory_remember":
            if not self.memory_enabled:
                response = "Memory is off, so I did not store that."
                memory_events.append("memory_disabled")
            else:
                stored = self.brain.memory.remember(routed.key, routed.value, kind=routed.query or "fact")
                response = "Remembered." if stored else "I did not store that because it looked sensitive or incomplete."
                memory_events.append(f"remembered:{routed.key}" if stored else "memory_rejected")
            task = self._assistant_reply_task(routed.understood, response)
        elif routed.kind == "empty":
            task = self._assistant_reply_task(routed.understood or "empty input", response)
        else:
            task = self._assistant_reply_task(routed.understood, response)

        task_dict = task.to_dict() if task else None
        needs_confirmation = bool(task_dict and task_dict.get("status") == TaskState.WAITING_FOR_CONFIRMATION.value)
        turn = self._turn(
            text,
            routed.understood,
            routed.kind,
            response,
            task=task_dict,
            needs_confirmation=needs_confirmation,
            memory_events=memory_events,
        )
        self._audit_turn(turn)
        return self._payload(turn)

    def memory_snapshot(self) -> dict[str, Any]:
        return {"enabled": self.memory_enabled, "items": self.brain.memory.list()}

    def set_memory_enabled(self, enabled: bool) -> dict[str, Any]:
        self.memory_enabled = bool(enabled)
        self.brain.memory.remember("memory_enabled", str(self.memory_enabled).lower(), kind="control")
        return self.memory_snapshot()

    def forget_memory(self, query: str) -> dict[str, Any]:
        removed = self.brain.memory.forget(query)
        return {"enabled": self.memory_enabled, "removed": removed, "items": self.brain.memory.list()}

    def _assistant_reply_task(self, utterance: str, message: str) -> TaskPlan:
        payload = self.brain.assistant.handle_tool_call(
            utterance,
            ToolCall("assistant_reply", {"message": message}),
            intent="conversation",
            source="fast_router",
        )
        step = TaskStep(
            step_id="1",
            utterance=utterance,
            status=TaskState.COMPLETED,
            tool_call=payload["tool_call"],
            policy=payload["policy"],
            result=payload["result"],
        )
        task = TaskPlan(
            task_id=str(uuid.uuid4()),
            original_goal=utterance,
            classification="conversation",
            status=TaskState.COMPLETED,
            steps=[step],
            summary=str(payload.get("result", {}).get("message") or message),
        )
        self.brain.session_memory["last_task"] = task.to_dict()
        return task

    def _learn_from_task(self, goal: str, task: TaskPlan) -> list[str]:
        if not self.memory_enabled or task.status != TaskState.COMPLETED:
            return []
        key = slugify(goal)[:56]
        self._command_counts[key] = self._command_counts.get(key, 0) + 1
        events = []
        if self._command_counts[key] >= 2:
            if self.brain.memory.remember(f"habit:command:{key}", goal, kind="common_command"):
                events.append(f"habit:command:{key}")
        first_tool = (task.steps[0].tool_call or {}).get("name") if task.steps else ""
        if first_tool:
            if self.brain.memory.remember("recent_tool", str(first_tool), kind="recent_tool"):
                events.append(f"recent_tool:{first_tool}")
        return events

    def _memory_summary(self) -> str:
        state = "on" if self.memory_enabled else "off"
        items = [item for item in self.brain.memory.list() if item.get("key") != "memory_enabled"]
        if not items:
            return f"Memory is {state}. I do not have any non-sensitive personal memory stored yet."
        return f"Memory is {state}.\n{format_memory(items)}"

    def _load_memory_enabled(self) -> bool:
        for item in self.brain.memory.list():
            if item.get("key") == "memory_enabled":
                return str(item.get("value", "true")).lower() != "false"
        return True

    def _turn(
        self,
        user_input: str,
        understood: str,
        route: str,
        response: str,
        *,
        task: dict[str, Any] | None = None,
        needs_confirmation: bool = False,
        memory_events: list[str] | None = None,
    ) -> ConversationTurn:
        turn = ConversationTurn(
            turn_id=str(uuid.uuid4()),
            user_input=user_input,
            understood=understood,
            route=route,
            response=response,
            task=task,
            needs_confirmation=needs_confirmation,
            memory_events=memory_events or [],
        )
        self.turns.append(turn)
        self.turns = self.turns[-30:]
        return turn

    def _payload(self, turn: ConversationTurn) -> dict[str, Any]:
        return {
            "status": "ok" if turn.route != "empty" else "empty",
            "route": turn.route,
            "understood": turn.understood,
            "response": turn.response,
            "subtitle": turn.response,
            "task": turn.task,
            "needs_confirmation": turn.needs_confirmation,
            "conversation": turn.to_dict(),
            "conversation_history": [item.to_dict() for item in self.turns[-10:]],
            "memory_enabled": self.memory_enabled,
        }

    def _audit_turn(self, turn: ConversationTurn) -> None:
        settings = self.brain.assistant.settings
        if not settings.write_audit:
            return
        append_audit_record({"record_type": "conversation_turn", "turn": turn.to_dict()}, settings.audit_log)


def cleanup_user_text(text: str) -> str:
    value = " ".join(str(text or "").strip().split())
    value = re.sub(r"^(?:hey\s+)?ultron[\s,.:;-]+", "", value, flags=re.IGNORECASE)
    return value.strip()


def clean_memory_value(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().strip(" .!?\"'"))


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "item"
