"""Has this post been seen, and which physical flat (object) does a listing describe?"""
import io

import asyncpg
import imagehash
from PIL import Image, UnidentifiedImageError

from directrent.models import Contact, Listing

PHASH_MAX_DISTANCE = 6
PRICE_TOLERANCE = 0.05
WINDOW = "30 days"
# Kinds that identify one person. Text @handles are too often channel or admin handles to link flats.
STRONG_KINDS = {"phone", "tg_user_id", "olx_user_id"}
_MASK = (1 << 64) - 1


def photo_hash(data: bytes) -> int | None:
    """64-bit dHash as a signed int64 (Postgres bigint), or None for unreadable bytes."""
    try:
        h = int(str(imagehash.dhash(Image.open(io.BytesIO(data)))), 16)
    except (UnidentifiedImageError, OSError, ValueError):
        return None
    return h - (1 << 64) if h >= 1 << 63 else h


def _distance(a: int, b: int) -> int:
    return ((a ^ b) & _MASK).bit_count()


def _close_price(a: int | None, b: int | None) -> bool:
    return a is not None and b is not None and abs(a - b) <= PRICE_TOLERANCE * max(a, b)


async def seen(conn: asyncpg.Connection, source: str, source_id: str) -> bool:
    return await conn.fetchval(
        "SELECT EXISTS (SELECT 1 FROM listings WHERE source = $1 AND source_id = $2)", source, source_id
    )


def _same_rooms(a: int | None, b: int | None) -> bool:
    return a == b  # both unknown counts as the same


async def find_or_create_object(conn: asyncpg.Connection, listing: Listing,
                                contacts: list[Contact] | None = None) -> int:
    """Spec §7.2: join an object that shares a contact (30 days) by photo hash, then by rooms+price.

    `contacts` overrides listing.contacts (the pipeline passes them without channel signatures).
    Only strong contact kinds link listings.
    """
    keys = [c for c in (listing.contacts if contacts is None else contacts) if c.kind in STRONG_KINDS]
    rows = []
    if keys:
        rows = await conn.fetch(
            f"""SELECT DISTINCT l.object_id, l.photo_hash, l.price_uah, l.rooms, l.ingested_at
                FROM listings l
                JOIN listing_contacts lc ON lc.listing_id = l.id
                JOIN contacts c ON c.id = lc.contact_id
                JOIN unnest($1::text[], $2::text[]) AS x(kind, value) ON c.kind = x.kind AND c.value = x.value
                WHERE l.object_id IS NOT NULL AND l.ingested_at > now() - interval '{WINDOW}'
                ORDER BY l.ingested_at DESC""",
            [c.kind for c in keys], [c.value for c in keys],
        )
    if listing.photo_hash is not None:
        for r in rows:
            if r["photo_hash"] is not None and _distance(r["photo_hash"], listing.photo_hash) <= PHASH_MAX_DISTANCE:
                return r["object_id"]
    for r in rows:
        if _same_rooms(r["rooms"], listing.rooms) and _close_price(r["price_uah"], listing.price_uah):
            return r["object_id"]
    return await conn.fetchval("INSERT INTO objects (photo_hash) VALUES ($1) RETURNING id", listing.photo_hash)
