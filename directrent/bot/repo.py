"""User and filter persistence for the bot."""
import asyncpg

from directrent.models import Filter


async def upsert_user(conn: asyncpg.Connection, tg_id: int, username: str | None) -> None:
    await conn.execute(
        """INSERT INTO users (tg_id, username) VALUES ($1, $2)
           ON CONFLICT (tg_id) DO UPDATE SET username = EXCLUDED.username""",
        tg_id, username,
    )


async def get_filter(conn: asyncpg.Connection, user_id: int) -> Filter | None:
    r = await conn.fetchrow(
        "SELECT user_id, districts, price_min, price_max, rooms, pets_required FROM filters WHERE user_id = $1",
        user_id,
    )
    if r is None:
        return None
    return Filter(r["user_id"], list(r["districts"]), r["price_min"], r["price_max"], list(r["rooms"]),
                  r["pets_required"])


async def save_filter(conn: asyncpg.Connection, f: Filter) -> None:
    await conn.execute(
        """INSERT INTO filters (user_id, districts, price_min, price_max, rooms, pets_required)
           VALUES ($1, $2, $3, $4, $5, $6)
           ON CONFLICT (user_id) DO UPDATE SET districts = EXCLUDED.districts, price_min = EXCLUDED.price_min,
               price_max = EXCLUDED.price_max, rooms = EXCLUDED.rooms, pets_required = EXCLUDED.pets_required,
               updated_at = now()""",
        f.user_id, f.districts, f.price_min, f.price_max, f.rooms, f.pets_required,
    )


async def set_paused(conn: asyncpg.Connection, user_id: int, paused: bool) -> None:
    await conn.execute("UPDATE users SET paused = $2 WHERE tg_id = $1", user_id, paused)


async def is_paused(conn: asyncpg.Connection, user_id: int) -> bool:
    return bool(await conn.fetchval("SELECT paused FROM users WHERE tg_id = $1", user_id))


async def delete_user_data(conn: asyncpg.Connection, user_id: int) -> None:
    """Remove the user and everything keyed to them (filters, complaints, deliveries, outbox cascade)."""
    await conn.execute("DELETE FROM users WHERE tg_id = $1", user_id)
