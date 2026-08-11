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
| `aof-forum/.env.example` | Documented `AWEMPIRE_PSID`, `AWEMPIRE_ACCESS_KEY`, `AWEMPIRE_VPAPI_FIXTURE_JSON`. **Note:** this file's diff also carries forward not-yet-committed P1–P8 env documentation (TBCC beacons, live embeds, export throttle, upload quotas) that shared the same hunk and wasn't cleanly separable via `git add -p` — disclosed in the commit message, not silently bundled. |

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
3. No Label4Editor work in this phase — task doc and the earlier frontier plan (`2026-08-10_aof-hub-frontier-plan-ask_report.md` §3) both defer it to a later phase pending justification.

## Blockers / deferred items

1. **Watch-page embed sandboxing — must be decided before Phase 2 starts.** `playerEmbedScript` is arbitrary partner script HTML meant for injection into the page's own DOM. Injecting it directly (e.g. via `dangerouslySetInnerHTML`) puts a third party's JS in the same origin/context as AOF Hub's own session — a real XSS-class risk even for a trusted affiliate partner, not a hypothetical one. Two options, need a pick before Phase 2 builds it:
   - **(a) Sandbox it** — render inside a sandboxed `<iframe srcdoc="...">` so the injected script cannot touch the parent origin, cookies, or DOM.
   - **(b) Skip the in-page watch experience for v1** — link out to Awempire's own hosted page instead (no watch route on AOF Hub at all), matching the "link-out only" framing in the task's own doctrine line more literally.
   Recommendation: **(b) for v1.** It's simpler, has zero new attack surface, and the task's doctrine already says "link-out only, no hosting cam/video bytes" — an outbound link is the most literal reading of that. Revisit (a) later if conversion data justifies the added complexity of an in-page player.
2. **`vpapiTags` unverified** — see Operator steps #2. Not a blocker for Phase 2 UI work (fixture mode covers that), but should be resolved before Phase 2's beacon/SEO work goes live, since wrong tags silently produce empty labels.
3. P10 fully deferred to Phase 3 per the task's own gating.

## Next

Stopped here per the working agreement ("STOP + write report after each phase, then STOP for Cursor ACK"). Awaiting a pick on the watch-page sandboxing question (§Blockers #1) before starting Phase 2.
