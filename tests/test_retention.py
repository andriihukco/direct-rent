from directrent.retention import purge
from directrent.store import save_listing
from directrent.models import Contact
from tests.factories import PASS, make_listing


async def test_purge(db):
    async with db.acquire() as c:
        o_old = await c.fetchval("INSERT INTO objects DEFAULT VALUES RETURNING id")
        o_new = await c.fetchval("INSERT INTO objects DEFAULT VALUES RETURNING id")
        old = await save_listing(c, make_listing(contacts=[Contact("phone", "+380670000001")]), o_old, PASS)
        await save_listing(c, make_listing(contacts=[Contact("phone", "+380670000002")]), o_new, PASS)
        bad = await save_listing(c, make_listing(contacts=[Contact("tg_username", "broker1")]), o_old, PASS)
        await c.execute("UPDATE contacts SET blacklisted = true WHERE value = 'broker1'")
        await c.execute("UPDATE listings SET ingested_at = now() - interval '61 days' WHERE id = ANY($1)", [old, bad])
        await c.execute("UPDATE listings SET ingested_at = now() - interval '59 days' WHERE id NOT IN ($1, $2)", old, bad)
        assert await purge(c) == 2
        assert await c.fetchval("SELECT count(*) FROM listings") == 1
        assert await c.fetchval("SELECT count(*) FROM objects") == 1
        values = {r["value"] for r in await c.fetch("SELECT value FROM contacts")}
        assert values == {"+380670000002", "broker1"}
