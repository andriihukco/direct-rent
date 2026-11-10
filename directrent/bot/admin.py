"""Admin-only /stats. Anyone else gets no reply."""
import asyncpg
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message
from datetime import UTC, datetime

from directrent.stats import collect, format_stats
from directrent.supervisor import SOURCE_HEALTH


def build_admin_router(pool: asyncpg.Pool, admin_id: int) -> Router:
    router = Router(name="admin")

    @router.message(Command("stats"), F.from_user.id == admin_id)
    async def on_stats(message: Message) -> None:
        async with pool.acquire() as c:
            s = await collect(c, datetime.now(UTC))
        await message.answer(format_stats(s, SOURCE_HEALTH))

    return router
