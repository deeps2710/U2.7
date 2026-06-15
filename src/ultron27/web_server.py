from __future__ import annotations

import argparse
import json
import mimetypes
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .brain import UltronBrain
from .config import load_config
from .runtime import RuntimeSettings, UltronAssistant


ROOT = Path(__file__).resolve().parents[2]
WEB_ROOT = ROOT / "web"


@dataclass
class WebState:
    brain: UltronBrain
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

    def toggle_subtitles(self, enabled: bool | None = None) -> dict[str, Any]:
        self.subtitles_enabled = not self.subtitles_enabled if enabled is None else bool(enabled)
        return self.snapshot({"status": "ok", "subtitles_enabled": self.subtitles_enabled})

    def set_visual_state(self, state: str) -> dict[str, Any]:
        if state not in {"idle", "listening", "thinking", "speaking"}:
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
    return WebState(UltronBrain(UltronAssistant(settings)))


def make_handler(state: WebState, web_root: Path = WEB_ROOT) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "UltronPhase7/1.0"

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/api/status":
                self._json(state.snapshot({"status": "ok"}))
                return
            if parsed.path == "/api/memory":
                self._json({"status": "ok", "memory": state.brain.memory.list()})
                return
            self._serve_static(parsed.path)

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            body = self._read_json()
            if parsed.path == "/api/command":
                self._json(state.command(str(body.get("command", "")), confirmed=bool(body.get("confirmed", False)), mode=str(body.get("mode", "do"))))
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
    parser = argparse.ArgumentParser(description="Run the ULTRON 2.7 Phase 7 visual interface")
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
