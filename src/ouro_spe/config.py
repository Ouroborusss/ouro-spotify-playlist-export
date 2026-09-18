"""Load Client ID and optional redirect URI from env / config.toml."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

DEFAULT_REDIRECT_URI = "http://127.0.0.1:4389/callback"

SCOPES = (
    "playlist-read-private",
    "playlist-read-collaborative",
    "user-library-read",
)


@dataclass(frozen=True)
class AppConfig:
    client_id: str
    redirect_uri: str = DEFAULT_REDIRECT_URI


def load_config(config_file: Path) -> AppConfig:
    client_id = os.environ.get("SPOTIFY_CLIENT_ID", "").strip()
    redirect = os.environ.get("SPOTIFY_REDIRECT_URI", "").strip()

    if config_file.is_file():
        data = tomllib.loads(config_file.read_text(encoding="utf-8"))
        client_id = client_id or str(data.get("SPOTIFY_CLIENT_ID", "")).strip()
        redirect = redirect or str(data.get("SPOTIFY_REDIRECT_URI", "")).strip()
        # Also accept nested [spotify] style if present
        spotify = data.get("spotify")
        if isinstance(spotify, dict):
            client_id = client_id or str(spotify.get("client_id", "")).strip()
            redirect = redirect or str(spotify.get("redirect_uri", "")).strip()

    if not client_id or client_id == "<CLIENT_ID>":
        raise SystemExit(
            "Missing SPOTIFY_CLIENT_ID. Set the env var or write it to "
            f"{config_file} (see config.example)."
        )

    return AppConfig(
        client_id=client_id,
        redirect_uri=redirect or DEFAULT_REDIRECT_URI,
    )
