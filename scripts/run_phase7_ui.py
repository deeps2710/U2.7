from __future__ import annotations

import sys
from pathlib import Path
import traceback


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ultron27.web_server import main  # noqa: E402


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log_dir = ROOT / ".ultron"
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / "phase7-launch-error.txt").write_text(traceback.format_exc(), encoding="utf-8")
        raise
