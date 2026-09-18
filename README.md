# ouro-spe

Export Spotify playlists and Liked Songs into a **local inventory** (SQLite) and
**transferable playlist packs** (one JSON file per playlist).

| Artifact | What it is |
| --- | --- |
| **Portable pack** | Shareable handoff: track identity + order only (`docs/pack-schema.md`) |
| **Inventory** | Local SQLite store: skips, problems, sameness, re-sync metadata |

Packs are not the full dataset — the inventory is the versatile store.

## Requirements

- Python **3.11+**
- A Spotify Developer app (Authorization Code + **PKCE**)

## Install

From a clone of this repo:

```bash
cd ouro-spotify-playlist-export
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
ouro-spe --help
```

If `ouro-spe` is “not found”, either activate the venv first or call it by path:

```bash
.venv/bin/ouro-spe --help
```

Optional wrapper (same as `ouro-spe setup` once installed):

```bash
./scripts/setup.sh
```

## Spotify Developer app

1. Open [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard) and create an app.
2. Use a **public / PKCE** client (no client secret required for this CLI).
3. Add this **Redirect URI** exactly (Spotify rejects `localhost`):

   ```text
   http://127.0.0.1:4389/callback
   ```

4. Copy the **Client ID** (32 hex characters). Do not commit it.

## Configure and log in

### Recommended: setup wizard

```bash
source .venv/bin/activate
ouro-spe setup
```

The wizard writes local config, prints remote-SSH tips, and can run login.

### Manual config

```bash
mkdir -p "${XDG_CONFIG_HOME:-$HOME/.config}/ouro-spotify-playlist-export"
cp config.example "${XDG_CONFIG_HOME:-$HOME/.config}/ouro-spotify-playlist-export/config.toml"
# Edit that file: set SPOTIFY_CLIENT_ID (and keep the 127.0.0.1 redirect)
chmod 600 "${XDG_CONFIG_HOME:-$HOME/.config}/ouro-spotify-playlist-export/config.toml"
ouro-spe login
```

### Login on a remote machine (SSH / Cursor Remote)

The authorize page opens in **your local browser**. After Accept, Spotify redirects to
`127.0.0.1:4389` on **your laptop**, not automatically on the remote host.

Pick one:

1. **Port forward 4389** (Cursor Ports panel, or `ssh -L 4389:127.0.0.1:4389 …`) so the
   success page reaches the CLI, **or**
2. **Paste the URL**: if the page is blank, copy the full address bar
   (`http://127.0.0.1:4389/callback?code=…`) and paste it at the login prompt.

Use the authorize link from the **current** `login` run. Codes are one-time;
pasting an old URL causes `state mismatch` or token errors.

## Use

```bash
source .venv/bin/activate

ouro-spe export                 # checkbox UI: space = toggle, enter = confirm
ouro-spe export --include-followed
ouro-spe logout
```

- **Liked Songs** is the first row; owned playlists follow.
- Followed playlists are hidden unless `--include-followed` (Spotify may **403**
  track listing if you are not owner/collaborator).
- After a successful export, packs are written under `./packs/` (cwd) and the
  inventory is updated. Empty playlists do not write a pack file.

### Paths

| Kind | Default |
| --- | --- |
| Config / tokens | `$XDG_CONFIG_HOME/ouro-spotify-playlist-export/` (`config.toml`, `tokens.json`) |
| Inventory | `$XDG_DATA_HOME/ouro-spotify-playlist-export/inventory.sqlite` |
| Packs | `./packs/*.playlist.pack.json` |

Overrides: `OURO_SPE_CONFIG_DIR`, `OURO_SPE_DATA_DIR`, `OURO_SPE_PACKS_DIR`,
or `--config-dir` / `--data-dir` / `--packs-dir`.

## Privacy

Never commit:

- `tokens.json`, real `config.toml` with your Client ID
- `inventory.sqlite` or real packs under `packs/`

`.gitignore` already excludes these. Keep secrets in the XDG config dir only.

## Development

```bash
source .venv/bin/activate
pytest
```

## License

MIT
