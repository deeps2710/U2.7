from __future__ import annotations

import os
import platform
import subprocess
import time
from pathlib import Path

from .models import ToolResult


DEFAULT_WINDOWS_APP_ALIASES = {
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "chrome": "chrome.exe",
    "google chrome": "chrome.exe",
    "explorer": "explorer.exe",
    "file explorer": "explorer.exe",
    "notepad": "notepad.exe",
    "spotify": "spotify.exe",
    "terminal": "wt.exe",
    "windows terminal": "wt.exe",
    "vs code": "code",
    "vscode": "code",
}

DEFAULT_WINDOWS_TERMINAL_ALIASES = {
    "default": "wt.exe",
    "terminal": "wt.exe",
    "windows terminal": "wt.exe",
    "command prompt": "cmd.exe",
    "cmd": "cmd.exe",
    "powershell": "powershell.exe",
}

_BLOCKED_TARGET_CHARS = {"\r", "\n", "&", "|", ";", "<", ">"}


class WindowsAutomationAdapter:
    """Typed Windows executor helpers.

    This adapter deliberately accepts only concrete typed arguments from the
    executor. It never receives a raw shell command from the planner or LLM.
    """

    def __init__(self, *, dry_run: bool, screenshot_dir: Path):
        self.dry_run = dry_run
        self.screenshot_dir = screenshot_dir

    def open_application(self, app: str, aliases: dict[str, str]) -> ToolResult:
        target = resolve_app_alias(app, aliases)
        if target is None:
            return ToolResult(
                "blocked",
                f"Application is not in the approved alias registry: {app}",
                data={"app": app, "available_aliases": sorted(aliases)},
            )
        if self.dry_run:
            return ToolResult("dry_run", f"Would open application: {app}", data={"app": app, "target": target})
        return _spawn_process(target, f"Opened application: {app}", {"app": app, "target": target})

    def open_terminal(self, terminal_type: str, aliases: dict[str, str]) -> ToolResult:
        target = resolve_app_alias(terminal_type, aliases) or aliases.get("default")
        if not target:
            return ToolResult(
                "blocked",
                f"Terminal is not in the approved alias registry: {terminal_type}",
                data={"terminal_type": terminal_type, "available_aliases": sorted(aliases)},
            )
        if self.dry_run:
            return ToolResult("dry_run", f"Would open terminal: {terminal_type}", data={"target": target})
        return _spawn_process(target, f"Opened terminal: {terminal_type}", {"target": target})

    def open_path(self, path: Path) -> ToolResult:
        if self.dry_run:
            return ToolResult("dry_run", f"Would open path: {path}", data={"path": str(path)})
        try:
            os.startfile(path)  # type: ignore[attr-defined]
        except OSError as exc:
            return ToolResult("error", f"Could not open path: {exc}", data={"path": str(path)})
        return ToolResult("success", f"Opened: {path.name}", changed={"path": str(path)})

    def write_clipboard(self, text: str) -> ToolResult:
        if self.dry_run:
            return ToolResult("dry_run", "Would copy text to clipboard.", data={"text_length": len(text)})
        try:
            import tkinter
        except ImportError:
            return ToolResult("not_implemented", "Clipboard write needs tkinter or another clipboard adapter.")
        root = tkinter.Tk()
        root.withdraw()
        try:
            root.clipboard_clear()
            root.clipboard_append(text)
            root.update()
        finally:
            root.destroy()
        return ToolResult("success", "Copied text to clipboard.", changed={"text_length": len(text)})

    def read_clipboard(self) -> ToolResult:
        if self.dry_run:
            return ToolResult("dry_run", "Would read clipboard text.")
        try:
            import tkinter
        except ImportError:
            return ToolResult("not_implemented", "Clipboard read needs tkinter or another clipboard adapter.")
        root = tkinter.Tk()
        root.withdraw()
        try:
            text = root.clipboard_get()
        except tkinter.TclError:
            text = ""
        finally:
            root.destroy()
        return ToolResult("success", "Read clipboard text.", data={"text": text})

    def take_screenshot(self) -> ToolResult:
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

    def set_system_volume(self, level: int) -> ToolResult:
        if self.dry_run:
            return ToolResult("dry_run", f"Would set volume to {level}%", data={"level": level})
        try:
            from ctypes import POINTER, cast

            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        except ImportError:
            return ToolResult("not_implemented", "Install pycaw and comtypes to enable Windows volume control.", data={"level": level})
        try:
            speakers = AudioUtilities.GetSpeakers()
            interface = speakers.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            volume = cast(interface, POINTER(IAudioEndpointVolume))
            volume.SetMasterVolumeLevelScalar(level / 100.0, None)
        except Exception as exc:  # pragma: no cover - depends on Windows audio stack
            return ToolResult("error", f"Could not set system volume: {exc}", data={"level": level})
        return ToolResult("success", f"Set volume to {level}%.", changed={"level": level})

    def set_mute(self, mute: bool) -> ToolResult:
        if self.dry_run:
            return ToolResult("dry_run", f"Would {'mute' if mute else 'unmute'} system audio.", data={"mute": mute})
        try:
            from ctypes import POINTER, cast

            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        except ImportError:
            return ToolResult("not_implemented", "Install pycaw and comtypes to enable Windows mute control.", data={"mute": mute})
        try:
            speakers = AudioUtilities.GetSpeakers()
            interface = speakers.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            volume = cast(interface, POINTER(IAudioEndpointVolume))
            volume.SetMute(1 if mute else 0, None)
        except Exception as exc:  # pragma: no cover - depends on Windows audio stack
            return ToolResult("error", f"Could not change mute state: {exc}", data={"mute": mute})
        return ToolResult("success", "Muted system audio." if mute else "Unmuted system audio.", changed={"mute": mute})

    def set_screen_brightness(self, level: int) -> ToolResult:
        if self.dry_run:
            return ToolResult("dry_run", f"Would set brightness to {level}%", data={"level": level})
        try:
            import screen_brightness_control as sbc
        except ImportError:
            return ToolResult("not_implemented", "Install screen-brightness-control to enable Windows brightness control.", data={"level": level})
        try:
            sbc.set_brightness(level)
        except Exception as exc:  # pragma: no cover - depends on display driver
            return ToolResult("error", f"Could not set screen brightness: {exc}", data={"level": level})
        return ToolResult("success", f"Set brightness to {level}%.", changed={"level": level})


def merge_windows_app_aliases(custom: dict[str, str] | None = None) -> dict[str, str]:
    return _merge_aliases(DEFAULT_WINDOWS_APP_ALIASES, custom)


def merge_windows_terminal_aliases(custom: dict[str, str] | None = None) -> dict[str, str]:
    terminal_overrides = {key: value for key, value in (custom or {}).items() if key.strip().lower() in DEFAULT_WINDOWS_TERMINAL_ALIASES}
    return _merge_aliases(DEFAULT_WINDOWS_TERMINAL_ALIASES, terminal_overrides)


def resolve_app_alias(app: str, aliases: dict[str, str]) -> str | None:
    key = app.strip().lower()
    target = aliases.get(key)
    if not target or not _safe_launch_target(target):
        return None
    return target


def _merge_aliases(defaults: dict[str, str], custom: dict[str, str] | None = None) -> dict[str, str]:
    merged = {key.strip().lower(): value.strip() for key, value in defaults.items()}
    for key, value in (custom or {}).items():
        clean_key = key.strip().lower()
        clean_value = value.strip()
        if clean_key and clean_value and _safe_launch_target(clean_value):
            merged[clean_key] = clean_value
    return merged


def _safe_launch_target(target: str) -> bool:
    if not target.strip() or any(char in target for char in _BLOCKED_TARGET_CHARS):
        return False
    return True


def _spawn_process(target: str, success_message: str, changed: dict[str, str]) -> ToolResult:
    try:
        subprocess.Popen([target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as exc:
        return ToolResult("error", f"Could not open Windows target: {exc}", data=changed)
    return ToolResult("success", success_message, changed=changed)


def is_windows() -> bool:
    return os.name == "nt" or platform.system().lower() == "windows"
