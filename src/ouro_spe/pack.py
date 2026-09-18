"""Write transferable one-playlist portable packs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ouro_spe.slug import slugify
from ouro_spe.spotify import TrackData

SCHEMA_VERSION = 1


def collapse_copies(tracks: list[TrackData]) -> tuple[list[TrackData], int]:
    """Keep first occurrence of each spotify_track_id; tracks without id always kept."""
    seen: set[str] = set()
    out: list[TrackData] = []
    collapsed = 0
    for t in tracks:
        if t.spotify_track_id:
            if t.spotify_track_id in seen:
                collapsed += 1
                continue
            seen.add(t.spotify_track_id)
        out.append(t)
    return out, collapsed


def track_to_pack_entry(track: TrackData, position: int) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "position": position,
        "title": track.title,
        "artists": list(track.artists),
        "duration_ms": track.duration_ms,
    }
    if track.spotify_track_id:
        entry["spotify_track_id"] = track.spotify_track_id
    if track.isrc:
        entry["isrc"] = track.isrc
    if track.album:
        entry["album"] = track.album
    if track.disc_number is not None:
        entry["disc_number"] = track.disc_number
    if track.track_number is not None:
        entry["track_number"] = track.track_number
    return entry


def build_pack_document(
    *,
    title: str,
    tracks: list[TrackData],
    description: str | None = None,
) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "source": "spotify",
        "pack_kind": "playlist",
        "title": title,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "tracks": [
            track_to_pack_entry(t, i) for i, t in enumerate(tracks, start=1)
        ],
    }
    if description:
        doc["description"] = description
    return doc


def write_pack(
    packs_dir: Path,
    *,
    title: str,
    tracks: list[TrackData],
    liked_songs: bool = False,
    description: str | None = None,
) -> Path | None:
    if not tracks:
        return None
    packs_dir.mkdir(parents=True, exist_ok=True)
    name = f"{slugify(title, liked_songs=liked_songs)}.playlist.pack.json"
    path = packs_dir / name
    doc = build_pack_document(title=title, tracks=tracks, description=description)
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path
