"""Daily purge of old listing data (spec §12: 60 days). Blacklisted contacts are kept."""
from datetime import datetime

import asyncpg

RETENTION = "60 days"
PHOTO_RETENTION = "1 day"  # cards are sent within minutes; later users reuse the Telegram file_id


async def purge(conn: asyncpg.Connection, now: datetime | None = None) -> int:
    """Delete listings older than the retention window, then orphaned objects and contacts."""
    async with conn.transaction():
        status = await conn.execute(
            f"DELETE FROM listings WHERE ingested_at < coalesce($1::timestamptz, now()) - interval '{RETENTION}'", now)
        await conn.execute(
            f"""UPDATE listings SET photo_bytes = NULL WHERE photo_bytes IS NOT NULL
                AND ingested_at < coalesce($1::timestamptz, now()) - interval '{PHOTO_RETENTION}'""", now)
        await conn.execute("DELETE FROM objects o WHERE NOT EXISTS (SELECT 1 FROM listings l WHERE l.object_id = o.id)")
        await conn.execute(
            """DELETE FROM contacts c WHERE NOT c.blacklisted
               AND NOT EXISTS (SELECT 1 FROM listing_contacts lc WHERE lc.contact_id = c.id)""")
    return int(status.split()[-1])
