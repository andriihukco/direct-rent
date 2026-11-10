from aiogram.methods import SendMessage

from directrent.bot.admin import build_admin_router
from tests.bot.test_handlers import Harness


async def _stats_replies(db, admin_id):
    h = Harness(db)
    h.dp.include_router(build_admin_router(db, admin_id))
    await h.text("/stats")
    return [r.text for r in h.session.requests if isinstance(r, SendMessage)]


async def test_admin_gets_stats(db):
    replies = await _stats_replies(db, admin_id=1)
    assert len(replies) == 1 and replies[0].startswith("📊 За 24 год")


async def test_non_admin_gets_nothing(db):
    assert await _stats_replies(db, admin_id=777) == []
