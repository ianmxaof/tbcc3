# Reverse handoff — AOF Hub P9 + P10

- Status: **Phase 2 of 3 complete** (Claude Code) — stopped for Cursor ACK per the working agreement.
- Branch: `lane-c/aof-hub-p9-p10`. Phase 1: `d5455a9`, `9a2bdf8` (report), `2396863` (report correction). Phase 2: `ffd7b4c` (pre-existing file baseline capture, see note below), `2cd2b13` (VPAPI grid/beacons/SEO).
- Report path: `tbcc/docs/handoffs/2026-08-10_aof-hub-p9-p10_report.md`
- ACK received: "ACK Phase 1 — build Phase 2 option (c). P10 stays Phase 3."

## Executive summary

**Phase 1** (P9 plumbing): a server-only Awempire VPAPI client with a fixture fallback, a label registry, and a skeleton route. The API contract was **verified against the vendor's own reference implementation** (`github.com/DoclerLabs/awe-vpapi-demo`), not assumed — see §"Contract verification" below, the same class of mistake that broke the TBCC↔forum bridge in P2 (`from-telegram.ts` guessed a contract that didn't exist). That verification surfaced a real gap: VPAPI has no per-video outbound URL anywhere in its confirmed contract, only an in-page `playerEmbedScript` — which is an XSS-class risk if injected carelessly. Flagged as a blocker rather than silently picked.

**Phase 2** (this update): built against Cursor's ACK of option (c) — grid UI with non-clickable cards (fixed a duplicate-href defect caught before commit — see "Grid design" below), one beacon-wrapped CTA per label, `generateMetadata` + `ItemList` JSON-LD + sitemap inclusion (gated on real credentials, same "no thin content" rule already applied to `/live`), and 4 new `web-vpapi-*` beacons seeded server-side. Surfaced one new finding for Phase 3: these beacons will always show clicks with zero touches (affiliate outbound, not a Telegram deep link) and need to not be flagged as broken on the dashboard.

**P10** (dashboard scoreboard) has not started — Phase 3 per the task's own order. Design is scoped (see "P10 design" below): no new backend endpoint needed, `gate_funnel_report` already carries everything required.

## Contract verification (why this took extra time, and why it was worth it)

The task pointed at `http://auth.awempire.com/video-promotion-api` (an authenticated dashboard, not fetchable) and `github.com/DoclerLabs/awe-vpapi-demo`. Fetched the actual source of `vpapi.js`, `components/videoList.js`, `components/videoThumb.js`, `routes/details.js`, `routes/tag.js`, and `components/pagination.js` via the GitHub contents API (WebFetch's HTML rendering of the repo didn't surface source; `gh api` + `curl` on `raw.githubusercontent.com` did). Confirmed:

- **Base URL:** `https://pt.protoawe.com/api/video-promotion/v1`
- **Auth:** `psid` + `accessKey` as query params on every GET (not headers, not a signature)
- **`GET /client/list`** params: `pageIndex`, `limit`, `sexualOrientation` (default `"straight"`), `primaryColor`/`labelColor` (widget theming, not content selectors), `tags` (array, comma-joined by `URLSearchParams` in the reference client)
- **Response envelope:** `{ data: { videos: [...], pagination: {...} } }` — the reference client unwraps `.data` before handing rows to callers
- **Video fields observed:** `id`, `title`, `previewImages: string[]` (hover-preview gallery)
- **Pagination fields observed:** `currentPage`, `totalPages`
- **`GET /client/details/{videoId}`** returns `title`, `performerId`, `tags: string[]`, and **`playerEmbedScript`** — a script string containing a `{CONTAINER}` placeholder token, meant to be string-replaced with a container element id and injected into the page. This is Awempire's actual embed mechanism — video bytes stream from their player, never touch AOF's B2, which satisfies the "no hosting" doctrine line. It is also the reason the watch page is a blocker, not a Phase 2 given (see below).
- **No native "label" concept.** VPAPI's own vocabulary is `tags` (see `routes/tag.js`: `/tag/:tagName` → `{ tags: [tagName] }`). The task's `/tube/awempire/[label]` naming and the `data-awe-list="label"` hint appear to reference a separate, simpler drop-in widget ("awe-html-kit") that has no publicly accessible source I could find — could not verify its contract, so I did not build against it. Instead, `vpapi-labels.json` is an **AOF-side adapter layer**: each label slug maps to one or more VPAPI `tags` values. This is an honest translation, not a guess dressed as fact — flagged inline in the JSON's `_comment` field and here.

## P9 — files touched (Phase 1)

| File | Purpose |
|---|---|
| `aof-forum/lib/awempire-vpapi.ts` | Server-only VPAPI client. `vpapiConfigured()` (mirrors `liveEmbedsConfigured()` from P5/P6), `fetchVpapiList()`. Degrades to fixture data on missing credentials, network failure, or non-200 — never throws through the page render. |
| `aof-forum/data/vpapi-labels.json` | 4 labels (`big-tits`, `amateur`, `milf`, `blowjob`) chosen to match existing AOF lane naming (`aof_network.py`). **`vpapiTags` values are unverified placeholders** — no live account to confirm against `GET /tags` yet. |
| `aof-forum/lib/vpapi-labels.ts` | Label registry loader/lookup — separate file from the API client (single responsibility), same JSON-import pattern as `live-embeds.ts`. |
| `aof-forum/app/(site)/tube/awempire/[label]/page.tsx` | Skeleton route. `generateStaticParams()` over the 4 known labels (ISR via `revalidate = 900`, not `force-dynamic` — this hits a third-party rate-limited API, unlike the rest of the app's Supabase-backed pages). Renders title/id/source (fixture vs live) per video — no grid polish, no beacon-wrapped outbound links, no metadata yet; all explicitly Phase 2. |
| `aof-forum/.env.example` | Documented `AWEMPIRE_PSID`, `AWEMPIRE_ACCESS_KEY`, `AWEMPIRE_VPAPI_FIXTURE_JSON`. **Note:** this file's diff also carries forward not-yet-committed P1–P8 env documentation (TBCC beacons, live embeds, export throttle, upload quotas). `git add -p` could have split the hunk (`s`/`e`) to isolate just the VPAPI block — chose to bundle it instead, since the other lines are the same product line's env docs, contain no secrets, and needed committing anyway. A choice, not a tooling limitation. |

## P9 — files touched (Phase 2, option c)

| File | Purpose |
|---|---|
| `aof-forum/components/VpapiVideoGrid.tsx` | `VpapiDisclaimer` + `VpapiVideoGrid`. Cards render title/thumbnail but are **not individually clickable** — see "Grid design" below. One `<a>` CTA button carries the click. |
| `aof-forum/app/(site)/tube/awempire/[label]/page.tsx` | Rewritten: `generateMetadata` (title/description/canonical/OG/Twitter), `ItemList` JSON-LD, `TelegramConversionFooter` (doctrine requirement), renders `VpapiVideoGrid` instead of the Phase 1 plain list. |
| `aof-forum/lib/vpapi-labels.ts` | Added `vpapiLabelOutboundHref(label)` — always resolves through `{NEXT_PUBLIC_TBCC_BEACON_BASE}/r/web-vpapi-{slug}` when a beacon base is configured, else a hardcoded `https://www.awempire.com/` fallback. Deliberately does **not** store a destination URL client-side — that lives once, server-side, in `web_hub_beacon_plan.py` (single source of truth; avoids the two-places-to-update-and-they-drift class of bug). |
| `aof-forum/lib/aof-cta.ts` | Added `"vpapi"` to the `CtaSurface` union so `TelegramConversionFooter` can be used on label pages with a proper `source_ref`. |
| `aof-forum/app/sitemap.ts` | Label routes added, gated on `vpapiConfigured()` — same "don't submit thin fixture-mode content" reasoning already applied to `/live`. |
| `tbcc/backend/app/data/web_hub_beacon_plan.py` | `web-vpapi-<slug>` × 4, all defaulting to the same `https://www.awempire.com/` placeholder (no per-category Awempire links exist yet). |
| `tbcc/backend/scripts/seed_web_hub_beacons.py` | `AWEMPIRE_VPAPI_OUTBOUND_URL` override, applied uniformly to all `web-vpapi-*` rows — same override pattern as the existing `AWEMPIRE_OUTBOUND_URL_GIRLS`/`_COUPLES`. |

**Commit hygiene note:** `aof-cta.ts`, `sitemap.ts`, `web_hub_beacon_plan.py`, and `seed_web_hub_beacons.py` were untracked (uncommitted P1–P8 work from elsewhere) before this phase. Rather than repeat the Phase 1 `.env.example` bundling choice, I reverted my edits, committed each file's pre-existing content on its own (`ffd7b4c`, explicitly labeled as not this lane's authorship), then reapplied and committed my actual diff (`2cd2b13`). `git diff --stat` on that second commit shows exactly what Phase 2 added (2–22 lines per file), not the full pre-existing file contents.

### Grid design — why cards aren't clickable

First draft made every card in the grid link to the same `outboundHref`. That's a duplicate-href pattern: 24 anchors with different visible text (video titles) all pointing at one URL, on the one page whose entire purpose is SEO — bad for crawlers, and misleading for a user who clicks "Video A" and lands on a generic partner homepage instead. Fixed before commit: cards are now plain divs (title + thumbnail only), and a single `<a>` CTA button below the grid carries the outbound click with honest, generic copy ("Browse more {label} on our partner site").

## P10 design (not started — scoped for Phase 3)

Confirmed via read-first pass: **no new backend endpoint needed.** `gate_funnel_report()` (`backend/app/services/gate_funnel.py`) already returns every `source_ref` row with `clicks`/`touches`/`revenue_usd`/`click_to_touch_pct`, and `dashboard/src/panels/Analytics.tsx` already fetches it wholesale via `api.analytics.gateFunnel(rangeDays)` for the existing "Gate funnel" section. The web-hub rows are already in that same payload — `web_hub_beacon_plan.py` seeds `source_ref` values as `src_web_*`. Phase 3 plan: add a "Web hub scoreboard" section to `Analytics.tsx` directly below the existing gate-funnel table, client-filtering `gateFunnelQ.data.gate_funnel` on `source_ref.startsWith("src_web_")`, with its own stat-card row (total web clicks/touches/$) reusing the existing `StatCard` component.

**New finding from Phase 2, Phase 3 needs to handle this:** the `web-vpapi-*` beacons point at `https://www.awempire.com/` — an outbound affiliate link, not a Telegram bot deep link. `payload_to_source_ref()` in `traffic_attribution.py` only produces a touch from a Telegram `/start=` payload, so these refs will **permanently show clicks with zero touches** — correct behavior (an affiliate outbound click physically cannot produce a Telegram touch), but `gate_funnel_report()`'s existing `clicks_without_touches` list will include them, and the dashboard currently surfaces that list as a problem signal ("broken destination or a click_only lane gate"). Phase 3 must either exclude `src_web_vpapi_*` (and `src_web_live_*`, which has the same shape) from that warning, or label affiliate-outbound refs separately in the scoreboard — otherwise Phase 3 ships a scoreboard that flags healthy rows as broken. No `test_gate_funnel.py` changes anticipated for the report shape itself; will re-run it plus `test_income_traffic_source.py` per the task's Phase 3 verify step regardless, since the new seeded rows flow through the same code path.

## Tests run (Phase 1 + 2)

- `npx tsc --noEmit` — clean, both phases
- `npx next lint --dir app --dir components --dir lib` — clean, both phases
- `py -3.13 scripts/seed_web_hub_beacons.py` (dry run) — confirms all 4 `web-vpapi-*` rows generate with correct beacon URLs (`http://127.0.0.1:8000/r/web-vpapi-<slug>` locally), placeholder destination, and `src_web_vpapi_<slug>` source_ref. Re-ran after the baseline-capture reconstruction (§commit hygiene note above) to confirm nothing broke in the revert/reapply.
- **Not run, either phase:** `next build`, or any actual page render. `.env.local` points at a live (non-localhost) Supabase project; a full build would prerender every route, including ones that call `createAdminClient()` and issue real SELECT queries against that project. Stated explicitly rather than implying full verification. **This means the grid's actual rendered output, the `generateMetadata` canonical/OG tags, and the `ItemList` JSON-LD have not been observed rendering — only reviewed as written.** `tsc`/`lint` catch type and syntax errors, not layout, metadata correctness, or JSON-LD validity. Recommend the operator run `npm run dev` and eyeball `/tube/awempire/big-tits` plus view-source the `<head>` before treating Phase 2 as UI-verified.
- No Python tests run beyond the seed script dry run (Phase 3's verify step is where `test_gate_funnel.py`/`test_income_traffic_source.py` run).

## Operator steps

1. **Awempire affiliate account** — PSID + access key from the dashboard once approved; set `AWEMPIRE_PSID` / `AWEMPIRE_ACCESS_KEY` (server-only, never `NEXT_PUBLIC_`).
2. **Confirm real tag vocabulary** — the 4 seeded labels' `vpapiTags` are placeholder guesses. Once credentials exist, a `GET /tags` diff script (endpoint exists per `vpapi.js`'s `loadTagList`) would let the operator verify `data/vpapi-labels.json` against real values before launch — a wrong tag string returns zero videos, indistinguishable from a broken integration. Not built yet; flagging again since Phase 2 shipped without it.
3. **After setting credentials, the page can still show "fixture" for up to 15 minutes.** `generateStaticParams()` + `revalidate = 900` means the fixture-vs-live decision is baked in at generation time. After setting credentials: redeploy, or wait out the 900s window and reload, and confirm the page footer reads `source: live` before assuming the integration is broken.
4. **Real category outbound URL** — once approved, set `AWEMPIRE_VPAPI_OUTBOUND_URL` and re-run `seed_web_hub_beacons.py --execute` so the 4 `web-vpapi-*` beacons stop pointing at the generic `awempire.com` placeholder.
5. No Label4Editor work in this phase — task doc and the earlier frontier plan (`2026-08-10_aof-hub-frontier-plan-ask_report.md` §3) both defer it to a later phase pending justification.

## Blockers / deferred items

1. **Watch-page embed sandboxing — resolved for v1 (option c), ACK'd.** Original Phase 1 finding stands: `playerEmbedScript` (in-page embed) and a plain per-video link are the two theoretical options, and only the embed is buildable from verified data — no per-video URL field exists anywhere in the confirmed contract. Cursor ACK'd option (c) (grid-only, single operator-supplied CTA, no in-page embed, no per-video link) explicitly, so this is no longer open. Option (a) — sandboxed `<iframe srcdoc>` embed of `playerEmbedScript` — remains the documented fallback if engagement data later justifies it, not built in Phase 2.
2. **`vpapiTags` still unverified** — see Operator steps #2. Not a blocker for what shipped (fixture mode covers the UI path regardless), but real category tags need confirming before this goes live, since a wrong tag string silently returns zero videos.
3. **`clicks_without_touches` false-positive — new in Phase 2, must be handled in Phase 3.** See "P10 design" above. `web-vpapi-*` (and the pre-existing `web-live-*`) beacons will always show 0 touches by design (affiliate outbound, not a Telegram deep link) and will otherwise appear on the dashboard as broken.
4. **UI/metadata/JSON-LD not rendered-verified** — see "Tests run" above. Reviewed as written, not observed in a browser.
5. P10 fully deferred to Phase 3 per the task's own gating — unchanged.

## Next

Stopped here per the working agreement. Phase 3 (P10 web hub scoreboard) is next: add the `Analytics.tsx` section per "P10 design" above, decide how to handle affiliate-outbound refs in `clicks_without_touches` (item 3 above) before shipping the scoreboard, then run `test_gate_funnel.py` + `test_income_traffic_source.py` + `dashboard && npm run build` per the task's own Phase 3 verify step. Awaiting ACK to proceed.
