# ThisVid promo drip — ToS-aware notes

TBCC extension MVP uploads watermarked R2 URLs via the site uploader. Scheduled Celery mirror is Phase C.

## Rules

- **Rate:** max 1–2 uploads per day per account; stagger from Telegram/VIP fires.
- **Titles:** no `t.me`, `@aof`, or Telegram CTAs in titles or descriptions.
- **Media:** watermarked `telegram.me/aofmainhub` only; hub landing via gate, not bare invite.
- **Content:** operator-approved pool tags only — no auto-mirror of scraped/off-brand media.

## Kill switches

- Per-scheduler `erome_mirror_enabled` / future `thisvid_mirror_enabled`
- Extension: manual operator paste on `my_video_upload`

## Funnel exit

ThisVid teaser → gated hub (`aofmainhub` Linkvertise) → pinned VIP CTA on mainhub.
