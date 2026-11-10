"""Stage 1 (contact reputation) and the complaint → blacklist loop."""
import asyncpg

from directrent.models import Contact, Decision, Verdict

MAX_OBJECTS_PER_CONTACT = 2
COMPLAINTS_TO_BLACKLIST = 2
SHARED_MIN_PHONES = 3  # a contact seen next to this many different phones is a channel signature
WINDOW = "30 days"


async def shared_contacts(conn: asyncpg.Connection, contacts: list[Contact],
                          extra_phones: set[str] = frozenset()) -> set[Contact]:
    """Contacts that appear next to many different phone numbers: channel footers, admin handles.

    They identify a channel, not a flat or a person, so reputation, dedup and blacklisting skip them.
    `extra_phones` are the phones of the listing being processed (not stored yet).
    """
    if not contacts:
        return set()
    rows = await conn.fetch(
        f"""SELECT c.kind, c.value, array_remove(array_agg(DISTINCT p.value), NULL) AS phones
            FROM unnest($1::text[], $2::text[]) AS x(kind, value)
            JOIN contacts c ON c.kind = x.kind AND c.value = x.value
            JOIN listing_contacts lc ON lc.contact_id = c.id
            JOIN listings l ON l.id = lc.listing_id AND l.ingested_at > now() - interval '{WINDOW}'
            LEFT JOIN listing_contacts lc2 ON lc2.listing_id = l.id
            LEFT JOIN contacts p ON p.id = lc2.contact_id AND p.kind = 'phone' AND p.id <> c.id
            GROUP BY c.kind, c.value""",
        [c.kind for c in contacts], [c.value for c in contacts],
    )
    shared = set()
    for r in rows:
        phones = set(r["phones"]) | (set(extra_phones) - {r["value"]})
        if len(phones) >= SHARED_MIN_PHONES:
            shared.add(Contact(r["kind"], r["value"]))
    return shared


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
    rows = await conn.fetch(
        """SELECT DISTINCT c.kind, c.value FROM contacts c
           JOIN listing_contacts lc ON lc.contact_id = c.id
           JOIN listings l ON l.id = lc.listing_id WHERE l.object_id = $1""",
        object_id,
    )
    contacts = [Contact(r["kind"], r["value"]) for r in rows]
    own = [c for c in contacts if c not in await shared_contacts(conn, contacts)]
    await conn.execute(
        """UPDATE contacts SET blacklisted = true
           FROM unnest($1::text[], $2::text[]) AS x(kind, value)
           WHERE contacts.kind = x.kind AND contacts.value = x.value""",
        [c.kind for c in own], [c.value for c in own],
    )
    return True
