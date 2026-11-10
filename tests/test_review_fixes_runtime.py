"""Regression tests for final-review findings I3, I6, I7 (command in budget step), I8 (retention), I11."""
from datetime import UTC, datetime
from types import SimpleNamespace

from directrent.bot import repo
from directrent.bot.handlers import NO_FILTER, FilterForm
from directrent.notifier import Notifier
from directrent.retention import purge
from directrent.sources.telegram import TelegramSource, is_post
from directrent.store import save_listing
from tests.bot.test_handlers import Harness
from tests.factories import PASS, make_listing
from tests.test_notifier import FakeBot, _drain, _setup, _status, nosleep


# I3
async def test_start_unpauses_user(db):
    async with db.acquire() as c:
        await repo.upsert_user(c, 1, "ann")
        await repo.set_paused(c, 1, True)
    h = Harness(db)
    await h.text("/start")
    async with db.acquire() as c:
        assert await repo.is_paused(c, 1) is False


# I7
async def test_command_during_budget_step_is_not_a_budget(db):
    h = Harness(db)
    await h.text("/start")
    await h.press("d:next")
    await h.text("/my_profile")
    assert "Не зрозумів. Приклад: 10000-18000" not in h.sent_texts()
    assert NO_FILTER in h.sent_texts()


async def test_any_budget_word_moves_on(db):
    h = Harness(db)
    await h.text("/start")
    await h.press("d:next")
    await h.text("будь-який")
    assert await h.state() == FilterForm.rooms.state


# I11
async def test_unexpected_send_error_is_an_attempt_not_a_crash(db):
    async with db.acquire() as c:
        await _setup(c)
    bot = FakeBot(errors=[RuntimeError("socket closed")])
    await _drain(Notifier(bot, db, sleep=nosleep))
    assert await _status(db) == [(1, "pending", 1)]


# I8 (retention part)
async def test_purge_drops_old_photo_bytes(db):
    async with db.acquire() as c:
        oid = await c.fetchval("INSERT INTO objects DEFAULT VALUES RETURNING id")
        lid = await save_listing(c, make_listing(photo_bytes=b"img"), oid, PASS)
        await c.execute("UPDATE listings SET ingested_at = now() - interval '2 days' WHERE id = $1", lid)
        await purge(c)
        assert await c.fetchval("SELECT photo_bytes FROM listings WHERE id = $1", lid) is None


# I6 + service messages
def test_is_post():
    assert is_post(SimpleNamespace(message="Здам", photo=None))
    assert is_post(SimpleNamespace(message="", photo=object()))
    assert not is_post(SimpleNamespace(action=object()))  # MessageService has no .message
    assert not is_post(SimpleNamespace(message="", photo=None))


class FakeClient:
    def __init__(self):
        self.log = []

    async def is_user_authorized(self):
        return True

    async def get_entity(self, name):
        return SimpleNamespace(id=5, username=name, title="T")

    def add_event_handler(self, fn, ev):
        self.log.append("handler")

    def remove_event_handler(self, fn):
        pass

    def iter_messages(self, entity, min_id, limit):
        self.log.append("backfill")

        async def gen():
            if False:
                yield None
        return gen()

    async def run_until_disconnected(self):
        self.log.append("run")


async def test_handlers_registered_before_backfill(db):
    import asyncio
    client = FakeClient()
    await TelegramSource(client, ["lviv_rent"], asyncio.Queue(), db).run()
    assert client.log == ["handler", "handler", "backfill", "run"]
