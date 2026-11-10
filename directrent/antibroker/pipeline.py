"""RawPost → stored, judged listing (+ outbox rows when it passes)."""
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

import asyncpg

from directrent.antibroker.llm import DailyBudget, LlmClassifier, LlmError, LlmResult
from directrent.antibroker.reputation import check_reputation
from directrent.antibroker.rules import classify_rules
from directrent.dedup import find_or_create_object, photo_hash, seen
from directrent.models import Decision, Listing, RawPost, Verdict
from directrent.normalize import normalize
from directrent.store import save_listing

log = logging.getLogger("directrent.pipeline")

FRESHNESS = timedelta(hours=2)
LLM_ATTEMPTS = 2
LLM_MIN_CONFIDENCE = 0.7

Enqueue = Callable[[asyncpg.Connection, int], Awaitable[int]]


@dataclass
class ProcessResult:
    listing_id: int
    decision: Decision
    queued: int


async def _ask_llm(llm: LlmClassifier, budget: DailyBudget, listing: Listing, now: datetime
                   ) -> tuple[Decision, LlmResult | None]:
    if not budget.take(now):
        return Decision(Verdict.PASS_UNVERIFIED, "llm", "llm:budget"), None
    for _ in range(LLM_ATTEMPTS):
        try:
            r = await llm.classify(listing)
        except LlmError as e:
            log.warning(json.dumps({"event": "llm_error", "source_id": listing.source_id, "error": str(e)}))
            continue
        ok = r.is_owner and r.confidence >= LLM_MIN_CONFIDENCE
        return Decision(Verdict.PASS if ok else Verdict.REJECT, "llm", f"llm:{r.reason}", r.confidence), r
    return Decision(Verdict.PASS_UNVERIFIED, "llm", "llm:error"), None


def _fill_missing(listing: Listing, r: LlmResult) -> None:
    listing.district = listing.district or r.district
    listing.rooms = listing.rooms or r.rooms
    listing.price_uah = listing.price_uah or r.price_uah
    if listing.pets == "unknown" and r.pets:
        listing.pets = r.pets


async def process(pool: asyncpg.Pool, raw: RawPost, llm: LlmClassifier, budget: DailyBudget,
                  usd_rate: float, now: datetime, enqueue: Enqueue | None = None) -> ProcessResult | None:
    if enqueue is None:
        from directrent.matcher import enqueue as default_enqueue
        enqueue = default_enqueue
    if now - raw.posted_at > FRESHNESS:
        return None
    async with pool.acquire() as conn:
        if await seen(conn, raw.source, raw.source_id):
            return None
        listing = normalize(raw, usd_rate)
        if listing.photo_bytes:
            listing.photo_hash = photo_hash(listing.photo_bytes)
        async with conn.transaction():
            object_id = await find_or_create_object(conn, listing)
            decision = await check_reputation(conn, listing.contacts, object_id) or classify_rules(listing.text)
            if decision is None:
                decision, result = await _ask_llm(llm, budget, listing, now)
                if result:
                    _fill_missing(listing, result)
            listing_id = await save_listing(conn, listing, object_id, decision)
            queued = 0 if decision.verdict == Verdict.REJECT else await enqueue(conn, listing_id)
    log.info(json.dumps({"event": "verdict", "source": raw.source, "source_id": raw.source_id,
                         "verdict": decision.verdict.value, "stage": decision.stage, "reason": decision.reason,
                         "queued": queued}, ensure_ascii=False))
    return ProcessResult(listing_id, decision, queued)
