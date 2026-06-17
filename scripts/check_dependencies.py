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

from ultron27.diagnostics import dependency_status


def build_dependency_report() -> dict[str, object]:
    required_paths = {
        "package": ROOT / "src" / "ultron27",
        "dataset": ROOT / "data" / "jarvis_dataset_v2" / "jarvis_laptop_commands_synthetic_v2.jsonl",
        "web_index": ROOT / "web" / "index.html",
        "three_vendor": ROOT / "web" / "vendor" / "three.module.min.js",
        "tests": ROOT / "tests" / "test_pipeline.py",
    }
    required_packages = {"docx", "reportlab", "pypdf", "PIL"}
    package_status = dependency_status()
    path_status = {
        name: {
            "path": str(path),
            "exists": path.exists(),
            "kind": "file" if path.is_file() else "directory" if path.is_dir() else "missing",
        }
        for name, path in required_paths.items()
    }
    missing_paths = [name for name, payload in path_status.items() if not payload["exists"]]
    missing_packages = [name for name in required_packages if not package_status.get(name, {}).get("available")]
    return {
        "status": "ok" if not missing_paths and not missing_packages else "missing_dependencies",
        "python": sys.version.split()[0],
        "root": str(ROOT),
        "paths": path_status,
        "packages": package_status,
        "missing_paths": missing_paths,
        "missing_packages": missing_packages,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check local ULTRON 2.7 dependencies.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    report = build_dependency_report()
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print("ULTRON 2.7 dependency check")
        print(f"Root: {report['root']}")
        print(f"Python: {report['python']}")
        print(f"Status: {report['status']}")
        print("\nRequired paths:")
        for name, payload in report["paths"].items():
            marker = "OK" if payload["exists"] else "MISSING"
            print(f"  [{marker}] {name}: {payload['path']}")
        print("\nPython packages:")
        for name, payload in report["packages"].items():
            marker = "OK" if payload["available"] else "OPTIONAL/MISSING"
            print(f"  [{marker}] {name}: {payload['purpose']}")
        if report["missing_packages"]:
            print("\nInstall missing report packages with:")
            print("  python -m pip install python-docx reportlab pypdf pillow")
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
