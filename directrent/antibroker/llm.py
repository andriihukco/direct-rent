"""Stage 3: ask Claude Haiku whether an ambiguous listing comes from the owner."""
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Literal, Protocol
from zoneinfo import ZoneInfo

import anthropic

from directrent.models import DISTRICTS, Listing

MODEL = "claude-haiku-5-5"
TOOL_NAME = "report_verdict"

SYSTEM = """You review long-term apartment rental listings from Lviv, Ukraine. Texts are in Ukrainian or Russian.
Decide whether the listing was posted by the owner of the flat (no agent, no commission) or by a broker/agency.
Broker signs: commission or "послуги" in %, agency wording, many flats offered, scripted marketing text,
"співпраця з агентствами", photos/descriptions of the "our company offers" kind.
Owner signs: first-person wording about their own flat, "власник", "без комісії", plain personal tone.
Brokers often pretend to be owners; weigh the whole text, not one phrase.
Also extract fields the text states: district (one of the given Lviv districts), rooms (1, 2, or 3 for 3+),
monthly price in UAH, and whether pets are allowed. Use null when the text does not say.
Always answer by calling the report_verdict tool."""

TOOL: dict[str, Any] = {
    "name": TOOL_NAME,
    "description": "Report whether the listing is from the owner, plus extracted fields.",
    "input_schema": {
        "type": "object",
        "properties": {
            "is_owner": {"type": "boolean"},
            "confidence": {"type": "number", "description": "0..1"},
            "reason": {"type": "string", "description": "One short sentence."},
            "district": {"anyOf": [{"type": "string", "enum": list(DISTRICTS)}, {"type": "null"}]},
            "rooms": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
            "price_uah": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
            "pets": {"anyOf": [{"type": "string", "enum": ["yes", "no"]}, {"type": "null"}]},
        },
        "required": ["is_owner", "confidence", "reason", "district", "rooms", "price_uah", "pets"],
        "additionalProperties": False,
    },
}


@dataclass
class LlmResult:
    is_owner: bool
    confidence: float
    reason: str
    district: str | None
    rooms: int | None
    price_uah: int | None
    pets: Literal["yes", "no"] | None


class LlmError(Exception):
    pass


class LlmClassifier(Protocol):
    async def classify(self, listing: Listing) -> LlmResult: ...


def _prompt(listing: Listing) -> str:
    known = {"district": listing.district, "rooms": listing.rooms, "price_uah": listing.price_uah, "pets": listing.pets}
    return (
        f"Lviv districts: {', '.join(DISTRICTS)}\n"
        f"Fields already extracted by regex (may be null): {known}\n\n"
        f"<listing>\n{listing.text[:4000]}\n</listing>"
    )


def _parse(data: Any) -> LlmResult:
    try:
        district = data["district"] if data["district"] in DISTRICTS else None
        rooms = data["rooms"]
        rooms = min(max(int(rooms), 1), 3) if isinstance(rooms, int) and rooms > 0 else None
        price = data["price_uah"] if isinstance(data["price_uah"], int) and data["price_uah"] > 0 else None
        pets = data["pets"] if data["pets"] in ("yes", "no") else None
        confidence = float(data["confidence"])
        if not isinstance(data["is_owner"], bool) or not 0 <= confidence <= 1:
            raise ValueError("bad is_owner/confidence")
        return LlmResult(data["is_owner"], confidence, str(data["reason"])[:200], district, rooms, price, pets)
    except (KeyError, TypeError, ValueError) as e:
        raise LlmError(f"invalid tool input: {e}") from e


class HaikuClassifier:
    def __init__(self, client: anthropic.AsyncAnthropic, model: str = MODEL):
        self.client, self.model = client, model

    async def classify(self, listing: Listing) -> LlmResult:
        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=300,
                system=SYSTEM,
                tools=[TOOL],
                tool_choice={"type": "tool", "name": TOOL_NAME},
                output_config={"effort": "low"},
                messages=[{"role": "user", "content": _prompt(listing)}],
            )
        except anthropic.APIError as e:
            raise LlmError(f"api: {type(e).__name__}") from e
        block = next((b for b in response.content if b.type == "tool_use" and b.name == TOOL_NAME), None)
        if block is None:
            raise LlmError(f"no tool call (stop_reason={getattr(response, 'stop_reason', None)})")
        return _parse(block.input)


class DailyBudget:
    """In-memory cap on LLM calls per local day. A restart resets it (accepted)."""

    def __init__(self, max_calls: int, tz: str = "Europe/Kyiv"):
        self.max_calls, self.tz = max_calls, ZoneInfo(tz)
        self._day: date | None = None
        self._used = 0

    def take(self, now: datetime) -> bool:
        day = now.astimezone(self.tz).date()
        if day != self._day:
            self._day, self._used = day, 0
        if self._used >= self.max_calls:
            return False
        self._used += 1
        return True
