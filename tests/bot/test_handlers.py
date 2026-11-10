from datetime import datetime

from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import SendMessage
from aiogram.types import Chat, Message

from directrent.bot import repo
from directrent.bot.handlers import FilterForm, build_router
from directrent.models import Filter

USER = {"id": 1, "is_bot": False, "first_name": "A", "username": "ann"}
CHAT = {"id": 1, "type": "private"}


class MockSession(BaseSession):
    def __init__(self):
        super().__init__()
        self.requests = []

    async def make_request(self, bot, method, timeout=None):
        self.requests.append(method)
        if method.__returning__ is bool:
            return True
        return Message(message_id=99, date=datetime.now(), chat=Chat(id=1, type="private"), text="ok")

    async def stream_content(self, *a, **kw):  # pragma: no cover
        yield b""

    async def close(self):
        pass


class Harness:
    def __init__(self, pool):
        self.session = MockSession()
        self.bot = Bot("42:TEST", session=self.session)
        self.dp = Dispatcher(storage=MemoryStorage())
        self.dp.include_router(build_router(pool))
        self.n = 0

    async def text(self, text):
        self.n += 1
        await self.dp.feed_raw_update(self.bot, {"update_id": self.n, "message": {
            "message_id": self.n, "date": 0, "chat": CHAT, "from": USER, "text": text}})

    async def press(self, data):
        self.n += 1
        await self.dp.feed_raw_update(self.bot, {"update_id": self.n, "callback_query": {
            "id": str(self.n), "from": USER, "chat_instance": "ci", "data": data,
            "message": {"message_id": 1, "date": 0, "chat": CHAT, "text": "x"}}})

    async def state(self):
        return await self.dp.storage.get_state(StorageKey(bot_id=42, chat_id=1, user_id=1))

    def sent_texts(self):
        return [r.text for r in self.session.requests if isinstance(r, SendMessage)]


async def test_full_filter_flow(db):
    h = Harness(db)
    await h.text("/start")
    assert await h.state() == FilterForm.districts.state
    await h.press("d:1")  # Сихівський
    await h.press("d:next")
    assert await h.state() == FilterForm.budget.state
    await h.text("дешево")
    assert await h.state() == FilterForm.budget.state
    assert "Не зрозумів. Приклад: 10000-18000" in h.sent_texts()
    await h.text("10000-18000")
    await h.press("r:2")
    await h.press("r:next")
    await h.press("p:save")
    assert await h.state() is None
    async with db.acquire() as c:
        assert await repo.get_filter(c, 1) == Filter(1, ["Сихівський"], 10000, 18000, [2], False)


async def test_any_district_clears_selection(db):
    h = Harness(db)
    await h.text("/start")
    await h.press("d:1")
    await h.press("d:any")
    await h.press("d:next")
    await h.text("-18000")
    await h.press("r:next")
    await h.press("p:toggle")
    await h.press("p:save")
    async with db.acquire() as c:
        assert await repo.get_filter(c, 1) == Filter(1, [], None, 18000, [], True)


async def test_broker_button_records_complaint(db):
    h = Harness(db)
    async with db.acquire() as c:
        await repo.upsert_user(c, 1, "ann")
        oid = await c.fetchval("INSERT INTO objects DEFAULT VALUES RETURNING id")
    await h.press(f"broker:{oid}")
    assert await db.fetchval("SELECT count(*) FROM complaints WHERE user_id = 1 AND object_id = $1", oid) == 1


async def test_profile_without_filter(db):
    h = Harness(db)
    await h.text("/my_profile")
    assert any("/filters" in t for t in h.sent_texts())


async def test_pause_and_delete_from_profile(db):
    h = Harness(db)
    async with db.acquire() as c:
        await repo.upsert_user(c, 1, "ann")
        await repo.save_filter(c, Filter(1, [], None, None, [], False))
    await h.press("prof:pause")
    async with db.acquire() as c:
        assert await repo.is_paused(c, 1) is True
    await h.press("prof:delete")
    async with db.acquire() as c:
        assert await repo.get_filter(c, 1) is not None  # needs confirmation
    await h.press("prof:delete_yes")
    async with db.acquire() as c:
        assert await repo.get_filter(c, 1) is None
