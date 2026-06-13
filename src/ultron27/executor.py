from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .models import ToolCall, ToolResult


class Executor:
    def __init__(self, dry_run: bool = True, workspace: Path | None = None):
        self.dry_run = dry_run
        self.workspace = workspace or Path.cwd()

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
        if self.dry_run:
            return ToolResult("dry_run", f"Would open application: {app}", data={"app": app})
        try:
            subprocess.Popen([app], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as exc:
            return ToolResult("error", f"Could not open application: {exc}", data={"app": app})
        return ToolResult("success", f"Opened application: {app}", changed={"app": app})

    def _handle_search_files(self, call: ToolCall) -> ToolResult:
        query = str(call.arguments["query"]).lower()
        folder = call.arguments.get("folder")
        root = _safe_search_root(folder)
        if self.dry_run:
            return ToolResult("dry_run", f"Would search {root} for: {query}", data={"root": str(root), "query": query})

        matches: list[str] = []
        for path in root.rglob("*"):
            if len(matches) >= 25:
                break
            if path.is_file() and query in path.name.lower():
                matches.append(str(path))
        return ToolResult("success", f"Found {len(matches)} file(s).", data={"matches": matches})

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

    def _handle_set_system_volume(self, call: ToolCall) -> ToolResult:
        level = int(call.arguments["level"])
        if self.dry_run:
            return ToolResult("dry_run", f"Would set volume to {level}%", data={"level": level})
        return ToolResult("not_implemented", "Volume control needs a Windows/macOS/Linux adapter.", data={"level": level})

    def _handle_set_screen_brightness(self, call: ToolCall) -> ToolResult:
        level = int(call.arguments["level"])
        if self.dry_run:
            return ToolResult("dry_run", f"Would set brightness to {level}%", data={"level": level})
        return ToolResult("not_implemented", "Brightness control needs a Windows/macOS/Linux adapter.", data={"level": level})

    def _handle_delete_file(self, call: ToolCall) -> ToolResult:
        file_name = str(call.arguments["file_name"])
        if self.dry_run:
            return ToolResult("dry_run", f"Would delete file after confirmation: {file_name}", data={"file_name": file_name})
        return ToolResult("not_implemented", "Destructive file deletion is intentionally not implemented in the MVP.", data=call.arguments)

    def _handle_run_script(self, call: ToolCall) -> ToolResult:
        return ToolResult("not_implemented", "Script execution requires a separate approved-script registry.", data=call.arguments)

    def _handle_send_email(self, call: ToolCall) -> ToolResult:
        return ToolResult("not_implemented", "Email sending is intentionally not implemented; use draft_email first.", data=call.arguments)


def _safe_search_root(folder: object | None) -> Path:
    home = Path.home()
    if not folder:
        return home
    candidate = home / str(folder)
    try:
        candidate.relative_to(home)
    except ValueError:
        return home
    return candidate if candidate.exists() else home


def _safe_filename(value: str) -> str:
    cleaned = "".join(char for char in value if char.isalnum() or char in {" ", "-", "_"}).strip()
    return cleaned.replace(" ", "_") or "untitled"

