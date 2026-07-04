# Erome Terms of Service — TBCC compliance reference

Source: user-provided Erome platform rules (2026). Keep this file updated when Erome revises policy.

**TBCC stance:** Erome is for **view-monetized teaser galleries**. Do **not** treat album descriptions or profile fields as an advertising surface. Route hub, Telegram, X, and affiliate links through **X captions**, **Telegram promos**, and **AllMyLinks** — not Erome album text.

---

## Prohibited uploads

| Category | Rule |
|----------|------|
| **Copyright** | Content you do not have the rights to display. |
| **Age / minors** | Minor appearance, titles implying minor, drawings/hentai representing minors. |
| **Doxing** | IDs, full name (non-famous), social media (non-famous), work info, address. Revenge porn strictly forbidden. |
| **AI / deepfakes** | Non-consensual AI-generated content strictly forbidden. |
| **Omegle / random chat** | Strangers without clear consent. |
| **Zoo / animal** | Not allowed. |
| **Real violence** | Not allowed. |
| **Excrement** | Not allowed. |
| **Advertising** | **No advertising watermark.** **No mention** of the full version available elsewhere (profile, website, Telegram, etc.). |
| **Tribute / solo male / sissy** | Profile or album must be **private** if it contains this content. |

---

## Your content & enforcement

- You own your content; it must comply with applicable law.
- Illegal, harassing, harmful, or offensive content → **account deleted without notice**.
- Erome cooperates with law enforcement and may disclose private information for illegal uploads or at LEA request.

---

## TBCC operational rules (derived)

### Do on Erome

- Watermarked **teaser** media only (see watermark section below).
- Neutral or search-friendly **titles** and **tags** (no `@handles`, no `t.me/…`, no “full pack on Telegram”).
- **Private** albums when content category requires it (tribute / solo male / sissy).
- Track views via `erome_view_sync` / upload ledger.

### Do not on Erome

- **Profile or album description links** promoting Telegram, X, AllMyLinks, gates, or affiliates.
- **Advertising watermarks** (brand CTAs, URLs, “subscribe @…” burned into media).
- **Title promos** like `t.me/aofmainhub` (TOS advertising risk — use neutral titles).
- Full-resolution or ungated content (keep full packs on Telegram / MEGA behind gates).

### Watermark (current practice vs TOS)

Erome forbids **advertising watermarks**. TBCC default `TBCC_EROME_WATERMARK=1` applies a small (~0.24 scale) mark. This is **compliance gray area** — you have been using it without consistent enforcement, but it is **not guaranteed safe**. Prefer:

- Minimal opacity, no URLs or @handles in the burn.
- Or disable for Erome (`TBCC_EROME_WATERMARK=0`) and rely on platform-native teaser length/crops.

Policy warnings: `erome_upload_policy.scan_title_for_tos()`, `scan_description_for_tos()`.

### Closed loop (X ↔ Erome) — TOS-safe pattern

```
X tweet     → SFW promo image + Erome album URL in tweet text (not in Erome description)
Erome album → teaser media + neutral title/tags only
Telegram    → full content + Linkvertise gates + hub links
Erome desc  → leave empty or generic (no outbound promo)
```

---

## Related env / code

| Item | Location |
|------|----------|
| Upload preflight | `app/services/erome_upload_policy.py` |
| Playwright upload | `app/services/erome_upload_provision.py` |
| Telegram → Erome ingest | `app/services/erome_telegram_ingest.py` |
| Promo copy (Telegram, not Erome desc) | `app/services/erome_promo_wire.py` |
| View sync | `app/services/erome_view_sync.py` |
