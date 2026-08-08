from __future__ import annotations

import argparse
import secrets
import string
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from ultron27.secrets import get_secret
from ultron27.spotify import DEFAULT_REDIRECT_URI, SpotifyAuthConfig, build_auth_url, exchange_code


def main() -> None:
    parser = argparse.ArgumentParser(description="Authorize ULTRON Spotify Premium playback.")
    parser.add_argument("--client-id", default=None, help="Spotify developer app client ID")
    parser.add_argument("--redirect-uri", default=DEFAULT_REDIRECT_URI)
    parser.add_argument("--workspace", type=Path, default=Path("."))
    args = parser.parse_args()

    client_id = args.client_id or get_secret("SPOTIFY_CLIENT_ID")
    if not client_id:
        raise SystemExit("Set SPOTIFY_CLIENT_ID first, or pass --client-id.")

    config = SpotifyAuthConfig(client_id=client_id, redirect_uri=args.redirect_uri, token_path=args.workspace / ".ultron" / "spotify_token.json")
    state = secrets.token_urlsafe(18)
    verifier = _code_verifier()
    auth_url = build_auth_url(config, code_verifier=verifier, state=state)
    callback = _CallbackHandler
    callback.state = state
    callback.code = ""
    callback.error = ""

    parsed = urllib.parse.urlparse(args.redirect_uri)
    server = HTTPServer((parsed.hostname or "127.0.0.1", parsed.port or 8766), callback)
    print("Opening Spotify authorization in your browser...")
    webbrowser.open(auth_url, new=2)
    print(f"Waiting for callback on {args.redirect_uri}")
    server.handle_request()
    server.server_close()

    if callback.error:
        raise SystemExit(f"Spotify authorization failed: {callback.error}")
    if not callback.code:
        raise SystemExit("Spotify authorization did not return a code.")

    exchange_code(config, code=callback.code, code_verifier=verifier)
    print(f"Spotify authorization saved to {config.token_path}")


class _CallbackHandler(BaseHTTPRequestHandler):
    state = ""
    code = ""
    error = ""

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        returned_state = (query.get("state") or [""])[0]
        if returned_state != self.state:
            self.error = "State mismatch."
        elif query.get("error"):
            self.error = str(query["error"][0])
        else:
            self.code = str((query.get("code") or [""])[0])
        body = b"Spotify authorization complete. You can close this tab and return to ULTRON."
        self.send_response(200 if not self.error else 400)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return None


def _code_verifier() -> str:
    alphabet = string.ascii_letters + string.digits + "-._~"
    return "".join(secrets.choice(alphabet) for _ in range(96))


if __name__ == "__main__":
    main()
