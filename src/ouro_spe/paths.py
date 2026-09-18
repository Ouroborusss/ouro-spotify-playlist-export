"""XDG and override paths for config, inventory, and packs."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

APP_DIR_NAME = "ouro-spotify-playlist-export"


def _xdg(env_key: str, fallback_home_subdir: str) -> Path:
    raw = os.environ.get(env_key)
    if raw:
        return Path(raw).expanduser()
    return Path.home() / fallback_home_subdir


@dataclass(frozen=True)
class AppPaths:
    config_dir: Path
    data_dir: Path
    packs_dir: Path

    @property
    def config_file(self) -> Path:
        return self.config_dir / "config.toml"

    @property
    def tokens_file(self) -> Path:
        return self.config_dir / "tokens.json"

    @property
    def inventory_file(self) -> Path:
        return self.data_dir / "inventory.sqlite"

    def ensure(self) -> None:
        self.config_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
        self.data_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
        self.packs_dir.mkdir(parents=True, exist_ok=True)


def resolve_paths(
    *,
    config_dir: str | Path | None = None,
    data_dir: str | Path | None = None,
    packs_dir: str | Path | None = None,
) -> AppPaths:
    cfg = (
        Path(config_dir).expanduser()
        if config_dir
        else Path(os.environ["OURO_SPE_CONFIG_DIR"]).expanduser()
        if os.environ.get("OURO_SPE_CONFIG_DIR")
        else _xdg("XDG_CONFIG_HOME", ".config") / APP_DIR_NAME
    )
    data = (
        Path(data_dir).expanduser()
        if data_dir
        else Path(os.environ["OURO_SPE_DATA_DIR"]).expanduser()
        if os.environ.get("OURO_SPE_DATA_DIR")
        else _xdg("XDG_DATA_HOME", ".local/share") / APP_DIR_NAME
    )
    packs = (
        Path(packs_dir).expanduser()
        if packs_dir
        else Path(os.environ["OURO_SPE_PACKS_DIR"]).expanduser()
        if os.environ.get("OURO_SPE_PACKS_DIR")
        else Path.cwd() / "packs"
    )
    return AppPaths(config_dir=cfg, data_dir=data, packs_dir=packs)
