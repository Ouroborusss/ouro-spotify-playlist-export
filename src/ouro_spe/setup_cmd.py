"""Interactive first-run setup: config file, Dashboard checklist, login."""

from __future__ import annotations

import re
from pathlib import Path

from ouro_spe import auth
from ouro_spe.config import DEFAULT_REDIRECT_URI, load_config
from ouro_spe.paths import AppPaths

_CLIENT_ID_RE = re.compile(r"^[0-9a-fA-F]{32}$")


def _read_existing_client_id(config_file: Path) -> str | None:
    if not config_file.is_file():
        return None
    try:
        cfg = load_config(config_file)
    except SystemExit:
        return None
    if cfg.client_id and cfg.client_id != "<CLIENT_ID>":
        return cfg.client_id
    return None


def _write_config(config_file: Path, client_id: str, redirect_uri: str) -> None:
    config_file.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    body = (
        f'SPOTIFY_CLIENT_ID = "{client_id}"\n'
        f'SPOTIFY_REDIRECT_URI = "{redirect_uri}"\n'
    )
    config_file.write_text(body, encoding="utf-8")
    config_file.chmod(0o600)


def _prompt(msg: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    raw = input(f"{msg}{suffix}: ").strip()
    if not raw and default is not None:
        return default
    return raw


def _yes(msg: str, default: bool = True) -> bool:
    hint = "Y/n" if default else "y/N"
    raw = input(f"{msg} ({hint}): ").strip().lower()
    if not raw:
        return default
    return raw in {"y", "yes"}


def run_setup(paths: AppPaths, *, skip_login: bool = False) -> None:
    paths.ensure()
    redirect = DEFAULT_REDIRECT_URI

    print("=== ouro-spe setup ===\n")
    print("1) Spotify Developer Dashboard")
    print("   https://developer.spotify.com/dashboard")
    print("   - Create an app (Authorization Code + PKCE / public client)")
    print(f"   - Redirect URI must be EXACTLY:\n       {redirect}")
    print("   - Do NOT use http://localhost:...  (Spotify rejects localhost)")
    print("   - Copy the Client ID (32 hex characters)\n")

    existing = _read_existing_client_id(paths.config_file)
    if existing:
        print(f"Found existing Client ID in {paths.config_file}")
        if _yes("Keep it?", default=True):
            client_id = existing
        else:
            client_id = _prompt("Paste Client ID")
    else:
        client_id = _prompt("Paste Client ID")

    if not _CLIENT_ID_RE.match(client_id):
        print(
            "Warning: Client ID usually looks like 32 hex chars. "
            "Continuing anyway — double-check the Dashboard if login fails."
        )

    _write_config(paths.config_file, client_id, redirect)
    print(f"\nWrote {paths.config_file} (mode 600)")
    print(f"Inventory will live at {paths.inventory_file}")
    print(f"Packs default to {paths.packs_dir}/\n")

    print("2) Remote SSH / Cursor remote")
    print("   Login opens Spotify in *your* browser. The redirect hits YOUR laptop.")
    print("   Pick one:")
    print("   A) Cursor: Ports panel → forward remote 4389 to local 4389")
    print("      then Accept; the success page should load.")
    print("   B) No port forward: after Accept (page may be blank), copy the FULL")
    print("      address-bar URL (…/callback?code=…) and paste it into the login prompt.\n")

    if skip_login:
        print("Skipping login (--skip-login). Next: ouro-spe login")
        return

    if not _yes("Run login now?", default=True):
        print("Skipped. When ready: ouro-spe login")
        return

    if auth.load_tokens(paths.tokens_file):
        if not _yes("Tokens already exist. Log in again?", default=False):
            print("Keeping existing tokens. Try: ouro-spe export")
            return

    cfg = load_config(paths.config_file)
    auth.login(cfg, paths.tokens_file)
    print(f"\nTokens saved to {paths.tokens_file}")
    print("Next: ouro-spe export")
