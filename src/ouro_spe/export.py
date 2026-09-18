"""Interactive export: select playlists, update inventory, write packs."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field

import questionary
from questionary import Choice

from ouro_spe.inventory import Inventory
from ouro_spe.matching import MatchKind
from ouro_spe.pack import collapse_copies, write_pack
from ouro_spe.paths import AppPaths
from ouro_spe.spotify import FetchProblem, PlaylistRef, SpotifyClient, TrackData


@dataclass
class Selection:
    key: str
    title: str
    liked: bool = False
    playlist: PlaylistRef | None = None


@dataclass
class RunStats:
    exported_tracks: int = 0
    skipped_known: int = 0
    collapsed_copies: int = 0
    empty_playlists: int = 0
    packs_written: int = 0
    problems: list[str] = field(default_factory=list)


@dataclass
class PlaylistWork:
    selection: Selection
    playlist_pk: int
    snapshot_id: str | None = None


def require_tty() -> None:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise SystemExit(
            "ouro-spe export needs an interactive terminal "
            "(checkbox select cannot run when piped)."
        )


def choose_playlists(
    playlists: list[PlaylistRef],
    *,
    include_followed: bool,
) -> list[Selection]:
    owned = [p for p in playlists if not p.followed]
    followed = [p for p in playlists if p.followed]

    choices: list[Choice] = [
        Choice(title="Liked Songs", value=Selection(key="liked", title="Liked Songs", liked=True))
    ]
    for p in owned:
        choices.append(
            Choice(
                title=p.name,
                value=Selection(key=p.id, title=p.name, playlist=p),
            )
        )
    if include_followed:
        for p in followed:
            choices.append(
                Choice(
                    title=f"[followed] {p.name}",
                    value=Selection(key=p.id, title=p.name, playlist=p),
                )
            )

    selected = questionary.checkbox(
        "Select playlists to export (space toggle, enter confirm):",
        choices=choices,
    ).ask()
    if selected is None:
        raise SystemExit("Cancelled.")
    return list(selected)


def _process_tracks(
    inv: Inventory,
    playlist_pk: int,
    tracks: list[TrackData],
    stats: RunStats,
) -> None:
    collapsed, n = collapse_copies(tracks)
    stats.collapsed_copies += n

    for track in collapsed:
        result = inv.match(track)
        if result.kind == MatchKind.KNOWN:
            stats.skipped_known += 1
            continue
        if result.kind == MatchKind.VARIANT:
            assert result.existing_track_pk is not None
            inv.queue_variant(
                playlist_pk,
                track,
                result.existing_track_pk,
                result.reason or "variant",
            )
            continue
        inv.insert_track(track)
        stats.exported_tracks += 1


def run_variant_guidance(inv: Inventory) -> bool:
    """Returns False if aborted mid-guidance."""
    pending = inv.list_pending_variants()
    if not pending:
        return True

    print("\n=== Needs guidance ===")
    try:
        for item in pending:
            cand = item.candidate
            label = (
                f"{cand.title} — {', '.join(cand.artists)}\n"
                f"  vs inventory: {item.existing_title} — {', '.join(item.existing_artists)}\n"
                f"  ({item.reason})"
            )
            action = questionary.select(
                label,
                choices=[
                    Choice("Treat as same (skip new listing)", value="same"),
                    Choice("Treat as different (keep both)", value="different"),
                    Choice("Skip for now", value="skip"),
                ],
            ).ask()
            if action is None:
                raise KeyboardInterrupt
            if action == "same":
                if cand.spotify_track_id:
                    inv.add_sameness(cand.spotify_track_id, item.existing_track_id)
                inv.delete_pending(item.row_id)
            elif action == "different":
                inv.insert_track(cand)
                inv.delete_pending(item.row_id)
            else:
                pass
    except KeyboardInterrupt:
        print("\nAborted guidance — unanswered variants left as skip-for-now; no packs written.")
        return False
    return True


def export_run(
    client: SpotifyClient,
    inv: Inventory,
    paths: AppPaths,
    *,
    include_followed: bool,
) -> None:
    require_tty()
    playlists = client.list_playlists()
    selected = choose_playlists(playlists, include_followed=include_followed)
    if not selected:
        print("Nothing selected.")
        return

    stats = RunStats()
    work_items: list[PlaylistWork] = []

    for sel in selected:
        if sel.liked:
            tracks, problems = client.liked_tracks()
            pk = inv.upsert_playlist(
                spotify_playlist_id=None,
                title="Liked Songs",
                kind="liked_songs",
            )
            for p in problems:
                _record_fetch_problem(inv, pk, p, stats)
            _process_tracks(inv, pk, tracks, stats)
            work_items.append(PlaylistWork(selection=sel, playlist_pk=pk))
            continue

        assert sel.playlist is not None
        pl = sel.playlist
        pk = inv.upsert_playlist(
            spotify_playlist_id=pl.id,
            title=pl.name,
            kind="playlist",
            snapshot_id=pl.snapshot_id,
        )
        tracks, problems, status = client.playlist_items(pl.id)
        if status == 403:
            msg = (
                f"Spotify blocked track listing for followed playlist "
                f"“{pl.name}” (not owner/collaborator)."
            )
            inv.record_problem(pk, reason="followed_items_forbidden")
            stats.problems.append(msg)
            print(msg)
            continue
        for p in problems:
            _record_fetch_problem(inv, pk, p, stats)
        _process_tracks(inv, pk, tracks, stats)
        work_items.append(
            PlaylistWork(
                selection=sel,
                playlist_pk=pk,
                snapshot_id=pl.snapshot_id,
            )
        )

    # Report problems collected so far
    print("\n=== Summary (pre-guidance) ===")
    print(
        f"new tracks: {stats.exported_tracks}, "
        f"already known: {stats.skipped_known}, "
        f"collapsed copies: {stats.collapsed_copies}"
    )
    if stats.problems:
        print("\n=== Problems ===")
        for line in stats.problems:
            print(f"- {line}")

    completed = run_variant_guidance(inv)
    if not completed:
        return

    paths.ensure()
    for item in work_items:
        sel = item.selection
        if sel.liked:
            tracks, _ = client.liked_tracks()
            title = "Liked Songs"
            liked = True
            snapshot = None
        else:
            assert sel.playlist is not None
            tracks, _, status = client.playlist_items(sel.playlist.id)
            if status == 403:
                continue
            title = sel.playlist.name
            liked = False
            snapshot = sel.playlist.snapshot_id

        collapsed, _ = collapse_copies(tracks)
        final: list[TrackData] = []
        for track in collapsed:
            result = inv.match(track)
            if result.kind == MatchKind.VARIANT:
                continue
            if result.kind == MatchKind.NEW:
                inv.insert_track(track)
            final.append(track)

        _apply_membership_final(inv, item.playlist_pk, final)
        inv.mark_exported(item.playlist_pk, snapshot)

        path = write_pack(
            paths.packs_dir,
            title=title,
            tracks=final,
            liked_songs=liked,
        )
        if path is None:
            stats.empty_playlists += 1
            print(f"No pack written for empty playlist: {title}")
        else:
            stats.packs_written += 1
            print(f"Wrote {path}")

    print(
        f"\nDone. Packs written: {stats.packs_written}. "
        f"Empty (no pack): {stats.empty_playlists}."
    )
    print(
        "Portable packs are a transferable handoff (identity + order only). "
        f"Full state (skips, problems, guidance) lives in the local inventory:\n"
        f"  {paths.inventory_file}"
    )


def _apply_membership_final(
    inv: Inventory, playlist_pk: int, tracks: list[TrackData]
) -> None:
    inv.clear_membership(playlist_pk)
    for i, track in enumerate(tracks, start=1):
        result = inv.match(track)
        if result.existing_track_pk is None:
            pk = inv.insert_track(track)
        else:
            pk = result.existing_track_pk
        inv.add_membership(playlist_pk, pk, i)
    inv.commit()


def _record_fetch_problem(
    inv: Inventory,
    playlist_pk: int,
    problem: FetchProblem,
    stats: RunStats,
) -> None:
    inv.record_problem(
        playlist_pk,
        reason=problem.reason,
        title=problem.title,
        artists=problem.artists,
        spotify_track_id=problem.spotify_track_id,
    )
    label = problem.title or problem.spotify_track_id or "?"
    stats.problems.append(f"{label}: {problem.reason}")
