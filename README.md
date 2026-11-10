# DirectRent Lviv

A Telegram bot that sends long-term rental listings in Lviv, **from owners only**, to people whose saved filter matches.
It reads Lviv rental channels with a Telethon user account, filters out brokers in three stages
(contact reputation → stop-words → Claude Haiku), and delivers a card within about a minute.

Design: `docs/superpowers/specs/2026-11-10-directrent-lviv-design.md`. OLX finding: `docs/spikes/2026-11-olx-phones.md`.

## Run on a VPS

1. `cp .env.example .env` and fill it in:
   - `BOT_TOKEN` from @BotFather
   - `TG_API_ID` and `TG_API_HASH` from my.telegram.org, for a **spare** Telegram account
   - `TG_CHANNELS` (comma-separated channel usernames)
   - `ANTHROPIC_API_KEY`
   - `ADMIN_TG_ID` (your numeric Telegram id)

   Set `POSTGRES_PASSWORD` in your shell or `.env` and use the same value in `DATABASE_URL`.
2. Log the spare account in once. It asks for the phone number and code and writes `data/telethon.session`, which is a secret:
   `docker compose run --rm app uv run --no-sync python -m directrent.login`
3. `docker compose up -d`
4. `docker compose logs -f app` should show the JSON lines `migrations` and `started`.
5. In Telegram, send `/start` to the bot. `/stats` (admin only) shows the last 24 h.

## Check precision (target ≥ 92% owners)

```bash
docker compose exec app uv run --no-sync python scripts/export_sample.py --n 200 --out /app/data/sample.csv
# label each row `owner` or `broker` in data/sample.csv, then:
uv run python scripts/precision.py data/sample.csv
```

## Develop

```bash
docker compose -f docker-compose.test.yml up -d   # test Postgres on :55432
uv run pytest -q
```
