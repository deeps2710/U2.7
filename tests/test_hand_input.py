from __future__ import annotations

import time
import unittest

from ultron27.hand_input import DesktopHandInputController


class _FakeInputBackend:
    def __init__(self) -> None:
        self.events: list[tuple[object, ...]] = []
        self.hotkey_pressed = False

    def virtual_desktop(self) -> dict[str, int]:
        return {"left": -1920, "top": 0, "width": 3840, "height": 1080}

    def move_absolute(self, x: float, y: float) -> None:
        self.events.append(("move", x, y))

    def button(self, button: str, state: str) -> None:
        self.events.append(("button", button, state))

    def scroll(self, vertical: int, horizontal: int) -> None:
        self.events.append(("scroll", vertical, horizontal))

    def zoom(self, delta: int) -> None:
        self.events.append(("zoom", delta))

    def command(self, command: str) -> None:
        self.events.append(("command", command))

    def emergency_hotkey_pressed(self) -> bool:
        return self.hotkey_pressed


class DesktopHandInputControllerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.backend = _FakeInputBackend()
        self.controller = DesktopHandInputController(self.backend, start_watchdog=False)
        self.controller.set_enabled(True)

    def tearDown(self) -> None:
        self.controller.close()

    def test_move_clamps_to_the_full_virtual_desktop_range(self) -> None:
        payload = self.controller.dispatch({"type": "move", "x": -0.4, "y": 1.4})

        self.assertTrue(payload["ok"])
        self.assertEqual(self.backend.events, [("move", 0.0, 1.0)])
        self.assertEqual(payload["virtual_desktop"]["width"], 3840)

    def test_button_transitions_are_idempotent_and_release_on_disable(self) -> None:
        self.controller.dispatch({"type": "button", "button": "left", "state": "down"})
        self.controller.dispatch({"type": "button", "button": "left", "state": "down"})
        payload = self.controller.set_enabled(False)

        self.assertEqual(
            self.backend.events,
            [("button", "left", "down"), ("button", "left", "up")],
        )
        self.assertFalse(payload["enabled"])
        self.assertEqual(payload["pressed_buttons"], [])

    def test_scroll_zoom_and_desktop_commands_are_bounded_and_allowlisted(self) -> None:
        self.controller.dispatch({"type": "scroll", "vertical": 5000, "horizontal": -5000})
        self.controller.dispatch({"type": "zoom", "delta": 120})
        self.controller.dispatch({"type": "command", "command": "desktop_right"})
        rejected = self.controller.dispatch({"type": "command", "command": "shutdown"})

        self.assertEqual(
            self.backend.events,
            [("scroll", 1200, -1200), ("zoom", 120), ("command", "desktop_right")],
        )
        self.assertFalse(rejected["ok"])
        self.assertIn("Unsupported hand command", rejected["message"])

    def test_pause_releases_drag_and_blocks_input_until_resume(self) -> None:
        self.controller.dispatch({"type": "button", "button": "left", "state": "down"})
        paused = self.controller.dispatch({"type": "pause", "reason": "fist_hold"})
        blocked = self.controller.dispatch({"type": "move", "x": 0.3, "y": 0.4})
        resumed = self.controller.dispatch({"type": "resume"})
        accepted = self.controller.dispatch({"type": "move", "x": 0.3, "y": 0.4})

        self.assertTrue(paused["paused"])
        self.assertFalse(blocked["ok"])
        self.assertTrue(resumed["ok"])
        self.assertTrue(accepted["ok"])
        self.assertEqual(
            self.backend.events,
            [
                ("button", "left", "down"),
                ("button", "left", "up"),
                ("move", 0.3, 0.4),
            ],
        )

    def test_watchdog_releases_a_stale_held_button(self) -> None:
        controller = DesktopHandInputController(self.backend, stale_button_seconds=0.2, start_watchdog=True)
        controller.set_enabled(True)
        try:
            controller.dispatch({"type": "button", "button": "right", "state": "down"})
            deadline = time.monotonic() + 1.0
            while ("button", "right", "up") not in self.backend.events and time.monotonic() < deadline:
                time.sleep(0.03)
            self.assertIn(("button", "right", "up"), self.backend.events)
            self.assertEqual(controller.status()["last_stop_reason"], "stale_input_release")
        finally:
            controller.close()

    def test_emergency_hotkey_disables_and_releases_all_buttons(self) -> None:
        controller = DesktopHandInputController(self.backend, start_watchdog=True)
        controller.set_enabled(True)
        try:
            controller.dispatch({"type": "button", "button": "middle", "state": "down"})
            self.backend.hotkey_pressed = True
            deadline = time.monotonic() + 1.0
            while controller.status()["enabled"] and time.monotonic() < deadline:
                time.sleep(0.03)
            self.assertFalse(controller.status()["enabled"])
            self.assertEqual(controller.status()["last_stop_reason"], "emergency_hotkey")
            self.assertIn(("button", "middle", "up"), self.backend.events)
        finally:
            controller.close()


if __name__ == "__main__":
    unittest.main()
