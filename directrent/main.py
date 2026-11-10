"""Entry point: one process running the Telegram reader, pipeline, notifier and bot."""
import asyncio
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import anthropic
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from telethon import TelegramClient

from directrent.antibroker.llm import DailyBudget, HaikuClassifier
from directrent.antibroker.pipeline import process
from directrent.bot.admin import build_admin_router
from directrent.bot.handlers import build_router
from directrent.config import Settings, get_settings
from directrent.db import create_pool, migrate
from directrent.logs import setup_logging
from directrent.models import RawPost
from directrent.notifier import Notifier
from directrent.retention import purge
from directrent.sources.telegram import TelegramSource, mark_processed
from directrent.supervisor import supervise

log = logging.getLogger("directrent.main")


def make_telethon(s: Settings) -> TelegramClient:
    Path(s.tg_session_path).parent.mkdir(parents=True, exist_ok=True)
    # Sleep through FloodWait of any length instead of raising (spec §15).
    return TelegramClient(s.tg_session_path, s.tg_api_id, s.tg_api_hash.get_secret_value(),
                          flood_sleep_threshold=24 * 3600)


async def main() -> None:
    setup_logging()
    s = get_settings()
    pool = await create_pool(s.database_url)
    log.info(json.dumps({"event": "migrations", "applied": await migrate(pool)}))

    bot = Bot(s.bot_token.get_secret_value())
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(build_admin_router(pool, s.admin_tg_id))
    dp.include_router(build_router(pool))

    client = make_telethon(s)
    queue: asyncio.Queue[RawPost] = asyncio.Queue(maxsize=1000)
    llm = HaikuClassifier(anthropic.AsyncAnthropic(api_key=s.anthropic_api_key.get_secret_value()))
    budget = DailyBudget(s.llm_daily_max_calls)
    notifier = Notifier(bot, pool)

    async def telegram() -> None:
        if not client.is_connected():
            await client.connect()
        await TelegramSource(client, s.tg_channels, queue, pool).run()

    async def pipeline() -> None:
        while True:
            raw = await queue.get()
            try:
                await process(pool, raw, llm, budget, s.usd_uah_rate, datetime.now(UTC))
                await mark_processed(pool, raw)
            except Exception:  # noqa: BLE001 - one bad post must not stop the worker
                log.exception(json.dumps({"event": "process_failed", "source_id": raw.source_id}))

    async def retention() -> None:
        while True:
            async with pool.acquire() as c:
                log.info(json.dumps({"event": "retention", "listings_deleted": await purge(c)}))
            await asyncio.sleep(24 * 3600)

    async def polling() -> None:
        await dp.start_polling(bot, handle_signals=False)

    tasks = {"telegram": telegram, "pipeline": pipeline, "notifier": notifier.run, "bot": polling,
             "retention": retention}
    log.info(json.dumps({"event": "started", "tasks": list(tasks), "channels": s.tg_channels}))
    try:
        await asyncio.gather(*(supervise(name, fn) for name, fn in tasks.items()))
    finally:
        await client.disconnect()
        await bot.session.close()
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
