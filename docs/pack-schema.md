# Portable pack schema (v1)

One playlist per JSON file. UTF-8. Transferable music identity only.

## Top level

| Field | Required | Notes |
| --- | --- | --- |
| `schema_version` | yes | Integer; start at `1` |
| `source` | yes | `"spotify"` |
| `pack_kind` | yes | `"playlist"` |
| `title` | yes | Playlist display name |
| `description` | no | Omit if empty |
| `exported_at` | yes | UTC ISO-8601 |
| `tracks` | yes | Ordered array |

No Spotify user ids, playlist owner fields, tokens, or local paths.

## Track object

**Required:** `position` (1-based), `title`, `artists` (string array), `duration_ms`

**Optional:** `spotify_track_id`, `isrc`, `album`, `disc_number`, `track_number`

## Filename

`{slug}.playlist.pack.json` — Liked Songs uses `liked-songs.playlist.pack.json`.

Empty playlists: do not write a file.
