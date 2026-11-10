"""Stage 1 (contact reputation) and the complaint → blacklist loop."""
import asyncpg

from directrent.models import Contact, Decision, Verdict

MAX_OBJECTS_PER_CONTACT = 2
COMPLAINTS_TO_BLACKLIST = 2
WINDOW = "30 days"


async def check_reputation(conn: asyncpg.Connection, contacts: list[Contact], object_id: int) -> Decision | None:
    if not contacts:
        return None
    kinds, values = [c.kind for c in contacts], [c.value for c in contacts]
    rows = await conn.fetch(
        f"""SELECT c.kind, c.blacklisted,
                   array_remove(array_agg(DISTINCT l.object_id), NULL) AS objects
            FROM unnest($1::text[], $2::text[]) AS x(kind, value)
            JOIN contacts c ON c.kind = x.kind AND c.value = x.value
            LEFT JOIN listing_contacts lc ON lc.contact_id = c.id
            LEFT JOIN listings l ON l.id = lc.listing_id AND l.ingested_at > now() - interval '{WINDOW}'
            GROUP BY c.id, c.kind, c.blacklisted""",
        kinds, values,
    )
    for r in rows:
        if r["blacklisted"]:
            return Decision(Verdict.REJECT, "reputation", f"blacklist:{r['kind']}")
    for r in rows:
        n = len(set(r["objects"]) | {object_id})
        if n > MAX_OBJECTS_PER_CONTACT:
            return Decision(Verdict.REJECT, "reputation", f"objects:{n}")
    return None


async def record_complaint(conn: asyncpg.Connection, user_id: int, object_id: int) -> bool:
    """Store a 'this is a broker' complaint. True once enough distinct users complained (contacts blacklisted)."""
    await conn.execute(
        "INSERT INTO complaints (user_id, object_id) VALUES ($1, $2) ON CONFLICT DO NOTHING", user_id, object_id
    )
    n = await conn.fetchval("SELECT count(*) FROM complaints WHERE object_id = $1", object_id)
    if n < COMPLAINTS_TO_BLACKLIST:
        return False
    await conn.execute(
        """UPDATE contacts SET blacklisted = true
           WHERE id IN (SELECT lc.contact_id FROM listing_contacts lc
                        JOIN listings l ON l.id = lc.listing_id WHERE l.object_id = $1)""",
        object_id,
    )
    return True
