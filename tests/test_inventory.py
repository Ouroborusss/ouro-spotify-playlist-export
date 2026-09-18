from pathlib import Path

from ouro_spe.inventory import Inventory
from ouro_spe.matching import MatchKind
from ouro_spe.spotify import TrackData


def _track(**kwargs) -> TrackData:
    base = dict(
        spotify_track_id="sid1",
        isrc="ISRC1",
        title="Song",
        artists=["Artist"],
        album="Album",
        duration_ms=120000,
        disc_number=1,
        track_number=1,
    )
    base.update(kwargs)
    return TrackData(**base)


def test_match_known_and_sameness(tmp_path: Path):
    inv = Inventory(tmp_path / "inv.sqlite")
    pk = inv.insert_track(_track())
    assert inv.match(_track()).kind == MatchKind.KNOWN

    inv.add_sameness("other", pk)
    m = inv.match(_track(spotify_track_id="other", isrc=None, title="Other"))
    assert m.kind == MatchKind.KNOWN
    assert m.existing_track_pk == pk
    inv.close()


def test_isrc_variant(tmp_path: Path):
    inv = Inventory(tmp_path / "inv.sqlite")
    inv.insert_track(_track())
    m = inv.match(_track(spotify_track_id="sid2", title="Song Acoustic"))
    assert m.kind == MatchKind.VARIANT
    inv.close()
