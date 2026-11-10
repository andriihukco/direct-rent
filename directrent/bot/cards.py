"""A listing rendered as a Telegram photo caption (HTML parse mode) plus buttons."""
import re
from dataclasses import dataclass
from datetime import datetime
from html import escape

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from directrent.models import Pets

CAPTION_LIMIT = 1024
BROKER_CB_PREFIX = "broker:"
UNKNOWN = "не вказано"
_PETS = {"yes": "дозволено", "no": "заборонено", "unknown": UNKNOWN}
_FOREIGN = re.compile(r"\$|usd|дол", re.IGNORECASE)


@dataclass
class CardData:
    rooms: int | None
    district: str | None
    street: str | None
    price_raw: str | None
    price_uah: int | None
    pets: Pets
    phones: list[str]
    text: str
    posted_at: datetime
    source_label: str
    url: str
    object_id: int
    unverified: bool


def _money(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def _rooms(rooms: int | None) -> str:
    if rooms is None:
        return "🏠 Квартира"
    return "🏠 3+ кімнатна квартира" if rooms >= 3 else f"🏠 {rooms}-кімнатна квартира"


def _place(district: str | None, street: str | None) -> str:
    line = f"📍 {escape(district) if district else UNKNOWN}"
    return f"{line} (вул. {escape(street)})" if street else line


def _price(raw: str | None, uah: int | None) -> str:
    if uah is None:
        return f"💰 {UNKNOWN}"
    if raw and _FOREIGN.search(raw):
        return f"💰 {escape(raw)} (≈{_money(uah)} грн) / міс"
    return f"💰 {_money(uah)} грн / міс"


def _age(posted_at: datetime, now: datetime) -> str:
    minutes = int((now - posted_at).total_seconds() // 60)
    if minutes < 1:
        return "щойно"
    if minutes < 60:
        return f"{minutes} хв тому"
    return f"{minutes // 60} год тому"


def _fit(text: str, room: int) -> str:
    """Escaped text no longer than `room` characters, cut with an ellipsis when needed."""
    text = text.strip()
    if len(escape(text)) <= room:
        return escape(text)
    cut = text[: max(room - 1, 0)]
    while cut and len(escape(cut)) + 1 > room:
        cut = cut[:-10]
    return escape(cut.rstrip()) + "…"


def render_caption(card: CardData, now: datetime) -> str:
    head = ["⚠️ не перевірено"] if card.unverified else []
    head += [_rooms(card.rooms), _place(card.district, card.street), _price(card.price_raw, card.price_uah),
             f"🐾 Тварини: {_PETS[card.pets]}"]
    if card.phones:
        head.append("📞 " + ", ".join(card.phones))
    tail = f"⏰ {_age(card.posted_at, now)} · {escape(card.source_label)}"
    fixed = len("\n".join(head)) + len("\n📝 \n") + len(tail)
    return "\n".join([*head, "📝 " + _fit(card.text, CAPTION_LIMIT - fixed), tail])


def card_keyboard(card: CardData) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🔗 Оригінал", url=card.url),
        InlineKeyboardButton(text="🚩 Це рієлтор", callback_data=f"{BROKER_CB_PREFIX}{card.object_id}"),
    ]])
