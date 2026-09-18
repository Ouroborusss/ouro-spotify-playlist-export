from ouro_spe.pack import collapse_copies, build_pack_document
from ouro_spe.spotify import TrackData


def _t(id_: str, title: str = "T") -> TrackData:
    return TrackData(
        spotify_track_id=id_,
        isrc=None,
        title=title,
        artists=["A"],
        album=None,
        duration_ms=1000,
        disc_number=1,
        track_number=1,
    )


def test_collapse_copies_first_wins():
    tracks, n = collapse_copies([_t("1", "a"), _t("1", "b"), _t("2", "c")])
    assert n == 1
    assert [t.title for t in tracks] == ["a", "c"]


def test_build_pack_document():
    doc = build_pack_document(title="Demo", tracks=[_t("abc")])
    assert doc["schema_version"] == 1
    assert doc["source"] == "spotify"
    assert doc["tracks"][0]["position"] == 1
    assert doc["tracks"][0]["spotify_track_id"] == "abc"
