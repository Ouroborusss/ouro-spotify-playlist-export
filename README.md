# ouro-spe

Export Spotify playlists and Liked Songs into a **local inventory** (SQLite) and
**transferable playlist packs** (one JSON file per playlist).

Portable packs are a handoff for a future download UI: music identity and list
order only. The local inventory holds skips, problems, sameness decisions, and
re-sync metadata — it is the versatile store.

## Setup

1. Create a Spotify Developer app and enable **Authorization Code with PKCE**.
2. Add a loopback redirect URI such as `http://127.0.0.1:4389/callback`
   (`localhost` is not allowed by Spotify).
3. Copy `config.example` values into
   `$XDG_CONFIG_HOME/ouro-spotify-playlist-export/config.toml`
   (or export `SPOTIFY_CLIENT_ID`). Use your own Client ID — do not commit it.
4. Install:

```bash
pip install -e ".[dev]"
```

## Usage

```bash
ouro-spe login
ouro-spe export
ouro-spe export --include-followed
ouro-spe logout
```

`export` opens a checkbox list (space to toggle, enter to confirm). Liked Songs
is first. Followed playlists are hidden unless `--include-followed` is set.

Defaults:

| Kind | Location |
| --- | --- |
| Config / tokens | `$XDG_CONFIG_HOME/ouro-spotify-playlist-export/` |
| Inventory | `$XDG_DATA_HOME/ouro-spotify-playlist-export/inventory.sqlite` |
| Packs | `./packs/` |

Overrides: `OURO_SPE_CONFIG_DIR`, `OURO_SPE_DATA_DIR`, `OURO_SPE_PACKS_DIR`,
or `--config-dir` / `--data-dir` / `--packs-dir`.

## Privacy

Never commit tokens, the inventory database, or real packs. See `.gitignore`.
Docs and examples use placeholders only — no personal usernames or home paths.

## License

MIT
