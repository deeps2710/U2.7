from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import time
import urllib.parse
import ctypes
from ctypes import wintypes
from pathlib import Path
from typing import Any, Callable

from .models import ToolResult


DEFAULT_WINDOWS_APP_ALIASES = {
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "camera": "microsoft.windows.camera:",
    "chrome": "chrome.exe",
    "google chrome": "chrome.exe",
    "control panel": "control.exe",
    "cursor": "cursor",
    "cursor editor": "cursor",
    "explorer": "explorer.exe",
    "file explorer": "explorer.exe",
    "notepad": "notepad.exe",
    "photos": "ms-photos:",
    "paint": "mspaint.exe",
    "mspaint": "mspaint.exe",
    "word": "winword.exe",
    "microsoft word": "winword.exe",
    "excel": "excel.exe",
    "microsoft excel": "excel.exe",
    "powerpoint": "powerpnt.exe",
    "microsoft powerpoint": "powerpnt.exe",
    "spotify": "spotify.exe",
    "settings": "ms-settings:",
    "windows settings": "ms-settings:",
    "store": "ms-windows-store:",
    "microsoft store": "ms-windows-store:",
    "task manager": "taskmgr.exe",
    "clock": "ms-clock:",
    "alarms": "ms-clock:",
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
VK_CONTROL = 0x11
VK_RETURN = 0x0D
VK_ESCAPE = 0x1B
VK_SPACE = 0x20
VK_TAB = 0x09
VK_V = 0x56
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_PLAY_PAUSE = 0xB3
KEYEVENTF_KEYUP = 0x0002
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
WM_CLOSE = 0x0010
_DPI_AWARENESS_INITIALIZED = False


class WindowsAutomationAdapter:
    """Typed Windows executor helpers.

    This adapter deliberately accepts only concrete typed arguments from the
    executor. It never receives a raw shell command from the planner or LLM.
    """

    def __init__(self, *, dry_run: bool, screenshot_dir: Path):
        _enable_windows_dpi_awareness()
        self.dry_run = dry_run
        self.screenshot_dir = screenshot_dir

    def open_application(self, app: str, aliases: dict[str, str]) -> ToolResult:
        target = resolve_app_target(app, aliases)
        if target is None:
            return ToolResult(
                "blocked",
                f"Could not find an installed application named: {app}",
                data={"app": app, "available_aliases": sorted(aliases)},
            )
        if self.dry_run:
            return ToolResult("dry_run", f"Would open application: {app}", data={"app": app, "target": target})
        return _spawn_process(target, f"Opened application: {app}", {"app": app, "target": target})

    def switch_application(self, app: str, aliases: dict[str, str]) -> ToolResult:
        target = resolve_app_target(app, aliases)
        if target is None:
            return ToolResult("not_found", f"Could not find an installed application named: {app}", data={"app": app})
        if self.dry_run:
            return ToolResult("dry_run", f"Would switch to application: {app}", data={"app": app, "target": target})
        deadline = time.time() + 3.0
        last_hwnd: int | None = None
        while time.time() < deadline:
            last_hwnd = _find_application_window(app, target)
            if last_hwnd is not None and _activate_window(last_hwnd):
                return ToolResult("success", f"Switched to {app}.", changed={"app": app, "window": last_hwnd})
            time.sleep(0.2)
        if last_hwnd is None:
            return ToolResult("not_found", f"{app} is installed but does not appear to be open.", data={"app": app, "target": target})
        return ToolResult("error", f"Found {app}, but Windows did not allow ULTRON to bring it forward.", data={"app": app})

    def close_application(self, app: str, aliases: dict[str, str]) -> ToolResult:
        target = resolve_app_target(app, aliases)
        if target is None:
            return ToolResult("not_found", f"Could not find an installed application named: {app}", data={"app": app})
        if self.dry_run:
            return ToolResult("dry_run", f"Would ask {app} to close.", data={"app": app, "target": target})
        hwnd = _find_application_window(app, target)
        if hwnd is None:
            return ToolResult("not_found", f"{app} is not currently open.", data={"app": app, "target": target})
        if not _user32().PostMessageW(hwnd, WM_CLOSE, 0, 0):
            return ToolResult("error", f"Windows rejected the close request for {app}.", data={"app": app, "window": hwnd})
        time.sleep(0.35)
        return ToolResult(
            "success",
            f"Asked {app} to close. Any unsaved-work prompt remains under your control.",
            changed={"app": app, "window": hwnd, "close_requested": True},
        )

    def lock_screen(self) -> ToolResult:
        if self.dry_run:
            return ToolResult("dry_run", "Would lock the Windows session after confirmation.")
        try:
            locked = bool(_user32().LockWorkStation())
        except Exception as exc:
            return ToolResult("error", f"Could not lock the Windows session: {exc}")
        if not locked:
            return ToolResult("error", "Windows rejected the lock request.")
        return ToolResult("success", "Locked the Windows session.", changed={"locked": True})

    def control_media(self, action: str) -> ToolResult:
        normalized = action.strip().lower()
        keys = {
            "play": VK_MEDIA_PLAY_PAUSE,
            "pause": VK_MEDIA_PLAY_PAUSE,
            "toggle": VK_MEDIA_PLAY_PAUSE,
            "next": VK_MEDIA_NEXT_TRACK,
            "previous": VK_MEDIA_PREV_TRACK,
        }
        vk = keys.get(normalized)
        if vk is None:
            return ToolResult("blocked", f"Unsupported media action: {action}", data={"action": action})
        if self.dry_run:
            return ToolResult("dry_run", f"Would send the Windows media command: {normalized}", data={"action": normalized})
        _tap_key(vk)
        label = {"next": "next track", "previous": "previous track"}.get(normalized, "play/pause")
        return ToolResult("success", f"Sent the Windows {label} command.", changed={"action": normalized})

    def write_text_in_application(self, app: str, text: str, aliases: dict[str, str]) -> ToolResult:
        target = resolve_app_alias(app, aliases)
        if target is None:
            return ToolResult(
                "blocked",
                f"Application is not in the approved alias registry: {app}",
                data={"app": app, "available_aliases": sorted(aliases)},
            )
        if self.dry_run:
            return ToolResult("dry_run", f"Would open {app} and write text.", data={"app": app, "target": target, "text_length": len(text)})
        try:
            process = subprocess.Popen([target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as exc:
            return ToolResult("error", f"Could not open Windows target: {exc}", data={"app": app, "target": target})
        try:
            _write_clipboard_windows(text)
        except (OSError, subprocess.CalledProcessError) as exc:
            return ToolResult("error", f"Opened {app}, but could not copy text for pasting: {exc}", changed={"app": app, "target": target})
        hwnd = _focus_window_for_automation(process_pid=process.pid, title_hint=app, timeout=3.0)
        if hwnd is None:
            hwnd = _focus_window_for_automation(title_hint=app, timeout=3.0)
        if hwnd is None:
            return ToolResult(
                "error",
                f"Opened {app}, but could not focus its window to paste text.",
                changed={"app": app, "target": target},
                data={"text_length": len(text)},
            )
        try:
            _send_key_sequence(("ctrl+v",))
        except OSError as exc:
            return ToolResult("error", f"Opened {app}, but could not paste text: {exc}", changed={"app": app, "target": target})
        return ToolResult("success", f"Opened {app} and wrote text.", changed={"app": app, "target": target, "text_length": len(text)})

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

    def play_spotify_query(self, query: str) -> ToolResult:
        spotify_uri = f"spotify:search:{urllib.parse.quote(query, safe='')}"
        if self.dry_run:
            return ToolResult("dry_run", f"Would open Spotify and play: {query}", data={"query": query, "url": spotify_uri})
        try:
            os.startfile(spotify_uri)  # type: ignore[attr-defined]
        except Exception as exc:
            return ToolResult("error", f"Could not open Spotify: {exc}", data={"query": query, "url": spotify_uri})
        hwnd = _focus_spotify_window(timeout=5.0)
        if hwnd is None:
            return ToolResult(
                "error",
                f"Opened Spotify for {query}, but could not focus its window, so playback was not started.",
                data={"query": query, "url": spotify_uri, "playback_started": False},
            )
        if not _force_spotify_search(query):
            return ToolResult(
                "error",
                f"Opened Spotify for {query}, but could not enter the exact search text, so playback was not started.",
                data={"query": query, "url": spotify_uri, "playback_started": False},
            )
        if not _click_spotify_result_play_button(hwnd):
            return ToolResult(
                "error",
                f"Spotify found the search page for {query}, but ULTRON could not reliably locate the first result's Play button. Configure Spotify Premium authorization for API playback.",
                data={"query": query, "url": spotify_uri, "playback_started": False},
            )
        return ToolResult(
            "success",
            f"Playing on Spotify: {query}",
            changed={"query": query},
            data={"provider": "spotify_desktop", "playback_started": True, "playback_method": "verified_play_button"},
        )

    def activate_spotify(self) -> ToolResult:
        if self.dry_run:
            return ToolResult("dry_run", "Would open Spotify for Spotify Connect activation.")
        try:
            os.startfile("spotify:")  # type: ignore[attr-defined]
        except Exception as exc:
            return ToolResult("error", f"Could not open Spotify: {exc}")
        hwnd = _focus_spotify_window(timeout=6.0)
        if hwnd is None:
            return ToolResult("error", "Spotify opened, but its window could not be focused.")
        time.sleep(1.0)
        return ToolResult("success", "Spotify is open and available for playback.")

    def send_whatsapp_message(self, recipient: str, message: str, contacts: dict[str, str]) -> ToolResult:
        phone, contact_source = resolve_whatsapp_recipient(recipient, contacts)
        if not phone:
            if _looks_like_phone_recipient(recipient):
                return ToolResult(
                    "blocked",
                    "WhatsApp phone numbers must include the country code. Nothing was sent.",
                    data={"recipient": recipient, "message_length": len(message)},
                )
            return self._send_whatsapp_named_contact(recipient, message)
        masked_phone = _mask_phone(phone)
        if self.dry_run:
            return ToolResult(
                "dry_run",
                f"Would send a WhatsApp message to {recipient} ({masked_phone}).",
                data={"recipient": recipient, "phone": masked_phone, "message_length": len(message), "contact_source": contact_source},
            )
        params = urllib.parse.urlencode({"phone": phone, "text": message}, quote_via=urllib.parse.quote)
        whatsapp_uri = f"whatsapp://send?{params}"
        try:
            os.startfile(whatsapp_uri)  # type: ignore[attr-defined]
        except Exception as exc:
            return ToolResult(
                "error",
                f"Could not open WhatsApp: {exc}. Nothing was sent.",
                data={"recipient": recipient, "phone": masked_phone, "message_length": len(message)},
            )
        hwnd = _focus_whatsapp_window(timeout=8.0)
        if hwnd is None:
            return ToolResult(
                "error",
                "WhatsApp opened, but ULTRON could not verify that its window was focused. Nothing was sent.",
                data={"recipient": recipient, "phone": masked_phone, "message_length": len(message)},
            )
        time.sleep(1.8)
        if _user32().GetForegroundWindow() != hwnd:
            return ToolResult(
                "error",
                "WhatsApp lost focus before sending, so ULTRON stopped. Nothing was sent.",
                data={"recipient": recipient, "phone": masked_phone, "message_length": len(message)},
            )
        try:
            _send_key_sequence(("enter",))
        except OSError as exc:
            return ToolResult(
                "error",
                f"WhatsApp was ready, but ULTRON could not press Send: {exc}",
                data={"recipient": recipient, "phone": masked_phone, "message_length": len(message)},
            )
        return ToolResult(
            "success",
            f"Sent WhatsApp message to {recipient}.",
            changed={"recipient": recipient, "message_length": len(message)},
            data={
                "provider": "whatsapp_desktop",
                "phone": masked_phone,
                "contact_source": contact_source,
                "send_submitted": True,
                "delivery_verified": False,
            },
        )

    def _send_whatsapp_named_contact(self, recipient: str, message: str) -> ToolResult:
        if not _safe_whatsapp_contact_name(recipient):
            return ToolResult(
                "blocked",
                "WhatsApp contact names must be between 2 and 80 characters and cannot contain control characters. Nothing was sent.",
                data={"recipient": recipient, "message_length": len(message)},
            )
        if self.dry_run:
            return ToolResult(
                "dry_run",
                f"Would find the exact WhatsApp contact {recipient} and send the exact message.",
                data={"recipient": recipient, "message_length": len(message), "contact_source": "desktop_exact_name"},
            )
        try:
            from pywinauto import Desktop, keyboard
        except ImportError:
            return ToolResult(
                "not_implemented",
                "Named WhatsApp contacts need pywinauto. Install ULTRON with the Windows extras.",
                data={"recipient": recipient, "message_length": len(message)},
            )

        hwnd = _focus_whatsapp_window(timeout=1.5)
        if hwnd is None:
            target = _find_installed_app_target("whatsapp")
            if target is None:
                return ToolResult("not_found", "WhatsApp is not installed. Nothing was sent.", data={"recipient": recipient})
            opened = _spawn_process(target, "Opened WhatsApp.", {"app": "whatsapp", "target": target})
            if opened.status != "success":
                return ToolResult("error", f"{opened.message} Nothing was sent.", data={"recipient": recipient})
            hwnd = _focus_whatsapp_window(timeout=12.0)
        if hwnd is None:
            return ToolResult(
                "error",
                "WhatsApp opened, but ULTRON could not access its window. Nothing was sent.",
                data={"recipient": recipient, "message_length": len(message)},
            )

        try:
            window, search = _wait_for_whatsapp_ui(Desktop, hwnd, timeout=18.0)
            if window is None or search is None:
                return ToolResult(
                    "error",
                    "WhatsApp opened, but its chat interface did not become ready in time. Nothing was sent.",
                    data={"recipient": recipient, "message_length": len(message)},
                )
            hwnd = int(window.handle)
            selected = _whatsapp_active_contact_matches(window, recipient)
            if not selected:
                search.click_input()
                _write_clipboard_windows(recipient)
                keyboard.send_keys("^a^v")
                time.sleep(0.8)
                candidates = _whatsapp_contact_result_candidates(window, recipient)
                for candidate in candidates:
                    candidate.click_input()
                    time.sleep(0.55)
                    window = Desktop(backend="uia").window(handle=hwnd)
                    if _whatsapp_active_contact_matches(window, recipient):
                        selected = True
                        break
            if not selected:
                return ToolResult(
                    "not_found",
                    f'WhatsApp did not expose an exact contact named "{recipient}". Nothing was sent.',
                    data={"recipient": recipient, "message_length": len(message)},
                )

            composer = _find_whatsapp_composer(window)
            if composer is None:
                return ToolResult(
                    "error",
                    f'ULTRON selected "{recipient}", but could not find the message box. Nothing was sent.',
                    data={"recipient": recipient, "message_length": len(message)},
                )
            existing = _whatsapp_composer_text(composer)
            if existing:
                return ToolResult(
                    "blocked",
                    f'WhatsApp already has an unsent draft for "{recipient}". ULTRON left it unchanged and sent nothing.',
                    data={"recipient": recipient, "message_length": len(message), "existing_draft_length": len(existing)},
                )

            composer.click_input()
            _write_clipboard_windows(message)
            keyboard.send_keys("^v")
            time.sleep(0.35)
            if _whatsapp_composer_text(composer) != message:
                keyboard.send_keys("^a{BACKSPACE}")
                return ToolResult(
                    "error",
                    "WhatsApp did not contain the exact requested message, so ULTRON cleared its draft and sent nothing.",
                    data={"recipient": recipient, "message_length": len(message)},
                )

            keyboard.send_keys("{ENTER}")
            deadline = time.time() + 3.0
            while time.time() < deadline:
                time.sleep(0.15)
                if not _whatsapp_composer_text(composer):
                    return ToolResult(
                        "success",
                        f"Sent WhatsApp message to {recipient}.",
                        changed={"recipient": recipient, "message_length": len(message)},
                        data={
                            "provider": "whatsapp_desktop_uia",
                            "contact_source": "desktop_exact_name",
                            "contact_verified": True,
                            "message_verified_before_send": True,
                            "send_submitted": True,
                            "delivery_verified": False,
                        },
                    )
            return ToolResult(
                "error",
                "WhatsApp did not clear the composer after Send, so ULTRON could not verify submission.",
                data={"recipient": recipient, "message_length": len(message)},
            )
        except Exception as exc:
            return ToolResult(
                "error",
                f"WhatsApp automation stopped before it could verify the send: {exc}",
                data={"recipient": recipient, "message_length": len(message)},
            )

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
            volume = _windows_endpoint_volume()
        except ImportError:
            return ToolResult("not_implemented", "Install pycaw and comtypes to enable Windows volume control.", data={"level": level})
        try:
            volume.SetMasterVolumeLevelScalar(level / 100.0, None)
        except Exception as exc:  # pragma: no cover - depends on Windows audio stack
            return ToolResult("error", f"Could not set system volume: {exc}", data={"level": level})
        return ToolResult("success", f"Set volume to {level}%.", changed={"level": level})

    def adjust_system_volume(self, direction: str, delta: int) -> ToolResult:
        if self.dry_run:
            return ToolResult("dry_run", f"Would turn volume {direction} by {delta}%.", data={"direction": direction, "delta": delta})
        try:
            volume = _windows_endpoint_volume()
        except ImportError:
            return ToolResult("not_implemented", "Install pycaw and comtypes to enable Windows volume control.", data={"direction": direction, "delta": delta})
        try:
            current = int(round(float(volume.GetMasterVolumeLevelScalar()) * 100))
            target = max(0, min(100, current + delta if direction == "up" else current - delta))
            volume.SetMasterVolumeLevelScalar(target / 100.0, None)
        except Exception as exc:  # pragma: no cover - depends on Windows audio stack
            return ToolResult("error", f"Could not adjust system volume: {exc}", data={"direction": direction, "delta": delta})
        return ToolResult("success", f"Set volume to {target}%.", changed={"previous_level": current, "level": target})

    def set_mute(self, mute: bool) -> ToolResult:
        if self.dry_run:
            return ToolResult("dry_run", f"Would {'mute' if mute else 'unmute'} system audio.", data={"mute": mute})
        try:
            volume = _windows_endpoint_volume()
        except ImportError:
            return ToolResult("not_implemented", "Install pycaw and comtypes to enable Windows mute control.", data={"mute": mute})
        try:
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

    def adjust_screen_brightness(self, direction: str, delta: int) -> ToolResult:
        if self.dry_run:
            return ToolResult("dry_run", f"Would turn brightness {direction} by {delta}%.", data={"direction": direction, "delta": delta})
        try:
            import screen_brightness_control as sbc
        except ImportError:
            return ToolResult("not_implemented", "Install screen-brightness-control to enable Windows brightness control.", data={"direction": direction, "delta": delta})
        try:
            levels = sbc.get_brightness(display=0)
            current = int(levels[0] if isinstance(levels, list) else levels)
            target = max(0, min(100, current + delta if direction == "up" else current - delta))
            sbc.set_brightness(target, display=0)
        except Exception as exc:  # pragma: no cover - depends on display driver
            return ToolResult("error", f"Could not adjust screen brightness: {exc}", data={"direction": direction, "delta": delta})
        return ToolResult("success", f"Set brightness to {target}%.", changed={"previous_level": current, "level": target})


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
    return _resolve_special_target(key, target)


def resolve_app_target(app: str, aliases: dict[str, str]) -> str | None:
    alias = resolve_app_alias(app, aliases)
    if alias:
        return alias
    return _find_installed_app_target(app)


def resolve_whatsapp_recipient(recipient: str, contacts: dict[str, str]) -> tuple[str, str]:
    key = " ".join(recipient.strip().casefold().split())
    normalized_contacts = {" ".join(name.strip().casefold().split()): number.strip() for name, number in contacts.items()}
    mapped = normalized_contacts.get(key)
    candidate = mapped if mapped is not None else recipient.strip()
    digits = re.sub(r"\D", "", candidate)
    explicitly_international = candidate.lstrip().startswith("+") or candidate.lstrip().startswith("00") or len(digits) >= 11
    if not explicitly_international or not 8 <= len(digits) <= 15 or digits.startswith("0"):
        return "", ""
    return digits, "configured_contact" if mapped is not None else "direct_number"


def _mask_phone(phone: str) -> str:
    return f"+***{phone[-4:]}" if len(phone) >= 4 else "+***"


def _looks_like_phone_recipient(value: str) -> bool:
    stripped = value.strip()
    return bool(stripped) and not any(char.isalpha() for char in stripped) and len(re.sub(r"\D", "", stripped)) >= 7


def _safe_whatsapp_contact_name(value: str) -> bool:
    cleaned = value.strip()
    return 2 <= len(cleaned) <= 80 and not any(ord(char) < 32 for char in cleaned)


def _normalize_contact_name(value: str) -> str:
    return " ".join(value.casefold().split())


def _unique_uia_controls(window: Any, control_type: str) -> list[Any]:
    unique: list[Any] = []
    seen: set[tuple[str, int, int, int, int]] = set()
    for control in window.descendants(control_type=control_type):
        rect = control.rectangle()
        if rect.width() <= 0 or rect.height() <= 0:
            continue
        key = (control.window_text(), rect.left, rect.top, rect.right, rect.bottom)
        if key in seen:
            continue
        seen.add(key)
        unique.append(control)
    return unique


def _wait_for_whatsapp_ui(desktop_factory: Any, hwnd: int, *, timeout: float) -> tuple[Any | None, Any | None]:
    deadline = time.time() + timeout
    last_window: Any | None = None
    current_hwnd = hwnd
    while time.time() < deadline:
        focused = _focus_whatsapp_window(timeout=0.5)
        if focused is not None:
            current_hwnd = focused
        try:
            last_window = desktop_factory(backend="uia").window(handle=current_hwnd)
            search = _find_whatsapp_search_control(last_window)
            if search is not None:
                return last_window, search
        except Exception:
            pass
        time.sleep(0.35)
    return last_window, None


def _whatsapp_active_contact_matches(window: Any, recipient: str) -> bool:
    bounds = window.rectangle()
    right_pane_start = bounds.left + int(bounds.width() * 0.40)
    header_bottom = bounds.top + 150
    expected = _normalize_contact_name(recipient)
    for button in _unique_uia_controls(window, "Button"):
        rect = button.rectangle()
        if rect.left < right_pane_start or rect.top > header_bottom:
            continue
        if _normalize_contact_name(button.window_text()) == expected:
            return True
    return False


def _find_whatsapp_search_control(window: Any) -> Any | None:
    bounds = window.rectangle()
    left_pane_end = bounds.left + int(bounds.width() * 0.43)
    for edit in _unique_uia_controls(window, "Edit"):
        rect = edit.rectangle()
        if rect.right <= left_pane_end and bounds.top + 90 <= rect.top <= bounds.top + 220 and rect.width() >= 120:
            return edit
    return None


def _whatsapp_contact_result_candidates(window: Any, recipient: str) -> list[Any]:
    bounds = window.rectangle()
    left_pane_end = bounds.left + int(bounds.width() * 0.45)
    expected = _normalize_contact_name(recipient)
    by_row: dict[tuple[int, int], Any] = {}
    for item in _unique_uia_controls(window, "DataItem"):
        rect = item.rectangle()
        accessible_name = _normalize_contact_name(item.window_text())
        if rect.right > left_pane_end or rect.top < bounds.top + 220 or rect.width() < int(bounds.width() * 0.25):
            continue
        if accessible_name != expected and not accessible_name.startswith(f"{expected} "):
            continue
        key = (rect.left, rect.top)
        current = by_row.get(key)
        if current is None or rect.height() > current.rectangle().height():
            by_row[key] = item
    return sorted(by_row.values(), key=lambda item: (item.rectangle().top, item.rectangle().left))


def _find_whatsapp_composer(window: Any) -> Any | None:
    bounds = window.rectangle()
    right_pane_start = bounds.left + int(bounds.width() * 0.45)
    candidates = []
    for edit in _unique_uia_controls(window, "Edit"):
        rect = edit.rectangle()
        if rect.left >= right_pane_start and rect.bottom >= bounds.bottom - 160 and rect.width() >= int(bounds.width() * 0.25):
            candidates.append(edit)
    if not candidates:
        return None
    return max(candidates, key=lambda edit: edit.rectangle().bottom)


def _whatsapp_composer_text(composer: Any) -> str:
    value = composer.window_text().strip()
    if _normalize_contact_name(value).startswith("type a message"):
        return ""
    return value


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


def _resolve_special_target(key: str, target: str) -> str:
    if key in {"cursor", "cursor editor"} and target.strip().lower() == "cursor":
        return _cursor_executable() or target
    return target


def _find_installed_app_target(app: str) -> str | None:
    cleaned = app.strip().strip('"')
    if not cleaned or any(char in cleaned for char in _BLOCKED_TARGET_CHARS):
        return None
    explicit = Path(cleaned).expanduser()
    if explicit.is_absolute() and explicit.is_file() and explicit.suffix.lower() in {".exe", ".lnk", ".appref-ms"}:
        return str(explicit)
    for candidate in _path_candidates(cleaned):
        if candidate:
            return candidate
    app_path = _app_paths_target(cleaned)
    if app_path:
        return app_path
    shortcut = _start_menu_shortcut(cleaned)
    if shortcut:
        return shortcut
    return _start_app_target(cleaned)


def _path_candidates(app: str) -> list[str]:
    names = [app]
    if not Path(app).suffix:
        names.append(f"{app}.exe")
    found: list[str] = []
    for name in names:
        if any(char in name for char in _BLOCKED_TARGET_CHARS):
            continue
        target = shutil.which(name)
        if target and target not in found:
            found.append(target)
    return found


def _start_menu_shortcut(app: str) -> str | None:
    needle = _normalize_app_name(app)
    if not needle:
        return None
    matches: list[tuple[int, str]] = []
    for root in _start_menu_roots():
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".lnk", ".appref-ms", ".url"}:
                continue
            name = _normalize_app_name(path.stem)
            parent = _normalize_app_name(path.parent.name)
            if name == needle:
                matches.append((0, str(path)))
            elif needle in name:
                matches.append((1, str(path)))
            elif needle and needle in parent:
                matches.append((2, str(path)))
    if not matches:
        return None
    matches.sort(key=lambda item: (item[0], len(item[1])))
    return matches[0][1]


def _app_paths_target(app: str) -> str | None:
    if not is_windows():
        return None
    try:
        import winreg
    except ImportError:
        return None
    needle = _normalize_app_name(app)
    if not needle:
        return None
    roots = (
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\App Paths"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\App Paths"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths"),
    )
    for hive, subkey in roots:
        try:
            with winreg.OpenKey(hive, subkey) as key:
                count = winreg.QueryInfoKey(key)[0]
                for index in range(count):
                    name = winreg.EnumKey(key, index)
                    normalized_name = _normalize_app_name(Path(name).stem)
                    if needle not in {normalized_name, _normalize_app_name(name)} and needle not in normalized_name:
                        continue
                    try:
                        with winreg.OpenKey(key, name) as app_key:
                            value, _kind = winreg.QueryValueEx(app_key, "")
                    except OSError:
                        continue
                    target = str(value).strip('"')
                    if target and Path(target).is_file():
                        return target
        except OSError:
            continue
    return None


def _start_app_target(app: str) -> str | None:
    if not is_windows():
        return None
    needle = _normalize_app_name(app)
    if not needle:
        return None
    command = [
        "powershell.exe",
        "-NoProfile",
        "-Command",
        "Get-StartApps | ConvertTo-Json -Compress",
    ]
    try:
        proc = subprocess.run(command, capture_output=True, check=True, timeout=8)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    payload = _loads_json_output(proc.stdout)
    if payload is None:
        return None
    rows = payload if isinstance(payload, list) else [payload]
    matches: list[tuple[int, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("Name") or "")
        app_id = str(row.get("AppID") or "")
        normalized = _normalize_app_name(name)
        if not normalized or not app_id or any(char in app_id for char in _BLOCKED_TARGET_CHARS):
            continue
        if normalized == needle:
            matches.append((0, app_id))
        elif needle in normalized:
            matches.append((1, app_id))
    if not matches:
        return None
    matches.sort(key=lambda item: (item[0], len(item[1])))
    return f"shell:AppsFolder\\{matches[0][1]}"


def _loads_json_output(output: bytes | str) -> object | None:
    import json

    if isinstance(output, str):
        candidates = [output]
    else:
        candidates = [
            output.decode("utf-8-sig", errors="replace"),
            output.decode("utf-16", errors="replace"),
            output.decode("utf-16le", errors="replace"),
        ]
    for text in candidates:
        text = text.strip()
        if not text:
            continue
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            continue
    return None


def _start_menu_roots() -> list[Path]:
    roots: list[Path] = []
    program_data = os.environ.get("PROGRAMDATA")
    app_data = os.environ.get("APPDATA")
    if program_data:
        roots.append(Path(program_data) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
    if app_data:
        roots.append(Path(app_data) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
    return roots


def _normalize_app_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _cursor_executable() -> str | None:
    if not is_windows():
        return shutil.which("cursor")
    local = os.environ.get("LOCALAPPDATA", "")
    for relative in (("Programs", "cursor", "Cursor.exe"), ("Programs", "Cursor", "Cursor.exe")):
        if not local:
            continue
        candidate = Path(local).joinpath(*relative)
        if candidate.is_file():
            return str(candidate)
    return shutil.which("cursor")


def _spawn_process(target: str, success_message: str, changed: dict[str, str]) -> ToolResult:
    try:
        suffix = Path(target).suffix.lower()
        if _is_launch_uri(target) or suffix in {".lnk", ".url", ".appref-ms"}:
            os.startfile(target)  # type: ignore[attr-defined]
        else:
            subprocess.Popen([target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as exc:
        return ToolResult("error", f"Could not open Windows target: {exc}", data=changed)
    return ToolResult("success", success_message, changed=changed)


def _is_launch_uri(target: str) -> bool:
    if re.match(r"^[a-z]:[\\/]", target, flags=re.IGNORECASE):
        return False
    return bool(re.match(r"^[a-z][a-z0-9+.-]*:", target, flags=re.IGNORECASE))


def _find_application_window(app: str, target: str) -> int | None:
    process_name = ""
    if not _is_launch_uri(target) and Path(target).suffix.lower() == ".exe":
        process_name = Path(target).name
    if process_name:
        hwnd = _find_window(process_name=process_name, title_hint=app)
        if hwnd is None:
            hwnd = _find_window(process_name=process_name)
        if hwnd is not None:
            return hwnd
    return _find_window(title_hint=app)


def _activate_window(hwnd: int) -> bool:
    user32 = _user32()
    user32.ShowWindow(hwnd, 5)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.2)
    if user32.GetForegroundWindow() == hwnd:
        return True
    rect = _window_rect(hwnd)
    if rect is None:
        return False
    left, top, right, _bottom = rect
    _click_screen_point((left + right) // 2, top + 8)
    time.sleep(0.2)
    return user32.GetForegroundWindow() == hwnd


def _windows_endpoint_volume() -> Any:
    from ctypes import POINTER, cast

    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

    speakers = AudioUtilities.GetSpeakers()
    endpoint = getattr(speakers, "EndpointVolume", None)
    if endpoint is not None:
        return endpoint
    interface = speakers.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return cast(interface, POINTER(IAudioEndpointVolume))


def _write_clipboard_windows(text: str) -> None:
    subprocess.run(["clip"], input=text, text=True, check=True)


def _focus_window_for_automation(*, process_pid: int | None = None, title_hint: str = "", timeout: float = 3.0) -> int | None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        hwnd = _find_window(process_pid=process_pid, title_hint=title_hint)
        if hwnd:
            user32 = _user32()
            user32.ShowWindow(hwnd, 5)
            user32.SetForegroundWindow(hwnd)
            time.sleep(0.15)
            return hwnd
        time.sleep(0.1)
    return None


def _focus_spotify_window(*, timeout: float = 3.0) -> int | None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        hwnd = _find_window(process_name="spotify.exe", title_hint="spotify")
        if hwnd is None:
            hwnd = _find_window(process_name="spotify.exe")
        if hwnd is None:
            hwnd = _find_window(title_hint="spotify")
        if hwnd:
            user32 = _user32()
            user32.ShowWindow(hwnd, 5)
            user32.SetForegroundWindow(hwnd)
            time.sleep(0.25)
            return hwnd
        time.sleep(0.1)
    return None


def _focus_whatsapp_window(*, timeout: float = 5.0) -> int | None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        hwnd = _find_window(process_name="whatsapp.root.exe", title_hint="whatsapp")
        if hwnd is None:
            hwnd = _find_window(process_name="whatsapp.root.exe")
        if hwnd is None:
            hwnd = _find_window(title_hint="whatsapp")
        if hwnd:
            user32 = _user32()
            user32.ShowWindow(hwnd, 5)
            user32.SetForegroundWindow(hwnd)
            time.sleep(0.25)
            return hwnd
        time.sleep(0.1)
    return None


def _find_window(*, process_pid: int | None = None, process_name: str = "", title_hint: str = "") -> int | None:
    user32 = _user32()
    title_hint = title_hint.lower()
    process_name = process_name.lower()
    found: list[int] = []

    @ctypes_callback
    def enum_proc(hwnd: int, _lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if process_pid is not None and pid.value != process_pid:
            return True
        if process_name and _process_name(pid.value).lower() != process_name:
            return True
        title = _window_title(hwnd).lower()
        if title_hint and title_hint not in title:
            return True
        found.append(hwnd)
        return False

    user32.EnumWindows(enum_proc, 0)
    return found[0] if found else None


def _window_title(hwnd: int) -> str:
    user32 = _user32()
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value


def _window_rect(hwnd: int) -> tuple[int, int, int, int] | None:
    rect = wintypes.RECT()
    if not _user32().GetWindowRect(hwnd, ctypes.byref(rect)):
        return None
    return (rect.left, rect.top, rect.right, rect.bottom)


def _process_name(pid: int) -> str:
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return ""
        return Path(buffer.value).name
    finally:
        kernel32.CloseHandle(handle)


def _send_key_sequence(sequence: tuple[str, ...]) -> None:
    for key in sequence:
        if key == "ctrl+l":
            _key_down(VK_CONTROL)
            _tap_key(0x4C)
            _key_up(VK_CONTROL)
        elif key == "ctrl+v":
            _key_down(VK_CONTROL)
            _tap_key(VK_V)
            _key_up(VK_CONTROL)
        elif key == "esc":
            _tap_key(VK_ESCAPE)
        elif key == "enter":
            _tap_key(VK_RETURN)
        elif key == "space":
            _tap_key(VK_SPACE)
        elif key == "tab":
            _tap_key(VK_TAB)
        time.sleep(0.12)


def _force_spotify_search(query: str) -> bool:
    time.sleep(0.6)
    try:
        _write_clipboard_windows(query)
    except (OSError, subprocess.CalledProcessError):
        return False
    _send_key_sequence(("ctrl+l", "ctrl+v", "enter"))
    time.sleep(1.4)
    return True


def _click_spotify_result_play_button(hwnd: int) -> bool:
    try:
        from PIL import ImageGrab
    except ImportError:
        return False

    if not _ensure_spotify_window_foreground(hwnd):
        return False

    for _attempt in range(6):
        time.sleep(0.45)
        rect = _window_rect(hwnd)
        if rect is None:
            return False
        left, top, right, bottom = rect
        width = max(0, right - left)
        height = max(0, bottom - top)
        if width < 300 or height < 250:
            return False
        regions = (
            (int(width * 0.22), 120, width - 20, min(height - 180, 390)),
            (80, 90, width - 20, height - 140),
        )
        for crop_left, crop_top, crop_right, crop_bottom in regions:
            if crop_right <= crop_left or crop_bottom <= crop_top:
                continue
            image = ImageGrab.grab(bbox=(left + crop_left, top + crop_top, left + crop_right, top + crop_bottom)).convert("RGB")
            center = _largest_spotify_green_component_center(image)
            if center is None:
                continue
            x, y = center
            screen_x = left + crop_left + x
            screen_y = top + crop_top + y
            if _spotify_play_button_state(screen_x, screen_y) == "pause":
                return True
            _click_screen_point(screen_x, screen_y)
            deadline = time.time() + 3.0
            while time.time() < deadline:
                time.sleep(0.2)
                if _spotify_play_button_state(screen_x, screen_y) == "pause":
                    return True
            return False
    return False


def _ensure_spotify_window_foreground(hwnd: int) -> bool:
    user32 = _user32()
    if user32.GetForegroundWindow() == hwnd:
        return True
    user32.ShowWindow(hwnd, 5)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.2)
    if user32.GetForegroundWindow() == hwnd:
        return True
    rect = _window_rect(hwnd)
    if rect is None:
        return False
    left, top, right, _bottom = rect
    _click_screen_point((left + right) // 2, top + 6)
    time.sleep(0.2)
    return user32.GetForegroundWindow() == hwnd


def _spotify_play_button_state(screen_x: int, screen_y: int) -> str:
    try:
        from PIL import ImageGrab
    except ImportError:
        return "unknown"
    image = ImageGrab.grab(
        bbox=(screen_x - 20, screen_y - 20, screen_x + 21, screen_y + 21)
    ).convert("RGB")
    return _spotify_button_icon_state(image)


def _spotify_button_icon_state(image: object) -> str:
    width, height = image.size  # type: ignore[attr-defined]
    pixels = image.load()  # type: ignore[attr-defined]
    column_counts = [
        sum(1 for y in range(height) if max(pixels[x, y]) < 90)
        for x in range(width)
    ]
    strong_columns = [index for index, count in enumerate(column_counts) if count >= max(8, int(height * 0.28))]
    groups: list[list[int]] = []
    for column in strong_columns:
        if not groups or column > groups[-1][-1] + 1:
            groups.append([column])
        else:
            groups[-1].append(column)
    substantial = [group for group in groups if len(group) >= 3]
    if len(substantial) >= 2:
        return "pause"
    if len(substantial) == 1:
        return "play"
    return "unknown"


def _largest_spotify_green_component_center(image: object) -> tuple[int, int] | None:
    width, height = image.size  # type: ignore[attr-defined]
    pixels = image.load()  # type: ignore[attr-defined]
    visited: set[tuple[int, int]] = set()
    best: tuple[int, int, int, int, int] | None = None

    def is_green(x: int, y: int) -> bool:
        red, green, blue = pixels[x, y]
        return green >= 145 and red <= 90 and blue <= 130 and green - red >= 70 and green - blue >= 40

    for y in range(0, height, 2):
        for x in range(0, width, 2):
            if (x, y) in visited or not is_green(x, y):
                continue
            stack = [(x, y)]
            visited.add((x, y))
            count = 0
            min_x = max_x = x
            min_y = max_y = y
            while stack:
                cx, cy = stack.pop()
                count += 1
                min_x = min(min_x, cx)
                max_x = max(max_x, cx)
                min_y = min(min_y, cy)
                max_y = max(max_y, cy)
                for nx, ny in ((cx + 2, cy), (cx - 2, cy), (cx, cy + 2), (cx, cy - 2)):
                    if nx < 0 or ny < 0 or nx >= width or ny >= height or (nx, ny) in visited:
                        continue
                    if is_green(nx, ny):
                        visited.add((nx, ny))
                        stack.append((nx, ny))
            box_width = max_x - min_x + 1
            box_height = max_y - min_y + 1
            if count >= 45 and 18 <= box_width <= 95 and 18 <= box_height <= 95:
                if best is None or count > best[0]:
                    best = (count, min_x, min_y, max_x, max_y)
    if best is None:
        return None
    _count, min_x, min_y, max_x, max_y = best
    return ((min_x + max_x) // 2, (min_y + max_y) // 2)


def _click_screen_point(x: int, y: int) -> None:
    user32 = _user32()
    user32.SetCursorPos(int(x), int(y))
    time.sleep(0.08)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.05)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


def _enable_windows_dpi_awareness() -> None:
    global _DPI_AWARENESS_INITIALIZED
    if _DPI_AWARENESS_INITIALIZED or platform.system().lower() != "windows":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
    _DPI_AWARENESS_INITIALIZED = True


def _tap_key(vk: int) -> None:
    _key_down(vk)
    _key_up(vk)


def _key_down(vk: int) -> None:
    _user32().keybd_event(vk, 0, 0, 0)


def _key_up(vk: int) -> None:
    _user32().keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)


def _user32() -> object:
    return ctypes.windll.user32


def ctypes_callback(function: Callable[[int, int], bool]) -> object:
    return ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(function)


def is_windows() -> bool:
    return os.name == "nt" or platform.system().lower() == "windows"
