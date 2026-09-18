"""Filename slug helpers for portable packs."""

from __future__ import annotations

import re
import unicodedata


def slugify(title: str, *, liked_songs: bool = False) -> str:
    if liked_songs:
        return "liked-songs"
    text = unicodedata.normalize("NFKD", title)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    text = re.sub(r"-{2,}", "-", text)
    return text or "playlist"
