from __future__ import annotations

import ctypes
import logging
import math
import sys
import threading
import time
from ctypes import wintypes
from typing import Any, Mapping


LOGGER = logging.getLogger(__name__)

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1

KEYEVENTF_KEYUP = 0x0002

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_XDOWN = 0x0080
MOUSEEVENTF_XUP = 0x0100
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x1000
MOUSEEVENTF_VIRTUALDESK = 0x4000
MOUSEEVENTF_ABSOLUTE = 0x8000

XBUTTON1 = 0x0001
XBUTTON2 = 0x0002

SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

VK_CONTROL = 0x11
VK_MENU = 0x12
VK_SHIFT = 0x10
VK_TAB = 0x09
VK_LEFT = 0x25
VK_RIGHT = 0x27
VK_LWIN = 0x5B

BUTTONS = {"left", "right", "middle", "x1", "x2"}
COMMANDS = {
    "minimize_all",
    "restore_all",
    "app_next",
    "app_previous",
    "task_view",
    "desktop_left",
    "desktop_right",
    "browser_back",
    "browser_forward",
}


class MOUSEINPUT(ctypes.Structure):
    _fields_ = (
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    )


class KEYBDINPUT(ctypes.Structure):
    _fields_ = (
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    )


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = (
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    )


class _INPUTUNION(ctypes.Union):
    _fields_ = (("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT))


class INPUT(ctypes.Structure):
    _anonymous_ = ("data",)
    _fields_ = (("type", wintypes.DWORD), ("data", _INPUTUNION))


def _mouse_input(flags: int, *, x: int = 0, y: int = 0, data: int = 0) -> INPUT:
    event = INPUT(type=INPUT_MOUSE)
    event.mi = MOUSEINPUT(
        dx=int(x),
        dy=int(y),
        mouseData=int(data) & 0xFFFFFFFF,
        dwFlags=int(flags),
        time=0,
        dwExtraInfo=0,
    )
    return event


def _keyboard_input(key: int, *, key_up: bool = False) -> INPUT:
    event = INPUT(type=INPUT_KEYBOARD)
    event.ki = KEYBDINPUT(
        wVk=int(key),
        wScan=0,
        dwFlags=KEYEVENTF_KEYUP if key_up else 0,
        time=0,
        dwExtraInfo=0,
    )
    return event


class WindowsSendInputBackend:
    """Thin Win32 input adapter. Policy and state live in DesktopHandInputController."""

    def __init__(self, user32: Any | None = None, *, shell_factory: Any | None = None):
        if user32 is None:
            if sys.platform != "win32":
                raise RuntimeError("Global hand input is available only on Windows.")
            user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.user32 = user32
        self.shell_factory = shell_factory
        try:
            self.user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
            self.user32.SendInput.restype = wintypes.UINT
            self.user32.GetSystemMetrics.argtypes = (ctypes.c_int,)
            self.user32.GetSystemMetrics.restype = ctypes.c_int
            self.user32.GetAsyncKeyState.argtypes = (ctypes.c_int,)
            self.user32.GetAsyncKeyState.restype = wintypes.SHORT
        except (AttributeError, TypeError):
            pass

    def virtual_desktop(self) -> dict[str, int]:
        return {
            "left": int(self.user32.GetSystemMetrics(SM_XVIRTUALSCREEN)),
            "top": int(self.user32.GetSystemMetrics(SM_YVIRTUALSCREEN)),
            "width": max(1, int(self.user32.GetSystemMetrics(SM_CXVIRTUALSCREEN))),
            "height": max(1, int(self.user32.GetSystemMetrics(SM_CYVIRTUALSCREEN))),
        }

    def move_absolute(self, x: float, y: float) -> None:
        normalized_x = round(max(0.0, min(1.0, float(x))) * 65535)
        normalized_y = round(max(0.0, min(1.0, float(y))) * 65535)
        self._send(
            [
                _mouse_input(
                    MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK,
                    x=normalized_x,
                    y=normalized_y,
                )
            ]
        )

    def button(self, button: str, state: str) -> None:
        flag_data = {
            ("left", "down"): (MOUSEEVENTF_LEFTDOWN, 0),
            ("left", "up"): (MOUSEEVENTF_LEFTUP, 0),
            ("right", "down"): (MOUSEEVENTF_RIGHTDOWN, 0),
            ("right", "up"): (MOUSEEVENTF_RIGHTUP, 0),
            ("middle", "down"): (MOUSEEVENTF_MIDDLEDOWN, 0),
            ("middle", "up"): (MOUSEEVENTF_MIDDLEUP, 0),
            ("x1", "down"): (MOUSEEVENTF_XDOWN, XBUTTON1),
            ("x1", "up"): (MOUSEEVENTF_XUP, XBUTTON1),
            ("x2", "down"): (MOUSEEVENTF_XDOWN, XBUTTON2),
            ("x2", "up"): (MOUSEEVENTF_XUP, XBUTTON2),
        }
        try:
            flags, data = flag_data[(button, state)]
        except KeyError as exc:
            raise ValueError(f"Unsupported mouse button transition: {button}/{state}") from exc
        self._send([_mouse_input(flags, data=data)])

    def scroll(self, vertical: int = 0, horizontal: int = 0) -> None:
        events: list[INPUT] = []
        if vertical:
            events.append(_mouse_input(MOUSEEVENTF_WHEEL, data=vertical))
        if horizontal:
            events.append(_mouse_input(MOUSEEVENTF_HWHEEL, data=horizontal))
        if events:
            self._send(events)

    def zoom(self, delta: int) -> None:
        if not delta:
            return
        self._send(
            [
                _keyboard_input(VK_CONTROL),
                _mouse_input(MOUSEEVENTF_WHEEL, data=delta),
                _keyboard_input(VK_CONTROL, key_up=True),
            ]
        )

    def command(self, name: str) -> None:
        if name == "minimize_all":
            self._shell_windows("MinimizeAll", fallback=(VK_LWIN, ord("D")))
        elif name == "restore_all":
            self._shell_windows("UndoMinimizeALL", fallback=(VK_LWIN, ord("D")))
        elif name == "app_next":
            self.key_chord(VK_MENU, VK_TAB)
        elif name == "app_previous":
            self.key_chord(VK_MENU, VK_SHIFT, VK_TAB)
        elif name == "task_view":
            self.key_chord(VK_LWIN, VK_TAB)
        elif name == "desktop_left":
            self.key_chord(VK_LWIN, VK_CONTROL, VK_LEFT)
        elif name == "desktop_right":
            self.key_chord(VK_LWIN, VK_CONTROL, VK_RIGHT)
        elif name == "browser_back":
            self.button("x1", "down")
            self.button("x1", "up")
        elif name == "browser_forward":
            self.button("x2", "down")
            self.button("x2", "up")
        else:
            raise ValueError(f"Unsupported desktop hand command: {name}")

    def key_chord(self, *keys: int) -> None:
        events = [_keyboard_input(key) for key in keys]
        events.extend(_keyboard_input(key, key_up=True) for key in reversed(keys))
        self._send(events)

    def emergency_hotkey_pressed(self) -> bool:
        return all(
            int(self.user32.GetAsyncKeyState(key)) & 0x8000
            for key in (VK_CONTROL, VK_MENU, ord("H"))
        )

    def _shell_windows(self, method: str, *, fallback: tuple[int, ...]) -> None:
        initialized = False
        try:
            if self.shell_factory is not None:
                shell = self.shell_factory()
            else:
                import pythoncom  # type: ignore[import-not-found]
                import win32com.client  # type: ignore[import-not-found]

                pythoncom.CoInitialize()
                initialized = True
                shell = win32com.client.Dispatch("Shell.Application")
            getattr(shell, method)()
        except Exception:
            LOGGER.exception("Windows Shell gesture action failed; using keyboard fallback")
            self.key_chord(*fallback)
        finally:
            if initialized:
                try:
                    pythoncom.CoUninitialize()  # type: ignore[name-defined]
                except Exception:
                    pass

    def _send(self, events: list[INPUT]) -> None:
        if not events:
            return
        event_array = (INPUT * len(events))(*events)
        sent = int(self.user32.SendInput(len(events), event_array, ctypes.sizeof(INPUT)))
        if sent != len(events):
            error = ctypes.get_last_error()
            raise OSError(error, f"SendInput inserted {sent} of {len(events)} events")


class DesktopHandInputController:
    """Validated, fail-safe dispatcher for Windows-wide hand input."""

    def __init__(
        self,
        backend: Any | None = None,
        *,
        platform: str | None = None,
        stale_button_seconds: float = 0.55,
        start_watchdog: bool = True,
    ):
        target_platform = platform or sys.platform
        if backend is None and target_platform == "win32":
            try:
                backend = WindowsSendInputBackend()
            except Exception:
                LOGGER.exception("Windows hand input backend could not initialize")
        self.backend = backend
        self.available = backend is not None
        self.enabled = False
        self.paused = False
        self.last_stop_reason = "not_started"
        self.stale_button_seconds = max(0.2, float(stale_button_seconds))
        self._pressed_buttons: set[str] = set()
        self._last_event_at = time.monotonic()
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._hotkey_latched = False
        self._watchdog: threading.Thread | None = None
        if self.available and start_watchdog:
            self._watchdog = threading.Thread(target=self._watchdog_loop, name="ultron-hand-input-watchdog", daemon=True)
            self._watchdog.start()

    def status(self) -> dict[str, Any]:
        with self._lock:
            bounds = self.backend.virtual_desktop() if self.available else None
            return {
                "available": self.available,
                "enabled": self.enabled,
                "paused": self.paused,
                "pressed_buttons": sorted(self._pressed_buttons),
                "last_stop_reason": self.last_stop_reason,
                "virtual_desktop": bounds,
                "emergency_hotkey": "Ctrl+Alt+H",
            }

    def set_enabled(self, enabled: bool) -> dict[str, Any]:
        with self._lock:
            if enabled and not self.available:
                return {**self.status(), "ok": False, "message": "Windows-wide hand input is unavailable."}
            if enabled:
                self.enabled = True
                self.paused = False
                self.last_stop_reason = ""
                self._last_event_at = time.monotonic()
                message = "Desktop hand control enabled."
            else:
                self._release_all_locked()
                self.enabled = False
                self.paused = False
                self.last_stop_reason = "disabled"
                message = "Desktop hand control disabled."
            return {**self.status(), "ok": True, "message": message}

    def dispatch(self, payload: Mapping[str, Any] | None) -> dict[str, Any]:
        if not isinstance(payload, Mapping):
            return {**self.status(), "ok": False, "message": "Hand input event must be an object."}
        action = str(payload.get("type", "")).strip().lower()
        with self._lock:
            if action == "status":
                return {**self.status(), "ok": True}
            if action == "disable":
                return self.set_enabled(False)
            if action == "release_all":
                self._release_all_locked()
                return {**self.status(), "ok": True}
            if action == "pause":
                self._release_all_locked()
                self.paused = True
                self.last_stop_reason = str(payload.get("reason", "gesture_pause"))
                return {**self.status(), "ok": True, "message": "Desktop hand control paused."}
            if action == "resume":
                if self.enabled:
                    self.paused = False
                    self.last_stop_reason = ""
                return {**self.status(), "ok": self.enabled, "message": "Desktop hand control resumed." if self.enabled else "Desktop hand control is off."}
            if not self.available or not self.enabled:
                return {**self.status(), "ok": False, "message": "Desktop hand control is off."}
            if self.paused:
                return {**self.status(), "ok": False, "message": "Desktop hand control is paused."}

            try:
                self._last_event_at = time.monotonic()
                if action == "move":
                    self.backend.move_absolute(_unit_float(payload.get("x")), _unit_float(payload.get("y")))
                elif action == "button":
                    self._button_event(str(payload.get("button", "")).lower(), str(payload.get("state", "")).lower())
                elif action == "scroll":
                    vertical = _bounded_int(payload.get("vertical", 0), -1200, 1200)
                    horizontal = _bounded_int(payload.get("horizontal", 0), -1200, 1200)
                    self.backend.scroll(vertical, horizontal)
                elif action == "zoom":
                    self.backend.zoom(_bounded_int(payload.get("delta", 0), -1200, 1200))
                elif action == "command":
                    command = str(payload.get("command", "")).lower()
                    if command not in COMMANDS:
                        raise ValueError(f"Unsupported hand command: {command or 'missing'}")
                    self.backend.command(command)
                elif action == "heartbeat":
                    pass
                else:
                    raise ValueError(f"Unsupported hand input event: {action or 'missing'}")
            except (TypeError, ValueError, OSError) as exc:
                return {**self.status(), "ok": False, "message": str(exc)}
            return {**self.status(), "ok": True}

    def emergency_stop(self, reason: str = "emergency_hotkey") -> None:
        with self._lock:
            self._release_all_locked()
            self.enabled = False
            self.paused = False
            self.last_stop_reason = reason

    def close(self) -> None:
        self.emergency_stop("desktop_shutdown")
        self._stop_event.set()
        if self._watchdog and self._watchdog is not threading.current_thread():
            self._watchdog.join(timeout=1.5)

    def _button_event(self, button: str, state: str) -> None:
        if button not in BUTTONS:
            raise ValueError(f"Unsupported mouse button: {button or 'missing'}")
        if state not in {"down", "up"}:
            raise ValueError(f"Unsupported mouse button state: {state or 'missing'}")
        if state == "down":
            if button in self._pressed_buttons:
                return
            self.backend.button(button, "down")
            self._pressed_buttons.add(button)
            return
        if button not in self._pressed_buttons:
            return
        self.backend.button(button, "up")
        self._pressed_buttons.discard(button)

    def _release_all_locked(self) -> None:
        for button in tuple(self._pressed_buttons):
            try:
                self.backend.button(button, "up")
            except Exception:
                LOGGER.exception("Could not release held %s mouse button", button)
            finally:
                self._pressed_buttons.discard(button)

    def _watchdog_loop(self) -> None:
        while not self._stop_event.wait(0.05):
            try:
                hotkey_pressed = bool(self.backend.emergency_hotkey_pressed())
            except Exception:
                hotkey_pressed = False
            if hotkey_pressed and not self._hotkey_latched:
                self.emergency_stop("emergency_hotkey")
            self._hotkey_latched = hotkey_pressed
            with self._lock:
                if self._pressed_buttons and time.monotonic() - self._last_event_at > self.stale_button_seconds:
                    self._release_all_locked()
                    self.last_stop_reason = "stale_input_release"


def build_hand_input_controller() -> DesktopHandInputController:
    return DesktopHandInputController()


def _unit_float(value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError("Hand cursor coordinates must be numbers.")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Hand cursor coordinates must be numbers.") from exc
    if not math.isfinite(number):
        raise ValueError("Hand cursor coordinates must be finite.")
    return max(0.0, min(1.0, number))


def _bounded_int(value: Any, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        raise ValueError("Hand input delta must be numeric.")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Hand input delta must be numeric.") from exc
    if not math.isfinite(number):
        raise ValueError("Hand input delta must be finite.")
    return max(minimum, min(maximum, round(number)))
