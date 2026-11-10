"""Regression tests for final-review findings C1, I1, I2, I4, I5, I8."""
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from directrent.antibroker.llm import DailyBudget, HaikuClassifier, LlmResult, make_llm_client
from directrent.antibroker.pipeline import process
from directrent.antibroker.reputation import record_complaint
from directrent.models import Contact, RawPost, Verdict
from tests.factories import make_listing

NOW = datetime.now(UTC)
OWNER = LlmResult(True, 0.9, "owner", None, None, None, None)


class FakeLlm:
    def __init__(self, result=OWNER, pool=None):
        self.result, self.pool, self.calls, self.open_txns = result, pool, 0, []

    async def classify(self, listing):
        self.calls += 1
        if self.pool:
            self.open_txns.append(await self.pool.fetchval(
                "SELECT count(*) FROM pg_stat_activity WHERE state = 'idle in transaction'"))
        return self.result


def post(text, sid, author=(), photo=None):
    return RawPost("telegram", sid, f"https://t.me/{sid.replace(':', '/')}", text, NOW - timedelta(seconds=30),
                   "Ch", list(author), photo_bytes=photo)


async def _user(db):
    await db.execute("INSERT INTO users (tg_id) VALUES (1); INSERT INTO filters (user_id) VALUES (1)")


async def run(db, p, llm=None):
    return await process(db, p, llm or FakeLlm(), DailyBudget(100), 41.5, datetime.now(UTC))


# C1
async def test_signed_channel_does_not_reject_or_merge(db):
    await _user(db)
    verdicts, objects = [], set()
    for i in range(5):
        text = f"Здам {1 + i % 2}к квартиру, власник, {15000 + 500 * i} грн, 06700000{10 + i}\nПідписуйтесь @lviv_rent_ads"
        r = await run(db, post(text, f"lviv_rent:{i}"))
        verdicts.append(r.decision.verdict)
        objects.add(await db.fetchval("SELECT object_id FROM listings WHERE id = $1", r.listing_id))
    assert verdicts == [Verdict.PASS] * 5 and len(objects) == 5
    assert await db.fetchval("SELECT count(*) FROM outbox") == 5


async def test_complaints_do_not_blacklist_shared_footer(db):
    await _user(db)
    await db.execute("INSERT INTO users (tg_id) VALUES (2)")
    lid = None
    for i in range(4):
        r = await run(db, post(f"Здам 2к, власник, {15000 + 1000 * i} грн, 06700000{20 + i}\n@lviv_rent_ads", f"c:{i}"))
        lid = r.listing_id
    oid = await db.fetchval("SELECT object_id FROM listings WHERE id = $1", lid)
    async with db.acquire() as c:
        await record_complaint(c, 1, oid)
        assert await record_complaint(c, 2, oid) is True
    rows = {r["value"]: r["blacklisted"] for r in await db.fetch("SELECT value, blacklisted FROM contacts")}
    assert rows["lviv_rent_ads"] is False and rows["+380670000023"] is True


# I1
async def test_cross_post_without_rooms_one_card_and_no_self_flag(db):
    await _user(db)
    text = "Здається квартира на Сихові від власника, 12000 грн, 0671234567"
    results = [await run(db, post(text, f"ch{i}:1")) for i in range(3)]
    assert [r.decision.verdict for r in results] == [Verdict.PASS] * 3
    assert [r.queued for r in results] == [1, 0, 0]


# I2
async def test_chat_chatter_does_not_count_against_owner(db):
    await _user(db)
    me = [Contact("tg_user_id", "42")]
    r1 = await run(db, post("Здам 2к квартиру, власник, 15000 грн", "chat:1", me))
    r2 = await run(db, post("", "chat:2", me, photo=b"x"))
    llm = FakeLlm()
    r3 = await run(db, post("Так, ще актуально", "chat:3", me), llm)
    r4 = await run(db, post("Здам 1к квартиру, власник, 11000 грн", "chat:4", me))
    assert r1.decision.verdict == Verdict.PASS
    assert (r2.decision.verdict, r2.decision.reason) == (Verdict.REJECT, "empty")
    assert (r3.decision.verdict, r3.decision.reason, llm.calls) == (Verdict.REJECT, "not_listing", 0)
    assert r4.decision.verdict == Verdict.PASS
    assert await db.fetchval("SELECT count(*) FROM listings WHERE object_id IS NULL") == 2


# I4
async def test_llm_runs_outside_transaction(db):
    llm = FakeLlm(pool=db)
    await run(db, post("Здам 2к квартиру, 15000 грн", "x:1"), llm)
    assert llm.calls == 1 and llm.open_txns == [0]


def test_llm_client_has_short_timeout():
    c = make_llm_client("test-key")
    assert c.timeout == 15.0 and c.max_retries == 1


# I5
async def test_llm_max_tokens_leaves_room_for_thinking():
    class M:
        async def create(self, **kw):
            self.kw = kw
            return SimpleNamespace(content=[SimpleNamespace(type="tool_use", name="report_verdict", input={
                "is_owner": True, "confidence": 1, "reason": "r", "district": None, "rooms": None,
                "price_uah": None, "pets": None})], stop_reason="tool_use")
    m = M()
    await HaikuClassifier(SimpleNamespace(messages=m)).classify(make_listing())
    assert m.kw["max_tokens"] >= 1024


# I8
async def test_photo_bytes_kept_only_when_queued(db):
    r_reject = await run(db, post("Комісія 50%, 2к, 15000 грн", "p:1", photo=b"img1"))
    r_nobody = await run(db, post("Здам 2к, власник, 15000 грн, 0671110001", "p:2", photo=b"img2"))
    await _user(db)
    r_sent = await run(db, post("Здам 1к, власник, 9000 грн, 0671110002", "p:3", photo=b"img3"))
    got = {r["id"]: r["photo_bytes"] for r in await db.fetch("SELECT id, photo_bytes FROM listings")}
    assert got[r_reject.listing_id] is None and got[r_nobody.listing_id] is None
    assert got[r_sent.listing_id] == b"img3"
