# ThisVid promo drip — ToS-aware notes

TBCC extension MVP fills the `my_video_upload` form from watermarked R2 URLs (operator still
clicks Submit). `backend/scripts/thisvid_upload_local.py` is the automated Playwright leg —
one operator-approved `--source-url` per run, private-first, gated by its own kill switch and
ledger (separate from Erome's — see `thisvid_upload_policy.py`). Scheduled Celery mirror is
still a later phase.

**Selectors are unconfirmed.** `thisvid_upload_flow.json` ships with best-guess locators.
Run `py scripts/thisvid_codegen.py --codegen` once against the live, logged-in upload.php
page and copy the real locators into `thisvid_upload_flow.local.json` before trusting
`--execute` beyond a single supervised headed run.

## Rules

- **Rate:** max 1–2 uploads per day per account; stagger from Telegram/VIP fires. Enforced by
  `TBCC_THISVID_MAX_UPLOADS_PER_DAY` (default 1) / `TBCC_THISVID_MIN_INTERVAL_MINUTES` (default 1440).
- **Titles:** no `t.me`, `@aof`, or Telegram CTAs in titles or descriptions. Enforced as a hard
  policy block (not a warning) — the watermark carries the CTA, not the copy.
- **Media:** watermarked `telegram.me/aofmainhub` only; hub landing via gate, not bare invite.
  The uploader does not watermark — feed it an already-watermarked source URL (R2 / `media.powercore.app`
  confirmed working; Erome-hosted direct links untested — referer/expiry may block ThisVid's fetch).
- **Content:** operator-approved pool tags only — no auto-mirror of scraped/off-brand media.
  `thisvid_upload_local.py` only accepts an explicit `--source-url`; it never pulls from
  browse-intel or any scrape table.

## Kill switches

- `TBCC_THISVID_MIRROR_ENABLED=0` (default) — hard-blocks `--execute` / any policy-checked call
  until explicitly flipped on. `--force` bypasses rate/kill-switch blocks only, never the TOS blocks.
- Extension: manual operator paste on `my_video_upload` (unchanged, still available as a fallback).

## Ramp / governance

New uploads default to **private** (`--public` to override) so a bad title/tag can be caught
before the video is discoverable — same shape as the Erome private-staging pattern. Ledger at
`.tbcc-run/thisvid-analytics/upload_ledger.jsonl`; `--list-pending` shows videos awaiting a
manual promote-to-public pass (no automated promote step yet).

## Funnel exit

ThisVid teaser → gated hub (`aofmainhub` Linkvertise) → pinned VIP CTA on mainhub.
