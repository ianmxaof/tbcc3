# Site intel — frontier LLM decision prompts

**Date:** 2026-07-16  
**Status:** Answered + implemented (ext **1.40.8**, FetLife suite thin Intel tab).  
**Merge target:** `POST /analytics/erome-browse-intel` — unified row schema in `docs/erome-enhancer/MARKET_INTEL_ARCHITECTURE.md`.

## Grok answers (must-collect matrix)

| Site | Verdict | Must-collect (wired) | Defer | Non-goals |
|------|---------|----------------------|-------|-----------|
| **Erome** | Keep primary | Existing v4.2 + **duration-band tags** (`dur_*`) | Deeper timeseries UI | Silent prod uploads |
| **ThisVid** | Extend Intel tab | Grid: views, duration band, public/private, **uploader**; Meta→Save for content tags; Push | Friends-graph velocity, cross-site join keys | Private messaging, login-gated DMs |
| **Motherless** | RSS-first GO | RSS Load → `platform:motherless` rows (title, entity id, group/member tags, media type, pubDate age); Export + **Push** | Full grid DOM scanner | Bio/profile promo as intel |
| **FetLife** | Thin context GO | Opt-in Intel tab: hashtags/kinks/group/place from current page only; manual Push | Hover/profile Spyscope, media scrape | Bulk downloaders, paywall bypass, auto-follow as intel |

**Ranking:** `aggregate_tag_scores()` now defaults to **all platforms** and soft-weights rows without view counts (RSS/context). Erome-only callers still pass `platform="erome"`.

### How to gather (operator)

1. Keep island tunnel up: `.\scripts\revenue-island\dashboard-tunnel.ps1` (so `:8000` is VM API).
2. Reload extension **1.40.8**.
3. **Erome** — browse with likes/intel on (unchanged); Push from enhancer settings.
4. **ThisVid** — Intel tab → Record on → scroll grids / Scan → Push.
5. **Motherless** — RSS tab → pick feed → Load + record → Push to TBCC.
6. **FetLife** — overlay → Intel → enable Record → Scan this page → Push (never auto).

---

## Shared contract (prepend to every site prompt)

```
You are advising TBCC (Altar of Flesh / AOF) on browse-intel collection.

Goal: decide WHICH signals to scrape/record from this site so we can:
1) rank AOF Telegram pools (tag / format / velocity overlap),
2) feed weekly market-intel cycle + content_signals,
3) bias upload/promo policy (Erome upload hints, ThisVid upload fill, X/Buffer surface).

Hard rules:
- Prefer passive DOM / RSS / public JSON already on the page over aggressive crawling.
- No bulk album downloaders, paywall bypass, or ToS-hostile automation in the recommendation.
- Normalize every recommended field into the unified market-intel row when possible:
  platform, captured_at, entity_id, entity_url, views, score/likes, comments,
  engagement_bps, tags[], format_bucket, uploaded_at_approx_days_ago,
  views_per_day_proxy, uploader, is_uploader_verified, media_sequence[], context{}.
- Output MUST be structured:
  A) Must-collect (wire this sprint)
  B) Nice-to-have (defer)
  C) Explicit non-goals
  D) Collector shape (extension tab / RSS / Playwright / backend probe)
  E) Ranking use (how AOF pools / growth hub consume it)
  F) Risk notes (rate limit, login wall, PII)
```

---

## 1) Erome — paste prompt

```
SITE: erome.com
ROLE TODAY: Primary market collector (Enhancer v4.x browse-intel + Pareto overlay).
ALREADY SHIPPED (do not reinvent): views, likes, tags, duration, format_bucket,
uploader, age/velocity proxies, media_sequence, JSONL export, POST to TBCC,
pool rank boost via TBCC_EROME_BROWSE_INTEL_RANK, weekly market-intel cycle.

Decide the NEXT intel slice only:
- What missing fields most improve tag→pool mapping and upload_policy hints?
- Which page contexts matter (explore / search / user / album)?
- Should we deepen velocity timeseries vs broaden tag coverage?
- How should Erome intel stay authoritative vs Reddit probe / Buffer metrics?

Respect docs/EROME_TOS.md — prefer staging flags over silent prod uploads.
Return A–F per shared contract.
```

### Answer (implemented)

- **A)** Duration-band tags on snapshots; keep page_context search_query.
- **B)** Richer timeseries dashboard.
- **C)** Prod auto-upload from intel alone.
- **D)** Existing enhancer + transport overlay.
- **E)** Tag overlap → `rank_pool_media`; upload_policy still Erome-filtered.
- **F)** Rate limits on like-count fetches — already gated.

---

## 2) ThisVid — paste prompt

```
SITE: thisvid.com
ROLE TODAY: Extension enhancer with Intel tab (Erome-parity).
ALREADY SHIPPED: grid scan → platform:thisvid rows (views, duration, private/public
format_bucket, title, entity_url); JSONL export; POST to same
/analytics/erome-browse-intel ingest; Meta→Save tag enrich on watch pages;
infinite scroll; upload fill from R2 library.

Decide WHAT intel to prioritize next for AOF flywheel:
- Uploader / member graph signals (friends, public_videos velocity) vs tag quality?
- Privacy mix (public vs private) as a ranking feature?
- Duration bands that predict Telegram album performance?
- Cross-post signals (same creator on Erome/Motherless) — worth a join key?
- What should NOT be scraped (login-gated private, messaging, etc.)?

Return A–F. Prefer extending the existing Intel tab + ingest URL over a new backend crawler.
```

### Answer (implemented)

- **A)** Uploader from card DOM; `dur_*` + public/private tags on grid scan.
- **B)** Friends-graph velocity; cross-site creator join.
- **C)** Messaging / private gallery crawls.
- **D)** Intel tab Scan + auto mutation scan + Push.
- **E)** Duration/privacy tags merge into multi-platform tag scores.
- **F)** Uploader missing on some card layouts — Meta→Save still fills.

---

## 3) Motherless — paste prompt

```
SITE: motherless.com
ROLE TODAY: Extension enhancer (Hide, Width rails, RSS tab reading native feeds).
ALREADY SHIPPED: group/member/site RSS discovery + load in overlay; no full
browse-intel JSONL → TBCC parity yet (gap vs Erome/ThisVid).

Decide the intel strategy for Motherless specifically:
- Is RSS (groups/members/uploads/favorites) enough for market signal, or do we
  need grid DOM intel like Erome?
- Which feeds map to AOF lanes (big tits, ass, AI, boy, etc.)?
- Worth recording: title, media type (image/video), group slug, member id,
  pubDate velocity — anything else?
- How to normalize Motherless entities into the unified row (platform:motherless)?
- Bio/profile promo is distribution, not intel — keep out of collector scope.

Return A–F. Bias toward RSS-first (already on-page) before building a second
browse-intel scanner.
```

### Answer (implemented)

- **A)** RSS-first: Load records rows with explicit `album_id`, group/member tags, format, pubDate age; Export + Push.
- **B)** Grid DOM scanner.
- **C)** Bio scrape as market intel.
- **D)** RSS tab controls (record checkbox, ingest URL, Push).
- **E)** Soft-weighted tags (no views) in `aggregate_tag_scores`.
- **F)** Feed may return HTML if logged out — surface error, don't invent rows.

---

## 4) FetLife — paste prompt

```
SITE: fetlife.com
ROLE TODAY: FetLife Suite (masonry, gender/ASL filter, infinite scroll, place-nav,
privacy console, social-proof overlay). Survey: docs/FETLIFE_MOD_SURVEY.md.
ALREADY SHIPPED: browser UX / operator tooling — NOT a market-intel collector.
EXPLICIT NON-GOALS from survey: bulk album downloaders, paywall bypass,
auto-follow bots outside gated TBCC controls.

Decide whether FetLife should contribute market-intel at all, and if so WHAT:
- Safe signals only: public discussion tags? event attendance themes? kinkster
  place/ASL aggregates from pages the operator already browses?
- Is social/growth intel (who engages with AOF-adjacent communities) more valuable
  than media tag intel?
- Hover/profile intel (age/sex/role) — rebuild vs skip (Spyscope risk)?
- Should FL stay "operator CRM / filter" with ZERO POST to browse-intel?

Return A–F with a clear GO / NO-GO on feeding /analytics/* from FetLife.
Default bias: NO-GO on media scrape; optional thin "context tags" only if
privacy + ToS risk is low.
```

### Answer (implemented)

- **GO (thin only):** context tags from current page; **NO-GO** media scrape.
- **A)** Opt-in Intel tab; Scan → `platform:fetlife` `format_bucket:context_page`; manual Push.
- **B)** ASL aggregates, event themes.
- **C)** Spyscope hover rebuild; photo bulk extract as intel.
- **D)** Suite overlay Intel page (default Record OFF).
- **E)** Weak tag presence signal only.
- **F)** PII — do not store profile ASL/sex; tags/group/place only.

---

## Operator checklist

1. Diff answers → one sprint slice per site (must-collect only). ✅
2. Wire collectors to unified row + `platform` field. ✅
3. Tests: `tests/test_erome_browse_intel.py` (+ thisvid/motherless/fetlife). ✅
4. Island dashboard: `.\scripts\revenue-island\dashboard-tunnel.ps1` for `:8000`.
