"""Shared data types. Every other module may import from here."""
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Literal

ContactKind = Literal["phone", "tg_user_id", "tg_username", "olx_user_id"]
Pets = Literal["yes", "no", "unknown"]
Stage = Literal["reputation", "rules", "llm"]

DISTRICTS: tuple[str, ...] = (
    "Франківський", "Сихівський", "Галицький", "Личаківський",
    "Залізничний", "Шевченківський", "Приміські",
)


class Verdict(StrEnum):
    PASS = "pass"
    PASS_UNVERIFIED = "pass_unverified"
    REJECT = "reject"


@dataclass(frozen=True)
class Contact:
    kind: ContactKind
    value: str


@dataclass
class RawPost:
    source: str
    source_id: str
    url: str
    text: str
    posted_at: datetime
    channel_title: str
    author_contacts: list[Contact] = field(default_factory=list)
    photo_bytes: bytes | None = None
    photo_url: str | None = None


@dataclass
class Listing:
    source: str
    source_id: str
    url: str
    text: str
    posted_at: datetime
    channel_title: str
    contacts: list[Contact]
    price_uah: int | None
    price_raw: str | None
    rooms: int | None  # 3 means "3+"
    district: str | None
    street: str | None
    pets: Pets
    photo_bytes: bytes | None
    photo_url: str | None
    photo_hash: int | None = None


@dataclass
class Decision:
    verdict: Verdict
    stage: Stage
    reason: str
    confidence: float | None = None


@dataclass
class Filter:
    user_id: int
    districts: list[str]
    price_min: int | None
    price_max: int | None
    rooms: list[int]
    pets_required: bool
