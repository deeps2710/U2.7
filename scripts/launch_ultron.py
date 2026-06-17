from __future__ import annotations

import argparse
import socket
import sys
import webbrowser
from http.server import ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from ultron27.web_server import build_state, make_handler


def find_open_port(host: str, requested: int, *, attempts: int = 20) -> int:
    for port in range(requested, requested + attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(0.25)
            if probe.connect_ex((host, port)) != 0:
                return port
    raise RuntimeError(f"No open port found from {requested} to {requested + attempts - 1}.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Launch ULTRON 2.7 backend and UI.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--strict-port", action="store_true")
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--dataset", type=Path, default=None)
    parser.add_argument("--workspace", type=Path, default=None)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-audit", action="store_true")
    parser.add_argument("--planner-mode", choices=["rules", "hybrid", "llm"], default=None)
    parser.add_argument("--llm-model", default=None)
    parser.add_argument("--llm-endpoint", default=None)
    parser.add_argument("--open", action="store_true", help="Open the UI in the default browser.")
    args = parser.parse_args(argv)

    port = args.port if args.strict_port else find_open_port(args.host, args.port)
    if port != args.port:
        print(f"Port {args.port} is busy. Using {port} instead.")
    args.port = port

    state = build_state(args)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(state))
    url = f"http://{args.host}:{args.port}"
    print("ULTRON 2.7 beta prototype is running.")
    print(f"UI:          {url}")
    print(f"Diagnostics: {url}/diagnostics")
    print("Press Ctrl+C to stop.")
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down ULTRON 2.7.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
