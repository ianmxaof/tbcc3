# AOF Hub (aof-forum) — Claude Code Frontier Plan/Ask Handoff

**Date:** 2026-08-10  
**Mode:** Plan / Ask first — **do not implement** until plan is written and operator picks phases.  
**Reverse report:** `tbcc/docs/handoffs/2026-08-10_aof-hub-frontier-plan-ask_report.md`  
**Source:** Cursor Frontier session — unified web hub (tube + live cams + galleries + bulk upload) as THE AOF website.

---

## Paste block (Claude Code)

```text
You are advising on TBCC / AOF in repo `telegram_bot2`. Primary greenfield surface: `aof-forum/` (Next.js 14 hub). Secondary integration surface: `tbcc/` (FastAPI ingest, bots, extension intel, monetization).

## MODE: PLAN / ASK ONLY (this session)

Do NOT edit production code in this pass unless the operator explicitly says "implement phase N" after you deliver the plan.

Your job: read the codebase + docs, validate assumptions against real files, and deliver a **shippable product + engineering plan** for THE AOF website — a unified clearnet hub folding tube, live cams (affiliate), user galleries, bulk upload, forum/community, and Telegram conversion.

When done, write:
`tbcc/docs/handoffs/2026-08-10_aof-hub-frontier-plan-ask_report.md`
Then STOP for operator ACK.

---

## OPERATOR VISION (locked intent — plan must align, flag conflicts)

Build **one website** that is the clearnet home for the AOF network:

| Mode | User promise | Monetization |
|------|--------------|--------------|
| **Tube** | Doom-scroll owned media (Motherless-style) | SEO, retention, gates → Telegram |
| **Live** | Find cam models / "she's online" | Awempire / LiveJasmin rev-share (do NOT host cams) |
| **Galleries** | "Make your own" — upload tons, don't worry about storage | UGC moat, shareable URLs, social distribution |
| **Community** | Forum + groups folded in, not a separate product | Engagement, return visits |
| **Conversion** | Every surface routes to owned bots (loot, VIP, companion) | Stars, subs, keys — primary $ |

**Working title:** "AOF Hub" (not final — operator may rename domain/brand).

**Strategic partners referenced (not literal product purchases):**
- Awempire affiliate stack: dashboard, promo tools, video promotion API, Label4Editor
  - https://auth.awempire.com/dashboard
  - https://auth.awempire.com/promo-tools
  - https://auth.awempire.com/video-promotion-api
  - https://label4editor.awempire.com/
- Funnel.io = **measurement pattern only** (unified marketing data). TBCC already has Zeus click beacons, gate funnel, analytics — do NOT recommend buying Funnel unless paid-acquisition scale justifies it.

**Motherless context:** motherless.com is effectively gone / dying. Operator wants action: capture the UX void (doom-scroll, groups, tags) with **owned inventory + UGC**, NOT mirror ML uploads (ToS/legal). TBCC extension already does RSS-first Motherless intel push (`platform:motherless`).

**Traffic expectations (plan must address honestly):**
- **Short-term (weeks):** owned distribution — Telegram mainhub, Loot Room, X/Buffer, Reddit beacons, extension users. Modest volume until content + URL exist.
- **Long-term (months+):** SEO on tag/performer/gallery/forum pages IF content volume + indexing compound. Not automatic on empty launch.

---

## STRATEGIC FRAME (locked — plan must align)

### Three-layer network (one identity)

```
Discover (web hub, X, extension intel)
    → Intent match (performer tag, lane, live?)
        → Monetize (Awempire live OR gated tube OR Telegram bots)
```

### Doctrine (do not violate)

1. **Telegram owns conversion** — web hub is top-of-funnel + SEO + UGC; loot/VIP/companion bots are cash register.
2. **One click = one primary gate** per `tbcc/docs/MONETIZATION_STACK_PLAYBOOK.md` — no nested lockers, no fake continue buttons.
3. **Do not host live cams** — Awempire embeds/deeplinks only.
4. **Do not mirror Motherless UGC at scale** — intel feeds seeding; slow drip only per `tbcc/docs/MOTHERLESS_TOS.md` (1–2/day max if ever).
5. **Do not build a second shop engine** — extend existing bots/APIs.
6. **Never spawn live Telegram bots, touch operator `.env`, or commit secrets** from this planning pass.
7. **API split:** public SEO site on apex domain; TBCC API on `api.<domain>` per `tbcc/docs/AOF_FORUM_DOMAIN.md`.

### Proposed IA (validate + refine in plan)

```
/                     Hub home (mission control — NOT just another feed clone)
/tube or /            Doom-scroll feed (Hot / New / For You)
/live                 Live cams (Awempire widgets + "online now")
/g or /galleries      Browse user galleries
/galleries/new        "Build yours" wizard
/upload               Bulk upload (drag-drop + URL paste)
/groups               Communities
/f or /community      Forum
/t/[slug]             Tag/performer SEO landing (+ live CTA if performer)
/m/[id]               Media player
/u/[handle]           Profile
```

Hub homepage concept: section launcher with rails — Live · Tube · Galleries · Upload — plus Telegram CTA strip (loot, VIP, companion).

---

## READ FIRST (in order)

1. `aof-forum/README.md` — stack, local dev, what's built
2. `tbcc/docs/AOF_FORUM_DOMAIN.md` — domain + API split + Cloudflare
3. `tbcc/docs/MONETIZATION_STACK_PLAYBOOK.md` — beacon → gate → bot → affiliate layers
4. `tbcc/docs/MOTHERLESS_TOS.md` — ML promo rules
5. `tbcc/docs/SPRINT_STATE.md` — in flight, do not touch
6. `tbcc/docs/handoffs/SITE_INTEL_FRONTIER_PROMPTS.md` — extension intel → pool bias
7. `tbcc/docs/handoffs/2026-07-27_module-a-stack-architect.md` — revenue stack spine (context)

---

## KEY CODE PATHS — aof-forum (validate what exists vs aspirational)

| Area | Paths | Status to verify |
|------|-------|------------------|
| App shell / nav | `aof-forum/app/(site)/layout.tsx`, `components/TopBar.tsx`, `components/LeftNav.tsx` | Generic "AOF Hub" brand; no Live section |
| Homepage | `aof-forum/app/(site)/page.tsx`, `components/HomeExploreRails.tsx` | Feed-first; rails exist but not hub launcher |
| Tube feed | `MediaGrid`, `/api/feed`, `/m/[id]`, `Player.tsx` | Built |
| Galleries | `app/(site)/g/page.tsx`, `g/[slug]/page.tsx`, `supabase/migrations/0002_galleries.sql` | Browse built; **create wizard unclear** |
| Groups | `groups/`, `0004_groups.sql` | Built |
| Forum | `app/(site)/f/`, `0003_forum.sql` | Built |
| Upload | `app/(site)/upload/page.tsx` | URL queue only; local inbox path documented; **no browser bulk UI** |
| Ingest pipeline | `workers/ingest/pipeline.ts`, `workers/ingest/index.ts`, adapters | B2, dhash dedupe, Stash sync; 3 adapters (local folder, job queue, telegram) |
| Stash sync | `workers/stash-sync/`, `lib/stash.ts` | Tag backfill |
| Storage | `lib/b2.ts`, `lib/media-url.ts` | B2 S3-compatible |
| Auth | Supabase magic link, `middleware.ts`, `0001_init.sql` profiles | Built |
| Reco | `lib/reco/`, `0006_reco.sql`, `0008_reco_functions.sql` | Related panels, for-you |
| Styles | `app/globals.css` | Dark noir + gold accent — align with AOF Link Hub menus |
| SEO / metadata | `app/layout.tsx` | Minimal metadata today |
| Live cams | — | **Not built** |
| Awempire integration | — | **Not built** |
| TBCC telegram ingest | `workers/ingest/adapters/from-telegram.ts` | Poll tbcc for captured media |
| Deploy docs | README "Vercel (launch)" + `AOF_FORUM_DOMAIN.md` Cloudflare Pages | Operator choice |

## KEY CODE PATHS — tbcc integration (read-only for plan)

| Area | Paths | Hub relevance |
|------|-------|---------------|
| Network map | `tbcc/backend/app/data/aof_network.py` | Lane keys, mainhub, loot room, VIP |
| Growth hub / storage deposit | `tbcc/backend/app/services/aof_growth_hub.py`, `storage_topic_deposit.py` | Forum topics → pool imports |
| Extension intel | `tbcc/extension/gallery.js` (livejasmin, motherless in trace hints), `SITE_INTEL_FRONTIER_PROMPTS.md` | Performer extraction, ML RSS |
| Click beacons | `tbcc/backend/app/services/click_beacon.py`, Zeus `/r/{slug}` | Attribute web → bot |
| Affiliate rotation | `tbcc/backend/app/services/promo_affiliate_rotation.py`, seed scripts | AI affiliates today; cam TBD |
| Link hub menus | `tbcc/docs/samples/link_hub_menus/`, `creative_prompt_catalog/link_hub_menus.json` | Visual brand reference |
| Crawler / ingest API | `tbcc/backend/app/api/import_.py`, crawler routes | Feed aof-forum via internal API |
| R2 / media | `TBCC_R2_BUCKET=aof-media` in sprint state | May overlap B2 — plan should pick canonical storage |
| Domain env | `tbcc/infra/env.revenue-island.example` | `api.<aof-forum-domain>` |

---

## GAP ANALYSIS TO PRODUCE (required)

Compare operator vision vs repo reality:

1. **Hub homepage** — feed clone vs mission-control launcher
2. **Bulk upload UX** — "drop 500 files, don't worry" vs URL-only + Windows folder path
3. **Gallery builder** — "make your own" wizard vs browse-only galleries
4. **Live cam section** — Awempire embed strategy (account, compliance, 2257, geo)
5. **Motherless replacement** — content seeding from TBCC pools vs user UGC vs intel-only
6. **SEO** — sitemap, meta, tag pages, indexing blockers for NSFW
7. **Hosting** — local dev vs Cloudflare Pages vs Vercel vs island worker for ingest
8. **Storage economics** — B2 costs, per-user quotas, dedupe story
9. **Brand** — name, domain, visual system vs existing AOF noir/gold
10. **Traffic plan** — short vs long horizon with realistic numbers and dependencies
11. **Monetization wiring** — where gates/beacons/bots attach on web (not just Telegram)
12. **TBCC ↔ forum sync** — single media canonical store or dual (R2 vs B2)?

---

## PLAN DELIVERABLES (required in report)

### 1. Current-state audit
- Feature matrix: built / partial / missing (with file evidence)
- What works locally today without operator secrets
- Blockers to public URL (domain, Supabase, B2, ingest worker hosting)

### 2. Product architecture
- Final recommended IA (sitemap)
- Hub homepage wireframe (ASCII or structured sections)
- User journeys (3): casual browser, gallery creator, live-intent visitor
- How tube + live + galleries + forum interlink (performer tag as join key)

### 3. Awempire integration plan
- Account/compliance checklist
- v1 embed surfaces (`/live`, performer tag pages)
- Video Promotion API + Label4Editor — phase 2+ or v1?
- Beacon wrap pattern for outbound cam links (align with `click_beacon`)
- What NOT to build (hosted rooms, custom player)

### 4. Motherless void strategy
- Seeding plan from TBCC ingest (volume targets for SEO)
- Extension intel → forum tag seeding workflow
- Explicit non-goals (mirror, scrape-at-scale)
- Optional slow-drip policy if operator insists

### 5. Upload & gallery product spec
- Bulk upload UX (drag-drop, progress, retry, quotas)
- Gallery wizard steps (create → add media → publish → share)
- "Don't worry about it" operator story (dedupe, storage, moderation)
- Moderation / public visibility gates

### 6. Hosting & launch ladder

| Stage | What ships | Where hosted | Operator vs agent |
|-------|-----------|--------------|-------------------|
| Local | dev loop | localhost:3001 | — |
| Soft launch | seeded content, Telegram links | ? | pick stack |
| Public beta | real domain, sitemap | Cloudflare Pages + Supabase + B2 CDN | |
| Hub v1 | live + bulk upload + brand | | |
| SEO compound | tag pages, volume | | |

Recommend: Cloudflare Pages vs Vercel vs other — with NSFW/policy notes.

### 7. Design system brief
- Typography, color (extend `globals.css` gold/charcoal), density
- Component priorities (cards, rails, live badge, upload dropzone)
- Reference: Link Hub menu aesthetic in `tbcc/docs/samples/link_hub_menus/`
- Name/domain recommendations (3 options with tradeoffs)

### 8. Phased implementation plan (numbered, independently shippable)

Proposed starter priority (reorder if audit disagrees):

| Phase | Scope | Effort | Owner |
|-------|-------|--------|-------|
| P0 | Name + domain + Cloudflare zone decision doc | S | operator |
| P1 | Hub homepage + nav restructure (Live/Tube/Galleries/Upload/Community) | S–M | agent |
| P2 | Soft launch: deploy Next.js + Supabase + seed from TBCC | M | agent + operator |
| P3 | Gallery create wizard + bulk attach API | M | agent |
| P4 | Browser bulk upload UI → existing ingest pipeline | M–L | agent |
| P5 | `/live` Awempire embed POC | M | agent (post affiliate approval) |
| P6 | Performer bridge: extension intel → forum tags → live CTA | M | agent |
| P7 | SEO pack (sitemap, meta, structured data, tag landings) | M | agent |
| P8 | Web monetization (beacon CTAs, gate links on outbound, bot deep links) | M | agent |
| P9 | Video Promotion API + Label4Editor batch creatives | L | Lane C grind |
| P10 | Unified scoreboard (Awempire + Zeus + bot — no Funnel.io) | S | agent |

For each phase: files to touch, new migrations, env vars, tests, operator-only steps, rollback, verification command.

### 9. Traffic & metrics model
- Short-term sources (Telegram, X, Reddit, extension) — realistic ranges, assumptions stated
- Long-term SEO levers — content volume thresholds, indexing risks for adult
- 30/60/90 day KPIs (sessions, uploads, galleries created, cam clicks, bot starts from web)
- What "success" looks like at each milestone

### 10. Copy pack (web + Telegram cross-links)
Draft ready-to-use:
- Hub homepage hero + section blurbs
- Upload page promise ("drop files, we handle the rest")
- Gallery CTA
- Live section disclaimer + affiliate disclosure
- Telegram conversion strip (loot, VIP, companion — use live bot URLs from `aof_network.py`)
- Mainhub pin copy pointing to clearnet hub

### 11. Risks, anti-patterns, open questions

**Anti-patterns to flag:**
- Empty launch expecting Google traffic
- Buying Funnel.io before paid acquisition exists
- Hosting cam streams yourself
- Dual canonical media stores (R2 + B2) without migration plan
- Nested link gates on web outbound
- Building full forum moderation suite before MVP

**Open questions for operator (max 5, prioritized):**
- Domain/name pick
- NSFW hosting policy on chosen platform
- Awempire account status
- Public vs gated default for uploads
- Content moderation appetite (automated vs manual)

### 12. Agent vs operator split
Clear table: what Claude Code / Cursor Auto can ship vs what requires operator (domain purchase, Awempire signup, Cloudflare, Supabase prod keys, island deploy, mainhub pin).

---

## OUT OF SCOPE (this plan pass)

- Implementing Awempire before account exists (plan only)
- Live Telegram bot changes or island deploy execution
- Committing `.env`, secrets, session files
- Scraping Motherless at scale
- Replacing TBCC tray/supervisor architecture
- Funnel.io subscription procurement

---

## VERIFICATION (plan pass only)

This is a documentation/planning pass. "Done" means:

1. Report file exists at `tbcc/docs/handoffs/2026-08-10_aof-hub-frontier-plan-ask_report.md`
2. Every claim about existing code cites a file path you actually read
3. Phases are independently shippable with verification commands for implementation phases
4. Traffic model states assumptions explicitly
5. Operator has ≤5 prioritized decisions to unblock P0–P2

No pytest required for plan-only pass. If you spot trivial doc fixes (broken paths in README), note them in report — do not implement.

---

## WORKING AGREEMENT

- Branch: plan-only — **no code commits** unless operator later says "implement phase N"
- After report: **STOP** for Cursor ACK via `/cc-report` or "read the CC report"
- Implementation phases (when approved): prefer `aof-forum/` PRs separate from `tbcc/` unless integration required
- Extension version bump only if `tbcc/extension/` touched in a later phase

---

## REVERSE REPORT STRUCTURE

Use markdown:

# Reverse handoff — AOF Hub frontier plan
- Status: complete | blocked | needs operator input
- Executive summary (≤10 bullets)
- Current-state audit table
- Recommended IA + homepage design
- Phased plan (P0–Pn)
- Traffic model
- Copy pack
- Operator decisions needed (numbered)
- Risks / anti-patterns
- Suggested first implementation slice for Cursor Auto
- Files read (list)

---

## CONTEXT FROM PRIOR CURSOR SESSION (for alignment)

Operator asked:
1. Will this generate new sustained traffic long-term? short-term?
2. Where/when can sites go up?
3. Is customization expansive?
4. Wants hub with live cams, tube, make-your-own gallery, bulk upload without worry
5. Wants to start designing THE website for AOF — confirmed `aof-forum` is the right place

Cursor assessment (validate against code):
- Short-term traffic = owned channels; long-term = SEO + UGC if volume compounds
- Customization is fully expansive (custom Next.js)
- Core ingest/gallery/forum bones exist; gaps are hub UX, bulk upload UI, live section, brand, deploy
- Awempire fills live monetization without hosting cams
- Motherless void = opportunity for owned hub, not ML mirror

Task: Deliver the full frontier plan per PLAN DELIVERABLES above. Plan/Ask only. Write report. Stop.
```

---

## Quota reminder

Run `/usage` in Claude Code before a long read pass. This job is **read-heavy** (two repos + migrations) — expect substantial context use. Plan/Ask only; no implementation burn.

## Lane note

This is **Frontier Plan/Ask** work (product doctrine + multi-system architecture). If Claude Code drifts into bulk implementation, pull back to report-only. Implementation phases belong in **Cursor Desktop Auto** or **Lane C** for mechanical grinds (P4 bulk upload, P9 creative batch).

## After Claude Code finishes

1. Say **"read the CC report"** or `/cc-report` in Cursor
2. Review `tbcc/docs/handoffs/2026-08-10_aof-hub-frontier-plan-ask_report.md`
3. Pick phase(s) to implement — typically **P0 (domain) + P1 (hub homepage)** first
