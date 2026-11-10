# DirectRent Lviv, phases 0–1: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Answer the OLX phone-number question (phase 0), then ship a Telegram bot that reads Lviv rental channels, filters out brokers, and sends matching owner listings to users within 60 s (phase 1).

**Architecture:** One asyncio process. Telethon pushes `RawPost`s onto a queue. The pipeline normalises each post, dedups it, runs the three anti-broker stages, and stores it. The matcher writes outbox rows in the same transaction. A notifier claims outbox rows with `SKIP LOCKED` and sends cards through aiogram. All state lives in Postgres.

**Tech Stack:** Python 3.12, uv, aiogram 3, Telethon, httpx, asyncpg, anthropic SDK, Pillow + imagehash, pydantic-settings, pytest + pytest-asyncio, Postgres 16, docker-compose.

**Spec:** `docs/superpowers/specs/2026-11-10-directrent-lviv-design.md`. Read it before any task; section numbers below (§n) refer to it.

## Global Constraints

- Python `>=3.12`, managed by `uv`. Package at `directrent/`, tests at `tests/`.
- Run tests with `uv run pytest -q`. DB tests use `TEST_DATABASE_URL` (default `postgresql://dr:dr@localhost:55432/dr_test`), served by `docker-compose.test.yml`.
- **Machine setup (verified 2026-11-10):** this Mac has Python 3.11 only, no `uv`, and Colima's Docker daemon is stopped. Task 1 installs `uv` and runs `colima start`.
- Bot UI text is Ukrainian. Code, comments, logs and docs are English.
- Secrets come only from env and a git-ignored `.env`, never from code, logs or fixtures. Fixture texts replace real phone numbers with `+380000000001`-style placeholders.
- Every source file stays under 400 lines.
- LLM model id: `claude-haiku-5-5`. Load the `claude-api` skill before writing `antibroker/llm.py`.
- Times are stored as `timestamptz` in UTC. "Today" for the LLM daily cap means Europe/Kyiv.
- Constants from the spec:

  | Constant | Value |
  |---|---|
  | `FRESHNESS` | 2 h |
  | `REPUTATION_WINDOW` | 30 days |
  | `MAX_OBJECTS_PER_CONTACT` | 2 (reject when greater) |
  | `PHASH_MAX_DISTANCE` | 6 |
  | `PRICE_TOLERANCE` | 0.05 |
  | `LLM_MIN_CONFIDENCE` | 0.7 |
  | `LLM_ATTEMPTS` | 2 |
  | `COMPLAINTS_TO_BLACKLIST` | 2 |
  | `GLOBAL_RATE` | 25 msg/s |
  | Per-chat rate | 1 msg/s |
  | `SEND_RETRIES` | 3 |
  | Caption limit | 1024 chars |
  | `RETENTION` | 60 days |
  | `LLM_DAILY_MAX_CALLS` default | 500 |

- Commit after every task, with messages in the form `feat: …` / `test: …` / `chore: …`.

## Review Focus

1. **The same flat arrives from two channels within a second.** The user must get exactly one card. Task 8 tests concurrent `enqueue` for one object.
2. **The user has blocked the bot** (`TelegramForbiddenError`). The notifier must pause that user and keep sending to everyone else, never loop. Covered in Task 10.
3. **A post with no text and only a photo, or text that is only an emoji or a link.** It must be stored as `reject`/`rules` "empty", not crash the pipeline or reach the LLM. Covered in Task 7.
4. **Budget typed as "10 000 - 18 000 грн", "до 18000", "18000-10000".** The first two must parse. A reversed range must swap. Garbage must re-ask without losing earlier answers. Covered in Task 11.
5. **The bot restarts mid-send.** Rows claimed but not sent must be retried, not lost. Claimed rows older than 2 minutes return to `pending`. Covered in Task 10.

---

## File map

| File | Responsibility | Task |
|---|---|---|
| `pyproject.toml`, `.gitignore`, `.env.example`, `docker-compose.test.yml` | project + test DB | 1 |
| `directrent/config.py` | `Settings` from env | 1 |
| `directrent/models.py` | shared dataclasses and enums | 1 |
| `directrent/db.py`, `migrations/001_init.sql` | pool, migration runner, schema | 2 |
| `tests/conftest.py` | `db` fixture (fresh schema per test) | 2 |
| `directrent/normalize/phones.py` | phones + contacts from text | 3 |
| `directrent/normalize/districts.py`, `fields.py` | price, rooms, pets, district, street | 4 |
| `directrent/normalize/__init__.py` | `normalize(raw) -> Listing` | 4 |
| `directrent/dedup.py`, `directrent/store.py` | seen check, photo hash, object assignment, save listing | 5 |
| `directrent/antibroker/reputation.py`, `rules.py` | stages 1, 2, complaints → blacklist | 6 |
| `directrent/antibroker/llm.py`, `pipeline.py` | stage 3, `process()` | 7 |
| `directrent/matcher.py` | listing → outbox + deliveries | 8 |
| `directrent/bot/cards.py` | caption + keyboard | 9 |
| `directrent/notifier.py` | outbox worker | 10 |
| `directrent/bot/repo.py`, `keyboards.py`, `handlers.py`, `budget.py` | user flows | 11 |
| `directrent/sources/telegram.py`, `directrent/supervisor.py`, `directrent/main.py`, `directrent/login.py` | ingestion + wiring | 12 |
| `directrent/bot/admin.py`, `directrent/stats.py`, `directrent/retention.py`, `scripts/*.py` | `/stats`, purge, precision | 13 |
| `Dockerfile`, `docker-compose.yml`, `README.md` | deploy | 14 |

---

### Task 0: OLX phone-number test (phase 0, throwaway)

**Files:**
- Create: `spikes/olx_phones.py` (throwaway, never imported by `directrent/`)
- Create: `docs/spikes/2026-11-olx-phones.md` (the deliverable)

- [ ] **Step 1:** With httpx and no login, fetch the first page of Lviv long-term rentals. Try the site's JSON endpoint (`https://www.olx.ua/api/v1/offers/?category_id=<rent flats>&region_id=<Lviv>`, ids read from the site's network calls) and record the response status.
- [ ] **Step 2:** For 20 offer ids, call the phone endpoint the site uses (find it in the browser network tab: "Показати телефон"). Space the calls 3–5 s apart. Record per call: status, whether a phone came back, and any captcha or 403.
- [ ] **Step 3:** Record whether offers expose a private/business flag and a stable user id.
- [ ] **Step 4:** Write `docs/spikes/2026-11-olx-phones.md`. It must contain a **Yes/No** for "phones without login for 20 listings", the method, the rate that worked, the flag and user-id findings, and a recommendation for phase 2.
- [ ] **Step 5:** Commit the spike doc only. Add `spikes/` to `.gitignore`.

Done when: the doc exists with a Yes/No answer. No production code depends on this task.

---

### Task 1: Project scaffold, config, models

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `.env.example`, `docker-compose.test.yml`, `directrent/__init__.py`, `directrent/config.py`, `directrent/models.py`
- Test: `tests/test_config.py`

**Interfaces — Produces:**

```python
# directrent/models.py
class Verdict(StrEnum): PASS = "pass"; PASS_UNVERIFIED = "pass_unverified"; REJECT = "reject"
ContactKind = Literal["phone", "tg_user_id", "tg_username", "olx_user_id"]
Pets = Literal["yes", "no", "unknown"]
DISTRICTS: tuple[str, ...] = ("Франківський", "Сихівський", "Галицький", "Личаківський",
                              "Залізничний", "Шевченківський", "Приміські")

@dataclass(frozen=True)
class Contact: kind: ContactKind; value: str

@dataclass
class RawPost:
    source: str; source_id: str; url: str; text: str; posted_at: datetime
    channel_title: str; author_contacts: list[Contact]
    photo_bytes: bytes | None = None; photo_url: str | None = None

@dataclass
class Listing:  # RawPost fields plus normalised ones
    source: str; source_id: str; url: str; text: str; posted_at: datetime; channel_title: str
    contacts: list[Contact]; price_uah: int | None; price_raw: str | None
    rooms: int | None          # 3 means "3+"
    district: str | None; street: str | None; pets: Pets
    photo_bytes: bytes | None; photo_url: str | None; photo_hash: int | None = None

@dataclass
class Decision: verdict: Verdict; stage: Literal["reputation", "rules", "llm"]; reason: str; confidence: float | None = None

@dataclass
class Filter: user_id: int; districts: list[str]; price_min: int | None; price_max: int | None; rooms: list[int]; pets_required: bool
```

```python
# directrent/config.py
class Settings(BaseSettings):  # env_file=".env"
    bot_token: SecretStr; tg_api_id: int; tg_api_hash: SecretStr; tg_session_path: str = "data/telethon.session"
    tg_channels: list[str]       # parsed from comma-separated env
    anthropic_api_key: SecretStr; database_url: str; admin_tg_id: int
    usd_uah_rate: float = 41.5; llm_daily_max_calls: int = 500
def get_settings() -> Settings  # cached
```

- [ ] **Step 1: Set up the machine.** Run `brew install uv`, `uv python install 3.12`, `colima start`, `git init`. Expected: `uv --version` prints, and `docker info` connects.
- [ ] **Step 2:** `uv init --package --name directrent -p 3.12`. Add the deps from Tech Stack, plus dev deps `pytest pytest-asyncio`. Set `asyncio_mode = "auto"` in `[tool.pytest.ini_options]`.
- [ ] **Step 3:** Create `.gitignore` with `.env`, `data/`, `*.session`, `spikes/`, `.venv/`, `__pycache__/`. Create `.env.example` with every `Settings` field as a placeholder. `docker-compose.test.yml` runs one `postgres:16` with user/password/db `dr`/`dr`/`dr_test` on host port `55432`, using tmpfs storage.
- [ ] **Step 4: Write a failing test.** `test_settings_parses_channels`: `monkeypatch` the env with `TG_CHANNELS="lviv_rent, @kvartyry_lviv"` plus the required vars. Assert `Settings().tg_channels == ["lviv_rent", "kvartyry_lviv"]` (trimmed, leading `@` removed). Run it and see it fail.
- [ ] **Step 5:** Implement `config.py` and `models.py`. Run `uv run pytest -q` and expect a pass.
- [ ] **Step 6:** Commit with `chore: scaffold project, config, models`.

---

### Task 2: Database schema and test fixture

**Files:**
- Create: `directrent/db.py`, `migrations/001_init.sql`, `tests/conftest.py`
- Test: `tests/test_db.py`

**Interfaces — Produces:**
- `async def create_pool(dsn: str) -> asyncpg.Pool`
- `async def migrate(pool: asyncpg.Pool, path: Path = Path("migrations")) -> list[str]`, which applies files in name order, once each, recorded in `schema_migrations(name PK, applied_at)`, and returns the names it applied.
- Fixture `db` (async) yields a pool on a freshly migrated DB. It runs `DROP SCHEMA public CASCADE; CREATE SCHEMA public` and then `migrate`.

**Schema:** the tables are exactly as in spec §12, with these additions, which are decisions made here:
- `listings.photo_bytes bytea null`. Cleared once `tg_file_id` is set. Needed because Telethon photo bytes cannot be re-fetched by the bot.
- `listings.raw_contacts jsonb`. Kept for debugging verdicts.
- `outbox.status text CHECK (status IN ('pending','sending','sent','failed'))`, `outbox.claimed_at timestamptz`, `outbox.sent_at timestamptz` (used for latency in `/stats`), `outbox.last_error text`.
- `users.username text null`.
- Indexes: `listing_contacts(contact_id)`, `listings(ingested_at)`, `outbox(status, next_try_at)`.
- `deliveries` is written at enqueue time; see Task 8.

- [ ] **Step 1: Failing test.** `test_migrate_is_idempotent`: the first `migrate()` returns `["001_init.sql"]` and the second returns `[]`. `test_listing_unique_source_id`: inserting the same `(source, source_id)` twice raises `asyncpg.UniqueViolationError`.
- [ ] **Step 2:** Run `docker compose -f docker-compose.test.yml up -d` and then `uv run pytest tests/test_db.py -q`. Expect a FAIL.
- [ ] **Step 3:** Implement `db.py`, the SQL and the fixture.
- [ ] **Step 4:** Run the tests and expect a PASS. Commit with `feat: schema and migration runner`.

---

### Task 3: Phones and contacts

**Files:**
- Create: `directrent/normalize/phones.py`
- Test: `tests/normalize/test_phones.py`

**Interfaces — Produces:**
- `def extract_phones(text: str) -> list[str]` returns unique `+380XXXXXXXXX` values in order of appearance.
- `def extract_contacts(text: str, author: list[Contact]) -> list[Contact]` combines phones, `@username` mentions in the text (lowercased, without `@`, 5–32 chars of `[a-z0-9_]`, as `tg_username`) and the author contacts. The result is deduplicated.

- [ ] **Step 1: Failing tests.** Each one is a parametrised assert:
  - `"+38 (067) 123-45-67"` → `["+380671234567"]`
  - `"067 123 45 67"` → `["+380671234567"]`
  - `"380671234567"` → `["+380671234567"]`
  - `"0671234567, 0671234567"` → one item
  - `"ціна 16000, 2 кімн"` → `[]`. Prices must not parse as phones.
  - `"18 000 грн"` → `[]`
  - `extract_contacts("пишіть @Owner_Lviv", [Contact("tg_user_id", "42")])` → contains `Contact("tg_username", "owner_lviv")` and `Contact("tg_user_id", "42")`.
- [ ] **Step 2:** Run the tests and expect a FAIL.
- [ ] **Step 3:** Implement. Accept only the Ukrainian mobile/landline shape: after normalisation it must be 9 digits following `380`, with an operator code starting `[3-9]`. Build the digits from a regex that allows spaces, dashes, dots and brackets between digit groups.
- [ ] **Step 4:** Run the tests and expect a PASS. Commit with `feat: phone and contact extraction`.

---

### Task 4: Field extraction and `normalize()`

**Files:**
- Create: `directrent/normalize/districts.py`, `directrent/normalize/fields.py`, `directrent/normalize/__init__.py`
- Create: `tests/fixtures/posts/*.txt` (at least 12 real channel posts with phones replaced, each with a header comment line `# expect: price=16000 rooms=2 district=Франківський pets=yes`)
- Test: `tests/normalize/test_fields.py`, `tests/normalize/test_fixtures.py`

**Interfaces — Produces:**
- `def parse_price(text: str, usd_rate: float) -> tuple[int | None, str | None]` returns `(price_uah, price_raw)`.
- `def parse_rooms(text: str) -> int | None` returns 1, 2 or 3, where 3 means 3 or more.
- `def parse_pets(text: str) -> Pets`
- `def parse_district(text: str) -> str | None` returns a value from `DISTRICTS`.
- `def parse_street(text: str) -> str | None` returns the text after `вул.` / `вулиця` / `просп.`, up to the next comma or line break.
- `def normalize(raw: RawPost, usd_rate: float) -> Listing`

`districts.py` holds `NEIGHBOURHOODS: dict[str, str]`, mapping a lowercase stem to its district. At minimum: сихів→Сихівський; левандівк, рясн, білогорщ→Залізничний; кастелівк, науков, стрийськ→Франківський; брюховичі, винники, сокільники, рудно→Приміські; погулянк, личаків→Личаківський; замарстинів, голоск, підзамч→Шевченківський; центр, площа ринок→Галицький. Explicit district names win over neighbourhoods.

- [ ] **Step 1: Failing tests:**
  - `parse_price("16 000 грн/міс", 41.5) == (16000, "16 000 грн")`
  - `parse_price("$400", 41.5) == (16600, "$400")`
  - `parse_price("400$ + комуналка", 41.5)[0] == 16600`
  - `parse_price("2 кімнати, 3 поверх", 41.5) == (None, None)`
  - Prices under 3000 UAH or over 200000 UAH return `None`, since they are not monthly rents.
  - `parse_rooms("2-кімнатна")`, `parse_rooms("двокімнатна")` and `parse_rooms("2к")` each return 2. `parse_rooms("4-кімн")` returns 3. `parse_rooms("однокімнатна")` returns 1.
  - `parse_pets("без тварин")` returns `"no"`. `parse_pets("можна з котом")` and `parse_pets("pet friendly")` return `"yes"`. `parse_pets("ремонт")` returns `"unknown"`.
  - `parse_district("Сихів, вул. Червоної Калини")` returns `"Сихівський"`.
  - `test_fixtures` asserts each fixture's `# expect` line.
- [ ] **Step 2:** Run the tests and expect a FAIL.
- [ ] **Step 3:** Implement. `normalize` calls `extract_contacts(raw.text, raw.author_contacts)` and the parsers, copies the rest, and leaves `photo_hash=None` (Task 5 computes it).
- [ ] **Step 4:** Run the tests and expect a PASS. Commit with `feat: listing field extraction`.

---

### Task 5: Dedup, photo hash, and storing listings

**Files:**
- Create: `directrent/dedup.py`, `directrent/store.py`
- Test: `tests/test_dedup.py` (DB)

**Interfaces — Produces:**
- `def photo_hash(data: bytes) -> int | None` returns the 64-bit `imagehash.dhash` as a signed int64 for Postgres, or `None` for unreadable bytes.
- `async def seen(conn, source: str, source_id: str) -> bool`
- `async def find_or_create_object(conn, listing: Listing) -> int`, implementing spec §7 step 2. Candidates are objects whose listings share a contact within 30 days. The first match is by Hamming distance `bit_count((a # b)::bit(64))` ≤ 6, then by the same rooms with price within ±5%. Otherwise it inserts a new object.
- `async def save_listing(conn, listing: Listing, object_id: int, decision: Decision) -> int` inserts the listing, upserts contacts, links `listing_contacts`, and returns `listing_id`.

- [ ] **Step 1: Failing tests:**
  - `photo_hash(b"not an image") is None`
  - Two listings with the same phone and a photo hash 3 bits apart resolve to the same object.
  - The same phone with a hash 20 bits apart, rooms 2 vs 2 and price 16000 vs 16500 gives the same object (by price).
  - The same phone, rooms 1 vs 3: different objects.
  - No shared contact: always a new object.
  - A shared contact whose last listing is 31 days old: a new object.
  - `seen()` is true after `save_listing`.
- [ ] **Step 2:** Run the tests and expect a FAIL. Then implement.
- [ ] **Step 3:** Run the tests and expect a PASS. Commit with `feat: object dedup and listing storage`.

---

### Task 6: Anti-broker stages 1–2 and complaints

**Files:**
- Create: `directrent/antibroker/__init__.py`, `reputation.py`, `rules.py`
- Test: `tests/antibroker/test_rules.py`, `tests/antibroker/test_reputation.py` (DB)

**Interfaces — Produces:**
- `def classify_rules(text: str) -> Decision | None` implements spec §8 steps 2a–2d exactly, in that order. It returns `REJECT` with reason `stopword:<match>`, `PASS` with reason `owner:<phrase>`, or `None` (ambiguous or no signal, so it goes to the LLM). Text that is empty or whitespace after stripping URLs and emoji returns `REJECT` with reason `empty`.
- `async def check_reputation(conn, contacts: list[Contact], object_id: int) -> Decision | None` returns `REJECT` with stage `reputation` when any contact is blacklisted (reason `blacklist:<kind>`), or when any contact has more than 2 distinct objects in 30 days counting `object_id` (reason `objects:<n>`). Otherwise it returns `None`.
- `async def record_complaint(conn, user_id: int, object_id: int) -> bool` is idempotent per (user, object). Once 2 distinct users have complained about an object, it blacklists all contacts of that object's listings and returns `True`.

- [ ] **Step 1: Failing rule tests (parametrised):**
  - `"Здам квартиру без комісії, власник"` → PASS
  - `"Комісія 50%"` → REJECT
  - `"Агентство нерухомості пропонує"` → REJECT
  - `"Ріелторам не турбувати"` → PASS
  - `"Без рієлторів. Послуги 30%"` → REJECT
  - `"Співпраця з агентствами можлива"` → `None`
  - `"Здам 2к квартиру, Сихів"` → `None`
  - `"👍 https://t.me/x"` → REJECT `empty`
- [ ] **Step 2: Failing reputation tests:**
  - A phone on 3 different objects with the 4th incoming → REJECT `objects:4`.
  - The same phone on 1 object cross-posted 3 times, with the same object incoming → `None`.
  - A blacklisted username → REJECT.
  - `record_complaint` returns False after the first user, False when the same user repeats, and True after a second user. The contacts are then `blacklisted`.
- [ ] **Step 3:** Run the tests and expect a FAIL. Implement. Keep the stop-word and owner lists as module constants at the top of `rules.py`.
- [ ] **Step 4:** Run the tests and expect a PASS. Commit with `feat: anti-broker reputation and rules`.

---

### Task 7: LLM stage and the pipeline

**Files:**
- Create: `directrent/antibroker/llm.py`, `directrent/antibroker/pipeline.py`
- Test: `tests/antibroker/test_llm.py`, `tests/antibroker/test_pipeline.py` (DB)

**Interfaces — Consumes:** `normalize` (Task 4), `seen`/`photo_hash`/`find_or_create_object`/`save_listing` (Task 5), `check_reputation`/`classify_rules` (Task 6), `matcher.enqueue` (Task 8; stub it in this task's tests).

**Interfaces — Produces:**

```python
@dataclass
class LlmResult: is_owner: bool; confidence: float; reason: str
    district: str | None; rooms: int | None; price_uah: int | None; pets: Literal["yes", "no"] | None
class LlmError(Exception): ...
class LlmClassifier(Protocol):
    async def classify(self, listing: Listing) -> LlmResult: ...
class HaikuClassifier:  # implements LlmClassifier
    def __init__(self, client: anthropic.AsyncAnthropic, model: str = "claude-haiku-5-5"): ...
class DailyBudget:
    def __init__(self, max_calls: int, tz: str = "Europe/Kyiv"): ...
    def take(self, now: datetime) -> bool   # False once today's cap is used; resets at local midnight
@dataclass
class ProcessResult: listing_id: int; decision: Decision; queued: int
async def process(pool, raw: RawPost, llm: LlmClassifier, budget: DailyBudget,
                  usd_rate: float, now: datetime, enqueue=matcher.enqueue) -> ProcessResult | None
```

- **`HaikuClassifier`:** forces one tool, `report_verdict`, whose input schema is the `LlmResult` fields, with `district` as an enum of `DISTRICTS` or null. It uses `max_tokens=300`. A short Ukrainian-aware system prompt states the owner-versus-broker criteria from spec §8. Any API error, or a missing or invalid tool input, raises `LlmError`. The budget is kept in memory, so a restart resets it; that is accepted.
- **`process` order:**
  1. Return `None` if `now - raw.posted_at > 2h` or if the post was `seen`.
  2. `normalize`, then `photo_hash`.
  3. In one transaction: `find_or_create_object`, then `check_reputation`, then `classify_rules`, then the LLM. The LLM step consumes the budget first. A false budget gives `PASS_UNVERIFIED` with reason `llm:budget`. Two failed attempts give `PASS_UNVERIFIED` with reason `llm:error`. `is_owner` with confidence ≥ 0.7 gives PASS; anything else gives REJECT.
  4. An LLM result fills only the fields that are `None`/`"unknown"`.
  5. `save_listing`. If the verdict is not REJECT, call `enqueue(conn, listing_id)`.
- **Logging:** each verdict is logged as one JSON line: `source`, `source_id`, `verdict`, `stage`, `reason`.

- [ ] **Step 1: Failing tests, using a `FakeLlm` that returns or raises as set:**
  - A rules PASS listing never calls the LLM (`fake.calls == 0`).
  - An ambiguous listing with the fake returning `is_owner=True, confidence=0.9, district="Сихівський"` gives PASS, and the stored district is `Сихівський`.
  - Confidence 0.5 → REJECT, stage `llm`.
  - The fake raising twice → PASS_UNVERIFIED `llm:error`, with `fake.calls == 2`.
  - `DailyBudget(1)`: the second ambiguous listing gives PASS_UNVERIFIED `llm:budget`. The budget resets after Kyiv midnight; test with two `now` values.
  - A post 3 h old → `None`, nothing stored.
  - The same post twice → the second returns `None`.
  - A REJECT never calls `enqueue`.
  - An emoji-only post → REJECT `empty` (Review Focus 3).
- [ ] **Step 2: Failing `HaikuClassifier` test:** a fake `AsyncAnthropic` whose `messages.create` returns a `tool_use` block yields the parsed `LlmResult`. A text-only response raises `LlmError`. Also assert that the request has `tool_choice == {"type": "tool", "name": "report_verdict"}`.
- [ ] **Step 3:** Run the tests and expect a FAIL. Implement.
- [ ] **Step 4:** Run the tests and expect a PASS. Optionally add `test_live_haiku`, skipped unless `ANTHROPIC_API_KEY` is set, which classifies one owner fixture and expects `is_owner`. Commit with `feat: llm stage and ingest pipeline`.

---

### Task 8: Matcher

**Files:**
- Create: `directrent/matcher.py`
- Test: `tests/test_matcher.py` (DB)

**Interfaces — Produces:** `async def enqueue(conn, listing_id: int) -> int` returns the number of outbox rows created.

One `INSERT … SELECT` selects users who are not paused and whose filter matches, per spec §9: an explicit mismatch excludes, and `NULL`/`unknown` never excludes. Rooms match when `filter.rooms` is empty, when `listing.rooms = ANY(filter.rooms)`, or when the listing rooms value is null. It excludes users with a row in `deliveries` or `complaints` for this object. In the same statement (a CTE) it inserts into `deliveries ON CONFLICT DO NOTHING` and creates `outbox` rows only for the newly inserted deliveries. That makes a concurrent double enqueue safe.

- [ ] **Step 1: Failing tests:**
  - A district mismatch excludes.
  - Listing district `NULL` matches a filter for Сихівський only.
  - A price of 20000 with `price_max` 18000 excludes. A `NULL` price matches.
  - `pets_required` with listing pets `no` excludes. With `unknown` it matches.
  - A paused user is excluded.
  - A second listing of an already delivered object → 0 rows.
  - A user who complained about the object → 0 rows.
  - Review Focus 1: two `enqueue` calls for two listings of the same object, run with `asyncio.gather` on two connections → exactly one outbox row in total for the user.
- [ ] **Step 2:** Run the tests and expect a FAIL. Implement.
- [ ] **Step 3:** Run the tests and expect a PASS. Commit with `feat: filter matcher`.

---

### Task 9: Card rendering

**Files:**
- Create: `directrent/bot/__init__.py`, `directrent/bot/cards.py`
- Test: `tests/bot/test_cards.py`

**Interfaces — Produces:**

```python
@dataclass
class CardData: rooms: int | None; district: str | None; street: str | None; price_raw: str | None
    price_uah: int | None; pets: Pets; phones: list[str]; text: str; posted_at: datetime
    source_label: str; url: str; object_id: int; unverified: bool
def render_caption(card: CardData, now: datetime) -> str  # HTML parse mode, ≤ 1024 chars
def card_keyboard(card: CardData) -> InlineKeyboardMarkup
BROKER_CB_PREFIX = "broker:"
```

The caption layout is exactly as in spec §10. These strings are fixed:

| Case | Text |
|---|---|
| Room line, rooms 3 | `🏠 3+ кімнатна квартира` |
| Room line, rooms unknown | `🏠 Квартира` |
| Any unknown field | `не вказано` |
| Pets yes | `дозволено` |
| Pets no | `заборонено` |
| Unverified listing, first line | `⚠️ не перевірено` |
| No phone | the phone line is omitted |
| Age under 1 minute | `щойно` |
| Age under 60 minutes | `N хв тому` |
| Older | `N год тому` |

All user text is HTML-escaped. The description is cut last, with `…`, so the total fits in 1024. The buttons are `🔗 Оригінал` (url) and `🚩 Це рієлтор` (callback `broker:<object_id>`).

- [ ] **Step 1: Failing tests:**
  - A full card matches a golden string.
  - A 3000-char description gives `len(caption) <= 1024` and the caption ends with the source line.
  - The text `<b>x</b>` is escaped.
  - Unknown district shows `📍 не вказано`.
  - The keyboard callback data is `broker:7`.
- [ ] **Step 2:** Run the tests and expect a FAIL. Implement.
- [ ] **Step 3:** Run the tests and expect a PASS. Commit with `feat: listing card`.

---

### Task 10: Notifier

**Files:**
- Create: `directrent/notifier.py`
- Test: `tests/test_notifier.py` (DB + fake bot)

**Interfaces — Consumes:** `render_caption`, `card_keyboard` (Task 9).

**Interfaces — Produces:**

```python
@dataclass
class OutboxRow: id: int; user_id: int; listing_id: int; attempts: int
class Notifier:
    def __init__(self, bot: Bot, pool, global_rate: int = 25, per_chat_interval: float = 1.0): ...
    async def claim(self, conn, limit: int = 25) -> list[OutboxRow]   # pending & next_try_at<=now → sending
    async def send_one(self, row: OutboxRow) -> None
    async def reclaim_stale(self, conn, older_than: timedelta = timedelta(minutes=2)) -> int
    async def run(self) -> None   # loop: reclaim_stale, claim, send concurrently under rate limits, sleep 0.5 s when idle
```

`send_one` loads the listing and builds `CardData`.
- **Photo choice:** if the listing has `tg_file_id`, send that. Otherwise, if it has `photo_bytes`, send a `BufferedInputFile`, then store the returned largest `file_id` and set `photo_bytes = NULL`. Otherwise, if it has `photo_url`, send the URL. Otherwise send a text message.
- **Errors:**
  - `TelegramRetryAfter` → sleep `retry_after`, then retry the same row without counting an attempt.
  - `TelegramForbiddenError` → mark the row `failed` and set `users.paused = true`.
  - Any other `TelegramAPIError` → `attempts += 1`, `next_try_at = now + 5 s × 2^attempts`, and `failed` after 3 attempts with `last_error` set.
  - Success → `sent`, `sent_at = now()`.

- [ ] **Step 1: Failing tests, with a `FakeBot` that records calls and raises when scripted:**
  - A photo_bytes listing: the first send uploads bytes, `tg_file_id` is stored and `photo_bytes` is null, and a second user's send uses the `file_id`.
  - Forbidden → row `failed` and user `paused`, and the next row is still sent.
  - A generic error 3 times → `failed`, attempts 3.
  - RetryAfter(1) then success → `sent`, attempts 0.
  - `reclaim_stale` returns a `sending` row claimed 3 minutes ago to `pending` (Review Focus 5).
  - Two notifiers claiming at once never get the same row.
- [ ] **Step 2:** Run the tests and expect a FAIL. Implement. Use a token bucket for the global rate and a dict of last send time per chat.
- [ ] **Step 3:** Run the tests and expect a PASS. Commit with `feat: outbox notifier`.

---

### Task 11: Bot user flows

**Files:**
- Create: `directrent/bot/budget.py`, `directrent/bot/repo.py`, `directrent/bot/keyboards.py`, `directrent/bot/handlers.py`
- Test: `tests/bot/test_budget.py`, `tests/bot/test_repo.py` (DB), `tests/bot/test_handlers.py`

**Interfaces — Consumes:** `record_complaint` (Task 6), `Filter` (Task 1).

**Interfaces — Produces:**
- `def parse_budget(text: str) -> tuple[int | None, int | None]` raises `ValueError` on garbage.
- `repo`:
  - `upsert_user(conn, tg_id, username)`
  - `get_filter(conn, user_id) -> Filter | None`
  - `save_filter(conn, f: Filter)`, which upserts the user's one filter
  - `set_paused(conn, user_id, paused: bool)`
  - `delete_user_data(conn, user_id)`, which deletes complaints, deliveries, outbox, filter and user
- `def build_router(pool) -> Router`
- FSM: `class FilterForm(StatesGroup): districts, budget, rooms, pets`
- `keyboards`: `districts_kb(selected: set[str])` (with "Будь-який" and "Далі ➡️"), `rooms_kb(selected: set[int])`, `pets_kb(required: bool)`, `profile_kb(paused: bool)`.

**Flows (spec §11):**
- `/start` → greeting, then it starts the filter form.
- The district toggles keep the selection in FSM data.
- At the budget step, invalid input re-asks with `Не зрозумів. Приклад: 10000-18000` and keeps the earlier answers.
- After pets → save the filter, then show the summary from `/my_profile`.
- `/my_profile` shows the summary plus pause/resume, edit, and `Видалити мої дані`. The delete button asks for confirmation first.
- The `broker:<id>` callback → `record_complaint`, then answer `Дякуємо, приховали це оголошення`.

**Budget cases** (Review Focus 4):

| Input | Result |
|---|---|
| `"10000-18000"` | `(10000, 18000)` |
| `"10 000 - 18 000 грн"` | `(10000, 18000)` |
| `"-18000"` | `(None, 18000)` |
| `"до 18000"` | `(None, 18000)` |
| `"від 10000"` | `(10000, None)` |
| `"18000-10000"` | `(10000, 18000)` (swapped) |
| `"дешево"` | raises |
| `"0-0"` | raises |

- [ ] **Step 1: Failing tests:**
  - The budget table above.
  - The repo round-trip for `save_filter`/`get_filter`.
  - `delete_user_data` leaves no rows for that user in any table.
  - Handlers, driven by aiogram's `Dispatcher.feed_update` with a mocked bot session and `MemoryStorage`: `/start` → the districts keyboard is sent; toggling "Сихівський", then "Далі", budget `"дешево"` (re-ask, state still `budget`), `"10000-18000"`, rooms 2, then "Зберегти" stores `Filter(districts=["Сихівський"], price_min=10000, price_max=18000, rooms=[2], pets_required=False)`.
  - `broker:5` calls `record_complaint(conn, user_id, 5)`.
- [ ] **Step 2:** Run the tests and expect a FAIL. Implement.
- [ ] **Step 3:** Run the tests and expect a PASS. Commit with `feat: bot filters, profile, complaints`.

---

### Task 12: Telegram source and process wiring

**Files:**
- Create: `directrent/sources/__init__.py`, `directrent/sources/telegram.py`, `directrent/supervisor.py`, `directrent/main.py`, `directrent/login.py`
- Test: `tests/sources/test_telegram.py`, `tests/test_supervisor.py`

**Interfaces — Consumes:** `process` (Task 7), `Notifier` (Task 10), `build_router` (Task 11).

**Interfaces — Produces:**
- `async def supervise(name: str, start: Callable[[], Awaitable[None]], min_delay=5.0, max_delay=300.0, sleep=asyncio.sleep) -> NoReturn` restarts on any exception, doubling the delay up to the max. The delay resets after 10 minutes of healthy running. It logs each restart and keeps `SOURCE_HEALTH[name] = {"restarts": n, "last_error": str}` for `/stats`.
- `def message_to_raw(msg, channel_username: str, channel_title: str, photo_bytes: bytes | None) -> RawPost`:
  - `source = "telegram"`, `source_id = f"{channel_username}:{msg.id}"`, `url = f"https://t.me/{channel_username}/{msg.id}"`, `posted_at = msg.date`.
  - `author_contacts` holds `tg_user_id`/`tg_username` only when `msg.from_id` is a user (not a channel post).
- `class TelegramSource`:
  - `__init__(self, client: TelegramClient, channels: list[str], queue: asyncio.Queue[RawPost], pool)`
  - `async def run(self)`: on start, for each channel, reads `source_state('telegram', channel)` as `last_id` and sends every newer message from `iter_messages(min_id=last_id)` (which goes newest first, so stop at 2 h old). It then subscribes `events.NewMessage` for messages with no `grouped_id` and `events.Album` for albums. Only the first photo is downloaded, and the album caption is the text of the first message that has one. It updates `last_id` after each enqueue. On `FloodWaitError` it sleeps `e.seconds`.
- `main.py`: `async def main()` loads settings, creates the pool, runs `migrate`, then starts four tasks under `supervise`: the Telethon source, the pipeline worker (reads the queue → `process(... now=datetime.now(UTC))`, so one bad post is logged and skipped), the notifier, and aiogram polling. The retention job (Task 13) runs daily. Logging is set to JSON lines on stdout. The entry point is `python -m directrent.main`.
- `login.py`: interactive `TelegramClient(session_path, api_id, api_hash).start()`. It prints only "Session saved", never the phone number or the code.

- [ ] **Step 1: Failing tests:**
  - `message_to_raw` with a fake message (`id=10`, channel `lviv_rent`, `from_id=PeerUser(42)`, a sender username `owner`) → `source_id == "lviv_rent:10"` and contacts include `tg_user_id 42`.
  - For a channel post (`from_id=None`) the author contacts are `[]`.
  - `supervise` with a `start` that raises twice then returns → two recorded restarts, with delays 5 then 10 through a fake `sleep`.
- [ ] **Step 2:** Run the tests and expect a FAIL. Implement.
- [ ] **Step 3:** Run the tests and expect a PASS.
- [ ] **Step 4: Manual smoke test, with real credentials in `.env` and one test channel the user owns.**
  - Run `uv run python -m directrent.login`, then `uv run python -m directrent.main`.
  - Set a filter in the bot, then post `Здам 2к, Сихів, 15000 грн, власник, +380000000001` to the test channel.
  - Expected: a card within 30 s, and the log shows `verdict=pass stage=rules`.
- [ ] **Step 5:** Commit with `feat: telegram source and app wiring`.

---

### Task 13: Admin `/stats`, retention, precision scripts

**Files:**
- Create: `directrent/stats.py`, `directrent/retention.py`, `directrent/bot/admin.py`, `scripts/export_sample.py`, `scripts/precision.py`
- Test: `tests/test_stats.py` (DB), `tests/test_retention.py` (DB), `tests/test_precision.py`

**Interfaces — Produces:**
- `@dataclass class Stats` holds:
  - `per_source: dict[str, int]`
  - `per_stage: dict[str, dict[str, int]]`, as stage → verdict → count
  - `llm_share: float`, the share of the 24 h listings whose stage is llm
  - `delivered: int`
  - `latency_p50_s: float | None` and `latency_p95_s: float | None`, computed from `outbox.sent_at - listings.posted_at` over sent rows in 24 h
- `async def collect(conn, now: datetime) -> Stats`
- `def format_stats(s: Stats, health: dict) -> str`
- `async def purge(conn, now: datetime) -> int` deletes listings (and their outbox and listing_contacts rows) older than 60 days, and orphan objects. It keeps contacts that are blacklisted.
- `admin.build_admin_router(pool, admin_id: int) -> Router`. `/stats` answers only `admin_id`; anyone else gets no reply.
- `export_sample.py --n 200 --out sample.csv` writes delivered (non-REJECT) listings, chosen at random. The columns are `listing_id,url,text,verdict,stage,label`, with `label` empty.
- `precision.py sample.csv` prints `precision=0.93 (186/200)`, counting only rows labelled `owner`/`broker`. It exits with code 1 if any row is unlabelled.

- [ ] **Step 1: Failing tests:**
  - With 10 listings (2 llm-stage, 8 rules) and 4 sent rows with latencies 10, 20, 30 and 100 s, `collect` gives `llm_share == 0.2`, `latency_p50_s == 25` and `delivered == 4`.
  - `purge` removes a 61-day-old listing, keeps a 59-day-old one, and keeps a blacklisted contact.
  - `precision.py` on a 4-row CSV with 3 owner and 1 broker prints `precision=0.75 (3/4)`.
- [ ] **Step 2:** Run the tests and expect a FAIL. Implement, and wire the admin router and the daily `purge` into `main.py`.
- [ ] **Step 3:** Run the tests and expect a PASS. Commit with `feat: admin stats, retention, precision tooling`.

---

### Task 14: Deployment

**Files:**
- Create: `Dockerfile`, `docker-compose.yml`, `README.md`

- `Dockerfile`: starts from `python:3.12-slim`, copies `uv` from `ghcr.io/astral-sh/uv:latest`, runs `uv sync --frozen --no-dev`, and uses `CMD ["uv", "run", "python", "-m", "directrent.main"]`.
- `docker-compose.yml` runs two services:
  - `app` uses `env_file: .env`, a volume `./data:/app/data` (the Telethon session), `restart: unless-stopped`, and `depends_on` postgres with `condition: service_healthy`.
  - `postgres:16` uses a named volume and a healthcheck with `pg_isready`.
  - `DATABASE_URL` points at the service name.
- `README.md` covers setup in about 20 lines: copy `.env.example`; `docker compose run --rm app uv run python -m directrent.login`; `docker compose up -d`; `docker compose logs -f app`; and how to run the precision check.

- [ ] **Step 1:** Run `docker compose build`. Expected: it succeeds.
- [ ] **Step 2:** Run `docker compose up -d`, then `docker compose logs app | head`. Expected: a JSON line saying migrations applied and every one of the four supervised tasks started. Then repeat the Task 12 smoke test against the container.
- [ ] **Step 3:** Commit with `chore: docker deployment`.

**Phase 1 exit (spec §17), not a coding task:**
1. Deploy to the VPS and run it for 48 h.
2. Read `/stats` for p50 under 30 s, p95 under 60 s and an LLM share of 20% or less.
3. Export 200 listings, label them, and run `precision.py` to check for 0.92 or higher. Report the measured numbers, not the targets.
