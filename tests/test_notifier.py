import asyncio
from types import SimpleNamespace

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.methods import SendMessage

from directrent.notifier import Notifier
from directrent.store import save_listing
from tests.factories import PASS, make_listing

M = SendMessage(chat_id=1, text="x")


class FakeBot:
    def __init__(self, errors=()):
        self.calls, self.errors = [], list(errors)

    async def _maybe_fail(self):
        if self.errors:
            raise self.errors.pop(0)

    async def send_photo(self, chat_id, photo, **kw):
        await self._maybe_fail()
        self.calls.append(("photo", chat_id, photo))
        return SimpleNamespace(photo=[SimpleNamespace(file_id="small"), SimpleNamespace(file_id="FILE1")])

    async def send_message(self, chat_id, text, **kw):
        await self._maybe_fail()
        self.calls.append(("text", chat_id, text))
        return SimpleNamespace()


async def nosleep(_):
    return None


async def _setup(c, users=(1,), **listing_kw):
    oid = await c.fetchval("INSERT INTO objects DEFAULT VALUES RETURNING id")
    lid = await save_listing(c, make_listing(**listing_kw), oid, PASS)
    for u in users:
        await c.execute("INSERT INTO users (tg_id) VALUES ($1) ON CONFLICT DO NOTHING", u)
        await c.execute("INSERT INTO outbox (user_id, listing_id) VALUES ($1, $2)", u, lid)
    return lid


async def _drain(n: Notifier):
    async with n.pool.acquire() as c:
        rows = await n.claim(c)
    for r in rows:
        await n.send_one(r)


async def _status(db):
    return [tuple(r) for r in await db.fetch("SELECT user_id, status, attempts FROM outbox ORDER BY id")]


async def test_photo_bytes_uploaded_once_then_file_id_reused(db):
    async with db.acquire() as c:
        lid = await _setup(c, users=(1, 2), photo_bytes=b"jpegbytes")
    bot = FakeBot()
    n = Notifier(bot, db, sleep=nosleep)
    async with db.acquire() as c:
        rows = await n.claim(c)
    await n.send_one(rows[0])
    await n.send_one(rows[1])
    first, second = bot.calls
    assert first[2].__class__.__name__ == "BufferedInputFile"
    assert second[2] == "FILE1"
    row = await db.fetchrow("SELECT tg_file_id, photo_bytes FROM listings WHERE id = $1", lid)
    assert (row["tg_file_id"], row["photo_bytes"]) == ("FILE1", None)
    assert [s for _, s, _ in await _status(db)] == ["sent", "sent"]


async def test_text_only_listing_sends_message(db):
    async with db.acquire() as c:
        await _setup(c)
    bot = FakeBot()
    await _drain(Notifier(bot, db, sleep=nosleep))
    assert bot.calls[0][0] == "text"


async def test_forbidden_pauses_user_and_others_still_sent(db):
    async with db.acquire() as c:
        await _setup(c, users=(1, 2))
    bot = FakeBot(errors=[TelegramForbiddenError(M, "bot was blocked by the user")])
    await _drain(Notifier(bot, db, sleep=nosleep))
    assert await _status(db) == [(1, "failed", 0), (2, "sent", 0)]
    assert await db.fetchval("SELECT paused FROM users WHERE tg_id = 1") is True


async def test_generic_error_three_times_fails(db):
    async with db.acquire() as c:
        await _setup(c)
    bot = FakeBot(errors=[TelegramBadRequest(M, "bad")] * 3)
    n = Notifier(bot, db, sleep=nosleep)
    for _ in range(3):
        await db.execute("UPDATE outbox SET next_try_at = now() WHERE status = 'pending'")
        await _drain(n)
    assert await _status(db) == [(1, "failed", 3)]
    assert await db.fetchval("SELECT last_error FROM outbox") == "Telegram server says - bad"


async def test_retry_after_waits_and_does_not_count_attempt(db):
    async with db.acquire() as c:
        await _setup(c)
    slept = []

    async def rec(s):
        slept.append(s)

    bot = FakeBot(errors=[TelegramRetryAfter(M, "flood", 1)])
    await _drain(Notifier(bot, db, sleep=rec))
    assert await _status(db) == [(1, "sent", 0)] and 1 in slept


async def test_reclaim_stale(db):
    async with db.acquire() as c:
        await _setup(c)
        await c.execute("UPDATE outbox SET status = 'sending', claimed_at = now() - interval '3 minutes'")
        n = Notifier(FakeBot(), db, sleep=nosleep)
        assert await n.reclaim_stale(c) == 1
    assert await _status(db) == [(1, "pending", 0)]


async def test_concurrent_claims_are_disjoint(db):
    async with db.acquire() as c:
        await _setup(c, users=(1, 2, 3, 4, 5, 6))
    n = Notifier(FakeBot(), db, sleep=nosleep)

    async def claim():
        async with db.acquire() as c, c.transaction():
            rows = await n.claim(c, limit=4)
            await asyncio.sleep(0.05)
            return {r.id for r in rows}

    a, b = await asyncio.gather(claim(), claim())
    assert not a & b and len(a | b) == 6
