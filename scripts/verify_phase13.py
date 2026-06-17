from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from ultron27.brain import UltronBrain
from ultron27.runtime import RuntimeSettings, UltronAssistant
from ultron27.web_server import WebState, make_handler


def main() -> int:
    checks = [
        ("tests", [sys.executable, "-m", "unittest", "discover", "-s", "tests"]),
        ("dataset", [sys.executable, "scripts/evaluate_dataset.py", "--split", "test"]),
        ("safety", [sys.executable, "scripts/evaluate_safety_regression.py"]),
    ]
    results: list[dict[str, object]] = []
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC)
    for name, command in checks:
        result = subprocess.run(command, cwd=ROOT, env=env, check=False, capture_output=True, text=True, timeout=120)
        results.append({"name": name, "returncode": result.returncode, "stdout": result.stdout[-3000:], "stderr": result.stderr[-3000:]})

    results.append({"name": "api_smoke", **api_smoke()})
    failed = [item for item in results if item.get("returncode", 0) != 0 or item.get("status") == "failed"]
    print(json.dumps({"status": "ok" if not failed else "failed", "results": results}, indent=2, ensure_ascii=False))
    return 1 if failed else 0


def api_smoke() -> dict[str, object]:
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        settings = RuntimeSettings(
            dataset_path=ROOT / "data" / "jarvis_dataset_v2" / "jarvis_laptop_commands_synthetic_v2.jsonl",
            audit_log=workspace / ".ultron" / "audit.jsonl",
            workspace=workspace,
            dry_run=True,
            safe_roots=(workspace,),
            app_aliases=None,
            screenshot_dir=workspace / ".ultron" / "screenshots",
            planner_mode="rules",
            llm_model="unused",
            llm_endpoint="http://localhost:11434",
            llm_timeout_seconds=1.0,
            write_audit=True,
        )
        state = WebState(UltronBrain(UltronAssistant(settings)))
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(state))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            status = _get(base + "/api/status")
            diagnostics = _get(base + "/api/diagnostics")
            command = _post(base + "/api/command", {"command": "create note verify phase thirteen", "mode": "do"})
            voice = _post(base + "/api/voice/transcribe", {"transcript": "ULTRON, create note verify voice"})
        finally:
            server.shutdown()
            server.server_close()
    ok = (
        status.get("status") == "ok"
        and diagnostics.get("status") == "ok"
        and command.get("task", {}).get("status") in {"completed", "waiting_for_confirmation"}
        and voice.get("status") == "ok"
    )
    return {
        "status": "ok" if ok else "failed",
        "returncode": 0 if ok else 1,
        "diagnostics_readiness": diagnostics.get("readiness"),
    }


def _get(url: str) -> dict[str, object]:
    return json.loads(urlopen(url, timeout=5).read().decode("utf-8"))


def _post(url: str, payload: dict[str, object]) -> dict[str, object]:
    return json.loads(
        urlopen(
            Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST"),
            timeout=5,
        )
        .read()
        .decode("utf-8")
    )


if __name__ == "__main__":
    raise SystemExit(main())
