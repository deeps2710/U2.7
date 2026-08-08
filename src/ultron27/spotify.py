from __future__ import annotations

import base64
import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import ToolResult
from .secrets import get_secret


AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
API_URL = "https://api.spotify.com/v1"
DEFAULT_REDIRECT_URI = "http://127.0.0.1:8766/callback"
SCOPES = "user-read-playback-state user-modify-playback-state"


@dataclass(frozen=True)
class SpotifyAuthConfig:
    client_id: str
    redirect_uri: str = DEFAULT_REDIRECT_URI
    token_path: Path = Path(".ultron/spotify_token.json")


class SpotifyWebPlayer:
    def __init__(self, config: SpotifyAuthConfig) -> None:
        self.config = config

    @classmethod
    def from_workspace(cls, workspace: Path) -> "SpotifyWebPlayer | None":
        token_path = workspace / ".ultron" / "spotify_token.json"
        saved = _read_token(token_path)
        client_id = get_secret("SPOTIFY_CLIENT_ID") or str(saved.get("client_id", ""))
        if not client_id:
            return None
        redirect_uri = os.environ.get("SPOTIFY_REDIRECT_URI") or str(saved.get("redirect_uri", "")) or DEFAULT_REDIRECT_URI
        return cls(SpotifyAuthConfig(client_id=client_id, redirect_uri=redirect_uri, token_path=token_path))

    def play(self, query: str) -> ToolResult:
        token = self._access_token()
        if not token:
            return ToolResult(
                "not_configured",
                "Spotify Premium playback needs one-time Spotify login. Run: python scripts/spotify_auth.py",
                data={"query": query},
            )
        try:
            track = self._search_track(query, token)
            device_id = self._active_or_first_device(token)
        except urllib.error.HTTPError as exc:
            return ToolResult(
                "error",
                f"Spotify API request failed with HTTP {exc.code}: {_http_error_detail(exc)}",
                data={"query": query, "provider": "spotify_web_api", "http_status": int(exc.code)},
            )
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            return ToolResult(
                "error",
                f"Spotify API could not be reached: {exc}",
                data={"query": query, "provider": "spotify_web_api"},
            )
        if not track:
            return ToolResult("not_found", f"Spotify did not find a playable track for: {query}", data={"query": query})
        if not device_id:
            return ToolResult(
                "device_unavailable",
                "Spotify is authorized, but no controllable Spotify Connect device is available. Open Spotify once and try again.",
                data={"query": query, "provider": "spotify_web_api"},
            )
        response = self._start_playback(token, track["uri"], device_id=device_id)
        if response in {200, 202, 204}:
            return ToolResult(
                "success",
                f"Playing on Spotify: {track['name']}",
                changed={"query": query, "track": track["name"], "uri": track["uri"]},
                data={"provider": "spotify_web_api", "artist": track.get("artist", ""), "device_id": device_id or ""},
            )
        return ToolResult("error", f"Spotify playback request failed with HTTP {response}.", data={"query": query, "track": track})

    def _access_token(self) -> str:
        token = _read_token(self.config.token_path)
        if not token:
            return ""
        if float(token.get("expires_at", 0)) - 30 > time.time():
            return str(token.get("access_token", ""))
        refresh_token = str(token.get("refresh_token", ""))
        if not refresh_token:
            return ""
        refreshed = self._refresh(refresh_token)
        if not refreshed:
            return ""
        if "refresh_token" not in refreshed:
            refreshed["refresh_token"] = refresh_token
        refreshed["client_id"] = self.config.client_id
        refreshed["redirect_uri"] = self.config.redirect_uri
        _write_token(self.config.token_path, refreshed)
        return str(refreshed.get("access_token", ""))

    def _refresh(self, refresh_token: str) -> dict[str, Any] | None:
        body = urllib.parse.urlencode(
            {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": self.config.client_id,
            }
        ).encode("utf-8")
        request = urllib.request.Request(TOKEN_URL, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception:
            return None
        payload["expires_at"] = time.time() + float(payload.get("expires_in", 3600))
        return payload

    def _search_track(self, query: str, token: str) -> dict[str, str] | None:
        params = urllib.parse.urlencode({"q": query, "type": "track", "limit": 1})
        data = self._api_json(f"{API_URL}/search?{params}", token)
        items = ((data.get("tracks") or {}).get("items") or []) if isinstance(data, dict) else []
        if not items:
            return None
        item = items[0]
        artists = item.get("artists") if isinstance(item, dict) else []
        artist = artists[0].get("name", "") if artists and isinstance(artists[0], dict) else ""
        return {"name": str(item.get("name", query)), "uri": str(item.get("uri", "")), "artist": str(artist)}

    def _active_or_first_device(self, token: str) -> str:
        data = self._api_json(f"{API_URL}/me/player/devices", token)
        devices = data.get("devices", []) if isinstance(data, dict) else []
        if not isinstance(devices, list):
            return ""
        for device in devices:
            if isinstance(device, dict) and device.get("is_active") and not device.get("is_restricted") and device.get("id"):
                return str(device["id"])
        for device in devices:
            if (
                isinstance(device, dict)
                and str(device.get("type", "")).lower() == "computer"
                and not device.get("is_restricted")
                and device.get("id")
            ):
                return str(device["id"])
        for device in devices:
            if isinstance(device, dict) and not device.get("is_restricted") and device.get("id"):
                return str(device["id"])
        return ""

    def _start_playback(self, token: str, uri: str, *, device_id: str = "") -> int:
        suffix = f"?{urllib.parse.urlencode({'device_id': device_id})}" if device_id else ""
        body = json.dumps({"uris": [uri]}).encode("utf-8")
        return self._api_status(f"{API_URL}/me/player/play{suffix}", token, method="PUT", body=body)

    def _api_json(self, url: str, token: str) -> dict[str, Any]:
        request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))

    def _api_status(self, url: str, token: str, *, method: str, body: bytes) -> int:
        request = urllib.request.Request(
            url,
            data=body,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return int(response.status)
        except urllib.error.HTTPError as exc:
            return int(exc.code)


def build_auth_url(config: SpotifyAuthConfig, *, code_verifier: str, state: str) -> str:
    challenge = base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode("ascii")).digest()).decode("ascii").rstrip("=")
    params = urllib.parse.urlencode(
        {
            "client_id": config.client_id,
            "response_type": "code",
            "redirect_uri": config.redirect_uri,
            "scope": SCOPES,
            "code_challenge_method": "S256",
            "code_challenge": challenge,
            "state": state,
        }
    )
    return f"{AUTH_URL}?{params}"


def exchange_code(config: SpotifyAuthConfig, *, code: str, code_verifier: str) -> dict[str, Any]:
    body = urllib.parse.urlencode(
        {
            "client_id": config.client_id,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": config.redirect_uri,
            "code_verifier": code_verifier,
        }
    ).encode("utf-8")
    request = urllib.request.Request(TOKEN_URL, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    with urllib.request.urlopen(request, timeout=20) as response:
        token = json.loads(response.read().decode("utf-8"))
    token["expires_at"] = time.time() + float(token.get("expires_in", 3600))
    token["client_id"] = config.client_id
    token["redirect_uri"] = config.redirect_uri
    _write_token(config.token_path, token)
    return token


def _read_token(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_token(path: Path, token: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(token, indent=2, sort_keys=True), encoding="utf-8")


def _http_error_detail(exc: urllib.error.HTTPError) -> str:
    try:
        payload = json.loads(exc.read().decode("utf-8", errors="replace"))
    except Exception:
        return str(exc.reason or "request rejected")
    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict):
        return str(error.get("message") or error.get("reason") or exc.reason or "request rejected")
    if error:
        return str(error)
    return str(exc.reason or "request rejected")
