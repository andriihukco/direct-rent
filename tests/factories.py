"""Test-only builders."""
from datetime import UTC, datetime
from itertools import count

from directrent.models import Contact, Decision, Listing, Verdict

_ids = count(1)


def make_listing(**kw) -> Listing:
    n = next(_ids)
    base = dict(
        source="telegram", source_id=f"ch:{n}", url=f"https://t.me/ch/{n}", text="Здам 2к квартиру",
        posted_at=datetime.now(UTC), channel_title="Ch", contacts=[Contact("phone", "+380670000001")],
        price_uah=16000, price_raw="16000 грн", rooms=2, district="Сихівський", street=None, pets="unknown",
        photo_bytes=None, photo_url=None, photo_hash=None,
    )
    base.update(kw)
    return Listing(**base)


PASS = Decision(Verdict.PASS, "rules", "owner:власник")
