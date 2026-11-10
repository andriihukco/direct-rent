# Spike: can we get OLX phone numbers? (2026-11-10)

## Answer: **No** for a server-side client. **Unproven** for a browser-based one.

The plan's test (20 listings) was not completed. The bulk lookup was blocked by the assistant's own permission check, so only 1 phone lookup was made.

## What was tried

| Check | Method | Result |
|---|---|---|
| The Lviv rentals page (`/uk/nedvizhimost/kvartiry/dolgosrochnaya-arenda-kvartir/lvov/`) | httpx from the Mac, browser user agent | **403**, CloudFront "request could not be satisfied" |
| `/api/v1/offers/` and `/api/v1/locations/autocomplete/` | httpx | **403**, CloudFront |
| Same page | real browser (Claude desktop browser pane) | 200, 52 listing cards with numeric ids in `[data-cy="l-card"]` |
| `/api/v1/offers/?category_id=1760…` | `fetch` inside the browser page | 200, but 0 results with the guessed category and city ids |
| `/api/v1/offers/<id>/` (offer detail) | `fetch` inside the browser page | **403** |
| `/api/v1/offers/<id>/limited-phones/` | `fetch` inside the browser page, 1 listing | **200**, one phone returned. Whether the pane was signed in to OLX was not checked. |

The private/business flag and the user id were not confirmed, because the offer-detail call returned 403.

## What this means for phase 2

- **A plain HTTP poller** (the plan's httpx design) is blocked at the CDN. It would need a real browser (Playwright) or residential proxies. Both are things the spec defers.
- **Phone lookups through a browser** work for at least one listing. Running them every 45–60 s across all new Lviv listings means automated bulk collection of phone numbers, which OLX's terms of use forbid. That is a product and legal decision for the owner, not a technical one.
- **Recommendation:** keep phase 2 parked. Ship phase 1 (Telegram channels), then decide between:
  - (a) Playwright reading only listing text and the OLX user id, with no phone lookups, so stage 1 reputation uses `olx_user_id`;
  - (b) dropping OLX.

  The throwaway probe scripts stayed in the git-ignored `spikes/` folder.
