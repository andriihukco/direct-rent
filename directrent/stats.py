"""Numbers for the admin /stats command (last 24 hours)."""
from dataclasses import dataclass
from datetime import datetime

import asyncpg


@dataclass
class Stats:
    per_source: dict[str, int]
    per_stage: dict[str, dict[str, int]]
    llm_share: float
    delivered: int
    latency_p50_s: float | None
    latency_p95_s: float | None


async def collect(conn: asyncpg.Connection, now: datetime) -> Stats:
    since = "$1::timestamptz - interval '24 hours'"
    rows = await conn.fetch(
        f"SELECT source, verdict_stage, verdict, count(*) AS n FROM listings WHERE ingested_at > {since} "
        "GROUP BY source, verdict_stage, verdict", now)
    per_source: dict[str, int] = {}
    per_stage: dict[str, dict[str, int]] = {}
    for r in rows:
        per_source[r["source"]] = per_source.get(r["source"], 0) + r["n"]
        per_stage.setdefault(r["verdict_stage"], {})[r["verdict"]] = r["n"]
    total = sum(per_source.values())
    llm = sum(per_stage.get("llm", {}).values())
    lat = await conn.fetchrow(
        f"""SELECT count(*) AS n,
                   percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM o.sent_at - l.posted_at)) AS p50,
                   percentile_cont(0.95) WITHIN GROUP (ORDER BY extract(epoch FROM o.sent_at - l.posted_at)) AS p95
            FROM outbox o JOIN listings l ON l.id = o.listing_id
            WHERE o.status = 'sent' AND o.sent_at > {since}""", now)
    return Stats(per_source, per_stage, llm / total if total else 0.0, lat["n"],
                 lat["p50"], lat["p95"])


def _sec(v: float | None) -> str:
    return "—" if v is None else f"{v:.0f} с"


def format_stats(s: Stats, health: dict) -> str:
    sources = ", ".join(f"{k} {v}" for k, v in sorted(s.per_source.items())) or "—"
    stages = "; ".join(f"{st}: " + ", ".join(f"{v} {n}" for v, n in sorted(vs.items()))
                       for st, vs in sorted(s.per_stage.items())) or "—"
    tasks = "; ".join(f"{name} перезапусків {h['restarts']}" + (f" ({h['last_error']})" if h["last_error"] else "")
                      for name, h in sorted(health.items())) or "—"
    return (f"📊 За 24 год\nДжерела: {sources}\nЕтапи: {stages}\nЧастка LLM: {s.llm_share:.0%}\n"
            f"Доставлено: {s.delivered}\nЗатримка p50 / p95: {_sec(s.latency_p50_s)} / {_sec(s.latency_p95_s)}\n"
            f"Задачі: {tasks}")
