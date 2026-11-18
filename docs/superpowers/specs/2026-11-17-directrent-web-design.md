# DirectRent web: cabinets, real data, uploads (design for approval)

Date: 2026-11-17. Status: draft, waiting for approval. Nothing built yet.
Supabase project: `directrent` (ref `iehajrxboqbrklgxsxkz`, org `directrent`, region eu-central-1).

## Goal
Real users sign in, see real listings, and upload their own data: tenants add profile and documents, owners add flats and photos. The Telegram bot keeps reading channels and writes its listings into the same database.

## Decisions (from chat)
- Stack: Next.js (App Router) deployed on Vercel. Data, auth and files: Supabase.
- Sign-in: email link, Google, Telegram, passkey.
- Two roles, one account each: `tenant` and `owner`. The role is chosen at sign-up and can be changed by admin only.
- Repo stays public: github.com/andriihukco/direct-rent.

## Architecture
- `web/` (Next.js): tenant cabinet (`/tenant`), owner cabinet (`/owner`), public listing pages later.
- `directrent/` (Python bot): keeps reading Telegram. Its `DATABASE_URL` switches from local Postgres to the Supabase database (SSL).
- Supabase Postgres holds all tables, with Row Level Security on every table.
- Supabase Storage holds two private buckets: `listing-photos` (owner uploads) and `tenant-docs` (student card, income proof). Files are served through short-lived signed URLs.

## Data model (first migration)
- `profiles(id = auth.users.id, role, name, phone, telegram_id, created_at)`
- `tenant_profiles(profile_id, occupation, move_in, term, people, pets, verified_dia, about)`
- `owner_flats(id, owner_id, district, rooms, price_uah, rules jsonb, contract_official, created_at)`
- `listings(id, source, source_id, owner_flat_id null, text, district, rooms, price_uah, pets, photos jsonb, verdict, posted_at)` — written by the bot and by owners.
- `tenant_docs(id, tenant_id, kind, storage_path, created_at)`
- `likes(from_role, from_id, to_role, to_id, created_at)` — a match is a pair of likes.
- Later: `contracts`, `bills`.

## Access rules (RLS)
- Tenants read listings with `verdict = pass`. They write only their own profile and docs.
- Owners read tenant profiles that have `verified_dia` or that liked one of their flats; they write only their own flats.
- Tenant docs are visible to an owner only after a match.
- The bot writes listings with the service role key. That key never reaches the browser.

## Phases
1. Auth, two cabinets, profile forms, file uploads, bot writes real listings into the database.
2. Likes and matches on real data (replaces the prototype's sample data).
3. Contracts, Дія signing, bills, renewal reminders.

## Needs from you before phase 1 works
- Google: create an OAuth client in Google Cloud and give me the client ID and secret (I put them into Supabase Auth, not into code).
- Telegram login: set the domain for the login widget in @BotFather (I'll tell you the exact domain once Vercel gives us one).
- Vercel: link the GitHub repo to a Vercel project (or confirm I may do it with the CLI).

## Open risks
- Passkey support in Supabase Auth: I have not confirmed the current API. I'll check the docs before writing that part, and fall back to email if it is not stable.
- Telegram login is not a Supabase built-in. It needs a small server function that checks the widget signature and creates a Supabase session.
- Free plan limits: this project is on the free plan. Storage and auth limits apply; check before launch.

## Calls I made (change if you disagree)
- Next.js over Vite: server code keeps the service key away from browsers.
- eu-central-1 region: closest to Lviv among available regions.
- Listing photos are deleted from storage after 60 days, same as the bot's retention.
