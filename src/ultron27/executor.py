from __future__ import annotations

import os
import platform
import subprocess
import sys
import time
import urllib.parse
import webbrowser
from pathlib import Path
from typing import Iterable

from .models import ToolCall, ToolResult
from .windows_executor import (
    WindowsAutomationAdapter,
    is_windows,
    merge_windows_app_aliases,
    merge_windows_terminal_aliases,
)


DEFAULT_APP_ALIASES = merge_windows_app_aliases()


class Executor:
    def __init__(
        self,
        dry_run: bool = True,
        workspace: Path | None = None,
        safe_roots: Iterable[Path] | None = None,
        app_aliases: dict[str, str] | None = None,
        screenshot_dir: Path | None = None,
    ):
        self.dry_run = dry_run
        self.workspace = (workspace or Path.cwd()).resolve()
        self.safe_roots = tuple(_resolve_safe_roots(safe_roots, self.workspace))
        self.app_aliases = merge_windows_app_aliases(app_aliases)
        self.terminal_aliases = merge_windows_terminal_aliases(app_aliases)
        self.screenshot_dir = _resolve_under_workspace(screenshot_dir or Path(".ultron/screenshots"), self.workspace)
        self.windows = WindowsAutomationAdapter(dry_run=dry_run, screenshot_dir=self.screenshot_dir)

    def execute(self, call: ToolCall) -> ToolResult:
        handler = getattr(self, f"_handle_{call.name}", None)
        if handler is None:
            return self._generic(call)
        return handler(call)

    def _generic(self, call: ToolCall) -> ToolResult:
        if self.dry_run:
            return ToolResult("dry_run", f"Would run {call.name}", data={"arguments": call.arguments})
        return ToolResult("not_implemented", f"{call.name} needs an OS-specific executor.", data={"arguments": call.arguments})

    def _handle_open_application(self, call: ToolCall) -> ToolResult:
        app = str(call.arguments["app"])
        if is_windows():
            return self.windows.open_application(app, self.app_aliases)
        target = self.app_aliases.get(app.lower())
        if target is None:
            return ToolResult("blocked", f"Application is not in the approved alias registry: {app}", data={"app": app})
        if self.dry_run:
            return ToolResult("dry_run", f"Would open application: {app}", data={"app": app, "target": target})
        try:
            subprocess.Popen([target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as exc:
            return ToolResult("error", f"Could not open application: {exc}", data={"app": app, "target": target})
        return ToolResult("success", f"Opened application: {app}", changed={"app": app, "target": target})

    def _handle_assistant_reply(self, call: ToolCall) -> ToolResult:
        message = str(call.arguments["message"]).strip()
        return ToolResult("success", message or "At your service.")

    def _handle_ask_clarification(self, call: ToolCall) -> ToolResult:
        question = str(call.arguments["question"]).strip()
        return ToolResult("success", question or "Could you clarify what you want me to do?")

    def _handle_open_terminal(self, call: ToolCall) -> ToolResult:
        terminal_type = str(call.arguments.get("terminal_type", "default"))
        if is_windows():
            return self.windows.open_terminal(terminal_type, self.terminal_aliases)
        target = self.terminal_aliases.get(terminal_type.lower(), self.terminal_aliases.get("default", "sh"))
        if self.dry_run:
            return ToolResult("dry_run", f"Would open terminal: {terminal_type}", data={"target": target})
        try:
            subprocess.Popen([target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as exc:
            return ToolResult("error", f"Could not open terminal: {exc}", data={"target": target})
        return ToolResult("success", f"Opened terminal: {terminal_type}", changed={"target": target})

    def _handle_search_files(self, call: ToolCall) -> ToolResult:
        query = str(call.arguments["query"]).lower()
        root, denied = self._select_search_root(call.arguments.get("folder"))
        if denied:
            return ToolResult(
                "blocked",
                f"Search folder is outside configured safe roots: {call.arguments.get('folder')}",
                data={"safe_roots": [str(root) for root in self.safe_roots]},
            )
        file_type = str(call.arguments.get("file_type", "")).lower().lstrip(".")
        if self.dry_run:
            return ToolResult("dry_run", f"Would search {root} for: {query}", data={"root": str(root), "query": query, "file_type": file_type})

        matches: list[str] = []
        for path in root.rglob("*"):
            if len(matches) >= 25:
                break
            if not path.is_file():
                continue
            if file_type and path.suffix.lower() != f".{file_type}":
                continue
            if query in path.name.lower():
                matches.append(str(path))
        return ToolResult("success", f"Found {len(matches)} file(s).", data={"matches": matches})

    def _handle_open_file(self, call: ToolCall) -> ToolResult:
        file_name = str(call.arguments["file_name"])
        if self._is_explicit_path_outside_roots(file_name):
            return ToolResult("blocked", f"File is outside configured safe roots: {file_name}", data={"safe_roots": [str(root) for root in self.safe_roots]})
        path = self._find_file(file_name)
        if path is None:
            return ToolResult("not_found", f"Could not find file in safe roots: {file_name}", data={"safe_roots": [str(root) for root in self.safe_roots]})
        if self.dry_run:
            return ToolResult("dry_run", f"Would open file: {path.name}", data={"path": str(path)})
        if is_windows():
            return self.windows.open_path(path)
        return _open_path(path)

    def _handle_open_folder(self, call: ToolCall) -> ToolResult:
        folder = str(call.arguments["folder"])
        if self._is_explicit_path_outside_roots(folder):
            return ToolResult("blocked", f"Folder is outside configured safe roots: {folder}", data={"safe_roots": [str(root) for root in self.safe_roots]})
        path = self._find_folder(folder)
        if path is None:
            return ToolResult("not_found", f"Could not find folder in safe roots: {folder}", data={"safe_roots": [str(root) for root in self.safe_roots]})
        if self.dry_run:
            return ToolResult("dry_run", f"Would open folder: {path}", data={"path": str(path)})
        if is_windows():
            return self.windows.open_path(path)
        return _open_path(path)

    def _handle_create_note(self, call: ToolCall) -> ToolResult:
        title = _safe_filename(str(call.arguments["title"]))
        content = str(call.arguments.get("content", ""))
        note_path = self.workspace / "notes" / f"{title}.md"
        if self.dry_run:
            return ToolResult("dry_run", f"Would create note: {note_path.name}", data={"path": str(note_path), "content": content})
        note_path.parent.mkdir(parents=True, exist_ok=True)
        note_path.write_text(content + os.linesep, encoding="utf-8")
        return ToolResult("success", f"Created note: {note_path.name}", changed={"path": str(note_path)})

    def _handle_append_to_note(self, call: ToolCall) -> ToolResult:
        title = _safe_filename(str(call.arguments["title"]))
        content = str(call.arguments["content"])
        note_path = self.workspace / "notes" / f"{title}.md"
        if self.dry_run:
            return ToolResult("dry_run", f"Would append to note: {note_path.name}", data={"path": str(note_path), "content": content})
        note_path.parent.mkdir(parents=True, exist_ok=True)
        with note_path.open("a", encoding="utf-8") as handle:
            handle.write(content + os.linesep)
        return ToolResult("success", f"Updated note: {note_path.name}", changed={"path": str(note_path)})

    def _handle_set_reminder(self, call: ToolCall) -> ToolResult:
        reminder = {
            "task": str(call.arguments["task"]),
            "time": str(call.arguments["time"]),
            "created_at": int(time.time()),
        }
        path = self.workspace / ".ultron" / "reminders.jsonl"
        if self.dry_run:
            return ToolResult("dry_run", f"Would set reminder: {reminder['task']} {reminder['time']}", data=reminder)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            import json

            handle.write(json.dumps(reminder, ensure_ascii=False, sort_keys=True) + "\n")
        return ToolResult("success", f"Reminder saved: {reminder['task']} {reminder['time']}", changed={"path": str(path), **reminder})

    def _handle_start_timer(self, call: ToolCall) -> ToolResult:
        timer = {
            "duration": str(call.arguments["duration"]),
            "created_at": int(time.time()),
            "status": "scheduled",
        }
        path = self.workspace / ".ultron" / "timers.jsonl"
        if self.dry_run:
            return ToolResult("dry_run", f"Would start timer: {timer['duration']}", data=timer)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            import json

            handle.write(json.dumps(timer, ensure_ascii=False, sort_keys=True) + "\n")
        return ToolResult("success", f"Timer saved: {timer['duration']}", changed={"path": str(path), **timer})

    def _handle_search_web(self, call: ToolCall) -> ToolResult:
        query = str(call.arguments["query"]).strip()
        if not query:
            return ToolResult("blocked", "Web search needs a non-empty query.")
        url = f"https://www.google.com/search?q={urllib.parse.quote_plus(query)}"
        if self.dry_run:
            return ToolResult("dry_run", f"Would search the web for: {query}", data={"query": query, "url": url})
        return _open_url(url, f"Opened web search for: {query}", {"query": query, "url": url})

    def _handle_play_music(self, call: ToolCall) -> ToolResult:
        query = str(call.arguments["query"]).strip()
        if not query:
            return ToolResult("blocked", "Music playback needs a song, artist, or playlist name.")
        spotify_url = f"https://open.spotify.com/search/{urllib.parse.quote(query, safe='')}"
        spotify_uri = f"spotify:search:{urllib.parse.quote(query, safe='')}"
        if self.dry_run:
            return ToolResult(
                "dry_run",
                f"Would open Spotify search for: {query}",
                data={"query": query, "url": spotify_url, "spotify_uri": spotify_uri},
            )
        opened = _open_url(spotify_uri, f"Opened Spotify search for: {query}", {"query": query, "url": spotify_uri})
        if opened.status == "success":
            return opened
        return _open_url(spotify_url, f"Opened Spotify web search for: {query}", {"query": query, "url": spotify_url})

    def _handle_take_screenshot(self, call: ToolCall) -> ToolResult:
        if is_windows():
            return self.windows.take_screenshot()
        path = self.screenshot_dir / f"screenshot-{int(time.time())}.png"
        if self.dry_run:
            return ToolResult("dry_run", f"Would save screenshot: {path}", data={"path": str(path)})
        try:
            from PIL import ImageGrab
        except ImportError:
            return ToolResult("not_implemented", "Screenshot capture needs Pillow with ImageGrab support.", data={"path": str(path)})
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            image = ImageGrab.grab()
            image.save(path)
        except Exception as exc:  # pragma: no cover - OS/display dependent
            return ToolResult("error", f"Could not capture screenshot: {exc}", data={"path": str(path)})
        return ToolResult("success", f"Screenshot saved: {path.name}", changed={"path": str(path)})

    def _handle_copy_to_clipboard(self, call: ToolCall) -> ToolResult:
        text = str(call.arguments["text"])
        if is_windows():
            return self.windows.write_clipboard(text)
        if self.dry_run:
            return ToolResult("dry_run", "Would copy text to clipboard.", data={"text_length": len(text)})
        return _write_clipboard(text)

    def _handle_read_clipboard(self, call: ToolCall) -> ToolResult:
        if is_windows():
            return self.windows.read_clipboard()
        if self.dry_run:
            return ToolResult("dry_run", "Would read clipboard text.")
        return _read_clipboard()

    def _handle_set_system_volume(self, call: ToolCall) -> ToolResult:
        level = int(call.arguments["level"])
        if is_windows():
            return self.windows.set_system_volume(level)
        if self.dry_run:
            return ToolResult("dry_run", f"Would set volume to {level}%", data={"level": level})
        return ToolResult("not_implemented", "Volume control needs an OS-specific adapter.", data={"level": level})

    def _handle_mute_system_volume(self, call: ToolCall) -> ToolResult:
        mute = bool(call.arguments["mute"])
        if is_windows():
            return self.windows.set_mute(mute)
        if self.dry_run:
            return ToolResult("dry_run", f"Would {'mute' if mute else 'unmute'} system audio.", data={"mute": mute})
        return ToolResult("not_implemented", "Mute control needs an OS-specific adapter.", data={"mute": mute})

    def _handle_set_screen_brightness(self, call: ToolCall) -> ToolResult:
        level = int(call.arguments["level"])
        if is_windows():
            return self.windows.set_screen_brightness(level)
        if self.dry_run:
            return ToolResult("dry_run", f"Would set brightness to {level}%", data={"level": level})
        return ToolResult("not_implemented", "Brightness control needs an OS-specific adapter.", data={"level": level})

    def _handle_adjust_system_volume(self, call: ToolCall) -> ToolResult:
        return ToolResult("not_implemented", "Relative volume adjustment needs current-level readback before it can run safely.", data=call.arguments)

    def _handle_adjust_screen_brightness(self, call: ToolCall) -> ToolResult:
        return ToolResult("not_implemented", "Relative brightness adjustment needs current-level readback before it can run safely.", data=call.arguments)

    def _handle_delete_file(self, call: ToolCall) -> ToolResult:
        file_name = str(call.arguments["file_name"])
        if self.dry_run:
            return ToolResult("dry_run", f"Would delete file after confirmation: {file_name}", data={"file_name": file_name})
        return ToolResult("not_implemented", "Destructive file deletion is intentionally not implemented in the MVP.", data=call.arguments)

    def _handle_run_script(self, call: ToolCall) -> ToolResult:
        return ToolResult("not_implemented", "Script execution requires a separate approved-script registry.", data=call.arguments)

    def _handle_send_email(self, call: ToolCall) -> ToolResult:
        return ToolResult("not_implemented", "Email sending is intentionally not implemented; use draft_email first.", data=call.arguments)

    def _handle_shutdown_system(self, call: ToolCall) -> ToolResult:
        return ToolResult("not_implemented", "Shutdown is intentionally not implemented in this prototype.", data=call.arguments)

    def _handle_restart_system(self, call: ToolCall) -> ToolResult:
        return ToolResult("not_implemented", "Restart is intentionally not implemented in this prototype.", data=call.arguments)

    def _handle_move_file(self, call: ToolCall) -> ToolResult:
        return ToolResult("not_implemented", "Moving files is confirmation-gated and not implemented until a safe move policy is designed.", data=call.arguments)

    def _handle_rename_file(self, call: ToolCall) -> ToolResult:
        return ToolResult("not_implemented", "Renaming files is confirmation-gated and not implemented until a safe rename policy is designed.", data=call.arguments)

    def _handle_close_application(self, call: ToolCall) -> ToolResult:
        return ToolResult("not_implemented", "Closing apps needs a separate allowlisted window-control adapter.", data=call.arguments)

    def _select_search_root(self, folder: object | None) -> tuple[Path, bool]:
        if not folder:
            return self.safe_roots[0], False
        explicit = Path(str(folder)).expanduser()
        if explicit.is_absolute():
            resolved = explicit.resolve()
            if resolved.is_dir() and any(_is_relative_to(resolved, root) for root in self.safe_roots):
                return resolved, False
            return self.safe_roots[0], True
        folder_name = str(folder).lower()
        for root in self.safe_roots:
            if root.name.lower() == folder_name:
                return root, False
            candidate = root / str(folder)
            if candidate.exists() and candidate.is_dir() and _is_relative_to(candidate.resolve(), root):
                return candidate.resolve(), False
        return self.safe_roots[0], False

    def _find_file(self, file_name: str) -> Path | None:
        target = file_name.lower()
        explicit = Path(file_name).expanduser()
        if explicit.is_absolute():
            resolved = explicit.resolve()
            if resolved.is_file() and any(_is_relative_to(resolved, root) for root in self.safe_roots):
                return resolved
            return None
        for root in self.safe_roots:
            direct = root / file_name
            if direct.is_file() and _is_relative_to(direct.resolve(), root):
                return direct.resolve()
            for path in root.rglob("*"):
                if path.is_file() and path.name.lower() == target:
                    return path.resolve()
        return None

    def _find_folder(self, folder_name: str) -> Path | None:
        target = folder_name.lower()
        explicit = Path(folder_name).expanduser()
        if explicit.is_absolute():
            resolved = explicit.resolve()
            if resolved.is_dir() and any(_is_relative_to(resolved, root) for root in self.safe_roots):
                return resolved
            return None
        for root in self.safe_roots:
            if root.name.lower() == target:
                return root
            direct = root / folder_name
            if direct.is_dir() and _is_relative_to(direct.resolve(), root):
                return direct.resolve()
            for path in root.rglob("*"):
                if path.is_dir() and path.name.lower() == target:
                    return path.resolve()
        return None

    def _is_explicit_path_outside_roots(self, value: str) -> bool:
        path = Path(value).expanduser()
        if not path.is_absolute():
            return False
        resolved = path.resolve()
        return not any(_is_relative_to(resolved, root) for root in self.safe_roots)


def _safe_filename(value: str) -> str:
    cleaned = "".join(char for char in value if char.isalnum() or char in {" ", "-", "_"}).strip()
    return cleaned.replace(" ", "_") or "untitled"


def _resolve_safe_roots(safe_roots: Iterable[Path] | None, workspace: Path) -> list[Path]:
    roots = list(safe_roots or (workspace,))
    resolved: list[Path] = []
    for root in roots:
        candidate = _resolve_under_workspace(root, workspace)
        if candidate not in resolved:
            resolved.append(candidate)
    return resolved or [workspace]


def _resolve_under_workspace(path: Path, workspace: Path) -> Path:
    candidate = path.expanduser()
    if not candidate.is_absolute():
        candidate = workspace / candidate
    return candidate.resolve()


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _open_path(path: Path) -> ToolResult:
    try:
        if os.name == "nt":
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.Popen(["xdg-open", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as exc:
        return ToolResult("error", f"Could not open path: {exc}", data={"path": str(path)})
    return ToolResult("success", f"Opened: {path.name}", changed={"path": str(path)})


def _open_url(url: str, success_message: str, changed: dict[str, str]) -> ToolResult:
    try:
        opened = webbrowser.open(url, new=2)
    except Exception as exc:
        return ToolResult("error", f"Could not open URL: {exc}", data=changed)
    if not opened:
        return ToolResult("error", "The system browser did not accept the URL.", data=changed)
    return ToolResult("success", success_message, changed=changed)


def _write_clipboard(text: str) -> ToolResult:
    if os.name == "nt":
        try:
            subprocess.run(["clip"], input=text, text=True, check=True)
        except OSError as exc:
            return ToolResult("error", f"Could not write clipboard: {exc}")
        except subprocess.CalledProcessError as exc:
            return ToolResult("error", f"Clipboard command failed: {exc}")
        return ToolResult("success", "Copied text to clipboard.", changed={"text_length": len(text)})
    return ToolResult("not_implemented", f"Clipboard write is not implemented on {platform.system()}.")


def _read_clipboard() -> ToolResult:
    if os.name != "nt":
        return ToolResult("not_implemented", f"Clipboard read is not implemented on {platform.system()}.")
    command = [
        "powershell.exe",
        "-NoProfile",
        "-Command",
        "Get-Clipboard -Raw",
    ]
    try:
        proc = subprocess.run(command, capture_output=True, text=True, check=True)
    except OSError as exc:
        return ToolResult("error", f"Could not read clipboard: {exc}")
    except subprocess.CalledProcessError as exc:
        return ToolResult("error", f"Clipboard command failed: {exc}")
    return ToolResult("success", "Read clipboard text.", data={"text": proc.stdout})

