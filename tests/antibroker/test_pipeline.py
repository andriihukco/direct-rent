from datetime import UTC, datetime, timedelta

from directrent.antibroker.llm import DailyBudget, LlmError, LlmResult
from directrent.antibroker.pipeline import process
from directrent.models import RawPost, Verdict

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)


class FakeLlm:
    def __init__(self, result=None, fail=0):
        self.result, self.fail, self.calls = result, fail, 0

    async def classify(self, listing):
        self.calls += 1
        if self.calls <= self.fail:
            raise LlmError("boom")
        return self.result


class Enqueue:
    def __init__(self):
        self.ids = []

    async def __call__(self, conn, listing_id):
        self.ids.append(listing_id)
        return 1


def raw(text, n=1, age=timedelta(minutes=1)):
    return RawPost("telegram", f"ch:{n}", f"https://t.me/ch/{n}", text, NOW - age, "Ch", [])


OWNER = LlmResult(True, 0.9, "owner", "Сихівський", None, None, None)


async def _run(db, post, llm=None, budget=None, enq=None):
    return await process(db, post, llm or FakeLlm(OWNER), budget or DailyBudget(100), 41.5, NOW,
                         enqueue=enq or Enqueue())


async def test_rules_pass_skips_llm(db):
    llm = FakeLlm(OWNER)
    r = await _run(db, raw("Здам 2к, власник, 15000 грн"), llm)
    assert r.decision.verdict == Verdict.PASS and r.decision.stage == "rules" and llm.calls == 0


async def test_ambiguous_goes_to_llm_and_fills_district(db):
    r = await _run(db, raw("Здам 2к квартиру, 15000 грн"))
    assert r.decision.verdict == Verdict.PASS and r.decision.stage == "llm"
    assert await db.fetchval("SELECT district FROM listings WHERE id = $1", r.listing_id) == "Сихівський"


async def test_llm_does_not_overwrite_regex_fields(db):
    r = await _run(db, raw("Здам 2к квартиру на Левандівці, 15000 грн"))
    assert await db.fetchval("SELECT district FROM listings WHERE id = $1", r.listing_id) == "Залізничний"


async def test_low_confidence_rejects(db):
    r = await _run(db, raw("Здам 2к квартиру"), FakeLlm(LlmResult(True, 0.5, "unsure", None, None, None, None)))
    assert r.decision.verdict == Verdict.REJECT and r.decision.stage == "llm"


async def test_llm_errors_twice_pass_unverified(db):
    llm = FakeLlm(OWNER, fail=2)
    r = await _run(db, raw("Здам 2к квартиру"), llm)
    assert (r.decision.verdict, r.decision.reason, llm.calls) == (Verdict.PASS_UNVERIFIED, "llm:error", 2)


async def test_llm_error_once_then_success(db):
    llm = FakeLlm(OWNER, fail=1)
    r = await _run(db, raw("Здам 2к квартиру"), llm)
    assert r.decision.verdict == Verdict.PASS and llm.calls == 2


async def test_budget_exhausted_pass_unverified(db):
    budget = DailyBudget(1)
    await _run(db, raw("Здам 2к квартиру", 1), budget=budget)
    r = await _run(db, raw("Здам 1к квартиру", 2), budget=budget)
    assert (r.decision.verdict, r.decision.reason) == (Verdict.PASS_UNVERIFIED, "llm:budget")


def test_budget_resets_after_kyiv_midnight():
    b = DailyBudget(1)
    assert b.take(datetime(2026, 11, 10, 21, 0, tzinfo=UTC))  # 23:00 Kyiv
    assert not b.take(datetime(2026, 11, 10, 21, 30, tzinfo=UTC))
    assert b.take(datetime(2026, 11, 10, 22, 30, tzinfo=UTC))  # 00:30 Kyiv next day


async def test_stale_post_ignored(db):
    assert await _run(db, raw("власник", age=timedelta(hours=3))) is None
    assert await db.fetchval("SELECT count(*) FROM listings") == 0


async def test_duplicate_post_ignored(db):
    await _run(db, raw("власник, 2к"))
    assert await _run(db, raw("власник, 2к")) is None


async def test_reject_never_enqueues(db):
    enq = Enqueue()
    r = await _run(db, raw("Комісія 50%, 2к"), enq=enq)
    assert r.decision.verdict == Verdict.REJECT and enq.ids == [] and r.queued == 0


async def test_pass_enqueues(db):
    enq = Enqueue()
    r = await _run(db, raw("власник, 2к"), enq=enq)
    assert enq.ids == [r.listing_id] and r.queued == 1


async def test_emoji_only_rejected_without_llm(db):
    llm = FakeLlm(OWNER)
    r = await _run(db, raw("👍🔥"), llm)
    assert (r.decision.verdict, r.decision.reason, llm.calls) == (Verdict.REJECT, "empty", 0)
