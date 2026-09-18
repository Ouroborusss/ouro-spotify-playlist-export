"""Thin Spotify Web API client with pagination and 429 backoff."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Iterator

import httpx

API_BASE = "https://api.spotify.com/v1"


@dataclass
class PlaylistRef:
    id: str
    name: str
    owner_id: str
    snapshot_id: str
    collaborative: bool
    followed: bool  # owner_id != current user


@dataclass
class TrackData:
    spotify_track_id: str | None
    isrc: str | None
    title: str
    artists: list[str]
    album: str | None
    duration_ms: int
    disc_number: int | None
    track_number: int | None
    is_local: bool = False


@dataclass
class FetchProblem:
    reason: str
    title: str | None = None
    artists: list[str] = field(default_factory=list)
    spotify_track_id: str | None = None


class SpotifyClient:
    def __init__(self, http: httpx.Client, access_token: str) -> None:
        self._http = http
        self._token = access_token

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    def _get(self, path: str, params: dict[str, Any] | None = None) -> httpx.Response:
        url = path if path.startswith("http") else f"{API_BASE}{path}"
        for attempt in range(6):
            resp = self._http.get(url, headers=self._headers(), params=params)
            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", "1"))
                time.sleep(max(wait, 1))
                continue
            if resp.status_code >= 500 and attempt < 5:
                time.sleep(2**attempt)
                continue
            return resp
        return resp

    def _paginate(self, path: str, params: dict[str, Any] | None = None) -> Iterator[dict]:
        params = dict(params or {})
        params.setdefault("limit", 50)
        while True:
            resp = self._get(path, params)
            resp.raise_for_status()
            payload = resp.json()
            for item in payload.get("items") or []:
                yield item
            nxt = payload.get("next")
            if not nxt:
                break
            path = nxt
            params = None

    def current_user_id(self) -> str:
        resp = self._get("/me")
        resp.raise_for_status()
        return str(resp.json()["id"])

    def list_playlists(self) -> list[PlaylistRef]:
        me = self.current_user_id()
        out: list[PlaylistRef] = []
        for item in self._paginate("/me/playlists"):
            owner = (item.get("owner") or {}).get("id") or ""
            out.append(
                PlaylistRef(
                    id=item["id"],
                    name=item.get("name") or "Untitled",
                    owner_id=owner,
                    snapshot_id=item.get("snapshot_id") or "",
                    collaborative=bool(item.get("collaborative")),
                    followed=owner != me,
                )
            )
        return out

    def playlist_items(
        self, playlist_id: str
    ) -> tuple[list[TrackData], list[FetchProblem], int | None]:
        """Returns tracks, problems, and HTTP status on hard failure (e.g. 403)."""
        tracks: list[TrackData] = []
        problems: list[FetchProblem] = []
        path = f"/playlists/{playlist_id}/items"
        params: dict[str, Any] | None = {"limit": 50, "additional_types": "track"}
        while True:
            resp = self._get(path, params)
            if resp.status_code == 403:
                return [], [], 403
            if resp.status_code >= 400:
                problems.append(
                    FetchProblem(reason=f"playlist_items_http_{resp.status_code}")
                )
                return tracks, problems, resp.status_code
            payload = resp.json()
            for row in payload.get("items") or []:
                parsed, problem = _parse_playlist_row(row)
                if problem:
                    problems.append(problem)
                if parsed:
                    tracks.append(parsed)
            nxt = payload.get("next")
            if not nxt:
                break
            path = nxt
            params = None
        return tracks, problems, None

    def liked_tracks(self) -> tuple[list[TrackData], list[FetchProblem]]:
        tracks: list[TrackData] = []
        problems: list[FetchProblem] = []
        for row in self._paginate("/me/tracks"):
            track = row.get("track")
            parsed, problem = _parse_track_object(track)
            if problem:
                problems.append(problem)
            if parsed:
                tracks.append(parsed)
        return tracks, problems


def _parse_playlist_row(row: dict[str, Any]) -> tuple[TrackData | None, FetchProblem | None]:
    item = row.get("item")
    if item is None and "track" in row:
        item = row.get("track")
    return _parse_track_object(item)


def _parse_track_object(
    track: Any,
) -> tuple[TrackData | None, FetchProblem | None]:
    if track is None:
        return None, FetchProblem(reason="null_or_unavailable_track")
    if not isinstance(track, dict):
        return None, FetchProblem(reason="invalid_track_payload")
    if track.get("type") == "episode":
        return None, FetchProblem(
            reason="episode_not_supported",
            title=track.get("name"),
        )
    if track.get("is_local"):
        return None, FetchProblem(
            reason="local_file_skipped",
            title=track.get("name"),
            artists=[a.get("name") for a in (track.get("artists") or []) if a.get("name")],
        )

    title = (track.get("name") or "").strip()
    artists = [a.get("name") for a in (track.get("artists") or []) if a.get("name")]
    duration = track.get("duration_ms")
    if not title or duration is None:
        return None, FetchProblem(
            reason="missing_required_fields",
            title=title or None,
            artists=artists,
            spotify_track_id=track.get("id"),
        )

    external = track.get("external_ids") or {}
    album = track.get("album") or {}
    return (
        TrackData(
            spotify_track_id=track.get("id"),
            isrc=external.get("isrc"),
            title=title,
            artists=artists,
            album=(album.get("name") or None) or None,
            duration_ms=int(duration),
            disc_number=track.get("disc_number"),
            track_number=track.get("track_number"),
            is_local=False,
        ),
        None,
    )
