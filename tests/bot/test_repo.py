from directrent.bot import repo
from directrent.models import Filter
from directrent.store import save_listing
from tests.factories import PASS, make_listing


async def test_filter_round_trip(db):
    async with db.acquire() as c:
        await repo.upsert_user(c, 1, "ann")
        f = Filter(1, ["Сихівський"], 10000, 18000, [2], True)
        await repo.save_filter(c, f)
        assert await repo.get_filter(c, 1) == f
        f2 = Filter(1, [], None, None, [], False)
        await repo.save_filter(c, f2)
        assert await repo.get_filter(c, 1) == f2


async def test_get_filter_missing(db):
    async with db.acquire() as c:
        assert await repo.get_filter(c, 5) is None


async def test_pause_and_delete(db):
    async with db.acquire() as c:
        await repo.upsert_user(c, 1, None)
        await repo.save_filter(c, Filter(1, [], None, None, [], False))
        await repo.set_paused(c, 1, True)
        assert await repo.is_paused(c, 1) is True
        oid = await c.fetchval("INSERT INTO objects DEFAULT VALUES RETURNING id")
        lid = await save_listing(c, make_listing(), oid, PASS)
        await c.execute("INSERT INTO complaints (user_id, object_id) VALUES (1, $1)", oid)
        await c.execute("INSERT INTO deliveries (user_id, object_id) VALUES (1, $1)", oid)
        await c.execute("INSERT INTO outbox (user_id, listing_id) VALUES (1, $1)", lid)
        await repo.delete_user_data(c, 1)
        for table, col in [("users", "tg_id"), ("filters", "user_id"), ("complaints", "user_id"),
                           ("deliveries", "user_id"), ("outbox", "user_id")]:
            assert await c.fetchval(f"SELECT count(*) FROM {table} WHERE {col} = 1") == 0
