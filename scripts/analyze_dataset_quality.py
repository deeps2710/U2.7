from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ultron27.dataset_quality import analyze_dataset, build_safety_cases, load_jsonl
from ultron27.planner import DEFAULT_DATASET_PATH


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze ULTRON dataset quality and safety coverage.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH)
    parser.add_argument("--out", type=Path, default=Path("docs/phase3_dataset_quality_report.json"))
    parser.add_argument("--safety-out", type=Path, default=Path("data/regression/safety_cases.jsonl"))
    parser.add_argument("--sample-limit", type=int, default=10)
    args = parser.parse_args()

    rows = load_jsonl(args.dataset)
    report = analyze_dataset(rows, sample_limit=args.sample_limit)
    safety_cases = build_safety_cases(rows)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    args.safety_out.parent.mkdir(parents=True, exist_ok=True)
    with args.safety_out.open("w", encoding="utf-8") as handle:
        for case in safety_cases:
            handle.write(json.dumps(case, ensure_ascii=False, sort_keys=True) + "\n")

    print(json.dumps({"report": str(args.out), "safety_cases": str(args.safety_out), **report}, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()

