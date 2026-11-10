"""RawPost → Listing."""
from directrent.models import Listing, RawPost
from directrent.normalize.fields import parse_district, parse_pets, parse_price, parse_rooms, parse_street
from directrent.normalize.phones import extract_contacts


def normalize(raw: RawPost, usd_rate: float) -> Listing:
    price_uah, price_raw = parse_price(raw.text, usd_rate)
    return Listing(
        source=raw.source, source_id=raw.source_id, url=raw.url, text=raw.text,
        posted_at=raw.posted_at, channel_title=raw.channel_title,
        contacts=extract_contacts(raw.text, raw.author_contacts),
        price_uah=price_uah, price_raw=price_raw, rooms=parse_rooms(raw.text),
        district=parse_district(raw.text), street=parse_street(raw.text), pets=parse_pets(raw.text),
        photo_bytes=raw.photo_bytes, photo_url=raw.photo_url,
    )
