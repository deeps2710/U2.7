from __future__ import annotations

import json
import socket
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen

from ultron27.app_paths import desktop_data_dir
from ultron27.desktop import (
    DESKTOP_PROFILE_VERSION,
    DesktopBridge,
    build_parser,
    create_desktop_config,
    migrate_desktop_config,
    run_desktop,
    start_backend,
)
from scripts.generate_desktop_icon import generate_assets


class _FakeWebview:
    def __init__(self) -> None:
        self.settings: dict[str, object] = {}
        self.window_args: tuple[object, ...] | None = None
        self.window_kwargs: dict[str, object] | None = None
        self.start_kwargs: dict[str, object] | None = None

    def create_window(self, *args: object, **kwargs: object) -> object:
        self.window_args = args
        self.window_kwargs = kwargs
        return object()

    def start(self, **kwargs: object) -> None:
        self.start_kwargs = kwargs


class _FakeHandController:
    available = True

    def __init__(self) -> None:
        self.events: list[dict[str, object] | None] = []
        self.enabled = False

    def status(self) -> dict[str, object]:
        return {
            "available": True,
            "enabled": self.enabled,
            "paused": False,
            "pressed_buttons": [],
            "last_stop_reason": "",
            "virtual_desktop": {"left": 0, "top": 0, "width": 1920, "height": 1080},
            "emergency_hotkey": "Ctrl+Alt+H",
        }

    def set_enabled(self, enabled: bool) -> dict[str, object]:
        self.enabled = enabled
        return {**self.status(), "ok": True}

    def dispatch(self, payload: dict[str, object] | None) -> dict[str, object]:
        self.events.append(payload)
        return {**self.status(), "ok": True}


class DesktopApplicationTest(unittest.TestCase):
    def test_logo_pipeline_generates_windows_and_web_assets(self) -> None:
        from PIL import Image

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.png"
            icon = root / "ultron.ico"
            web_logo = root / "ultron-logo.png"
            favicon = root / "favicon.png"
            Image.new("RGB", (300, 300), "#07110d").save(source)

            generate_assets(source, icon, web_logo, favicon)

            with Image.open(icon) as generated_icon:
                self.assertEqual(generated_icon.format, "ICO")
                self.assertEqual(generated_icon.size, (256, 256))
            with Image.open(web_logo) as generated_web_logo:
                self.assertEqual(generated_web_logo.size, (256, 256))
            with Image.open(favicon) as generated_favicon:
                self.assertEqual(generated_favicon.size, (64, 64))

    def test_windows_data_directory_uses_local_app_data(self) -> None:
        path = desktop_data_dir(
            {"LOCALAPPDATA": r"C:\Users\Tester\AppData\Local"},
            platform="win32",
            home=Path(r"C:\Users\Tester"),
        )

        self.assertEqual(path, Path(r"C:\Users\Tester\AppData\Local") / "ULTRON 2.7")

    def test_packaged_config_uses_writable_user_paths_and_bundled_dataset(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "bundle"
            data_dir = Path(directory) / "profile"
            home = Path(directory) / "home"
            root.mkdir()
            home.mkdir()
            (root / "ultron.config.example.json").write_text(
                json.dumps({"dry_run": False, "whatsapp_contacts": {"sample": "+10000000000"}}),
                encoding="utf-8",
            )

            path = create_desktop_config(root, data_dir, home=home)
            payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertFalse(payload["dry_run"])
        self.assertEqual(payload["desktop_profile_version"], DESKTOP_PROFILE_VERSION)
        self.assertEqual(payload["whatsapp_contacts"], {})
        self.assertEqual(payload["workspace"], str(home.resolve()))
        self.assertEqual(
            payload["dataset_path"],
            str((root / "data/jarvis_dataset_v2/jarvis_laptop_commands_synthetic_v2.jsonl").resolve()),
        )
        self.assertEqual(payload["audit_log"], str((data_dir / "audit.jsonl").resolve()))

    def test_packaged_config_migration_enables_execution_and_keeps_user_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "bundle"
            data_dir = Path(directory) / "profile"
            root.mkdir()
            data_dir.mkdir()
            (root / "ultron.config.json").write_text(
                json.dumps(
                    {
                        "dry_run": False,
                        "planner_mode": "hybrid",
                        "llm_provider": "groq",
                        "llm_model": "current-model",
                        "voice_stt_provider": "deepgram",
                        "voice_tts_provider": "deepgram",
                        "voice_tts_model": "aura-2-orion-en",
                        "voice_preference": "Microsoft George",
                        "voice_rate": 1.03,
                        "voice_pitch": 1.0,
                    }
                ),
                encoding="utf-8",
            )
            config_path = data_dir / "ultron.config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "dry_run": True,
                        "workspace": str(Path(directory) / "home"),
                        "safe_roots": [str(Path(directory) / "home")],
                        "whatsapp_contacts": {"friend": "+10000000000"},
                        "planner_mode": "rules",
                        "llm_provider": "ollama",
                    }
                ),
                encoding="utf-8",
            )

            migrate_desktop_config(root, config_path, data_dir)
            payload = json.loads(config_path.read_text(encoding="utf-8"))

        self.assertFalse(payload["dry_run"])
        self.assertEqual(payload["planner_mode"], "hybrid")
        self.assertEqual(payload["llm_provider"], "groq")
        self.assertEqual(payload["llm_model"], "current-model")
        self.assertEqual(payload["voice_stt_provider"], "deepgram")
        self.assertEqual(payload["voice_tts_provider"], "deepgram")
        self.assertEqual(payload["voice_tts_model"], "aura-2-orion-en")
        self.assertEqual(payload["voice_preference"], "Microsoft George")
        self.assertEqual(payload["voice_rate"], 1.03)
        self.assertEqual(payload["voice_pitch"], 1.0)
        self.assertEqual(payload["whatsapp_contacts"], {"friend": "+10000000000"})
        self.assertEqual(payload["desktop_profile_version"], DESKTOP_PROFILE_VERSION)

    def test_current_desktop_profile_refreshes_managed_paths_without_changing_mode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "bundle"
            data_dir = Path(directory) / "profile"
            root.mkdir()
            data_dir.mkdir()
            config_path = data_dir / "ultron.config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "desktop_profile_version": DESKTOP_PROFILE_VERSION,
                        "dry_run": True,
                        "dataset_path": "stale/dataset.jsonl",
                        "whatsapp_contacts": {"friend": "+10000000000"},
                    }
                ),
                encoding="utf-8",
            )

            migrate_desktop_config(root, config_path, data_dir)
            payload = json.loads(config_path.read_text(encoding="utf-8"))

        self.assertTrue(payload["dry_run"])
        self.assertEqual(
            payload["dataset_path"],
            str((root / "data/jarvis_dataset_v2/jarvis_laptop_commands_synthetic_v2.jsonl").resolve()),
        )
        self.assertEqual(payload["whatsapp_contacts"], {"friend": "+10000000000"})

    def test_local_backend_serves_static_ui_and_stops_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            web_root = Path(directory) / "web"
            web_root.mkdir()
            (web_root / "index.html").write_text("<title>ULTRON desktop test</title>", encoding="utf-8")
            args = build_parser().parse_args(["--port", "0"])
            args.host = "127.0.0.1"
            backend = start_backend(args, web_root=web_root, state_factory=lambda _args: object())
            try:
                html = urlopen(backend.url, timeout=5).read().decode("utf-8")
                self.assertIn("ULTRON desktop test", html)
                self.assertTrue(backend.thread.is_alive())
            finally:
                backend.stop()
            self.assertFalse(backend.thread.is_alive())

    def test_desktop_backend_rejects_invalid_port(self) -> None:
        args = build_parser().parse_args(["--port", "70000"])
        args.host = "127.0.0.1"

        with self.assertRaisesRegex(ValueError, "between 0 and 65535"):
            start_backend(args, state_factory=lambda _args: object())

    def test_desktop_backend_uses_next_port_when_requested_port_is_busy(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as blocker:
            blocker.bind(("127.0.0.1", 0))
            blocker.listen(1)
            occupied_port = int(blocker.getsockname()[1])
            args = build_parser().parse_args(["--port", str(occupied_port)])
            args.host = "127.0.0.1"
            backend = start_backend(args, state_factory=lambda _args: object())
            try:
                self.assertNotEqual(args.port, occupied_port)
                self.assertEqual(args.port, backend.server.server_address[1])
            finally:
                backend.stop()

    def test_desktop_runner_creates_persistent_native_window(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "bundle"
            app_data = Path(directory) / "profile"
            web_root = root / "web"
            dataset = root / "data/jarvis_dataset_v2/jarvis_laptop_commands_synthetic_v2.jsonl"
            web_root.mkdir(parents=True)
            dataset.parent.mkdir(parents=True)
            dataset.write_text("{}\n", encoding="utf-8")
            (web_root / "index.html").write_text("<title>ULTRON</title>", encoding="utf-8")
            fake = _FakeWebview()
            args = build_parser().parse_args(["--port", "0", "--windowed", "--width", "1100", "--height", "700"])

            result = run_desktop(
                args,
                webview_module=fake,
                root=root,
                app_data=app_data,
                state_factory=lambda _args: object(),
            )

        self.assertEqual(result, 0)
        self.assertEqual(fake.window_args[0], "ULTRON 2.7")
        self.assertTrue(str(fake.window_args[1]).endswith("/?shell=desktop"))
        self.assertEqual(fake.window_kwargs["width"], 1100)
        self.assertFalse(fake.window_kwargs["maximized"])
        self.assertFalse(fake.start_kwargs["private_mode"])
        self.assertEqual(fake.start_kwargs["storage_path"], str(app_data.resolve() / "webview"))
        self.assertTrue(fake.settings["ALLOW_DOWNLOADS"])
        self.assertFalse(any(thread.name == "ultron-local-api" and thread.is_alive() for thread in threading.enumerate()))

    def test_desktop_bridge_exposes_only_runtime_metadata(self) -> None:
        payload = DesktopBridge(Path("profile")).runtime_info()

        self.assertEqual(payload["application"], "ULTRON 2.7")
        self.assertEqual(payload["shell"], "desktop")
        self.assertFalse(payload["hand_input_available"])

    def test_desktop_bridge_exposes_validated_hand_control_only_to_native_shell(self) -> None:
        controller = _FakeHandController()
        bridge = DesktopBridge(Path("profile"), controller)  # type: ignore[arg-type]

        enabled = bridge.set_hand_control(True)
        moved = bridge.hand_input({"type": "move", "x": 0.2, "y": 0.3})

        self.assertTrue(enabled["enabled"])
        self.assertTrue(moved["ok"])
        self.assertEqual(controller.events, [{"type": "move", "x": 0.2, "y": 0.3}])
        self.assertTrue(bridge.runtime_info()["hand_input_available"])


if __name__ == "__main__":
    unittest.main()
