from __future__ import annotations

import argparse
import json
import mimetypes
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .brain import UltronBrain
from .config import load_config
from .runtime import RuntimeSettings, UltronAssistant
from .voice import VoiceSession, build_voice_session


ROOT = Path(__file__).resolve().parents[2]
WEB_ROOT = ROOT / "web"


@dataclass
class WebState:
    brain: UltronBrain
    voice: VoiceSession = field(default_factory=VoiceSession)
    visual_state: str = "idle"
    subtitles_enabled: bool = True
    last_subtitle: str = "ULTRON 2.7 online."
    last_task: dict[str, Any] | None = None

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
        elif lowered.startswith("/do "):
            task = self.brain.execute(command[4:].strip(), confirmed=confirmed)
        elif mode == "plan":
            task = self.brain.plan(command)
        else:
            task = self.brain.execute(command, confirmed=confirmed)

        self.last_task = task.to_dict()
        self.last_subtitle = task.summary or f"Task {task.status.value}."
        self.visual_state = "speaking"
        return self.snapshot({"status": "ok", "task": self.last_task, "subtitle": self.last_subtitle})

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
        if voice_payload.get("status") == "empty":
            self.last_subtitle = str(voice_payload.get("message", "No speech was detected."))
            self.visual_state = "listening"
            return self.snapshot(voice_payload)
        user_line = voice_payload.get("record", {}).get("user_said", "")
        spoken = str(voice_payload.get("spoken_response", self.last_subtitle))
        self.last_subtitle = f"You: {user_line}\nULTRON: {spoken}"
        self.visual_state = "speaking" if not self.voice.status.muted else "idle"
        return self.snapshot({**voice_payload, "subtitle": self.last_subtitle})

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
            user_line = wake_payload.get("record", {}).get("user_said", "")
            spoken = str(wake_payload.get("spoken_response", self.last_subtitle))
            self.last_subtitle = f"You: {user_line}\nULTRON: {spoken}"
            self.visual_state = "speaking" if not self.voice.status.muted else "waiting_for_wake_word"
            return self.snapshot({**wake_payload, "subtitle": self.last_subtitle})
        self.visual_state = "waiting_for_wake_word"
        return self.snapshot(wake_payload)

    def voice_status(self) -> dict[str, Any]:
        return self.snapshot({"status": "ok", **self.voice.snapshot()})

    def voice_providers(self) -> dict[str, Any]:
        return self.snapshot({"status": "ok", **self.voice.providers_status()})

    def voice_test_stt(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.snapshot(self.voice.test_stt(payload))

    def voice_test_tts(self, payload: dict[str, Any]) -> dict[str, Any]:
        text = str(payload.get("text") or "ULTRON voice provider test.")
        return self.snapshot(self.voice.test_tts(text))

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
        }
        if extra:
            payload.update(extra)
        return payload


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
    return WebState(UltronBrain(UltronAssistant(settings)), voice=build_voice_session(config))


def make_handler(state: WebState, web_root: Path = WEB_ROOT) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "UltronPhase10/1.0"

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/api/status":
                self._json(state.snapshot({"status": "ok"}))
                return
            if parsed.path == "/api/memory":
                self._json({"status": "ok", "memory": state.brain.memory.list()})
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
            self._serve_static(parsed.path)

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            body = self._read_json()
            if parsed.path == "/api/command":
                self._json(state.command(str(body.get("command", "")), confirmed=bool(body.get("confirmed", False)), mode=str(body.get("mode", "do"))))
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
            if parsed.path == "/api/voice/test-stt":
                self._json(state.voice_test_stt(body))
                return
            if parsed.path == "/api/voice/test-tts":
                self._json(state.voice_test_tts(body))
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
            relative = "index.html" if request_path in {"", "/"} else request_path.lstrip("/")
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
