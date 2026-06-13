from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ultron27.evaluate import evaluate_dataset
from ultron27.planner import DEFAULT_DATASET_PATH, DatasetPlanner


SPLITS = {
    "all": DEFAULT_DATASET_PATH,
    "train": Path("data/jarvis_dataset_v2/splits/train.jsonl"),
    "validation": Path("data/jarvis_dataset_v2/splits/validation.jsonl"),
    "test": Path("data/jarvis_dataset_v2/splits/test.jsonl"),
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate ULTRON planner on the supplied dataset.")
    parser.add_argument("--split", choices=sorted(SPLITS), default="test")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    planner = DatasetPlanner.from_jsonl(DEFAULT_DATASET_PATH)
    metrics = evaluate_dataset(planner, SPLITS[args.split], args.limit)
    print(json.dumps(metrics, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
