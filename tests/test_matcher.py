import asyncio

from directrent.matcher import enqueue
from directrent.store import save_listing
from tests.factories import PASS, make_listing


async def _user(c, uid=1, districts=(), pmin=None, pmax=None, rooms=(), pets=False, paused=False):
    await c.execute("INSERT INTO users (tg_id, paused) VALUES ($1, $2)", uid, paused)
    await c.execute(
        "INSERT INTO filters (user_id, districts, price_min, price_max, rooms, pets_required) VALUES ($1,$2,$3,$4,$5,$6)",
        uid, list(districts), pmin, pmax, list(rooms), pets,
    )


async def _listing(c, object_id=None, **kw):
    if object_id is None:
        object_id = await c.fetchval("INSERT INTO objects DEFAULT VALUES RETURNING id")
    return await save_listing(c, make_listing(**kw), object_id, PASS), object_id


async def test_district_mismatch_excludes(db):
    async with db.acquire() as c:
        await _user(c, districts=["Сихівський"])
        lid, _ = await _listing(c, district="Галицький")
        assert await enqueue(c, lid) == 0


async def test_unknown_district_matches(db):
    async with db.acquire() as c:
        await _user(c, districts=["Сихівський"])
        lid, _ = await _listing(c, district=None)
        assert await enqueue(c, lid) == 1


async def test_price_above_max_excludes_and_null_price_matches(db):
    async with db.acquire() as c:
        await _user(c, pmax=18000)
        lid, _ = await _listing(c, price_uah=20000)
        assert await enqueue(c, lid) == 0
        lid, _ = await _listing(c, price_uah=None)
        assert await enqueue(c, lid) == 1


async def test_price_below_min_excludes(db):
    async with db.acquire() as c:
        await _user(c, pmin=10000)
        lid, _ = await _listing(c, price_uah=9000)
        assert await enqueue(c, lid) == 0


async def test_rooms(db):
    async with db.acquire() as c:
        await _user(c, rooms=[1, 2])
        lid, _ = await _listing(c, rooms=3)
        assert await enqueue(c, lid) == 0
        lid, _ = await _listing(c, rooms=None)
        assert await enqueue(c, lid) == 1


async def test_pets_required(db):
    async with db.acquire() as c:
        await _user(c, pets=True)
        lid, _ = await _listing(c, pets="no")
        assert await enqueue(c, lid) == 0
        lid, _ = await _listing(c, pets="unknown")
        assert await enqueue(c, lid) == 1


async def test_paused_user_excluded(db):
    async with db.acquire() as c:
        await _user(c, paused=True)
        lid, _ = await _listing(c)
        assert await enqueue(c, lid) == 0


async def test_user_without_filter_gets_nothing(db):
    async with db.acquire() as c:
        await c.execute("INSERT INTO users (tg_id) VALUES (9)")
        lid, _ = await _listing(c)
        assert await enqueue(c, lid) == 0


async def test_same_object_delivered_once(db):
    async with db.acquire() as c:
        await _user(c)
        lid, oid = await _listing(c)
        assert await enqueue(c, lid) == 1
        lid2, _ = await _listing(c, object_id=oid)
        assert await enqueue(c, lid2) == 0


async def test_complained_object_excluded(db):
    async with db.acquire() as c:
        await _user(c)
        lid, oid = await _listing(c)
        await c.execute("INSERT INTO complaints (user_id, object_id) VALUES (1, $1)", oid)
        assert await enqueue(c, lid) == 0


async def test_concurrent_enqueue_same_object_one_row(db):
    async with db.acquire() as c:
        await _user(c)
        lid1, oid = await _listing(c)
        lid2, _ = await _listing(c, object_id=oid)

    async def run(lid):
        async with db.acquire() as c, c.transaction():
            n = await enqueue(c, lid)
            await asyncio.sleep(0.05)
            return n

    results = await asyncio.gather(run(lid1), run(lid2))
    assert sorted(results) == [0, 1]
    assert await db.fetchval("SELECT count(*) FROM outbox") == 1
