# AOF Hub — Frontier Product + Engineering Plan (Plan/Ask)

**Date:** 2026-08-10
**Mode:** Plan / Ask only — no production code touched in this pass.
**Source task:** `tbcc/docs/handoffs/2026-08-10_aof-hub-frontier-plan-ask.md`
**Status:** Reviewed and cross-checked against the repo by a second pass (2026-08-10) — verdict **GO**, all file citations validated. Operator ACK'd all 5 decisions in §11 with the defaults below; see "Operator ACK log" at the end of this report.
**Verdict up front:** The operator's own status guesses in the task doc were almost all correct. The audit below confirms them file-by-file and adds four load-bearing findings the task doc didn't know about — the biggest being that **the tube's SEO plumbing is currently zero** (no metadata, no sitemap, every page force-dynamic, media URLs are 1-hour presigned links), which changes phase order more than anything else in this report. Second: **the TBCC↔forum ingest bridge (`from-telegram.ts`) is calling an API contract that doesn't exist** — wrong path, wrong pagination shape, wrong response envelope, and no `url` field to download from at all. Both are cheap to fix; both must move earlier than the original P7/P2 slotting implied.

---

## 1. Current-state audit (feature matrix, file-cited)

| Surface | Status | Evidence |
|---|---|---|
| App shell / nav | **Built**, brand = "AOF Hub" hardcoded | [`components/TopBar.tsx:9`](../../../aof-forum/components/TopBar.tsx), [`components/LeftNav.tsx`](../../../aof-forum/components/LeftNav.tsx) — no Live link anywhere in nav |
| Homepage | **Feed-first, not a hub launcher** | [`app/(site)/page.tsx`](../../../aof-forum/app/(site)/page.tsx) — `/` renders `HomeExploreRails` + Hot/New `MediaGrid` directly. There is no mode-switcher page above the feed. |
| Home rails | **Built**, gallery-only rails | [`components/HomeExploreRails.tsx`](../../../aof-forum/components/HomeExploreRails.tsx) — Hot/Most-viewed/Buzzing/Fresh galleries + a "Popular now" media strip. No Live rail, no Groups rail, no Telegram CTA strip. |
| Tube feed | **Built** | `MediaGrid`, `/api/feed`, `/m/[id]`, `Player.tsx` — confirmed live and wired to Supabase `media_items`. |
| Galleries — browse | **Built** | [`app/(site)/g/page.tsx`](../../../aof-forum/app/(site)/g/page.tsx), [`g/[slug]/page.tsx`](../../../aof-forum/app/(site)/g/[slug]/page.tsx), schema in [`supabase/migrations/0002_galleries.sql`](../../../aof-forum/supabase/migrations/0002_galleries.sql). |
| Galleries — create | **Not built. Confirmed missing, and the UI lies about it.** | `g/page.tsx:29` tells users *"No public galleries yet. Create one from any media page."* No media page, no route, no server action inserts into `galleries` anywhere in the repo (grepped `galleries.*insert` — only migration files match). Users who follow that copy hit a dead end today. |
| Groups | **Built, including create** | [`app/(site)/groups/new/page.tsx`](../../../aof-forum/app/(site)/groups/new/page.tsx) is a complete, working create-flow: slug validation, visibility enum, server action `insert` into `groups`, RLS-checked. **This is the exact pattern to clone for the gallery wizard (P3)** — it is not greenfield work. |
| Forum | **Built** | `app/(site)/f/`, schema `0003_forum.sql`. |
| Upload | **URL-queue only, no bulk browser UI** | [`app/(site)/upload/page.tsx`](../../../aof-forum/app/(site)/upload/page.tsx) — one URL input → `ingest_jobs` row → local worker polls and processes. Copy literally tells users to "drop into `C:\aof-media\inbox\`" for direct files — a local-machine-only path that does not exist for a real visitor. No drag-drop, no multi-file, no progress UI. |
| Ingest pipeline | **Built for local/URL, broken for Telegram** | [`workers/ingest/pipeline.ts`](../../../aof-forum/workers/ingest/pipeline.ts) — dHash dedupe, B2 upload, Stash handoff, all solid. But [`workers/ingest/adapters/from-telegram.ts`](../../../aof-forum/workers/ingest/adapters/from-telegram.ts) is broken against the real backend (see §8, P2). |
| Live cams | **Not built** — zero code, zero env vars. Confirmed by repo-wide grep for `awempire`/`livejasmin`/"cam model" — only hits are the task doc itself and unrelated extension username-search files. |
| Awempire integration | **Not built.** Same grep. |
| Styles | **Built** — dark noir + gold accent, coherent design tokens | [`app/globals.css`](../../../aof-forum/app/globals.css) — `--accent: #c9a227`, full component classes for cards/tabs/votes/forum already exist. Extend, don't replace. |
| TBCC Telegram ingest bridge | **Contract is wrong, not just unbuilt** | See §8 P2 — full breakdown. |
| SEO plumbing | **Zero.** No `app/sitemap.ts`, no `app/robots.ts`, no `generateMetadata` anywhere in the repo (grepped case-insensitively, zero files). Every page read (`/`, `/g`, `/g/[slug]`, `/t/[slug]`, `/u/[handle]`) declares `export const dynamic = "force-dynamic"`, including the one page built specifically to be an SEO landing (`/t/[slug]`). |
| Media URL delivery | **Presigned, 1-hour expiry, by default** | [`lib/media-url.ts`](../../../aof-forum/lib/media-url.ts) — `resolveMediaUrl()` only returns a stable public URL if `NEXT_PUBLIC_MEDIA_BASE_URL` is set (it's blank in `.env.example`); otherwise it mints a 1-hour `signedGetUrl`. Every page that renders media (including the tag/SEO page) currently ships expiring URLs. Uncacheable at the CDN, unstable for image search indexing, and will 403 in shared/screenshotted links after an hour. |
| RLS / quotas / moderation | **RLS exists for ownership, no quota or report/flag system** | [`supabase/migrations/0007_rls.sql`](../../../aof-forum/supabase/migrations/0007_rls.sql) — `media_insert_self`, `galleries_write_own` etc. are all "any authenticated user, unlimited rows." No per-user row-count or byte-quota constraint in schema; nothing analogous to a `reports` table in the migrations read. Quotas/moderation are app-level work, not present today. |
| `/t/[slug]` performer/tag SEO page | **Built functionally, but not indexable** (see SEO row above) | [`app/(site)/t/[slug]/page.tsx`](../../../aof-forum/app/(site)/t/[slug]/page.tsx) — has related-tag co-occurrence, follow button, media grid. Good bones, zero metadata. |
| `/u/[handle]` profile | **Built** | uploads + galleries tabs, follow button. |

### New finding: the TBCC↔forum bridge is not "missing," it's mis-specified

`from-telegram.ts:8-18` states its own contract as an *assumption*:
```
GET {TBCC_API_URL}/api/media?since_id=<n>&limit=50
-> { items: [{ id, source_channel, media_type, url, telegram_message_id, ... }, ...] }
```
The real backend route is [`backend/app/api/media.py:498`](../../backend/app/api/media.py), mounted at `/media` (not `/api/media`) in [`main.py:1245`](../../backend/app/main.py). It:
- Takes `before_id` (descending cursor), not `since_id` (ascending) — opposite pagination direction.
- Returns a bare JSON array (`orm_to_dict` per row), not `{ items: [...] }`.
- Has **no `url` field** — `Media` rows store `telegram_message_id` + `source_channel` ([`backend/app/models/media.py:12,16`](../../app/models/media.py)), and bytes are only reachable by streaming through `GET /media/{id}/file`, which pulls from Telegram live via Telethon (`FileReferenceExpiredError` import, `StreamingResponse`) — not a static, fetchable URL.
- Header mismatch: the adapter sends `X-Internal-Key` ([`from-telegram.ts:30`](../../../aof-forum/workers/ingest/adapters/from-telegram.ts)); every backend consumer (`payment_bot.py`, `loot_bot.py`, `link_resolver.py`, `internal_api_auth.py`) sends/expects `X-TBCC-Internal-Key`. Confirmed via [`internal_api_auth.py:69`](../../backend/app/middleware/internal_api_auth.py). **This is currently latent, not live-breaking:** `internal_api_auth.py:26-29` allowlists any GET under `/media/` as public (`_PUBLIC_GET_PREFIXES`), so today's `GET /media/` calls pass through regardless of the gate or header name — the mismatch is harmless against the *existing* route even with `TBCC_API_REQUIRE_INTERNAL=1` set. It becomes real the moment P2 adds an authenticated export route (mutating or scoped-read), which is exactly what P2 below proposes — so the header fix has to ship *with* that new endpoint, not be assumed already-correct.

None of this is hard to fix, but it means **P2 ("soft launch deploy + TBCC seed") is not a deploy step — it's a small new backend endpoint plus an adapter rewrite.** See §8.

**Additional P2 constraint — no static media URL exists to seed from.** [`backend/app/models/media.py:11-23`](../../backend/app/models/media.py) shows the `Media` row has no R2/B2/CDN key at all — only Telegram identifiers (`file_id`, `file_unique_id`, `telegram_message_id`). There is no shortcut to a static file URL; the only path to bytes is `GET /media/{id}/file`, which streams live through Telethon. Per memory (`tbcc-telegram-io-serialized`), **all Telegram I/O in TBCC is serialized behind one global lock** — the same lock the live bots (payment, loot, companion) depend on for responsiveness. A bulk forum seed pulling hundreds of rows through `/media/{id}/file` queues behind that lock and can starve bot responsiveness (this is the documented root cause of the "Could not load pools" timeout in other contexts). P2 must batch/throttle the seed (e.g. small batches with delay, off-peak scheduling) rather than pull in a tight loop — this is a hard constraint on the new export endpoint's design, not an optional nicety.

---

## 2. Product architecture

### 2.1 IA — one conflict to resolve now, not later

The task doc's locked IA lists both:
```
/                     Hub home (mission control — NOT just another feed clone)
/tube or /            Doom-scroll feed (Hot / New / For You)
```
Today `/` **is** the feed ([`page.tsx`](../../../aof-forum/app/(site)/page.tsx)) — there is no separate hub-launcher route. These two intents can't both own `/`. Recommendation: **`/` stays the feed** (it's the highest-traffic, lowest-friction entry point for a doom-scroll product, and it's what's actually built and working), and the "mission control" concept ships as a **top strip on the existing feed page** — a slim four-tile launcher (Live · Tube · Galleries · Upload) rendered above `HomeExploreRails`, not a new route competing for `/`. This preserves the Motherless-style "land on content immediately" promise while still giving Live/Galleries/Upload top billing on first paint. Revisit a dedicated `/` mission-control page only if analytics show feed-first hurts Live/Galleries discovery.

Revised IA (delta from task doc only):

```
/                     Feed (Hot/New/For You) + 4-tile mode strip + Telegram CTA strip
/live                 NEW — Awempire embeds ("online now")
/g                    Galleries browse (exists)
/g/new                NEW — create wizard (clone groups/new pattern)
/upload               Rebuild — bulk drag-drop + URL paste (exists as URL-only today)
/groups, /f           unchanged (built)
/t/[slug]             unchanged (built, needs metadata — see P1.5/SEO)
/m/[id], /u/[handle]  unchanged (built)
```

### 2.2 Hub homepage wireframe (text)

```
┌─────────────────────────────────────────────────────────┐
│ TopBar: AOF Hub | search | For You · Groups · Forum · ⬆ │
├─────────────────────────────────────────────────────────┤
│ [ 🔴 LIVE ]  [ 🎬 TUBE ]  [ 🖼 GALLERIES ]  [ ⬆ UPLOAD ]  │  ← 4-tile mode strip, new
├─────────────────────────────────────────────────────────┤
│ Telegram CTA strip: Loot Room · VIP · Companion  →t.me   │  ← new, thin, dismissible
├─────────────────────────────────────────────────────────┤
│ Hot | New | For You                    (existing tabs)   │
│ [ existing HomeExploreRails: galleries + hot media ]     │
│ [ existing MediaGrid feed ]                               │
└─────────────────────────────────────────────────────────┘
```

### 2.3 Three user journeys

1. **Doom-scroll visitor (SEO/organic).** Lands on `/t/[slug]` from a search engine (once indexable) → scrolls tag feed → media page → sees related tag rail → clicks a Telegram CTA on the media page footer → `t.me/aof_lootgod_bot?start=src_web_tag_<slug>`. Requires: metadata + stable URLs (P1.5) + a web→bot CTA that doesn't exist on `/m/[id]` yet (P8).
2. **"She's online" visitor (Live).** Lands on `/live` from Buffer/X/extension → sees Awempire embed grid → clicks through to Awempire (rev-share, beacon-wrapped per L0 in the monetization playbook) → separately, sees an AOF Telegram CTA in the same rail for users who bounce off the cam. Requires P5.
3. **Creator/UGC visitor (Galleries).** Signs in → `/g/new` (cloned from `groups/new`) → names a gallery → `/upload` bulk-adds media directly into it → shares `/g/<slug>` URL to their own audience → that URL needs to be stable and indexable to be worth sharing (ties back to P1.5). Requires P3 + P4.

---

## 3. Awempire integration plan (v1 only — embeds, not Video API)

**Scope for v1:** `/live` page with embedded cam widgets/deeplinks only. Do not host cams (doctrine #3). Defer Video Promotion API and Label4Editor to P9 — no account exists yet, and Module A's own finding (`photos_sold = 0` trailing 30 days, companion conversion "outranks the margin problem") says the highest-leverage work right now is proving *any* clearnet→Telegram conversion path, not adding a second content-generation integration.

- **P5 build:** static `/live` route, a `LiveEmbedGrid` component rendering Awempire iframe/widget embeds per the affiliate dashboard's promo-tools config (account required — operator step, not agent-buildable this pass).
- **Compliance:** every outbound Awempire link gets `promo_affiliate_beacon_wrap` treatment (L0 in the monetization playbook — attribution only, not a second gate) so it shows up in `revenue_by_source()` alongside gate/bot revenue instead of being invisible.
- **Beacon wrap:** reuse `click_beacon.py` + `promo_affiliate_links` seeding pattern already live for AI affiliates (`promo_affiliate_rotation.py`) — Awempire becomes a new `network_key`, not a new subsystem.
- **Do not build in this phase:** Video Promotion API ingestion, Label4Editor asset pipeline, "online now" polling (Awempire API access + rate limits unknown pre-account) — a static curated grid is the v1, refreshed manually or on a slow cron once an account exists.

---

## 4. Motherless void strategy

- **Non-goal, explicit:** do not mirror Motherless UGC at scale. `MOTHERLESS_TOS.md` caps any mirror at 1–2/day, watermarked, routed through the gated hub not bare `t.me`, and states plainly "no `motherless_mirror` service yet — extension intel only."
- **What's actually available today:** RSS-first intel via the extension (`SITE_INTEL_FRONTIER_PROMPTS.md` §3) — group/member/site feeds, normalized into the `platform:motherless` unified row, soft-weighted into `aggregate_tag_scores()`. This is a **ranking signal**, not a content source.
- **Hub's actual void-capture move:** the void isn't "missing Motherless content," it's "missing doom-scroll UX + groups + tags on the open web." AOF Hub already has that shape (Tube + Groups + `/t/[slug]`) — the strategy is to **fill it with owned/UGC inventory** (P2 seed from TBCC's existing pools + P4 bulk upload from real users), not scraped Motherless media. Intel stays confined to biasing which AOF lanes/tags get promoted, per the existing `Site intel frontier` doctrine — keep it there.
- **If/when Phase C (scheduled upload mirror) is ever revisited:** it is out of scope for this plan per the task's explicit OUT OF SCOPE list ("ML scrape-at-scale"). Flag, don't build.

---

## 5. Upload & gallery product spec

### Gallery create wizard (P3)
Clone [`groups/new/page.tsx`](../../../aof-forum/app/(site)/groups/new/page.tsx) almost verbatim: same slug-validation regex, same server-action pattern, insert into `galleries` instead of `groups` (schema already supports it — `owner_id`, `title`, `description`, `is_public`; RLS `galleries_write_own` already permits it). This closes the dead-end copy on `g/page.tsx:29` today ("Create one from any media page") — actual fix is simpler: add a real "New gallery" button in the `/g` page and on `/u/me`, pointing at `/g/new`.

### Bulk upload UX (P4)
Current `/upload` is a single URL textbox. Rebuild as:
- Drag-drop multi-file zone (client-side, using existing `@aws-sdk/s3-request-presigner` dependency already installed for B2 — presigned **PUT** URLs so large files upload direct-to-B2 from the browser, not proxied through the Next.js server).
- Keep the existing URL-paste queue (erome/bunkr/generic) as a second tab — it already works end-to-end via `ingest_jobs` → local worker.
- Progress UI per file (queued → uploading → processing → done/duplicate/failed), reusing the `ingest_jobs.status` state machine already in the schema.
- On completion, prompt "add to a gallery?" inline (dropdown of the user's own galleries + "new gallery" shortcut) — ties directly into P3.

### Quotas
Nothing exists today (§1 table). Recommend simple app-level counters, not new infra: a `daily_upload_bytes` / `daily_upload_count` check in the upload server action against `media_items` rows `where uploader_id = auth.uid() and created_at > now() - interval '1 day'`. Ship a generous default (operator decision — see §11) and tune from actual abuse, not speculative limits.

### Moderation
No `reports` table exists. Minimum viable: a `flags` table (`target_kind`, `target_id`, `reporter_id`, `reason`, `created_at`) + a "Report" button on `MediaCard`/`Player`, and a simple admin-only view (reuse the `profiles` table's implicit owner check, or add an `is_admin` boolean) to soft-delete (`media_items.is_deleted`, already a column per the RLS file). This is new schema work, sized for P4, not P0-P2.

---

## 6. Hosting & launch ladder

| Stage | What | Notes |
|---|---|---|
| Local (now) | Next.js `:3001` + local Stash + local ingest worker | Current state, per `README.md`. |
| Soft launch | Deploy web app, keep B2/Supabase (already cloud) | **Host conflict to resolve, not assume:** `aof-forum/README.md:11` says Vercel; `AOF_FORUM_DOMAIN.md:16` says Cloudflare Pages/Worker. Do not pick from memory — NSFW/adult-content acceptable-use posture differs by host and changes over time; this is operator decision #1 (§11). Plan the deploy so it isn't Vercel-locked: keep the app framework-agnostic (it already is — plain Next.js, no Vercel-only APIs used in the files read), so either target works once chosen. |
| Public beta | `api.<domain>` split live (per `AOF_FORUM_DOMAIN.md`), Cloudflare proxy on apex, TBCC bridge fixed (P2) | Gate: P1.5 (SEO/media URL fixes) done first, or public beta accumulates unindexed, expiring-URL pages from day one. |
| Hub v1 | Live + Galleries wizard + bulk upload + beacon-wrapped conversion live | Gate: P5–P8 done. |

**NSFW hosting note:** flag explicitly rather than assume — Cloudflare Pages and Vercel both have adult-content restrictions that shift; this needs an operator confirmation step before soft launch, not an agent guess baked into infra choice.

---

## 7. Design system brief

`app/globals.css` already has a coherent, shippable dark-noir + gold system: CSS custom properties for bg/fg/accent layers, card/tab/vote/forum component classes, a 4/3 media-card grid, tag-pill kind-coloring (performer/studio/category). **Extend, do not replace:**
- Add `--live-accent` (a distinct hot-pink/red, e.g. `#ff4a6b`) reserved only for the `/live` "online now" indicator and the 4-tile mode strip's Live tile, so Live reads as a different *mode* from Tube at a glance, consistent with the operator's per-mode promise table.
- Add a `.mode-strip` component class for the 4-tile launcher (§2.2) reusing existing `.card`/`.badge` primitives — no new visual language needed.
- Telegram CTA strip: thin bar using existing `--accent`/`--accent-2` gold tokens (already reads as "premium/gold" — matches Loot/VIP branding conventions visible in `tbcc/docs/samples/link_hub_menus/`).

**Three name/domain options** (operator decision #2, §11) — kept distinct from "AOF Hub" internal working title per task doc:
1. **AOF Hub** (keep as-is) — zero rename cost, already the on-page brand string in `TopBar.tsx:9`.
2. **The Vault** / similar noun that matches the gold/noir visual system already built.
3. Performer/tag-first brand (e.g. tied to the `/t/` SEO surface) — only worth it if SEO is the primary growth bet; adds naming risk if the operator later wants a broader identity.

---

## 8. Phased implementation (P0–P10, reordered)

**Note on P1.5's media-URL fix — not a one-line env change.** `resolveMediaUrl()` only skips the 1-hour presigned URL if `NEXT_PUBLIC_MEDIA_BASE_URL` is set ([`lib/media-url.ts:15-16`](../../../aof-forum/lib/media-url.ts)), but [`aof-forum/README.md:26`](../../../aof-forum/README.md) specifies the B2 bucket as **private**. Pointing `NEXT_PUBLIC_MEDIA_BASE_URL` at a private bucket just 403s every image. The real fix is a bucket-visibility decision: either (a) make the bucket public-read for media objects (simplest, but full B2 egress cost with no caching) or (b) put Cloudflare in front of the private B2 bucket with origin credentials (stable public URL, CDN caching, egress cost controlled) — option (b) is the one `AOF_FORUM_DOMAIN.md` already gestures at ("Cloudflare CDN added at launch only" per the README). This is coupled to the hosting decision (§11 decision #1) — folded in there rather than added as a separate operator decision.

**Reorder rationale (the one substantive change from the task doc's proposed order):** the task doc put "SEO pack" at P7 and "soft launch deploy + TBCC seed" at P2. The audit shows public content would go live with **zero metadata, zero sitemap, force-dynamic rendering, and 1-hour-expiring media URLs** (§1) — every page indexed between P2 and P7 is either unindexable or will 404/403 within an hour of being crawled. That's not a later polish pass, it's a precondition for P2 having any long-term value at all. Concretely: **move minimal SEO plumbing + a stable media URL strategy into P1.5**, run it in parallel with P2's backend-bridge fix (they touch different files and don't block each other).

| Phase | Scope | Files / env | Verification |
|---|---|---|---|
| **P0** | Name + domain + host decision | operator decision #1/#2 | Domain purchased, host AUP confirmed for NSFW |
| **P1** | Hub homepage + nav restructure | `app/(site)/page.tsx` (add 4-tile strip), `TopBar.tsx`/`LeftNav.tsx` (add Live link), new `.mode-strip` CSS | Manual click-through of all 4 tiles + Telegram CTA strip |
| **P1.5 (new)** | Indexability baseline | `app/sitemap.ts`, `app/robots.ts`, `generateMetadata` on `/t/[slug]`, `/g/[slug]`, `/m/[id]`; stable media URLs (see note below — not a config-only fix) | `curl` sitemap.xml, view-source metadata on `/t/[slug]`, confirm media `<img src>` doesn't expire on reload after 1hr |
| **P2** | TBCC bridge fix + soft-launch deploy | Backend: add a proper `GET /media/export` (or extend existing `GET /media/` with `since_id` + a `url`-bearing response, e.g. resolve to `/media/{id}/file`) with `X-TBCC-Internal-Key`; rewrite `from-telegram.ts` to match. Deploy per §6. | Adapter pulls N rows end-to-end into `media_items` without 401/403; spot-check 5 items render on `/m/[id]` |
| **P3** | Gallery create wizard | `app/(site)/g/new/page.tsx` (clone `groups/new/page.tsx` pattern), "New gallery" button on `/g` and `/u/me` | Create → item add → `/g/<slug>` loads publicly |
| **P4** | Bulk upload UI + quotas + moderation | Rebuild `app/(site)/upload/page.tsx`, new `flags` migration, presigned-PUT direct-to-B2 upload | Drag 10 files, confirm B2 objects + `media_items` rows + quota block at threshold |
| **P5** | `/live` Awempire embed POC | New route + `LiveEmbedGrid`; requires Awempire account (operator) | Embed renders, outbound click beacon-wrapped and shows in `revenue_by_source()` |
| **P6** | Performer bridge (intel → tag → live CTA) | Extend `/t/[slug]` with a "Live now" CTA when tag `kind=performer` and an Awempire mapping exists | Tag page shows Live CTA only for mapped performers |
| **P7** | Remaining SEO pack (structured data, OpenGraph images, canonical tags) | Builds on P1.5 baseline | Rich-result test passes on `/t/[slug]`, `/g/[slug]` |
| **P8** | Web monetization (beacons on media/gallery pages, gate wrap, bot deep links) | `/m/[id]` and `/g/[slug]` get a Telegram CTA footer with `?start=src_web_*`; wire to `click_beacon.py` | Beacon hit row created on click; `source_ref` resolves in `gate_funnel_report` |
| **P9** | Awempire Video Promotion API + Label4Editor | Deferred — no account, `photos_sold=0` says fix conversion basics first | N/A this pass |
| **P10** | Unified scoreboard | Reuse `revenue_by_source()` / `attributed_revenue_pct` — no Funnel.io | Dashboard shows web-sourced touches alongside existing gate/bot sources |

---

## 9. Traffic & metrics model (honest)

**Short-term (weeks):** owned distribution only — Telegram mainhub, Loot Room, X/Buffer, Reddit beacons, extension users pointed at `/live` or `/t/[slug]` links. Volume will be modest; the site has no existing inbound links or indexed pages to compound on (§1 SEO finding). Do not model organic traffic in week 1–4 projections.

**Long-term (months+):** SEO on tag/performer/gallery/forum pages **if and only if** P1.5 + P7 ship and content volume compounds — this is conditional, not automatic, exactly as the task doc's own framing requires. Google indexing lag for a brand-new domain is typically weeks-to-months even with perfect technical SEO; budget accordingly.

**Conversion is not yet proven, and the plan should say so plainly:** Module A's live probe found `photos_sold = 0` over the trailing 30 days on the companion bot, and the 16 wk31 gate beacons "receive zero traffic until each slug's destination is repointed" in Linkvertise (`2026-07-27_module-a-stack-architect.md`, Operator actions §). That means **P8's web→bot beacon wiring is necessary but not sufficient** — it depends on the operator finishing beacon repointing that's already outstanding from Module A, independent of anything this hub ships. Treat P8 as blocked on that operator step, not purely an engineering deliverable.

**30/60/90 KPIs (stated assumptions, not promises):**
- Day 30: P0–P4 shipped, soft launch live, 0 organic sessions assumed, 100% owned-distribution sessions. KPI: TBCC bridge (P2) pulling media with zero manual intervention for 7 consecutive days.
- Day 60: P5–P8 shipped. KPI: `attributed_revenue_pct` (existing north-star metric from Module A) includes a nonzero `web` source bucket for the first time.
- Day 90: P1.5/P7 SEO baseline had 30-45 days to get crawled. KPI: Search Console shows >0 indexed `/t/[slug]` pages (a floor, not a traffic target — indexing precedes ranking).

---

## 10. Copy pack

**Hub hero (mode strip context):**
> "Everything AOF, one door. Scroll the tube, catch her live, build your own gallery — all funneling home to Telegram."

**Upload promise:**
> "Drop in as much as you want. We handle storage, dedupe, and tagging — you just build."

**Live disclaimer (required near any Awempire embed):**
> "Live cams are hosted by our streaming partner, not AOF. Clicking through takes you to their site."

**Telegram CTA strip (3 variants, rotate):**
> "🪙 Loot Room live now — free daily pulls." · "🔞 VIP ladder — daily god-rolls, $18/mo." · "💬 Meet your companion — free trial reveal."

---

## 11. Risks, anti-patterns, operator decisions (≤5)

**Risks / anti-patterns:**
- Shipping P2 (public content) before P1.5 (SEO baseline) permanently burns the domain's first-crawl impression with Google — first-indexed-content quality matters disproportionately for a new domain.
- Treating `from-telegram.ts` as "just point it at the API" without fixing the contract mismatch (§1) will silently no-op forever — no error a human sees, just zero rows pulled.
- Building Awempire Video Promotion API (P9) before proving any clearnet→Telegram conversion (P8, currently unproven per `photos_sold=0`) repeats the doctrine violation flagged in Module A: "add VIP value to fix conversion" is listed there as an anti-pattern; adding *more integrations* before proving the *simplest* funnel works is the same mistake in a new location.
- Unlimited upload quotas (nothing in schema today) plus no moderation table (§5) is an abuse vector the moment `/upload` is public — ship P4's `flags` table and a basic quota together, not upload-first-moderate-later.

**Operator decisions (5, hard cap):**
1. **Hosting platform for NSFW at launch, plus media bucket visibility/CDN** — Vercel (per README) vs Cloudflare Pages (per `AOF_FORUM_DOMAIN.md`) have different, changing adult-content AUPs; needs an explicit confirm before P0/soft launch, not an assumption. Bundled in: public B2 bucket vs Cloudflare-fronted private B2 (§8 P1.5 note) — the two choices are coupled, since Cloudflare-as-host and Cloudflare-in-front-of-B2 are the same infra decision either way.
2. **Domain + brand name** — keep "AOF Hub," or one of the two alternates in §7.
3. **`/` = feed vs `/` = mission-control launcher** — this report recommends feed-with-mode-strip (§2.1); confirm or override.
4. **Awempire account timing** — P5/P6/P9 are blocked until an account exists; operator controls when that account gets created.
5. **Upload quota posture** — generous-by-default-and-tune-from-abuse (this report's recommendation, §5) vs conservative caps from day one.

---

## 12. Agent vs operator split

| Work | Owner |
|---|---|
| P1 hub homepage restructure, P1.5 SEO baseline, P2 backend endpoint + adapter rewrite, P3 gallery wizard, P4 upload rebuild + quotas/moderation schema, P7 SEO pack, P8 beacon wiring on web pages | **Agent** — all standard code changes against an existing, well-understood codebase |
| P0 domain purchase, host AUP confirmation, brand name pick | **Operator** — purchasing/legal decisions |
| P5/P6/P9 Awempire account creation, dashboard config, promo-tools setup | **Operator** — third-party account the agent cannot create |
| Module A's outstanding beacon-repointing in Linkvertise (blocks P8's real revenue signal, independent of this plan) | **Operator** — already flagged as outstanding in `2026-07-27_module-a-stack-architect.md`, not new to this report |
| P10 scoreboard | **Agent**, once P8 data exists to display |

---

## Summary for operator ACK

Confirmed-built: Tube, Forum, Groups (incl. create), Galleries (browse only), `/t/[slug]` and `/u/[handle]`, a solid dark-noir design system, and a working (if URL-only) upload pipeline. Confirmed-missing: Live/Awempire (zero code), gallery create UI (schema-ready, just needs the `groups/new` pattern cloned), bulk upload UI, and — the two findings that weren't in the task doc's own status guesses — **working SEO plumbing** and **a functioning TBCC↔forum media bridge**. Recommended change from the task doc's proposed phasing: pull SEO baseline forward into a new **P1.5**, running parallel to P2's bridge fix, because the original P7 slot would mean weeks of public, unindexable, expiring-URL pages before the fix ever landed. Everything else in the proposed P0–P10 ladder holds. Awaiting operator pick of phases per the 5 decisions in §11.

---

## Operator ACK log (2026-08-10)

Second-pass review confirmed all file citations and the P1.5 reorder rationale. Operator ACK'd all 5 decisions with defaults:

1. **Hosting + media CDN:** Cloudflare Pages + Cloudflare CDN in front of private B2 (report §8 option b) — not Vercel. Keeps `api.<domain>` on the same account as the revenue-island tunnel.
2. **Domain + brand:** keep "AOF Hub" working title; operator picks a TLD (`aofhub.com` / `aof-forum.com` / `altarofflesh.com` under consideration).
3. **`/` = feed vs mission control:** confirmed — `/` stays the doom-scroll feed, add 4-tile mode strip + Telegram CTA bar above existing rails (report §2.1), not a separate hub route.
4. **Awempire timing:** open account now, in parallel with P1/P1.5; P5 (`/live`) gated on account approval, not on soft launch. P8 (web→bot beacons) still gates Video Promotion API / Label4Editor (P9).
5. **Upload quota posture:** generous defaults (e.g. 50 files/day or 5GB/day, app-level counter not schema constraint), `flags` table ships with P4 not after, and public uploads default `is_public=false` until the user explicitly publishes a gallery.

**Approved next steps:** P1 (hub mode strip + Live nav link) and P1.5 (sitemap/robots/metadata + stable media URLs) start in parallel; P0 (domain, Cloudflare zone, B2/CDN visibility decision) is an operator step, not gated on P1/P1.5 starting. Hard gate: P1.5 must land before the site is publicly reachable (avoid burning first-crawl on expiring URLs / no metadata). Hard gate: P2's export endpoint must ship with the Telegram-I/O-lock batch throttle noted in §8 before the TBCC seed is called done.

**Open item carried over, not new to this report:** P8's real revenue signal still depends on the operator repointing the 16 wk31 gate beacons in Linkvertise, per the outstanding action in `2026-07-27_module-a-stack-architect.md` — independent of anything this hub ships.

---

## P1 + P1.5 implementation log (2026-08-10)

Operator confirmed implementation should happen in this session. Shipped, type-checked (`tsc --noEmit`, clean) and linted (`next lint`, clean):

**P1 — hub mode strip + Live nav**
- `components/ModeStrip.tsx` (new) — 4-tile launcher (Live/Tube/Galleries/Upload) per report §2.2, rendered above `HomeExploreRails` on `/`.
- `components/TelegramCtaStrip.tsx` (new) — 3-link conversion strip using the public loot CTA (`telegram.me/aof_lootgod_bot`, no `?start=`, per the SPRINT_STATE.md doctrine), `aofsubscriptions_bot`, `aof_spicybot_bot`.
- `app/(site)/live/page.tsx` (new) — placeholder route so the new nav link doesn't 404 ahead of P5's real Awempire embeds; carries the live-cam disclaimer copy from report §10 and a Telegram fallback CTA.
- `components/TopBar.tsx`, `components/LeftNav.tsx` — added "Live" link (styled with the new `--live-accent` token).
- `app/globals.css` — `--live-accent`/`--live-accent-2` tokens, `.mode-strip`/`.mode-tile`/`.live-dot`/`.cta-strip` classes, extending the existing design system per report §7 (no new visual language).
- `app/(site)/page.tsx` — wired `<ModeStrip />` + `<TelegramCtaStrip />` above the existing rails.

**P1.5 — indexability baseline**
- `app/sitemap.ts` (new) — static routes + tags (cap 1000, by `uses_count`) + public galleries (cap 500, by score) + public media (cap 2000, by score) + non-private groups (cap 300, by score). Caps keep it well under the 50k/sitemap limit at current content volume; revisit as a sitemap index only if any bucket grows past a few thousand rows.
- `app/robots.ts` (new) — allows all, disallows `/api/`, `/auth/`, `/upload`, `/bookmarks`; points at `/sitemap.xml`.
- `generateMetadata` added to `/t/[slug]`, `/g/[slug]`, `/m/[id]` — title, description, canonical, OpenGraph + Twitter card, cover/thumb image resolved through the existing `resolveMediaUrl()`. All three pages stay `force-dynamic`; metadata is still generated and injected server-side per request, which is sufficient for crawling (force-dynamic blocks static caching, not indexability).

**Explicitly not done — infrastructure, not code:** the presigned-1hr-URL problem (§1, §8 P1.5 note) is unchanged. `lib/media-url.ts`/`lib/b2.ts` already correctly prefer `NEXT_PUBLIC_MEDIA_BASE_URL` when set — there is no further app code to write. It stays inert until the operator finishes the P0 Cloudflare-in-front-of-B2 (or public-bucket) setup and sets that env var. Until then, OpenGraph/sitemap image URLs newly added in this pass will still be live but will expire after an hour, same as in-page images do today.

**Not run:** `next build` / dev server against live Supabase/B2. `sitemap.ts` and `generateMetadata` issue real SELECT queries through `createAdminClient()` (service-role); running a full build here would execute those against whatever Supabase project `.env.local` points at, which this session doesn't have visibility into (dev vs anything resembling prod) — left for the operator to smoke-test with `npm run dev` / `npm run build` locally.

**Second-pass corrections (post-implementation advisor review, same session):** the review caught four defects that `tsc`/`next lint` cannot see — all valid, all fixed, re-verified clean:
1. **`metadataBase` was missing** — `alternates.canonical` and relative OG image resolution in Next 14 fall back to `http://localhost:3000` without it. Added `metadataBase: new URL(NEXT_PUBLIC_SITE_URL ?? "http://127.0.0.1:3001")` to `app/layout.tsx`'s root metadata. Without this fix, production canonical tags would have pointed at localhost — the opposite of the P1.5 goal.
2. **`app/sitemap.ts` had no `revalidate`**, so Next would statically freeze it at build time — new galleries/media/tags would never enter the sitemap without a redeploy, undercutting the "compounding indexable pages" argument the whole P1.5 reorder rests on. Added `export const revalidate = 3600`.
3. **OG images on `/g/[slug]` and `/m/[id]` were unconditionally resolving through `resolveMediaUrl()`**, which falls back to a 1-hour presigned B2 URL when `NEXT_PUBLIC_MEDIA_BASE_URL` is unset. Telegram/X/Discord snapshot an OG image URL at share time and keep serving the cached (now-403'd) preview — worse than no image, and Telegram/X is the entire near-term distribution channel per §9. Both routes now only attach an `images` entry when `NEXT_PUBLIC_MEDIA_BASE_URL` is set. (`/t/[slug]`'s `cover_url` comes from Stash's `image_path` via `workers/stash-sync/index.ts:55`, not B2 presigning — a separate, pre-existing localhost-hosting risk, left as-is and out of this pass's scope.)
4. **Thin-content hygiene in the sitemap:** removed the content-free `/live` stub from `staticRoutes` (was sitting at priority 0.7, above real galleries/media) — resubmit once P5 ships real embeds. Added `.gt("uses_count", 0)` to the tags query so empty tag pages aren't submitted.

All four fixes are in the same files listed above; no new files. Re-ran `tsc --noEmit` and `next lint` after — both clean.

---

## P2 + P3 implementation log (2026-08-10, parallel)

Operator ACK'd parallel execution after P1/P1.5.

### P2 — TBCC media export + throttled forum seed

**tbcc/backend:**
- `app/api/media.py` — new `GET /media/export` (`since_id` ascending, `limit` capped 50, default `status=approved`, optional `pool_id`). Returns `{ items, next_since_id, count }` with `file_path: /media/{id}/file` per row.
- `app/middleware/internal_api_auth.py` — `/media/export` excluded from public `/media/` GET allowlist (requires `X-TBCC-Internal-Key` when gate on).
- `tests/test_media_export.py` — export shape + limit clamp + auth path tests.
- `tests/test_internal_api_auth.py` — `/media/export` not public.

**aof-forum:**
- `workers/ingest/adapters/from-telegram.ts` — full rewrite: calls `/media/export`, downloads bytes via `/media/{id}/file` with `X-TBCC-Internal-Key`, writes temp file → `ingestOne`, dedicated `tbcc://export-cursor` row for resume, `TBCC_EXPORT_BATCH_LIMIT` (default 10) + `TBCC_EXPORT_ITEM_DELAY_MS` (default 3000) throttle between items.
- `.env.example` — documents throttle env vars.

**Operator to verify P2:**
1. Island deploy backend (export route must be live on `TBCC_API_URL`).
2. Set `TBCC_INTERNAL_API_KEY` in aof-forum `.env.local` (same as TBCC).
3. Run ingest worker: `npm run ingest` (one-shot) or `npm run ingest:watch`.
4. Spot-check 5 items on `/m/[id]`; watch TBCC tray for Telegram lock contention — tune `TBCC_EXPORT_ITEM_DELAY_MS` up if bots lag.

### P3 — gallery create wizard

- `app/(site)/g/new/page.tsx` — clone of `groups/new` pattern: slug/title/description, public/private select, server action insert → redirect `/g/<slug>`.
- `app/(site)/g/page.tsx` — "New gallery" button; fixed dead-end empty state copy.
- `app/(site)/u/[handle]/page.tsx` — "New gallery" on own profile; private galleries visible only to owner; public filter for other profiles.

**Tests:** `pytest tests/test_media_export.py tests/test_internal_api_auth.py` — 5 passed. `aof-forum` `tsc` + `next lint` — clean.

**Not done:** attaching media to galleries post-create (P4 bulk upload), island deploy of export endpoint.

---

## P4 implementation log (2026-08-10)

**Bulk upload UI + quotas + moderation flags**

- `supabase/migrations/0010_flags.sql` — `flags` table + RLS (auth insert, admin read).
- `lib/upload-limits.ts` — daily file/byte quotas, per-file max, MIME allowlist.
- `lib/b2.ts` — `signedPutUrl`, `getObjectBuffer`.
- `lib/server/finalize-b2-upload.ts` — post-PUT finalize: head verify, dhash dedupe, `media_items` insert (`is_public=false` unless attached to public gallery), optional `gallery_items` attach.
- `app/api/upload/presign/route.ts` — presigned PUT URLs + quota gate.
- `app/api/upload/complete/route.ts` — batch finalize.
- `app/api/upload/galleries/route.ts` — gallery dropdown for upload attach.
- `app/api/report/route.ts` — flag content.
- `components/UploadPanel.tsx` — drag-drop, progress per file, Files | URL tabs, gallery picker.
- `components/ReportButton.tsx` — on media pages.
- `app/(site)/upload/page.tsx` — rebuilt around `UploadPanel`.
- `app/(site)/u/[handle]/page.tsx` — own profile shows private uploads + galleries.
- `app/globals.css` — upload dropzone + queue styles.
- `.env.example` — upload quota env vars documented.

**Operator:** run `npx supabase db push` (or apply `0010_flags.sql`) before using Report. B2 creds + `SUPABASE_SERVICE_ROLE_KEY` required for presign/complete.

**Verify:** sign in → `/upload` → drop 2–3 images → watch progress → links to `/m/[id]`; optional gallery attach; Report on media page.

**Tests:** `tsc --noEmit` + `next lint` clean.

---

## P5 + P7 + P8 + P6 implementation log (2026-08-10)

### P5 — `/live` Awempire embed POC

- `data/live-embeds.json` — embed slots + beacon slugs (operator fills `iframeSrc` / `outboundUrl` after Awempire approval).
- `lib/live-embeds.ts` — load embeds, `liveEmbedsConfigured()`, beacon-wrapped outbound URLs.
- `components/LivePageBody.tsx`, `LiveEmbedGrid`, `AwempireDisclaimer` — grid + setup hint when unconfigured.
- `app/(site)/live/page.tsx` — real page body (replaces thin stub).
- `app/globals.css` — live embed + conversion footer styles.
- `app/sitemap.ts` — re-adds `/live` only when `liveEmbedsConfigured()`.

### P7 — JSON-LD (partial)

- `components/JsonLd.tsx` — shared script injector.
- `app/(site)/m/[id]/page.tsx` — VideoObject / ImageObject when public.
- `app/(site)/g/[slug]/page.tsx` — ImageGallery.
- `app/(site)/t/[slug]/page.tsx` — CollectionPage.

**Remainder:** canonical/OG audit across forum routes; stable OG images still gated on P0 `NEXT_PUBLIC_MEDIA_BASE_URL`.

### P8 — Web conversion footers

- `lib/aof-cta.ts` — hub vs contextual CTAs; optional TBCC beacon slugs (`NEXT_PUBLIC_TBCC_BEACON_BASE`).
- `components/TelegramConversionFooter.tsx` — contextual footer on media, gallery, tag, live pages.
- `components/TelegramCtaStrip.tsx` — uses `hubCtas()` (loot stays bare on hub).
- `.env.example` — beacon slug env vars documented.

**Operator:** seed `web-live-*`, `web-vip`, `web-spicy` slugs in TBCC; finish Module A Linkvertise repointing for revenue signal.

### P6 — Performer bridge

- `data/live-embeds.json` — `performerMappings[]` (tag slug → embedId / outboundUrl / beaconSlug).
- `lib/live-embeds.ts` — `resolvePerformerLiveCta()`.
- `components/LivePerformerCta.tsx` — shows live CTA on `/t/[slug]` **only** when mapping resolves to a beacon-wrapped outbound URL.

**Operator:** add real performer slugs + Awempire room URLs as intel maps performers in the extension → forum tags pipeline.

**Tests:** `tsc --noEmit` + `next lint` clean after all of the above.
