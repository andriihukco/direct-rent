# DirectRent Lviv: design spec

Date: 2026-11-10. Status: approved in chat, waiting for review of this written spec.
Source: the Ukrainian PRD the user pasted, plus the decisions made in chat (listed in §2).

## 1. Goal

A Telegram bot that sends long-term rental listings in Lviv, **from owners only**, to people whose saved filter matches them, within a minute of the listing appearing.

Success, measured at the end of phase 1:
- **Latency:** for Telegram-channel listings, the time from the post to the card in the user's chat has a p50 under 30 s and a p95 under 60 s.
- **Precision:** at least 92% of delivered listings are from owners, measured on a hand-labelled sample of 200 delivered listings.
- **LLM share:** at most 20% of incoming listings reach the LLM stage.

## 2. Decisions taken

| Topic | Decision |
|---|---|
| Scope | Personal tool for the user and friends, up to about 100 users. No payments. |
| Sources | Phase 1: Telegram channels. Phase 2: OLX. Phase 3: DOM.RIA through its official API. LUN is dropped. |
| Telegram reader | Telethon on a separate account with its own SIM, never the user's main account. |
| LLM | Claude Haiku 5.5 (`claude-haiku-5-5`), only for listings that stages 1–2 leave ambiguous. |
| UI language | Ukrainian only. No language picker. |
| Hosting | Small VPS with docker-compose: one app container and one Postgres container. |
| Architecture | One async Python process with strict module boundaries. No FastAPI, no Redis. |

Changes from the PRD, and why:
- **Phone button removed.** Telegram inline buttons accept only `http(s)://` and `tg://` URLs, so `tel:` is rejected. The phone number goes in the caption instead, where Telegram makes it tappable.
- **One photo per card, not an album.** `sendMediaGroup` cannot carry `reply_markup`. A single photo with a caption can carry the buttons.
- **The reputation rule counts objects, not listings.** An owner who cross-posts one flat to 3 channels must not be flagged.
- **Reputation uses any contact, not only phones.** Telegram posts often give only `@username`, so the same counting applies to phone numbers, Telegram user ids and usernames, and OLX user ids.

## 3. Stack

Python 3.12, `uv` for dependencies, aiogram 3, Telethon, httpx, asyncpg with plain SQL migrations, anthropic SDK, Pillow and imagehash, pytest.

## 4. Module layout

```
directrent/
  config.py          settings read from env (pydantic-settings)
  db.py              asyncpg pool + migration runner (migrations/*.sql, applied in order)
  models.py          Listing, Verdict, Filter dataclasses
  sources/
    telegram.py      Telethon listener → raw posts
    olx.py           phase 2
    domria.py        phase 3
  normalize/
    phones.py        extract + normalise to +380XXXXXXXXX
    fields.py        price, currency, rooms, district, street, pets
    districts.py     district names + neighbourhood keyword map
  dedup.py           source-id dedup + object fingerprint
  antibroker/
    reputation.py    stage 1
    rules.py         stage 2 (stop-words, owner markers)
    llm.py           stage 3 (Haiku)
    pipeline.py      runs the stages, returns a Verdict
  matcher.py         listing → matching filter ids (SQL)
  notifier.py        outbox worker, rate limiting, retries
  bot/
    handlers.py      /start, /filters, /my_profile, callbacks
    keyboards.py
    cards.py         renders a listing as caption + buttons
    admin.py         /stats for the admin
  main.py            starts the sources, pipeline, notifier and bot in one event loop
  login.py           one-off interactive Telethon login
```

Each module exposes a small interface and imports only `models`, `db` and `config`, never another module's internals. Source files stay under about 400 lines.

## 5. Data flow

```
source → raw post → normalize → dedup ─(already seen)→ drop
                                   │
                                   ▼
                       antibroker (stages 1 → 2 → 3)
                                   │
                         reject ◄──┴──► pass / pass_unverified
                                          │
                                          ▼
                              matcher → outbox rows → notifier → card
```

- **Freshness.** Posts older than 2 h are ignored. On restart, the Telegram source resumes from the last message id stored per channel and does not backfill further.
- **One process.** Every stage runs in the same event loop. Sources push raw posts onto an `asyncio.Queue` that the pipeline worker reads. Outbox rows are in Postgres, so a crash loses nothing that has already been matched.

## 6. Normalisation

- **Phones.** Matches `+380…`, `380…`, `0XX…` with spaces, dashes or brackets in between, and normalises to `+380XXXXXXXXX`.
- **Contacts.** Each listing carries 0..n contacts of the kinds `phone`, `tg_user_id`, `tg_username` and `olx_user_id`. For a channel post, the sender's id counts only when the post was made by a person, not by the channel itself.
- **Price.** Parsed in UAH or USD. USD is converted with `USD_UAH_RATE` from env for matching, and the card shows the original.
- **Rooms** are 1, 2, 3 or more. **Pets** are yes, no or unknown, from phrases such as "з тваринами", "без тварин", "pet friendly".
- **District.** One of Франківський, Сихівський, Галицький, Личаківський, Залізничний, Шевченківський, Приміські. It comes from the district names plus a neighbourhood map (Сихів → Сихівський, Левандівка → Залізничний, Брюховичі → Приміські, and so on).
- **Missing fields.** Any field we cannot extract is set to `unknown`. Stage 3 fills it in when that listing reaches the LLM.

## 7. Deduplication

1. `(source, source_id)` is unique. A repeat is dropped.
2. **Object fingerprint.** The dHash of the first photo is computed. A listing joins an existing object when the Hamming distance is ≤ 6 **and** at least one contact is shared, within 30 days. Failing that, it joins on the same contact, price within ±5% and the same room count. Otherwise a new object is created.
3. **Same object seen before.** A new listing for an object that was already delivered is not delivered again.

## 8. Anti-broker pipeline

| Stage | Rule | Result |
|---|---|---|
| 1. Reputation | A contact is on the blacklist, **or** a contact is linked to more than 2 distinct objects in the last 30 days. | reject |
| 2a. Owner phrases | Find and cut out owner phrases: "без комісії", "без посередників", "без рієлторів/ріелторів", "рієлторам не турбувати", "власник", "від господаря". Record that the listing had one. | (no verdict yet) |
| 2b. Stop-words | On the remaining text, match: комісі\w*, агентств\w*, агенці\w*, р[іи][еє]лтор\w*, послуги \d+\s?%, \d+\s?% від. | reject |
| 2c. Owner pass | No stop-word, and 2a found an owner phrase. | pass |
| 2d. Ambiguous | Text mentions співпрац\w* (for example "співпраця з агентствами"), which can mean either. | goes to stage 3 |

Step 2a runs first because owner phrases contain stop-words: "без комісії" contains "комісії".
| 3. LLM | Everything else. | pass if `is_owner` and `confidence ≥ 0.7`, otherwise reject |

**Stage 3 contract.** One Haiku call per listing. It uses tool use to force this JSON shape:
`{is_owner: bool, confidence: 0..1, reason: str, district: str|null, rooms: int|null, price_uah: int|null, pets: "yes"|"no"|null}`.
The prompt holds the listing text and the fields already extracted.

**Failures and limits.**
- After 2 failed LLM attempts, the verdict is `pass_unverified`.
- The same verdict is used once the daily call count passes `LLM_DAILY_MAX_CALLS`.
- A `pass_unverified` card carries `⚠️ не перевірено`.

**Logging.** Every verdict is stored with its stage, rule or reason, and LLM confidence.

The stop-word and owner-marker lists live in one file, `antibroker/rules.py`, so they can be tuned without touching the pipeline.

## 9. Matching

A filter has: a set of districts (empty means any), `price_min` and `price_max`, a set of rooms (empty means any), and `pets_required` as a bool.

**Rule:** an explicit mismatch excludes a listing. An `unknown` value never excludes, and the card shows it as "не вказано".

`matcher.py` runs one SQL query against the active filters, skipping paused users and users who already got this object. For each match it writes an outbox row.

## 10. Notifier and card

- **Sending.** The notifier claims outbox rows with `FOR UPDATE SKIP LOCKED`. It stays at or below 25 messages/s overall and 1 per second per chat. On a 429 it sleeps for `retry_after`. Other errors get 3 retries with backoff, then the row is marked failed.
- **Photo.** The first photo is downloaded once, through Telethon or HTTP, and sent as an upload. The returned `file_id` is cached on the listing, so the other users reuse it. A listing without a photo is sent as a text message.
- **Caption** (Ukrainian, ≤ 1024 characters, description cut to fit):

```
🏠 2-кімнатна квартира
📍 Франківський (вул. Наукова)
💰 16 000 грн / міс
🐾 Тварини: дозволено
📞 +380XXXXXXXXX
📝 <опис, обрізаний>
⏰ 1 хв тому · Telegram: <канал>
```

- **Buttons:** `🔗 Оригінал` (URL) and `🚩 Це рієлтор` (callback).
- **Complaints.** The complaint hides that object for the user who complained. Complaints from 2 distinct users blacklist all of the object's contacts.

## 11. Bot

- `/start`: a short greeting and how the bot works, then it opens `/filters`.
- `/filters`: an FSM with four steps:
  1. District multi-select (inline toggles plus "Будь-який").
  2. Budget as text `10000-18000`, or `-18000`. Anything that doesn't parse is asked again.
  3. Rooms toggles 1 / 2 / 3+.
  4. Pets toggle, then save.

  One filter per user in the MVP.
- `/my_profile`: shows the filter, with pause/resume, edit, and "Видалити мої дані", which deletes the user, the filter and the user's complaints.
- `/stats` (only for `ADMIN_TG_ID`): listings per source and per verdict stage over 24 h, LLM share, delivered count, and p50/p95 latency.

## 12. Data model (Postgres)

- `users(tg_id PK, created_at, paused bool)`
- `filters(id PK, user_id FK, districts text[], price_min int, price_max int, rooms int[], pets_required bool, updated_at)`
- `objects(id PK, first_seen_at, photo_hash bigint null)`
- `listings(id PK, source, source_id, url, object_id FK, text, price_uah int null, price_raw text, rooms int null, district text null, street text null, pets text, posted_at, ingested_at, verdict, verdict_stage, verdict_reason, llm_confidence real null, photo_url text null, tg_file_id text null, UNIQUE(source, source_id))`
- `contacts(id PK, kind, value, blacklisted bool, UNIQUE(kind, value))`
- `listing_contacts(listing_id FK, contact_id FK)`
- `complaints(user_id FK, object_id FK, created_at, PK(user_id, object_id))`
- `deliveries(user_id FK, object_id FK, delivered_at, PK(user_id, object_id))`
- `outbox(id PK, user_id, listing_id, status, attempts, next_try_at, created_at)`
- `source_state(source, key, value)`, which holds the last message id per channel.

**Retention.** A daily job deletes listings, text and outbox rows older than 60 days. Contacts that are blacklisted are kept.

## 13. Configuration and secrets

All values come from env. A git-ignored `.env` file holds them locally and on the VPS, and `.env.example` is committed with placeholders.

| Variable | Purpose |
|---|---|
| `BOT_TOKEN` | Bot API token |
| `TG_API_ID`, `TG_API_HASH` | Telethon credentials |
| `TG_SESSION_PATH` | Telethon session file, kept in a volume |
| `TG_CHANNELS` | Comma-separated list of channels to read |
| `ANTHROPIC_API_KEY` | LLM access |
| `DATABASE_URL` | Postgres connection |
| `ADMIN_TG_ID` | Who can run `/stats` |
| `USD_UAH_RATE` | Rate used to convert USD prices |
| `LLM_DAILY_MAX_CALLS` | Daily cap, default 500 |

The Telethon session file is a credential. It is never committed or logged.

## 14. Deployment

`docker-compose.yml` defines two services:
- `app`: python:3.12-slim with `uv sync --frozen`, `restart: unless-stopped`.
- `postgres`: postgres:16, with a named volume.

Migrations run on app start. `python -m directrent.login` is a one-off interactive run on the VPS that creates the session file. Logs are JSON lines on stdout.

## 15. Error handling

- **Sources.** Each source runs inside a supervisor that restarts it with exponential backoff (5 s → 5 min). A failed source is logged and shows in `/stats`. The other sources keep running.
- **Pipeline.** A bad post (a parse error) is logged with its source id and skipped. It never stops the worker.
- **Telethon `FloodWait`.** The source sleeps for the time Telegram requests.

## 16. Testing

- **Unit tests** (pytest) cover phones, fields, districts, rules, dedup fingerprinting and the caption renderer. They run against `tests/fixtures/*.txt`, which hold real listing texts with personal data replaced.
- **Integration tests** cover the matcher and the outbox against a throwaway Postgres (docker), including the "unknown never excludes" rule and `SKIP LOCKED` claiming.
- **The LLM stage** is tested with a fake client. One opt-in live test runs only when `ANTHROPIC_API_KEY` is set.
- **Precision:** `scripts/export_sample.py` writes 200 random delivered listings to CSV, the user labels them owner or broker, and `scripts/precision.py` reports the result.

## 17. Phases

| Phase | Scope | Done when |
|---|---|---|
| 0 | OLX test: can phone numbers be fetched for 20 listings without login and without being blocked? | A written yes or no answer, with the method. Throwaway code. |
| 1 | Telegram source, normalize, dedup, anti-broker, matcher, notifier, bot, admin `/stats`, docker-compose. | §1 targets met on a labelled sample. It runs on the VPS for 48 h without a manual restart. |
| 2 | OLX source (built only if phase 0 says yes), polling every 45–60 s. The OLX "Приватна особа / Бізнес" flag feeds stage 2. | OLX listings reach cards with p95 under 90 s. |
| 3 | DOM.RIA through its official API, polling every 180 s. | DOM.RIA listings reach cards. |

## 18. Out of scope for the MVP

- Payments, more than one filter per user, other cities, a language picker.
- A web UI, Playwright, proxies (revisit after phase 0), Redis.
- An LLM fine-tuning loop. Complaints and verdict logs are only stored for now.

## 19. Risks

| Risk | Mitigation |
|---|---|
| The Telethon account is banned. | Use a spare account and read only public channels, never write to them. If it is banned, a new session takes minutes. |
| OLX blocks us or hides phones. | Phase 0 decides before any build. Without phone numbers, OLX would need a different reputation key (`olx_user_id`). |
| Real owners with 3 or more flats are rejected. | Accepted as a known false negative. A complaint flow for that case is out of scope. |
| Personal data (third-party phones). | Data is kept 60 days, there is no export, users can delete their data, and the service is private. |
| LLM cost. | Stages 1–2 run first, a daily cap applies, and Haiku is used. |
