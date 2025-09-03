import pathlib


from aventuroo.autopost.utils import slugify, parse_feed


def load_bytes(name: str) -> bytes:
    path = pathlib.Path(__file__).parent / "feeds" / name
    return path.read_bytes()


def test_slugify():
    assert slugify("Hello World!") == "hello-world"
    assert slugify("   many---spaces__") == "many-spaces"
    assert slugify("$$$") == "post"


def test_parse_feed_rss():
    xml = load_bytes("sample_rss.xml")
    items = parse_feed(xml)
    assert len(items) == 2
    first = items[0]
    assert first["title"] == "First Post"
    assert first["link"] == "http://example.com/1"
    assert first["summary"] == "First item"


def test_parse_feed_atom():
    xml = load_bytes("sample_atom.xml")
    items = parse_feed(xml)
    assert len(items) == 2
    first = items[0]
    assert first["title"] == "Atom One"
    assert first["link"] == "http://example.com/a1"
    assert first["summary"] == "First entry"


def test_parse_feed_invalid():
    assert parse_feed(b"not xml") == []
    assert parse_feed(b"") == []
