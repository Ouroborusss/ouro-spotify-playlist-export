"""Track identity matching: exact id, sameness, ISRC, fuzzy variant cues."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum, auto

from ouro_spe.spotify import TrackData

VARIANT_CUES = re.compile(
    r"\b(acoustic|live|remaster(?:ed)?|demo|instrumental|karaoke|unplugged|edit|mix)\b",
    re.IGNORECASE,
)


class MatchKind(Enum):
    KNOWN = auto()  # same track or sameness link — skip add
    VARIANT = auto()  # needs guidance
    NEW = auto()


@dataclass(frozen=True)
class MatchResult:
    kind: MatchKind
    existing_track_pk: int | None = None
    reason: str | None = None


def normalize_title(title: str) -> str:
    t = title.lower().strip()
    t = VARIANT_CUES.sub("", t)
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"[\(\)\[\]\{\}\-_/]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def artists_key(artists: list[str]) -> str:
    return "|".join(a.lower().strip() for a in artists if a.strip())


def looks_like_variant(a: TrackData, b_title: str, b_artists: list[str]) -> bool:
    if artists_key(a.artists) != artists_key(b_artists):
        return False
    na, nb = normalize_title(a.title), normalize_title(b_title)
    if not na or not nb:
        return False
    if na == nb:
        return VARIANT_CUES.search(a.title) is not None or VARIANT_CUES.search(b_title) is not None
    return na in nb or nb in na
