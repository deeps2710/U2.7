from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "ultron.config.json"
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


DEFAULT_ALIASES = {
    "chrome": "chrome.exe",
    "google chrome": "chrome.exe",
    "vs code": "code",
    "vscode": "code",
    "notepad": "notepad.exe",
    "spotify": "spotify.exe",
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "camera": "microsoft.windows.camera:",
    "settings": "ms-settings:",
    "task manager": "taskmgr.exe",
    "control panel": "control.exe",
    "file explorer": "explorer.exe",
    "explorer": "explorer.exe",
    "terminal": "wt.exe",
}


def generate_config(
    *,
    workspace: str = ".",
    safe_roots: list[str] | None = None,
    stt_provider: str = "browser",
    capture_provider: str = "browser",
    stt_model: str | None = None,
    tts_provider: str = "browser_speech_synthesis",
    dry_run: bool = True,
    app_aliases: dict[str, str] | None = None,
    whatsapp_contacts: dict[str, str] | None = None,
) -> dict[str, object]:
    return {
        "dataset_path": "data/jarvis_dataset_v2/jarvis_laptop_commands_synthetic_v2.jsonl",
        "audit_log": ".ultron/audit.jsonl",
        "dry_run": dry_run,
        "workspace": workspace,
        "safe_roots": safe_roots or [workspace, "~/Desktop", "~/Documents", "~/Downloads", "~/Pictures", "~/Music", "~/Videos"],
        "screenshot_dir": ".ultron/screenshots",
        "app_aliases": app_aliases or DEFAULT_ALIASES,
        "whatsapp_contacts": whatsapp_contacts or {},
        "whatsapp_require_confirmation": True,
        "planner_mode": "rules",
        "llm_provider": "ollama",
        "llm_model": "qwen2.5:7b-instruct",
        "llm_endpoint": "http://localhost:11434",
        "llm_timeout_seconds": 8,
        "voice_stt_provider": stt_provider,
        "voice_capture_provider": capture_provider,
        "voice_microphone_device": None,
        "voice_sample_rate": 16000,
        "voice_capture_seconds": 4,
        "voice_tts_provider": tts_provider,
        "voice_stt_model": stt_model,
        "voice_tts_model": "aura-2-orion-en",
        "voice_stt_language": "multi",
        "voice_stt_keyterms": ["ULTRON", "WhatsApp", "Spotify"],
        "voice_stt_model_path": None,
        "voice_tts_model_path": None,
        "voice_tts_voice_path": None,
        "voice_device": "cpu",
        "voice_identity": "ULTRON",
        "voice_preference": "Microsoft George",
        "voice_rate": 1.03,
        "voice_pitch": 1.0,
        "voice_volume": 1.0,
        "wake_word_provider": "text",
        "wake_auto_start": False,
        "wake_phrases": ["ULTRON", "Hey ULTRON"],
        "wake_model_path": None,
        "vad_provider": "energy",
        "vad_energy_threshold": 0.015,
        "startup_briefing_enabled": True,
        "assistant_location": "Jabalpur",
        "speech_barge_in_enabled": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a local ultron.config.json.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--defaults", action="store_true", help="Write a safe default config without prompts.")
    parser.add_argument("--force", action="store_true", help="Overwrite an existing config file.")
    args = parser.parse_args(argv)

    if args.output.exists() and not args.force:
        print(f"Config already exists: {args.output}")
        print("Use --force to overwrite it.")
        return 1

    if args.defaults:
        config = generate_config()
    else:
        print("ULTRON 2.7 config wizard")
        workspace = _ask("Workspace path", ".")
        safe_roots_text = _ask(
            "Safe roots, separated by semicolons",
            f"{workspace};~/Desktop;~/Documents;~/Downloads;~/Pictures;~/Music;~/Videos",
        )
        stt = _ask("STT provider (browser, text_payload, faster_whisper, whisper_cpp, mock)", "browser")
        capture = _ask("Capture provider (browser, sounddevice, mock)", "browser")
        stt_model = _ask("faster-whisper model name, if used", "base.en") if stt == "faster_whisper" else None
        tts = _ask("TTS provider (browser_speech_synthesis, deepgram, piper, pyttsx3, mock)", "browser_speech_synthesis")
        dry_run = _ask("Start in dry-run mode? (yes/no)", "yes").strip().lower() not in {"no", "n", "false", "0"}
        config = generate_config(
            workspace=workspace,
            safe_roots=[item.strip() for item in safe_roots_text.split(";") if item.strip()],
            stt_provider=stt,
            capture_provider=capture,
            stt_model=stt_model,
            tts_provider=tts,
            dry_run=dry_run,
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote config: {args.output}")
    return 0


def _ask(prompt: str, default: str) -> str:
    value = input(f"{prompt} [{default}]: ").strip()
    return value or default


if __name__ == "__main__":
    raise SystemExit(main())
