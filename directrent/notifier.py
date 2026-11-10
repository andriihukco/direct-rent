"""Outbox worker: claims pending rows and sends listing cards under Telegram's rate limits."""
import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import asyncpg
from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import BufferedInputFile, LinkPreviewOptions

from directrent.bot.cards import CardData, card_keyboard, render_caption
from directrent.models import Verdict

log = logging.getLogger("directrent.notifier")

SEND_RETRIES = 3
BASE_BACKOFF_S = 5


@dataclass
class OutboxRow:
    id: int
    user_id: int
    listing_id: int
    attempts: int


def _card(r: asyncpg.Record) -> CardData:
    contacts = json.loads(r["raw_contacts"])
    label = f"Telegram: {r['channel_title']}" if r["source"] == "telegram" else r["source"].upper()
    return CardData(
        rooms=r["rooms"], district=r["district"], street=r["street"], price_raw=r["price_raw"],
        price_uah=r["price_uah"], pets=r["pets"], phones=[c["value"] for c in contacts if c["kind"] == "phone"],
        text=r["text"], posted_at=r["posted_at"], source_label=label, url=r["url"], object_id=r["object_id"],
        unverified=r["verdict"] == Verdict.PASS_UNVERIFIED.value,
    )


class Notifier:
    def __init__(self, bot: Bot, pool: asyncpg.Pool, global_rate: int = 25, per_chat_interval: float = 1.0,
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep):
        self.bot, self.pool, self.sleep = bot, pool, sleep
        self.min_gap = 1.0 / global_rate
        self.per_chat_interval = per_chat_interval
        self._last_global = 0.0
        self._last_chat: dict[int, float] = {}
        self._lock = asyncio.Lock()

    async def claim(self, conn: asyncpg.Connection, limit: int = 25) -> list[OutboxRow]:
        rows = await conn.fetch(
            """UPDATE outbox SET status = 'sending', claimed_at = now()
               WHERE id IN (SELECT id FROM outbox WHERE status = 'pending' AND next_try_at <= now()
                            ORDER BY id FOR UPDATE SKIP LOCKED LIMIT $1)
               RETURNING id, user_id, listing_id, attempts""",
            limit,
        )
        return [OutboxRow(**dict(r)) for r in sorted(rows, key=lambda r: r["id"])]

    async def reclaim_stale(self, conn: asyncpg.Connection, older_than: timedelta = timedelta(minutes=2)) -> int:
        status = await conn.execute(
            "UPDATE outbox SET status = 'pending' WHERE status = 'sending' AND claimed_at < now() - $1::interval",
            older_than,
        )
        return int(status.split()[-1])

    async def _throttle(self, chat_id: int) -> None:
        async with self._lock:
            now = time.monotonic()
            wait = max(self._last_global + self.min_gap - now,
                       self._last_chat.get(chat_id, -1e9) + self.per_chat_interval - now, 0)
            if wait:
                await self.sleep(wait)
            self._last_global = self._last_chat[chat_id] = time.monotonic()

    async def _deliver(self, row: OutboxRow, listing: asyncpg.Record) -> None:
        card = _card(listing)
        caption, markup = render_caption(card, datetime.now(UTC)), card_keyboard(card)
        common = {"parse_mode": ParseMode.HTML, "reply_markup": markup}
        if listing["tg_file_id"]:
            await self.bot.send_photo(row.user_id, listing["tg_file_id"], caption=caption, **common)
        elif listing["photo_bytes"]:
            msg = await self.bot.send_photo(
                row.user_id, BufferedInputFile(listing["photo_bytes"], "photo.jpg"), caption=caption, **common
            )
            async with self.pool.acquire() as c:
                await c.execute("UPDATE listings SET tg_file_id = $2, photo_bytes = NULL WHERE id = $1",
                                listing["id"], msg.photo[-1].file_id)
        elif listing["photo_url"]:
            await self.bot.send_photo(row.user_id, listing["photo_url"], caption=caption, **common)
        else:
            await self.bot.send_message(row.user_id, caption, link_preview_options=LinkPreviewOptions(is_disabled=True),
                                        **common)

    async def send_one(self, row: OutboxRow) -> None:
        async with self.pool.acquire() as c:
            listing = await c.fetchrow("SELECT * FROM listings WHERE id = $1", row.listing_id)
        while True:
            await self._throttle(row.user_id)
            try:
                await self._deliver(row, listing)
                break
            except TelegramRetryAfter as e:
                await self.sleep(e.retry_after)
                async with self.pool.acquire() as c:
                    listing = await c.fetchrow("SELECT * FROM listings WHERE id = $1", row.listing_id)
            except TelegramForbiddenError as e:
                async with self.pool.acquire() as c, c.transaction():
                    await c.execute("UPDATE outbox SET status = 'failed', last_error = $2 WHERE id = $1", row.id, str(e))
                    await c.execute("UPDATE users SET paused = true WHERE tg_id = $1", row.user_id)
                log.info(json.dumps({"event": "user_blocked_bot", "user_id": row.user_id}))
                return
            except Exception as e:  # noqa: BLE001 - TelegramAPIError or anything unexpected: count an attempt
                attempts = row.attempts + 1
                status = "failed" if attempts >= SEND_RETRIES else "pending"
                async with self.pool.acquire() as c:
                    await c.execute(
                        """UPDATE outbox SET status = $2, attempts = $3, last_error = $4,
                                  next_try_at = now() + make_interval(secs => $5) WHERE id = $1""",
                        row.id, status, attempts, str(e), float(BASE_BACKOFF_S * 2**attempts),
                    )
                log.warning(json.dumps({"event": "send_error", "outbox_id": row.id, "error": str(e), "status": status}))
                return
        async with self.pool.acquire() as c:
            await c.execute("UPDATE outbox SET status = 'sent', sent_at = now() WHERE id = $1", row.id)

    async def run(self) -> None:
        while True:
            async with self.pool.acquire() as c:
                await self.reclaim_stale(c)
                rows = await self.claim(c)
            if not rows:
                await asyncio.sleep(0.5)
                continue
            for r in await asyncio.gather(*(self.send_one(r) for r in rows), return_exceptions=True):
                if isinstance(r, Exception):
                    log.error(json.dumps({"event": "send_one_crashed", "error": f"{type(r).__name__}: {r}"}))
