from directrent.antibroker.reputation import check_reputation, record_complaint
from directrent.dedup import find_or_create_object
from directrent.models import Contact, Verdict
from directrent.store import save_listing
from tests.factories import PASS, make_listing

P = Contact("phone", "+380670000001")


async def _new_object(c) -> int:
    return await c.fetchval("INSERT INTO objects DEFAULT VALUES RETURNING id")


async def _store_on(c, object_id, contacts=(P,)):
    await save_listing(c, make_listing(contacts=list(contacts)), object_id, PASS)


async def test_three_objects_plus_incoming_rejects(db):
    async with db.acquire() as c:
        for _ in range(3):
            await _store_on(c, await _new_object(c))
        d = await check_reputation(c, [P], await _new_object(c))
        assert d.verdict == Verdict.REJECT and d.stage == "reputation" and d.reason == "objects:4"


async def test_cross_posted_single_object_passes(db):
    async with db.acquire() as c:
        oid = await _new_object(c)
        for _ in range(3):
            await _store_on(c, oid)
        assert await check_reputation(c, [P], oid) is None


async def test_blacklisted_username_rejects(db):
    async with db.acquire() as c:
        await c.execute("INSERT INTO contacts (kind, value, blacklisted) VALUES ('tg_username', 'broker', true)")
        d = await check_reputation(c, [Contact("tg_username", "broker")], await _new_object(c))
        assert d.verdict == Verdict.REJECT and d.reason == "blacklist:tg_username"


async def test_no_contacts_passes(db):
    async with db.acquire() as c:
        assert await check_reputation(c, [], await _new_object(c)) is None


async def test_two_complaints_blacklist_contacts(db):
    async with db.acquire() as c:
        await c.execute("INSERT INTO users (tg_id) VALUES (1), (2)")
        li = make_listing(contacts=[P])
        oid = await find_or_create_object(c, li)
        await save_listing(c, li, oid, PASS)
        assert await record_complaint(c, 1, oid) is False
        assert await record_complaint(c, 1, oid) is False
        assert await record_complaint(c, 2, oid) is True
        assert await c.fetchval("SELECT blacklisted FROM contacts WHERE value = $1", P.value) is True
