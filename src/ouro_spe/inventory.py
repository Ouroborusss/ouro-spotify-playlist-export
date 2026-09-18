"""SQLite working inventory."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ouro_spe.matching import MatchKind, MatchResult, looks_like_variant
from ouro_spe.spotify import TrackData

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tracks (
  id INTEGER PRIMARY KEY,
  spotify_track_id TEXT UNIQUE,
  isrc TEXT,
  title TEXT NOT NULL,
  artists_json TEXT NOT NULL,
  album TEXT,
  duration_ms INTEGER NOT NULL,
  disc_number INTEGER,
  track_number INTEGER
);

CREATE TABLE IF NOT EXISTS playlists (
  id INTEGER PRIMARY KEY,
  spotify_playlist_id TEXT UNIQUE,
  title TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('playlist', 'liked_songs')),
  snapshot_id TEXT,
  last_exported_at TEXT
);

CREATE TABLE IF NOT EXISTS playlist_tracks (
  playlist_id INTEGER NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
  track_id INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
  position INTEGER NOT NULL,
  PRIMARY KEY (playlist_id, track_id)
);

CREATE TABLE IF NOT EXISTS problems (
  id INTEGER PRIMARY KEY,
  playlist_id INTEGER REFERENCES playlists(id) ON DELETE SET NULL,
  spotify_track_id TEXT,
  title TEXT,
  artists_json TEXT,
  reason TEXT NOT NULL,
  seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS variant_pending (
  id INTEGER PRIMARY KEY,
  playlist_id INTEGER REFERENCES playlists(id) ON DELETE CASCADE,
  candidate_json TEXT NOT NULL,
  existing_track_id INTEGER REFERENCES tracks(id) ON DELETE CASCADE,
  reason TEXT NOT NULL,
  UNIQUE (playlist_id, existing_track_id, reason)
);

CREATE TABLE IF NOT EXISTS sameness_links (
  spotify_track_id TEXT PRIMARY KEY,
  track_id INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_tracks_isrc ON tracks(isrc);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class PendingVariant:
    row_id: int
    candidate: TrackData
    existing_track_id: int
    existing_title: str
    existing_artists: list[str]
    reason: str


class Inventory:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(_SCHEMA)
        cur = self._conn.execute(
            "SELECT value FROM meta WHERE key = 'schema_version'"
        ).fetchone()
        if cur is None:
            self._conn.execute(
                "INSERT INTO meta(key, value) VALUES ('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )
            self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def upsert_playlist(
        self,
        *,
        spotify_playlist_id: str | None,
        title: str,
        kind: str,
        snapshot_id: str | None = None,
    ) -> int:
        if spotify_playlist_id:
            row = self._conn.execute(
                "SELECT id FROM playlists WHERE spotify_playlist_id = ?",
                (spotify_playlist_id,),
            ).fetchone()
        elif kind == "liked_songs":
            row = self._conn.execute(
                "SELECT id FROM playlists WHERE kind = 'liked_songs'"
            ).fetchone()
        else:
            row = None

        if row:
            pk = int(row["id"])
            self._conn.execute(
                """
                UPDATE playlists
                SET title = ?, snapshot_id = COALESCE(?, snapshot_id)
                WHERE id = ?
                """,
                (title, snapshot_id, pk),
            )
        else:
            cur = self._conn.execute(
                """
                INSERT INTO playlists(spotify_playlist_id, title, kind, snapshot_id)
                VALUES (?, ?, ?, ?)
                """,
                (spotify_playlist_id, title, kind, snapshot_id),
            )
            pk = int(cur.lastrowid)
        self._conn.commit()
        return pk

    def mark_exported(self, playlist_pk: int, snapshot_id: str | None = None) -> None:
        self._conn.execute(
            """
            UPDATE playlists
            SET last_exported_at = ?, snapshot_id = COALESCE(?, snapshot_id)
            WHERE id = ?
            """,
            (_now(), snapshot_id, playlist_pk),
        )
        self._conn.commit()

    def clear_membership(self, playlist_pk: int) -> None:
        self._conn.execute(
            "DELETE FROM playlist_tracks WHERE playlist_id = ?", (playlist_pk,)
        )
        self._conn.commit()

    def add_membership(self, playlist_pk: int, track_pk: int, position: int) -> None:
        self._conn.execute(
            """
            INSERT INTO playlist_tracks(playlist_id, track_id, position)
            VALUES (?, ?, ?)
            ON CONFLICT(playlist_id, track_id) DO UPDATE SET position = excluded.position
            """,
            (playlist_pk, track_pk, position),
        )

    def insert_track(self, track: TrackData) -> int:
        cur = self._conn.execute(
            """
            INSERT INTO tracks(
              spotify_track_id, isrc, title, artists_json, album,
              duration_ms, disc_number, track_number
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                track.spotify_track_id,
                track.isrc,
                track.title,
                json.dumps(track.artists),
                track.album,
                track.duration_ms,
                track.disc_number,
                track.track_number,
            ),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def record_problem(
        self,
        playlist_pk: int | None,
        *,
        reason: str,
        title: str | None = None,
        artists: list[str] | None = None,
        spotify_track_id: str | None = None,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO problems(
              playlist_id, spotify_track_id, title, artists_json, reason, seen_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                playlist_pk,
                spotify_track_id,
                title,
                json.dumps(artists or []),
                reason,
                _now(),
            ),
        )
        self._conn.commit()

    def add_sameness(self, spotify_track_id: str, track_pk: int) -> None:
        self._conn.execute(
            """
            INSERT INTO sameness_links(spotify_track_id, track_id)
            VALUES (?, ?)
            ON CONFLICT(spotify_track_id) DO UPDATE SET track_id = excluded.track_id
            """,
            (spotify_track_id, track_pk),
        )
        self._conn.commit()

    def queue_variant(
        self,
        playlist_pk: int,
        candidate: TrackData,
        existing_track_id: int,
        reason: str,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO variant_pending(
              playlist_id, candidate_json, existing_track_id, reason
            ) VALUES (?, ?, ?, ?)
            ON CONFLICT(playlist_id, existing_track_id, reason) DO UPDATE SET
              candidate_json = excluded.candidate_json
            """,
            (playlist_pk, json.dumps(_track_dict(candidate)), existing_track_id, reason),
        )
        self._conn.commit()

    def list_pending_variants(self, playlist_pk: int | None = None) -> list[PendingVariant]:
        if playlist_pk is None:
            rows = self._conn.execute(
                """
                SELECT vp.id, vp.candidate_json, vp.existing_track_id, vp.reason,
                       t.title AS existing_title, t.artists_json AS existing_artists
                FROM variant_pending vp
                JOIN tracks t ON t.id = vp.existing_track_id
                ORDER BY vp.id
                """
            ).fetchall()
        else:
            rows = self._conn.execute(
                """
                SELECT vp.id, vp.candidate_json, vp.existing_track_id, vp.reason,
                       t.title AS existing_title, t.artists_json AS existing_artists
                FROM variant_pending vp
                JOIN tracks t ON t.id = vp.existing_track_id
                WHERE vp.playlist_id = ?
                ORDER BY vp.id
                """,
                (playlist_pk,),
            ).fetchall()
        out: list[PendingVariant] = []
        for r in rows:
            cand = _track_from_dict(json.loads(r["candidate_json"]))
            out.append(
                PendingVariant(
                    row_id=int(r["id"]),
                    candidate=cand,
                    existing_track_id=int(r["existing_track_id"]),
                    existing_title=r["existing_title"],
                    existing_artists=json.loads(r["existing_artists"]),
                    reason=r["reason"],
                )
            )
        return out

    def delete_pending(self, row_id: int) -> None:
        self._conn.execute("DELETE FROM variant_pending WHERE id = ?", (row_id,))
        self._conn.commit()

    def match(self, track: TrackData) -> MatchResult:
        if track.spotify_track_id:
            row = self._conn.execute(
                "SELECT id FROM tracks WHERE spotify_track_id = ?",
                (track.spotify_track_id,),
            ).fetchone()
            if row:
                return MatchResult(MatchKind.KNOWN, existing_track_pk=int(row["id"]))
            link = self._conn.execute(
                "SELECT track_id FROM sameness_links WHERE spotify_track_id = ?",
                (track.spotify_track_id,),
            ).fetchone()
            if link:
                return MatchResult(MatchKind.KNOWN, existing_track_pk=int(link["track_id"]))

        if track.isrc:
            rows = self._conn.execute(
                "SELECT id, spotify_track_id, title, artists_json FROM tracks WHERE isrc = ?",
                (track.isrc,),
            ).fetchall()
            for row in rows:
                if track.spotify_track_id and row["spotify_track_id"] == track.spotify_track_id:
                    continue
                if row["spotify_track_id"] != track.spotify_track_id:
                    return MatchResult(
                        MatchKind.VARIANT,
                        existing_track_pk=int(row["id"]),
                        reason="isrc_clash",
                    )

        rows = self._conn.execute(
            "SELECT id, title, artists_json FROM tracks"
        ).fetchall()
        for row in rows:
            artists = json.loads(row["artists_json"])
            if looks_like_variant(
                TrackData(
                    spotify_track_id=None,
                    isrc=None,
                    title=row["title"],
                    artists=artists,
                    album=None,
                    duration_ms=0,
                    disc_number=None,
                    track_number=None,
                ),
                track.title,
                track.artists,
            ):
                return MatchResult(
                    MatchKind.VARIANT,
                    existing_track_pk=int(row["id"]),
                    reason="fuzzy_variant",
                )

        return MatchResult(MatchKind.NEW)

    def commit(self) -> None:
        self._conn.commit()


def _track_dict(track: TrackData) -> dict[str, Any]:
    return {
        "spotify_track_id": track.spotify_track_id,
        "isrc": track.isrc,
        "title": track.title,
        "artists": track.artists,
        "album": track.album,
        "duration_ms": track.duration_ms,
        "disc_number": track.disc_number,
        "track_number": track.track_number,
    }


def _track_from_dict(data: dict[str, Any]) -> TrackData:
    return TrackData(
        spotify_track_id=data.get("spotify_track_id"),
        isrc=data.get("isrc"),
        title=data["title"],
        artists=list(data.get("artists") or []),
        album=data.get("album"),
        duration_ms=int(data["duration_ms"]),
        disc_number=data.get("disc_number"),
        track_number=data.get("track_number"),
    )
