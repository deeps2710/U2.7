from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from ultron27.config import load_config
from ultron27.voice import build_voice_session


def build_provider_report(config_path: Path | None = None) -> dict[str, object]:
    config = load_config(config_path, base_dir=ROOT)
    voice = build_voice_session(config)
    providers = voice.providers_status()
    gate = voice.gate_status()
    warnings: list[str] = []
    for kind in ("stt", "tts"):
        health = providers.get("providers", {}).get(kind, {})
        if health and not health.get("available", True):
            warnings.append(str(health.get("detail", f"{kind.upper()} provider unavailable")))
    return {
        "status": "ok" if not warnings else "fallback_active",
        "providers": providers,
        "wake_and_vad": gate,
        "warnings": warnings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check configured ULTRON STT/TTS/wake/VAD providers.")
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true", help="Return non-zero when configured local providers fall back.")
    args = parser.parse_args(argv)

    report = build_provider_report(args.config)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        providers = report["providers"]
        print("ULTRON 2.7 provider check")
        print(f"Status: {report['status']}")
        print(f"STT configured: {providers['configured']['stt']} | active: {providers['active']['stt']}")
        print(f"TTS configured: {providers['configured']['tts']} | active: {providers['active']['tts']}")
        print(f"Voice identity: {providers['voice_identity']}")
        print(f"Wake provider: {report['wake_and_vad']['gate_providers']['active_wake']['name']}")
        print(f"VAD provider: {report['wake_and_vad']['gate_providers']['active_vad']['name']}")
        for warning in report["warnings"]:
            print(f"Warning: {warning}")
    return 1 if args.strict and report["warnings"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
