"""Read rental posts from public Telegram channels/chats with a Telethon user account."""
import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta

import asyncpg
from telethon import TelegramClient, events, utils
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.types import PeerUser

from directrent.models import Contact, RawPost

log = logging.getLogger("directrent.telegram")

SOURCE = "telegram"
BACKFILL_WINDOW = timedelta(hours=2)
BACKFILL_LIMIT = 300


def _author(msg) -> list[Contact]:
    if not isinstance(msg.from_id, PeerUser):
        return []  # a channel posting as itself has no personal contact
    out = [Contact("tg_user_id", str(msg.from_id.user_id))]
    username = getattr(getattr(msg, "sender", None), "username", None)
    if username:
        out.append(Contact("tg_username", username.lower()))
    return out


def message_to_raw(msg, channel_username: str, channel_title: str, photo_bytes: bytes | None) -> RawPost:
    return RawPost(
        source=SOURCE, source_id=f"{channel_username}:{msg.id}", url=f"https://t.me/{channel_username}/{msg.id}",
        text=msg.message or "", posted_at=msg.date, channel_title=channel_title,
        author_contacts=_author(msg), photo_bytes=photo_bytes,
    )


def album_to_raw(messages: list, channel_username: str, channel_title: str, photo_bytes: bytes | None) -> RawPost:
    first = min(messages, key=lambda m: m.id)
    captioned = next((m for m in sorted(messages, key=lambda m: m.id) if m.message), first)
    raw = message_to_raw(captioned, channel_username, channel_title, photo_bytes)
    raw.source_id, raw.url = f"{channel_username}:{first.id}", f"https://t.me/{channel_username}/{first.id}"
    raw.author_contacts = _author(captioned) or _author(first)
    return raw


async def mark_processed(pool: asyncpg.Pool, raw: RawPost) -> None:
    """Remember the highest processed message id per channel (resume point after restart)."""
    channel, _, msg_id = raw.source_id.rpartition(":")
    await pool.execute(
        """INSERT INTO source_state (source, key, value) VALUES ($1, $2, $3)
           ON CONFLICT (source, key) DO UPDATE
           SET value = GREATEST(source_state.value::bigint, EXCLUDED.value::bigint)::text""",
        SOURCE, channel, msg_id,
    )


def is_post(msg) -> bool:
    """A message with text or a photo. Service messages (joins, pins) have no .message at all."""
    return bool(getattr(msg, "message", None) or getattr(msg, "photo", None))


def chat_key(chat_id: int) -> int:
    """Telethon event chat ids are 'marked' (-100… for channels); entity ids are not."""
    return utils.resolve_id(chat_id)[0]


async def _first_photo(messages: list) -> bytes | None:
    for m in sorted(messages, key=lambda m: m.id):
        if getattr(m, "photo", None):
            return await m.download_media(file=bytes)
    return None


class TelegramSource:
    def __init__(self, client: TelegramClient, channels: list[str], queue: "asyncio.Queue[RawPost]",
                 pool: asyncpg.Pool):
        self.client, self.channels, self.queue, self.pool = client, channels, queue, pool
        self._names: dict[int, tuple[str, str]] = {}  # entity id → (username, title)

    async def _emit(self, messages: list, chat_id: int) -> None:
        username, title = self._names[chat_id]
        photo = await _first_photo(messages)
        raw = (album_to_raw(messages, username, title, photo) if len(messages) > 1
               else message_to_raw(messages[0], username, title, photo))
        await self.queue.put(raw)

    async def _backfill(self, entity, username: str) -> None:
        last = await self.pool.fetchval(
            "SELECT value::bigint FROM source_state WHERE source = $1 AND key = $2", SOURCE, username
        ) or 0
        cutoff = datetime.now(UTC) - BACKFILL_WINDOW
        batch = []
        async for m in self.client.iter_messages(entity, min_id=last, limit=BACKFILL_LIMIT):
            if m.date < cutoff:
                break
            if is_post(m):
                batch.append(m)
        groups: dict[object, list] = {}
        for m in sorted(batch, key=lambda m: m.id):
            groups.setdefault(m.grouped_id or ("single", m.id), []).append(m)
        for messages in groups.values():
            await self._emit(messages, entity.id)
        log.info(json.dumps({"event": "backfill", "channel": username, "posts": len(groups), "from_id": last}))

    async def run(self) -> None:
        if not await self.client.is_user_authorized():
            raise RuntimeError("Telethon session is not authorised; run `python -m directrent.login` first")
        entities = []
        for name in self.channels:
            ent = await self.client.get_entity(name)
            if getattr(ent, "left", False):
                # Telegram sends live updates only to members (the account must join each channel/group).
                await self.client(JoinChannelRequest(ent))
                log.info(json.dumps({"event": "joined", "channel": name}))
            self._names[ent.id] = (getattr(ent, "username", None) or name, getattr(ent, "title", name))
            entities.append(ent)

        async def on_message(event) -> None:
            if event.message.grouped_id is None and is_post(event.message):
                await self._emit([event.message], chat_key(event.chat_id))

        async def on_album(event) -> None:
            await self._emit(list(event.messages), chat_key(event.chat_id))

        # Listen first, then backfill: posts arriving during backfill are caught live, and seen()
        # plus the unique source id absorb any overlap.
        self.client.add_event_handler(on_message, events.NewMessage(chats=entities))
        self.client.add_event_handler(on_album, events.Album(chats=entities))
        try:
            for ent in entities:
                await self._backfill(ent, self._names[ent.id][0])
            await self.client.run_until_disconnected()
        finally:
            self.client.remove_event_handler(on_message)
            self.client.remove_event_handler(on_album)
