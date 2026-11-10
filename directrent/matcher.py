"""Listing → outbox rows for every user whose filter matches (spec §9)."""
import asyncpg

# Explicit mismatch excludes; an unknown (NULL / 'unknown') listing value never excludes.
# Deliveries are inserted in the same statement, so a concurrent enqueue for another listing
# of the same object blocks on the primary key and then inserts nothing (one card per object).
_ENQUEUE = """
WITH l AS (
    SELECT id, object_id, district, price_uah, rooms, pets FROM listings WHERE id = $1
), candidates AS (
    SELECT u.tg_id
    FROM users u
    JOIN filters f ON f.user_id = u.tg_id
    CROSS JOIN l
    WHERE NOT u.paused
      AND (cardinality(f.districts) = 0 OR l.district IS NULL OR l.district = ANY (f.districts))
      AND (f.price_min IS NULL OR l.price_uah IS NULL OR l.price_uah >= f.price_min)
      AND (f.price_max IS NULL OR l.price_uah IS NULL OR l.price_uah <= f.price_max)
      AND (cardinality(f.rooms) = 0 OR l.rooms IS NULL OR l.rooms = ANY (f.rooms))
      AND (NOT f.pets_required OR l.pets <> 'no')
      AND NOT EXISTS (SELECT 1 FROM complaints c WHERE c.user_id = u.tg_id AND c.object_id = l.object_id)
), delivered AS (
    INSERT INTO deliveries (user_id, object_id)
    SELECT tg_id, (SELECT object_id FROM l) FROM candidates
    ON CONFLICT DO NOTHING
    RETURNING user_id
)
INSERT INTO outbox (user_id, listing_id)
SELECT user_id, $1 FROM delivered
RETURNING id
"""


async def enqueue(conn: asyncpg.Connection, listing_id: int) -> int:
    """Create outbox rows for matching users. Returns how many."""
    return len(await conn.fetch(_ENQUEUE, listing_id))
