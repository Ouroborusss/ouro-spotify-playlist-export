from ouro_spe.slug import slugify


def test_slugify_basic():
    assert slugify("Hello World!") == "hello-world"


def test_slugify_liked():
    assert slugify("anything", liked_songs=True) == "liked-songs"


def test_slugify_empty():
    assert slugify("@@@") == "playlist"
