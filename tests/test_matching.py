from ouro_spe.matching import looks_like_variant, normalize_title
from ouro_spe.spotify import TrackData


def test_normalize_strips_cues():
    assert "acoustic" not in normalize_title("Hello (Acoustic)")


def test_looks_like_variant():
    a = TrackData(
        spotify_track_id=None,
        isrc=None,
        title="Hello",
        artists=["Band"],
        album=None,
        duration_ms=1,
        disc_number=None,
        track_number=None,
    )
    assert looks_like_variant(a, "Hello - Acoustic", ["Band"])
