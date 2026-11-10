from datetime import UTC, datetime, timedelta

from directrent.models import Decision, Verdict
from directrent.stats import collect, format_stats
from directrent.store import save_listing
from tests.factories import make_listing

NOW = datetime.now(UTC)


async def test_collect(db):
    async with db.acquire() as c:
        await c.execute("INSERT INTO users (tg_id) VALUES (1)")
        oid = await c.fetchval("INSERT INTO objects DEFAULT VALUES RETURNING id")
        ids = []
        for i in range(10):
            d = Decision(Verdict.PASS, "llm", "llm:x") if i < 2 else Decision(Verdict.REJECT, "rules", "stopword:x")
            ids.append(await save_listing(c, make_listing(posted_at=NOW - timedelta(minutes=5)), oid, d))
        for lid, secs in zip(ids, (10, 20, 30, 100)):
            await c.execute(
                """INSERT INTO outbox (user_id, listing_id, status, sent_at)
                   SELECT 1, $1, 'sent', posted_at + make_interval(secs => $2) FROM listings WHERE id = $1""",
                lid, float(secs))
        old = await save_listing(c, make_listing(), oid, Decision(Verdict.PASS, "rules", "owner:x"))
        await c.execute("UPDATE listings SET ingested_at = now() - interval '2 days' WHERE id = $1", old)
        s = await collect(c, NOW)
    assert s.per_source == {"telegram": 10}
    assert s.per_stage == {"llm": {"pass": 2}, "rules": {"reject": 8}}
    assert s.llm_share == 0.2 and s.delivered == 4 and s.latency_p50_s == 25
    text = format_stats(s, {"telegram": {"restarts": 1, "last_error": "x"}})
    assert "20%" in text and "25" in text and "telegram" in text


async def test_collect_empty(db):
    async with db.acquire() as c:
        s = await collect(c, NOW)
    assert s.llm_share == 0 and s.latency_p50_s is None
    assert "—" in format_stats(s, {})
