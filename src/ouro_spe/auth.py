"""Authorization Code + PKCE against Spotify accounts."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import threading
import time
import urllib.parse
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import httpx

from ouro_spe.config import SCOPES, AppConfig

AUTHORIZE_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _pkce_pair() -> tuple[str, str]:
    verifier = _b64url(secrets.token_bytes(64))
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


@dataclass
class TokenSet:
    access_token: str
    refresh_token: str
    expires_at: float
    scope: str = ""

    @property
    def expired(self) -> bool:
        return time.time() >= self.expires_at - 60

    def to_json(self) -> dict[str, Any]:
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at,
            "scope": self.scope,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> TokenSet:
        return cls(
            access_token=str(data["access_token"]),
            refresh_token=str(data["refresh_token"]),
            expires_at=float(data["expires_at"]),
            scope=str(data.get("scope", "")),
        )


def load_tokens(path: Path) -> TokenSet | None:
    if not path.is_file():
        return None
    try:
        return TokenSet.from_json(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def save_tokens(path: Path, tokens: TokenSet) -> None:
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    path.write_text(json.dumps(tokens.to_json(), indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)


def delete_tokens(path: Path) -> None:
    if path.is_file():
        path.unlink()


def _parse_redirect(redirect_uri: str) -> tuple[str, int, str]:
    parsed = urllib.parse.urlparse(redirect_uri)
    if parsed.hostname not in {"127.0.0.1", "::1"}:
        raise SystemExit(
            "Redirect URI must use loopback 127.0.0.1 (Spotify disallows localhost)."
        )
    port = parsed.port or 80
    path = parsed.path or "/"
    return parsed.hostname or "127.0.0.1", port, path


@dataclass
class _OAuthResult:
    code: str | None = None
    error: str | None = None


def _make_handler(
    expected_state: str, expected_path: str, result: _OAuthResult
) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
            return

        def do_GET(self) -> None:  # noqa: N802
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path != expected_path:
                self.send_response(404)
                self.end_headers()
                return
            qs = urllib.parse.parse_qs(parsed.query)
            state = (qs.get("state") or [""])[0]
            if state != expected_state:
                result.error = "state_mismatch"
                body = b"Login failed (state mismatch). You can close this tab."
                self.send_response(400)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if "error" in qs:
                result.error = qs["error"][0]
                body = b"Login denied. You can close this tab."
                code = None
            else:
                code = (qs.get("code") or [None])[0]
                result.code = code
                body = b"Login complete. You can close this tab and return to the terminal."
            self.send_response(200 if code else 400)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


def _exchange_code(
    client: httpx.Client,
    cfg: AppConfig,
    code: str,
    verifier: str,
) -> TokenSet:
    resp = client.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": cfg.redirect_uri,
            "client_id": cfg.client_id,
            "code_verifier": verifier,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    resp.raise_for_status()
    data = resp.json()
    return TokenSet(
        access_token=data["access_token"],
        refresh_token=data["refresh_token"],
        expires_at=time.time() + float(data.get("expires_in", 3600)),
        scope=data.get("scope", ""),
    )


def refresh_tokens(client: httpx.Client, cfg: AppConfig, tokens: TokenSet) -> TokenSet:
    resp = client.post(
        TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": tokens.refresh_token,
            "client_id": cfg.client_id,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    if resp.status_code == 400 and resp.json().get("error") == "invalid_grant":
        raise SystemExit("Refresh token invalid or expired. Run: ouro-spe login")
    resp.raise_for_status()
    data = resp.json()
    return TokenSet(
        access_token=data["access_token"],
        refresh_token=data.get("refresh_token", tokens.refresh_token),
        expires_at=time.time() + float(data.get("expires_in", 3600)),
        scope=data.get("scope", tokens.scope),
    )


def login(cfg: AppConfig, tokens_path: Path) -> TokenSet:
    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(24)
    host, port, path = _parse_redirect(cfg.redirect_uri)

    params = {
        "client_id": cfg.client_id,
        "response_type": "code",
        "redirect_uri": cfg.redirect_uri,
        "scope": " ".join(SCOPES),
        "state": state,
        "code_challenge_method": "S256",
        "code_challenge": challenge,
    }
    auth_url = f"{AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"

    result = _OAuthResult()
    server = HTTPServer((host, port), _make_handler(state, path, result))
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()

    print(f"Opening browser for Spotify login…\n{auth_url}")
    webbrowser.open(auth_url)
    thread.join(timeout=300)
    server.server_close()

    if result.error:
        raise SystemExit(f"Login failed: {result.error}")
    if not result.code:
        raise SystemExit("Login timed out or no authorization code received.")

    with httpx.Client(timeout=30.0) as client:
        tokens = _exchange_code(client, cfg, result.code, verifier)
    save_tokens(tokens_path, tokens)
    return tokens


def ensure_access_token(
    client: httpx.Client,
    cfg: AppConfig,
    tokens_path: Path,
) -> str:
    tokens = load_tokens(tokens_path)
    if tokens is None:
        raise SystemExit("Not logged in. Run: ouro-spe login")
    if tokens.expired:
        tokens = refresh_tokens(client, cfg, tokens)
        save_tokens(tokens_path, tokens)
    return tokens.access_token
