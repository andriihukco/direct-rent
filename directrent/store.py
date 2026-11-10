"""Persist a processed listing and its contacts."""
import json
from dataclasses import asdict

import asyncpg

from directrent.models import Decision, Listing


async def save_listing(conn: asyncpg.Connection, listing: Listing, object_id: int | None,
                       decision: Decision) -> int:
    listing_id = await conn.fetchval(
        """INSERT INTO listings (source, source_id, url, object_id, text, channel_title, price_uah, price_raw,
               rooms, district, street, pets, posted_at, verdict, verdict_stage, verdict_reason, llm_confidence,
               photo_url, photo_bytes, photo_hash, raw_contacts)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21)
           RETURNING id""",
        listing.source, listing.source_id, listing.url, object_id, listing.text, listing.channel_title,
        listing.price_uah, listing.price_raw, listing.rooms, listing.district, listing.street, listing.pets,
        listing.posted_at, decision.verdict.value, decision.stage, decision.reason, decision.confidence,
        listing.photo_url, listing.photo_bytes, listing.photo_hash,
        json.dumps([asdict(c) for c in listing.contacts], ensure_ascii=False),
    )
    for c in listing.contacts:
        contact_id = await conn.fetchval(
            """INSERT INTO contacts (kind, value) VALUES ($1, $2)
               ON CONFLICT (kind, value) DO UPDATE SET kind = EXCLUDED.kind RETURNING id""",
            c.kind, c.value,
        )
        await conn.execute(
            "INSERT INTO listing_contacts (listing_id, contact_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
            listing_id, contact_id,
        )
    return listing_id
