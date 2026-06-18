from __future__ import annotations

import argparse
import json
import mimetypes
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .audit import append_audit_record, read_recent_audit_records
from .brain import TaskState, UltronBrain
from .config import load_config
from .conversation import ConversationManager
from .diagnostics import PHASE13_VERSION, build_diagnostics
from .knowledge import KnowledgeBase
from .runtime import RuntimeSettings, UltronAssistant
from .skills import SkillRegistry
from .voice import VoiceSession, build_voice_session


ROOT = Path(__file__).resolve().parents[2]
WEB_ROOT = ROOT / "web"


@dataclass(frozen=True)
class TaskPlanProxy:
    payload: dict[str, Any]

    @property
    def status(self) -> str:
        return str(self.payload.get("status", "completed"))

    @property
    def summary(self) -> str:
        return str(self.payload.get("summary") or "")


def _task_from_payload(payload: dict[str, Any] | None) -> TaskPlanProxy:
    task = payload.get("task") if isinstance(payload, dict) else None
    return TaskPlanProxy(task if isinstance(task, dict) else {})


@dataclass
class WebState:
    brain: UltronBrain
    knowledge: KnowledgeBase | None = None
    skills: SkillRegistry | None = None
    conversation: ConversationManager | None = None
    voice: VoiceSession = field(default_factory=VoiceSession)
    visual_state: str = "idle"
    subtitles_enabled: bool = True
    last_subtitle: str = "ULTRON 2.7 online."
    last_task: dict[str, Any] | None = None
    recent_tasks: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        settings = self.brain.assistant.settings
        if self.conversation is None:
            self.conversation = ConversationManager(self.brain)
        if self.knowledge is None:
            self.knowledge = KnowledgeBase(
                settings.workspace / ".ultron" / "knowledge" / "index.json",
                workspace=settings.workspace,
                safe_roots=settings.safe_roots,
            )
        if self.skills is None:
            self.skills = SkillRegistry.with_builtins(self.brain.assistant, self.knowledge)

    def command(self, text: str, *, confirmed: bool = False, mode: str = "do") -> dict[str, Any]:
        command = text.strip()
        self.visual_state = "thinking"
        if not command:
            self.visual_state = "idle"
            self.last_subtitle = "No command received."
            return self.snapshot({"status": "empty", "message": self.last_subtitle})

        lowered = command.lower()
        if lowered.startswith("/plan "):
            task = self.brain.plan(command[6:].strip())
            conversation_payload = None
        elif lowered.startswith("/do "):
            conversation_payload = self.conversation.handle(command[4:].strip(), confirmed=confirmed) if self.conversation else None
            task = _task_from_payload(conversation_payload)
        elif mode == "plan":
            task = self.brain.plan(command)
            conversation_payload = None
        else:
            conversation_payload = self.conversation.handle(command, confirmed=confirmed) if self.conversation else None
            task = _task_from_payload(conversation_payload)

        if task is not None and isinstance(task, TaskPlanProxy):
            self.last_task = task.payload
            task_status = task.status
            summary = task.summary
        else:
            self.last_task = task.to_dict()
            task_status = task.status.value
            summary = task.summary
        self._remember_task(self.last_task)
        self.last_subtitle = (
            str(conversation_payload.get("response") or conversation_payload.get("subtitle"))
            if isinstance(conversation_payload, dict)
            else summary or f"Task {task_status}."
        )
        self.visual_state = "listening" if task_status == TaskState.WAITING_FOR_CONFIRMATION.value else "speaking"
        extra = {"status": "ok", "task": self.last_task, "subtitle": self.last_subtitle}
        if isinstance(conversation_payload, dict):
            extra.update(
                {
                    "route": conversation_payload.get("route"),
                    "understood": conversation_payload.get("understood"),
                    "response": conversation_payload.get("response"),
                    "conversation": conversation_payload.get("conversation"),
                    "conversation_history": conversation_payload.get("conversation_history"),
                    "memory_enabled": conversation_payload.get("memory_enabled"),
                }
            )
        return self.snapshot(extra)

    def voice_start(self, *, push_to_talk: bool | None = None) -> dict[str, Any]:
        self.visual_state = "listening"
        return self.snapshot(self.voice.start(push_to_talk=push_to_talk))

    def voice_stop(self) -> dict[str, Any]:
        payload = self.voice.stop()
        self.visual_state = "idle"
        return self.snapshot(payload)

    def voice_transcribe(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.visual_state = "thinking"
        voice_payload = self.voice.transcribe_and_run(payload, lambda goal, confirmed=False: self.command(goal, confirmed=confirmed))
        return self._voice_response_snapshot(voice_payload)

    def voice_capture(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.visual_state = "listening"
        voice_payload = self.voice.capture_and_run(payload, lambda goal, confirmed=False: self.command(goal, confirmed=confirmed))
        return self._voice_response_snapshot(voice_payload)

    def _voice_response_snapshot(self, voice_payload: dict[str, Any]) -> dict[str, Any]:
        if voice_payload.get("status") == "empty":
            self.last_subtitle = str(voice_payload.get("message", "No speech was detected."))
            self.visual_state = "listening"
            return self.snapshot(voice_payload)
        if voice_payload.get("status") == "capture_unavailable":
            self.last_subtitle = str(voice_payload.get("message", "Backend microphone capture is unavailable."))
            self.visual_state = "listening"
            return self.snapshot(voice_payload)
        record = voice_payload.get("record", {})
        spoken = str(voice_payload.get("spoken_response", self.last_subtitle))
        self.last_subtitle = spoken
        self.visual_state = "speaking" if not self.voice.status.muted else "idle"
        return self.snapshot({**voice_payload, "subtitle": self.last_subtitle, "voice_record": record})

    def memory_status(self) -> dict[str, Any]:
        if self.conversation is None:
            return {"status": "ok", "enabled": True, "memory": self.brain.memory.list()}
        snapshot = self.conversation.memory_snapshot()
        return self.snapshot({"status": "ok", "enabled": snapshot["enabled"], "memory": snapshot["items"]})

    def memory_forget(self, query: str) -> dict[str, Any]:
        if self.conversation is None:
            removed = self.brain.memory.forget(query)
            return self.snapshot({"status": "ok", "removed": removed, "memory": self.brain.memory.list()})
        snapshot = self.conversation.forget_memory(query)
        self.last_subtitle = f"Forgot {snapshot['removed']} matching memory item(s)." if snapshot["removed"] else "No matching memory item found."
        return self.snapshot({"status": "ok", "enabled": snapshot["enabled"], "removed": snapshot["removed"], "memory": snapshot["items"]})

    def memory_toggle(self, enabled: bool) -> dict[str, Any]:
        if self.conversation is None:
            self.brain.memory.remember("memory_enabled", str(bool(enabled)).lower(), kind="control")
            return self.snapshot({"status": "ok", "enabled": bool(enabled), "memory": self.brain.memory.list()})
        snapshot = self.conversation.set_memory_enabled(bool(enabled))
        self.last_subtitle = "Memory is now on." if snapshot["enabled"] else "Memory is now off."
        return self.snapshot({"status": "ok", "enabled": snapshot["enabled"], "memory": snapshot["items"]})

    def wake_start(self) -> dict[str, Any]:
        self.visual_state = "waiting_for_wake_word"
        payload = self.voice.start_wake()
        self.last_subtitle = "Always-listening is on. Say ULTRON or Hey ULTRON."
        return self.snapshot(payload)

    def wake_stop(self) -> dict[str, Any]:
        payload = self.voice.stop_wake()
        self.visual_state = "idle"
        self.last_subtitle = "Always-listening is off."
        return self.snapshot(payload)

    def wake_status(self) -> dict[str, Any]:
        return self.snapshot(self.voice.wake_snapshot())

    def wake_process(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.visual_state = "transcribing"
        wake_payload = self.voice.process_wake_input(payload, lambda goal, confirmed=False: self.command(goal, confirmed=confirmed))
        status = wake_payload.get("status")
        if status in {"ignored", "inactive"}:
            self.last_subtitle = str(wake_payload.get("message", "Input ignored by wake/VAD gate."))
            self.visual_state = "waiting_for_wake_word" if self.voice.wake_status.always_listening else "idle"
            return self.snapshot(wake_payload)
        if status == "wake_detected":
            self.last_subtitle = str(wake_payload.get("message", "Wake word detected. Listening."))
            self.visual_state = "listening"
            return self.snapshot(wake_payload)
        if wake_payload.get("command_executed"):
            record = wake_payload.get("record", {})
            spoken = str(wake_payload.get("spoken_response", self.last_subtitle))
            self.last_subtitle = spoken
            self.visual_state = "speaking" if not self.voice.status.muted else "waiting_for_wake_word"
            return self.snapshot({**wake_payload, "subtitle": self.last_subtitle, "voice_record": record})
        self.visual_state = "waiting_for_wake_word"
        return self.snapshot(wake_payload)

    def voice_status(self) -> dict[str, Any]:
        return self.snapshot({"status": "ok", **self.voice.snapshot()})

    def voice_providers(self) -> dict[str, Any]:
        return self.snapshot({"status": "ok", **self.voice.providers_status()})

    def audit_recent(self, *, limit: int = 25) -> dict[str, Any]:
        audit_log = self.brain.assistant.settings.audit_log
        return self.snapshot({"status": "ok", "audit_log": str(audit_log), "records": read_recent_audit_records(audit_log, limit=limit)})

    def diagnostics(self) -> dict[str, Any]:
        return build_diagnostics(self)

    def skills_list(self) -> dict[str, Any]:
        return self.snapshot({"status": "ok", "skills": self.skills.list() if self.skills else []})

    def skills_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.skills is None:
            return self.snapshot({"status": "error", "message": "Skill registry is unavailable."})
        name = str(payload.get("name") or payload.get("skill") or "")
        skill_input = payload.get("input") if isinstance(payload.get("input"), dict) else {}
        result = self.skills.run(name, skill_input, confirmed=bool(payload.get("confirmed", False)))
        self.last_subtitle = str(result.get("result", {}).get("message") or result.get("message") or "Skill run completed.")
        self.visual_state = "speaking" if result.get("status") not in {"blocked", "confirmation_required"} else "listening"
        return self.snapshot(result)

    def knowledge_ingest(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.knowledge is None:
            return self.snapshot({"status": "error", "message": "Knowledge base is unavailable."})
        result = self.knowledge.ingest(str(payload.get("path") or ""))
        self._audit_knowledge("knowledge_ingest", result)
        self.last_subtitle = str(result.get("message", "Knowledge ingest completed."))
        return self.snapshot({"status": result.get("status", "ok"), "knowledge": result, "sources": self.knowledge.sources()})

    def knowledge_search(self, query: str, *, limit: int = 5) -> dict[str, Any]:
        if self.knowledge is None:
            return self.snapshot({"status": "error", "message": "Knowledge base is unavailable."})
        result = self.knowledge.search(query, limit=limit)
        self._audit_knowledge("knowledge_search", {"query": query, "limit": limit, "match_count": len(result.get("matches", []))})
        return self.snapshot({"status": result.get("status", "ok"), "knowledge": result})

    def voice_test_stt(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.snapshot(self.voice.test_stt(payload))

    def voice_test_tts(self, payload: dict[str, Any]) -> dict[str, Any]:
        text = str(payload.get("text") or "ULTRON voice provider test.")
        return self.snapshot(self.voice.test_tts(text))

    def voice_calibrate(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = self.voice.calibrate_microphone(payload)
        self.last_subtitle = str(result.get("message") or "Voice calibration completed.")
        return self.snapshot(result)

    def voice_warmup(self) -> dict[str, Any]:
        stt = self.voice.stt
        health = stt.warm_up() if hasattr(stt, "warm_up") else self.voice.providers_status()["providers"]["active_stt"]
        return self.snapshot({"status": "ok", "stt": health.to_dict() if hasattr(health, "to_dict") else health, **self.voice.providers_status()})

    def speak(self, payload: dict[str, Any]) -> dict[str, Any]:
        action = str(payload.get("action", "speak"))
        if action == "stop":
            self.visual_state = "listening"
            return self.snapshot(self.voice.stop_speaking())
        if "muted" in payload:
            self.voice.set_muted(bool(payload.get("muted")))
        text = str(payload.get("text") or self.last_subtitle or "").strip()
        speech = self.voice.speak(text)
        self.visual_state = "speaking" if speech.get("voice", {}).get("speaking") else self.visual_state
        return self.snapshot(speech)

    def cancel_confirmation(self) -> dict[str, Any]:
        self.visual_state = "listening" if self.voice.status.microphone_enabled else "idle"
        self.last_subtitle = "Action cancelled."
        return self.snapshot(self.voice.cancel_confirmation())

    def toggle_subtitles(self, enabled: bool | None = None) -> dict[str, Any]:
        self.subtitles_enabled = not self.subtitles_enabled if enabled is None else bool(enabled)
        return self.snapshot({"status": "ok", "subtitles_enabled": self.subtitles_enabled})

    def set_visual_state(self, state: str) -> dict[str, Any]:
        if state not in {"idle", "inactive", "waiting_for_wake_word", "listening", "transcribing", "thinking", "speaking"}:
            return self.snapshot({"status": "error", "message": f"Unknown state: {state}"})
        self.visual_state = state
        return self.snapshot({"status": "ok", "visual_state": self.visual_state})

    def snapshot(self, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = {
            "visual_state": self.visual_state,
            "subtitles_enabled": self.subtitles_enabled,
            "last_subtitle": self.last_subtitle,
            "last_task": self.last_task,
            "recent_tasks": self.recent_tasks[-8:],
            "knowledge_sources": self.knowledge.sources() if self.knowledge else [],
            "memory_enabled": self.conversation.memory_enabled if self.conversation else True,
            "conversation_history": [item.to_dict() for item in self.conversation.turns[-10:]] if self.conversation else [],
        }
        if extra:
            payload.update(extra)
        return payload

    def _remember_task(self, task: dict[str, Any]) -> None:
        self.recent_tasks.append(
            {
                "task_id": task.get("task_id"),
                "goal": task.get("original_goal"),
                "status": task.get("status"),
                "summary": task.get("summary"),
                "created_at": task.get("created_at"),
            }
        )
        self.recent_tasks = self.recent_tasks[-20:]

    def _audit_knowledge(self, record_type: str, payload: dict[str, Any]) -> None:
        settings = self.brain.assistant.settings
        if not settings.write_audit:
            return
        append_audit_record({"record_type": record_type, **payload}, settings.audit_log)


def build_state(args: argparse.Namespace) -> WebState:
    config = load_config(args.config)
    dry_run = config.dry_run
    if args.execute:
        dry_run = False
    if args.dry_run:
        dry_run = True
    settings = RuntimeSettings.from_config(
        config,
        dataset_path=args.dataset,
        workspace=args.workspace,
        dry_run=dry_run,
        execute_requested=args.execute,
        write_audit=not args.no_audit,
        planner_mode=args.planner_mode,
        llm_model=args.llm_model,
        llm_endpoint=args.llm_endpoint,
    )
    assistant = UltronAssistant(settings)
    knowledge = KnowledgeBase(
        settings.workspace / ".ultron" / "knowledge" / "index.json",
        workspace=settings.workspace,
        safe_roots=settings.safe_roots,
    )
    return WebState(
        UltronBrain(assistant),
        knowledge=knowledge,
        skills=SkillRegistry.with_builtins(assistant, knowledge),
        voice=build_voice_session(config),
    )


def make_handler(state: WebState, web_root: Path = WEB_ROOT) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = PHASE13_VERSION

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/api/status":
                self._json(state.snapshot({"status": "ok"}))
                return
            if parsed.path == "/api/diagnostics":
                self._json(state.diagnostics())
                return
            if parsed.path == "/api/memory":
                self._json(state.memory_status())
                return
            if parsed.path == "/api/skills":
                self._json(state.skills_list())
                return
            if parsed.path == "/api/knowledge/search":
                query = parse_qs(parsed.query)
                search = str((query.get("query") or query.get("q") or [""])[0])
                try:
                    limit = int((query.get("limit") or ["5"])[0])
                except ValueError:
                    limit = 5
                self._json(state.knowledge_search(search, limit=max(1, min(limit, 25))))
                return
            if parsed.path == "/api/voice/status":
                self._json(state.voice_status())
                return
            if parsed.path == "/api/voice/providers":
                self._json(state.voice_providers())
                return
            if parsed.path == "/api/wake/status":
                self._json(state.wake_status())
                return
            if parsed.path == "/api/audit/recent":
                query = parse_qs(parsed.query)
                try:
                    limit = int((query.get("limit") or ["25"])[0])
                except ValueError:
                    limit = 25
                self._json(state.audit_recent(limit=max(1, min(limit, 100))))
                return
            self._serve_static(parsed.path)

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            body = self._read_json()
            if parsed.path == "/api/command":
                self._json(state.command(str(body.get("command", "")), confirmed=bool(body.get("confirmed", False)), mode=str(body.get("mode", "do"))))
                return
            if parsed.path == "/api/skills/run":
                self._json(state.skills_run(body))
                return
            if parsed.path == "/api/knowledge/ingest":
                self._json(state.knowledge_ingest(body))
                return
            if parsed.path == "/api/memory/forget":
                self._json(state.memory_forget(str(body.get("query") or body.get("key") or "")))
                return
            if parsed.path == "/api/memory/toggle":
                self._json(state.memory_toggle(bool(body.get("enabled", True))))
                return
            if parsed.path == "/api/voice/start":
                push_to_talk = body.get("push_to_talk")
                self._json(state.voice_start(push_to_talk=push_to_talk if isinstance(push_to_talk, bool) else None))
                return
            if parsed.path == "/api/voice/stop":
                self._json(state.voice_stop())
                return
            if parsed.path == "/api/voice/transcribe":
                self._json(state.voice_transcribe(body))
                return
            if parsed.path == "/api/voice/capture":
                self._json(state.voice_capture(body))
                return
            if parsed.path == "/api/voice/test-stt":
                self._json(state.voice_test_stt(body))
                return
            if parsed.path == "/api/voice/test-tts":
                self._json(state.voice_test_tts(body))
                return
            if parsed.path == "/api/voice/calibrate":
                self._json(state.voice_calibrate(body))
                return
            if parsed.path == "/api/voice/warmup":
                self._json(state.voice_warmup())
                return
            if parsed.path == "/api/wake/start":
                self._json(state.wake_start())
                return
            if parsed.path == "/api/wake/stop":
                self._json(state.wake_stop())
                return
            if parsed.path == "/api/wake/process":
                self._json(state.wake_process(body))
                return
            if parsed.path == "/api/speak":
                self._json(state.speak(body))
                return
            if parsed.path == "/api/confirmation/cancel":
                self._json(state.cancel_confirmation())
                return
            if parsed.path == "/api/subtitles/toggle":
                enabled = body.get("enabled")
                self._json(state.toggle_subtitles(enabled if isinstance(enabled, bool) else None))
                return
            if parsed.path == "/api/state":
                self._json(state.set_visual_state(str(body.get("state", ""))))
                return
            self._json({"status": "not_found", "message": "Unknown API route."}, status=404)

        def log_message(self, format: str, *args: object) -> None:
            return

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0") or "0")
            if length <= 0:
                return {}
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
            except json.JSONDecodeError:
                return {}
            return payload if isinstance(payload, dict) else {}

        def _json(self, payload: dict[str, Any], *, status: int = 200) -> None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _serve_static(self, request_path: str) -> None:
            if request_path in {"", "/"}:
                relative = "index.html"
            elif request_path == "/diagnostics":
                relative = "diagnostics.html"
            else:
                relative = request_path.lstrip("/")
            path = (web_root / relative).resolve()
            try:
                path.relative_to(web_root.resolve())
            except ValueError:
                self.send_error(403)
                return
            if not path.exists() or not path.is_file():
                self.send_error(404)
                return
            data = path.read_bytes()
            content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            if path.suffix == ".js":
                content_type = "text/javascript"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    return Handler


def serve(args: argparse.Namespace) -> ThreadingHTTPServer:
    state = build_state(args)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(state))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the ULTRON 2.7 visual and voice interface")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--dataset", type=Path, default=None)
    parser.add_argument("--workspace", type=Path, default=None)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-audit", action="store_true")
    parser.add_argument("--planner-mode", choices=["rules", "hybrid", "llm"], default=None)
    parser.add_argument("--llm-model", default=None)
    parser.add_argument("--llm-endpoint", default=None)
    args = parser.parse_args(argv)

    state = build_state(args)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(state))
    print(f"ULTRON 2.7 interface running at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Shutting down ULTRON interface.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
