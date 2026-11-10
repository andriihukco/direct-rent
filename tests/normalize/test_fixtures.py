from pathlib import Path

import pytest

from directrent.normalize.fields import parse_district, parse_pets, parse_price, parse_rooms

POSTS = sorted((Path(__file__).parent.parent / "fixtures" / "posts").glob("*.txt"))


def _expect(header: str) -> dict:
    pairs = dict(p.split("=", 1) for p in header.removeprefix("# expect:").split())
    return {k: (None if v == "none" else v) for k, v in pairs.items()}


@pytest.mark.parametrize("path", POSTS, ids=[p.stem for p in POSTS])
def test_fixture(path):
    header, body = path.read_text().split("\n", 1)
    e = _expect(header)
    got = {
        "price": parse_price(body, 41.5)[0],
        "rooms": parse_rooms(body),
        "district": parse_district(body),
        "pets": parse_pets(body),
    }
    want = {
        "price": int(e["price"]) if e["price"] else None,
        "rooms": int(e["rooms"]) if e["rooms"] else None,
        "district": e["district"],
        "pets": e["pets"],
    }
    assert got == want


def test_enough_fixtures():
    assert len(POSTS) >= 12
