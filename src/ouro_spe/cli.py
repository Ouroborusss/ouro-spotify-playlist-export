"""ouro-spe CLI entrypoint."""

from __future__ import annotations

import argparse
import sys

import httpx

from ouro_spe import auth
from ouro_spe.config import load_config
from ouro_spe.export import export_run
from ouro_spe.inventory import Inventory
from ouro_spe.paths import resolve_paths
from ouro_spe.spotify import SpotifyClient


def _add_path_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config-dir", default=None, help="Override config/tokens directory")
    parser.add_argument("--data-dir", default=None, help="Override inventory data directory")
    parser.add_argument("--packs-dir", default=None, help="Override pack output directory")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="ouro-spe",
        description=(
            "Export Spotify playlists to a local inventory and transferable packs. "
            "Packs are a handoff (identity + order); the inventory holds full local state."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_login = sub.add_parser("login", help="Authorize with Spotify (PKCE) and store tokens")
    _add_path_flags(p_login)

    p_logout = sub.add_parser("logout", help="Delete local tokens")
    _add_path_flags(p_logout)

    p_export = sub.add_parser(
        "export",
        help=(
            "Checkbox-select playlists, update inventory, write packs. "
            "Packs are transferable handoff only; inventory is the versatile store."
        ),
    )
    _add_path_flags(p_export)
    p_export.add_argument(
        "--include-followed",
        action="store_true",
        help="Include followed playlists in the checkbox list (may 403 on track fetch)",
    )

    args = parser.parse_args(argv)
    paths = resolve_paths(
        config_dir=args.config_dir,
        data_dir=args.data_dir,
        packs_dir=getattr(args, "packs_dir", None),
    )
    paths.ensure()

    if args.command == "login":
        cfg = load_config(paths.config_file)
        auth.login(cfg, paths.tokens_file)
        print(f"Tokens saved to {paths.tokens_file}")
        return

    if args.command == "logout":
        auth.delete_tokens(paths.tokens_file)
        print("Logged out.")
        return

    if args.command == "export":
        cfg = load_config(paths.config_file)
        with httpx.Client(timeout=60.0) as http:
            token = auth.ensure_access_token(http, cfg, paths.tokens_file)
            client = SpotifyClient(http, token)
            inv = Inventory(paths.inventory_file)
            try:
                export_run(
                    client,
                    inv,
                    paths,
                    include_followed=args.include_followed,
                )
            finally:
                inv.close()
        return

    parser.error(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main(sys.argv[1:])
