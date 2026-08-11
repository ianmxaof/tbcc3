# Reverse handoff — AOF Hub P9 + P10

- Status: **Phase 1 of 3 complete** (Claude Code) — stopped for Cursor ACK per the working agreement.
- Branch: `lane-c/aof-hub-p9-p10`, commit `d5455a9`.
- Report path: `tbcc/docs/handoffs/2026-08-10_aof-hub-p9-p10_report.md`

## Executive summary

Phase 1 (P9 plumbing) is done and verified: a server-only Awempire VPAPI client with a fixture fallback, a label registry, and a skeleton `/tube/awempire/[label]` route. The API contract was **verified against the vendor's own reference implementation** (`github.com/DoclerLabs/awe-vpapi-demo`), not assumed — see §"Contract verification" below, which is the same class of mistake that broke the TBCC↔forum bridge in P2 (`from-telegram.ts` guessed a contract that didn't exist). One real design decision is surfaced and deliberately **not resolved** in this phase: the VPAPI details endpoint returns a `playerEmbedScript` meant for direct DOM injection, which is an XSS surface if handled carelessly. Phase 2 (grid UI + watch page + beacons + SEO) cannot start until that's settled — see "Blockers" below.

P10 (dashboard scoreboard) has not started — it's phase 3 per the task's own phase order, gated behind P9 Phase 2. Its design is scoped though (see "P10 design" below) since the read-first pass already confirmed `gate_funnel_report` needs no new backend endpoint.

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

## P10 design (not started — scoped for Phase 3)

Confirmed via read-first pass: **no new backend endpoint needed.** `gate_funnel_report()` (`backend/app/services/gate_funnel.py`) already returns every `source_ref` row with `clicks`/`touches`/`revenue_usd`/`click_to_touch_pct`, and `dashboard/src/panels/Analytics.tsx` already fetches it wholesale via `api.analytics.gateFunnel(rangeDays)` for the existing "Gate funnel" section. The web-hub rows are already in that same payload — `web_hub_beacon_plan.py` (P8, already landed) seeds `source_ref` values as `src_web_*`. Phase 3 plan: add a "Web hub scoreboard" section to `Analytics.tsx` directly below the existing gate-funnel table, client-filtering `gateFunnelQ.data.gate_funnel` on `source_ref.startsWith("src_web_")`, with its own stat-card row (total web clicks/touches/$) reusing the existing `StatCard` component. No `test_gate_funnel.py` changes anticipated (report shape unchanged); will re-run it plus `test_income_traffic_source.py` per the task's Phase 3 verify step regardless, since the P9 `web-vpapi-*` beacon-plan extension (Phase 2) adds new seeded rows that flow through the same code path.

## Tests run (Phase 1)

- `npx tsc --noEmit` — clean
- `npx next lint --dir app --dir components --dir lib` — clean
- **Not run:** `next build`. `.env.local` points at a live (non-localhost) Supabase project; a full build would prerender every route, including ones that call `createAdminClient()` and issue real SELECT queries against that project. Stated explicitly per the same caution applied in the P1.5 report, rather than implying full verification. This route's own data path (Awempire-or-fixture) doesn't touch Supabase, but the build isn't scoped to one route.
- No Python tests touched or run this phase (P9 Phase 1 is TypeScript-only).

## Operator steps

1. **Awempire affiliate account** — PSID + access key from the dashboard once approved; set `AWEMPIRE_PSID` / `AWEMPIRE_ACCESS_KEY` (server-only, never `NEXT_PUBLIC_`).
2. **Confirm real tag vocabulary** — the 4 seeded labels' `vpapiTags` are placeholder guesses. Once credentials exist, Phase 2 should add a `GET /tags` diff script (endpoint exists per `vpapi.js`'s `loadTagList`) so the operator can verify `data/vpapi-labels.json` against real values before launch — a wrong tag string returns zero videos, indistinguishable from a broken integration.
3. **After setting credentials, the page can still show "fixture" for up to 15 minutes.** `generateStaticParams()` + `revalidate = 900` means the fixture-vs-live decision is baked in at generation time. If the four label pages were generated before `AWEMPIRE_PSID`/`AWEMPIRE_ACCESS_KEY` were set, they keep serving the "not configured" fixture card until the ISR window elapses *and* a new request triggers regeneration — or until a redeploy. After setting credentials: redeploy, or wait out the 900s window and reload, and confirm the page footer reads `source: live` before assuming the integration is broken.
3. No Label4Editor work in this phase — task doc and the earlier frontier plan (`2026-08-10_aof-hub-frontier-plan-ask_report.md` §3) both defer it to a later phase pending justification.

## Blockers / deferred items

1. **Watch-page embed sandboxing — must be decided before Phase 2 starts, and the evidence narrows the options more than first thought.** `playerEmbedScript` is arbitrary partner script HTML meant for injection into the page's own DOM. Injecting it directly (e.g. via `dangerouslySetInnerHTML`) puts a third party's JS in the same origin/context as AOF Hub's own session — a real XSS-class risk even for a trusted affiliate partner, not a hypothetical one.

   The obvious alternative — "just link out to Awempire's own video page instead of embedding" — **does not have a verified URL to link to.** Everything confirmed from the reference client (§Contract verification): `/client/list` returns `id`, `title`, `previewImages` — no link field. `/client/details/{id}` returns `title`, `performerId`, `tags`, and `playerEmbedScript` — also no plain link field. The reference demo app itself never links out to awempire.com for an individual video; it renders `playerEmbedScript` in-page at its own `/details/{id}` SPA route. VPAPI's actual design looks like "embed the whole browsing + playback experience on the affiliate's own domain," not "browse here, click through to watch there" — which may not be what the task's "link-out only" doctrine line assumed going in. Bytes still stream from Awempire's player either way (satisfies the no-hosting rule), but a literal outbound link per video isn't something the verified contract supports today.

   Three real options for Phase 2, in order of how much they need from Phase 3+ discovery:
   - **(c) Grid-only v1, no per-video click-through.** Show titles/thumbnails as a promotional listing; a single **operator-supplied** outbound CTA (manually pasted, same pattern as `outboundUrl` in `data/live-embeds.json` today) sends visitors to Awempire's general site/promo landing, not a specific video. Zero new attack surface, fully buildable from what's verified today, and the most literal reading of "link-out only."
   - **(a) Sandboxed iframe embed** of `playerEmbedScript` via `<iframe srcdoc="...">` so the injected script can't touch the parent origin/cookies/DOM. Buildable from verified data, but is an embed, not a link-out — a doctrine question for the operator, not just an engineering one.
   - **(unverified) Construct a per-video URL** (e.g. a guessed `awempire.com/video/{id}` pattern) — explicitly **not** recommended; would repeat the exact mistake this phase was trying to avoid (asserting a contract that wasn't confirmed).

   Recommendation: **(c) for Phase 2 v1** — matches the doctrine's literal wording, ships without the sandboxing question needing to be settled first, and defers (a) to a later phase only if engagement data justifies the added complexity and the operator accepts "embed" as satisfying "link-out only."
2. **`vpapiTags` unverified** — see Operator steps #2. Not a blocker for Phase 2 UI work (fixture mode covers that), but should be resolved before Phase 2's beacon/SEO work goes live, since wrong tags silently produce empty labels.
3. P10 fully deferred to Phase 3 per the task's own gating.

## Next

Stopped here per the working agreement ("STOP + write report after each phase, then STOP for Cursor ACK"). Phase 2 can proceed with option (c) (grid-only, operator-supplied outbound CTA, no per-video watch page) without further discovery — recommended default above. If the reviewer instead wants an in-page embed (option a) or wants to hold for a verified per-video link (unverified path, not recommended), say so before Phase 2 starts; otherwise Phase 2 will build against (c).
