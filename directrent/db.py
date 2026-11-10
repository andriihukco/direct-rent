"""Postgres pool and a tiny ordered-SQL-file migration runner."""
from pathlib import Path

import asyncpg

MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"


async def create_pool(dsn: str) -> asyncpg.Pool:
    return await asyncpg.create_pool(dsn, min_size=1, max_size=10)


async def migrate(pool: asyncpg.Pool, path: Path = MIGRATIONS) -> list[str]:
    """Apply each *.sql file in name order exactly once. Returns the names applied now."""
    applied: list[str] = []
    async with pool.acquire() as conn:
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations"
            " (name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
        )
        done = {r["name"] for r in await conn.fetch("SELECT name FROM schema_migrations")}
        for f in sorted(path.glob("*.sql")):
            if f.name in done:
                continue
            async with conn.transaction():
                await conn.execute(f.read_text())
                await conn.execute("INSERT INTO schema_migrations (name) VALUES ($1)", f.name)
            applied.append(f.name)
    return applied
