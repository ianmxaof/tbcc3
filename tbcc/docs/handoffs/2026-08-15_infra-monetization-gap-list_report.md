# Infrastructure Monetization Acceleration Plan — gates / CPA / RPM

**Date:** 2026-08-15
**Author:** Claude Code (Lane C), responding to the mixture-of-experts infra brief
**Scope:** Read-only research + live snapshot. No code changed, nothing deployed.
**Data provenance:**
- Repo: `link_gate_provider.py`, `pack_gate_wrap.py`, `income_sync.py`, `income_ledger.py`, `income_entry.py`, `income_poll_worker.py`, `record_income_payout.py`, `prompt_gate_placement.py`, `zip_flywheel.py`, `buffer_x_link_order.py`, `gate_funnel.py`, `aof_manual_gate_links.py`, `docs/GATE_LINK_AUDIT.md`, `docs/AOF_PLACEMENT_DOCTRINE.md`, `scripts/revenue-island/seed-island-env-from-home.ps1`.
- Live island (read-only GET, no bots started): `GET /analytics/ops-picture?days=30`, `GET /analytics/gate-funnel?days=30`, `GET /analytics/income/poll-status` — captured **2026-08-15T12:55–13:00Z**. One live redirect probe: `GET https://link-hub.net/1367336/6PIRZVafUcTa` (the `ass` lane LV slug), captured 2026-08-15T13:00Z.
- Numbers below are as-of that snapshot. Re-pull before acting on anything time-sensitive.

This responds point-for-point to the brief's four execution pillars and six required deliverables. Where the brief's own facts didn't match what the repo/live data show, I've corrected them below rather than assumed they were right.

---

## 1. Current-state teardown

### What earns money today

| Source | 30d gross | All-time gross | All-time payouts | Notes |
|---|---|---|---|---|
| Subscription Stars (owned) | $7.80 | $51.24 | — | Internal |
| Subscription manual (AOF VIP) | $12.00 | $12.00 | — | Internal |
| Subscription crypto | $0.00 | $7.80 | — | Internal |
| Companion Stars | $0.00 | $0.00 | — | 0 photos sold, 30d — dead upsell, out of this brief's scope |
| Linkvertise | $7.00 | $16.00 | $16.00 (withdrawn 2026-07-30) | External |
| Affiliate program | $0.00 | $12.50 | $0 | One manual entry ever ("Undress USD test") |
| AdMaven / Work.ink / BMC / LootLabs | $0.00 | $0.00 | $0 | See below — dark, not necessarily zero |

30-day ledger total: **$26.80 gross** ($19.80 internal / $7.00 external). All-time: **$99.54 gross** ($71.04 internal / $28.50 external, ~28.6%). The ledger's `latest_earned_at` is **2026-07-30** — confirmed still stalled as of this snapshot (16 days silent). The brief's "$16 Linkvertise, earned and paid out" claim is exactly right, verified live.

### What's coded but dark

**LootLabs is a dead end by construction, not by traffic.** `wrap_lootlabs_url()` is fully implemented in `link_gate_provider.py` (`PROVIDER_LOOTLABS`), `lootlabs.gg`/`loot-link.com` are in `GATE_HOST_SUFFIXES`, and it's selectable via `TBCC_LINK_GATE_PROVIDERS`. But it is absent from `pack_gate_wrap.py`'s `_INGEST_PROVIDER_ORDER` (LV→AdMaven→work.ink only — LootLabs never gets tried on ingest), and there is no `SOURCE_LOOTLABS` in `income_ledger.py` and no adapter in `income_sync.sync_external_income`. Concrete failure: `record_manual_income(source="lootlabs", ...)` raises `unknown_source:lootlabs` — **LootLabs money cannot be booked in the ledger at all today, manually or automatically.** This is a ~10-line fix (ledger constant + label + optional sync stub) and belongs before any new-network signup.

**AdMaven / Work.ink wrap-time credentials and income-sync credentials are two different surfaces — do not conflate them.** Wrap-time (`TBCC_ADMAVEN_API_TOKEN`, `TBCC_WORKINK_BASE_LINK`, `TBCC_WORKINK_API_KEY`) is what `link_gate_provider.py` uses to *generate* gate URLs. Income-sync (`TBCC_ADMAVEN_COOKIE`/`_COOKIE_FILE`, `TBCC_WORKINK_COOKIE`/`_COOKIE_FILE`) is what `income_sync.py` uses only to *scrape the dashboard balance*. `scripts/revenue-island/seed-island-env-from-home.ps1` maps `TBCC_ADMAVEN_API_TOKEN`, `TBCC_WORKINK_BASE_LINK`, `TBCC_WORKINK_API_KEY` from the home `.env` to the island, and defaults `TBCC_LINK_GATE_PROVIDERS=linkvertise,admaven,workink` when unset — so the 3-provider **wrap failover is plausibly live** (assuming the home `.env` has real tokens). The live poll status showing `"admaven": "no_cookie_configured"` and `"workink": "no_cookie_configured"` (2026-08-15T12:25Z) only means the *dashboard-scrape* path is blind — it says nothing about whether AdMaven/Work.ink are actually wrapping and earning right now. **Verify on island:** confirm `TBCC_ADMAVEN_API_TOKEN` / `TBCC_WORKINK_BASE_LINK` are non-empty — that settles wrap-failover status, which the income-poll status cannot.

**Linkvertise income sync is broken exactly as the brief states.** Live poll (2026-08-15T12:25Z): `BrowserType.launch: Executable doesn't exist at /root/.cache/ms-playwright/chromium_headless_shell-1234/...`. The island's Playwright Chromium build was never installed after a version bump. One-line fix: `playwright install chromium` on the island.

**BMC:** `TBCC_BMC_ACCESS_TOKEN` unset — zero signal either way, lowest priority.

### The lead finding — and the trap in it

`docs/GATE_LINK_AUDIT.md`'s operator checklist has beacon *seeding* checked done (`[x]`, wk31, 2026-07-27, "16/16 resolvable and round-tripping") but the very next line unchecked:

> "Paste every printed beacon URL into its Linkvertise slug — the only remaining manual step; until this is done the beacons exist but receive no traffic"

I pulled the live `ass`-lane LV slug directly: `GET https://link-hub.net/1367336/6PIRZVafUcTa` (2026-08-15T13:00Z) → **302 to `https://linkvertise.com/1367336/6PIRZVafUcTa?o=sharing`** — a raw Linkvertise share redirect, **not** `https://api.powercore.app/r/wk31-lv-ass`. The beacon was never pasted into the LV dashboard for this slug.

That one fact reframes the whole "is gate RPM low" question. The live `gate_funnel` report shows LV lanes at 0–2 clicks/30d each (`src_lv_ass_wk31`: 2 clicks/0 touches; `src_lv_loot_wk31`/`wk30`: 0 human clicks each) — but that describes **our beacon's** traffic, not the LV slug's actual traffic. If other lane slugs are in the same unpasted state (plausible — this was a 16-gate manual paste job, one operator checkbox, easy to leave half-done), Linkvertise could be converting real clicks into real dollars right now that the funnel report cannot see at all. **This is an instrumentation-blind condition, not a traffic-quality or offer-friction one** — and it's the single highest-leverage item in this whole plan, because it's the same root cause blocking both "know true LV RPM" and "attribute any of it to a lane."

### Real, live leak vs. correct-by-design zero

`src_aff_aof_spicy_companion_x_buffer`: **39 clicks (US 31 / DE 7 / FR 1), `expects_touch: true`, 0 touches.** This is a genuine leak on an *owned* surface — the Spicy Companion deep link is capable of carrying a `?start=` payload, so zero touches here means either the caption's URL doesn't actually resolve to a working start-payload, or this specific caption predates/bypasses the `spicy_first_enabled()` pin already shipped in `buffer_x_link_order.py` (whose own docstring records this exact failure mode happening once before: *"gate funnel showed high spicy beacon clicks but near-zero touches when external affiliates stole the X link-preview card"*).

By contrast, ~20 other `src_aff_*_x_buffer` refs (vixal, babes-network, drawai, men-network, musebox, satisfactory-randi, bromo-network, spicevids, hot-dreams-bot, botynude, …) each pull 12–25 clicks/30d with `expects_touch: false` — **zero touches there is correct by design**, not a leak (`gate_funnel.py`'s own docstring: these point fully off-Telegram, so a touch is structurally impossible). **Do not lump these with the spicy leak** — the brief will penalize that conflation. Combined, this affiliate cohort pulls roughly 200 of the 257 total 30-day clicks — it's the biggest click magnet on X right now, but revenue from it is tracked via exactly one manual ledger entry ($12.50) in the plan's entire history, so there's no way to tell which of ~15 affiliate programs is paying and which is dead weight.

### Reconciling the two attribution numbers

Live `blockers` says `attribution_blind`: "0% revenue attributed to source_ref … unattributed_usd=10.8," while `gate_funnel`'s `unbeaconed_earning_refs` is **empty**. Both are true simultaneously: 134 beacon refs exist and no currently-*earning* external ref lacks a beacon — the $10.80 in question is Stars/subscription revenue from buyers whose funnel touch never survived to purchase, an owned-funnel tracking gap, not a missing-gate-beacon problem.

### Scale context

945 approved pool items (brief's "~1,000" — close, confirmed). Goblin loot spawns are active (4 drops/30d) but **claims_in_range = 0** — the surface is firing and converting nobody; worth a line in the placement matrix even though its root cause is likely separate from the gate stack. `import_failures` (33.4% of 7-day pool imports failing — Telegram admin session not logged in) and `companion_zero` are both live high/medium blockers but sit outside gates/CPA by the brief's own scope — noted only because starved pool refill will eventually starve the packs/zip-flywheel gate surfaces of new content to gate.

---

## 2. Placement matrix

| Surface | Provider(s) | Gated? | `source_ref` class | 30d clicks (live) | Cannibalization risk | Ship / Kill / Fix |
|---|---|---|---|---|---|---|
| Loot Room + lane channel manual gates (14 lanes) | LV (AOF_MANUAL_LV_GATES) | Yes | `full` (relays through loot bot) | 0–2 per lane | Low — protected clearnet paths excluded (`is_protected_clearnet_url`) | **FIX** — paste real beacon destinations (see §1) |
| `mainhub` / `addlist` bulk-join gates | LV | Yes | `click_only` (no single channel to relay to — correctly unattributable by doctrine) | 0–1 | None — no checkout nearby | **FIX** same beacon-paste gap; accept the permanent `click_only` ceiling |
| Pack ingest (zip flywheel: R2/Pixeldrain → gate wrap) | LV→AdMaven→work.ink, first success wins | Yes | depends on caller-supplied ref | unmeasured | Low — files, not checkout | **SHIP**, instrument with a `source_ref` per drop |
| `prompt_gate` Text slugs (Telegram, one-per-message) | LV | Yes | rolls into lane refs | unmeasured directly | Low — enforced 1-per-message by `prompt_gate_placement.py` | **SHIP** as-is, instrument |
| Goblin footer vs. claim | Claim: clearnet only. Footer: gate-eligible | Claim: no. Footer: yes | n/a for claim | 4 drops / **0 claims** (30d) | n/a to gates specifically | **INVESTIGATE** — dead conversion surface, likely not a gate problem |
| Buffer/X link-preview card | None by default (`TBCC_X_USE_LINKVERTISE=0`); loot→spicy→affiliate priority | No (by design) | mixed | ~200+ across ~20 affiliate refs, 39 on spicy | **HIGH** if flipped to LV — this is the exact failure the pillar-2/3 tension warns about | **SHIP current default, do not touch.** Fix the spicy leak instead (§1) |
| Secretary bot DM copy | — | verify in repo | — | — | Likely high if gated — DM sits directly upstream of Stars checkout | **verify in repo:** `secretary_drafts.py` / `secretary_sales_coach.py` for any gate URL in DM copy. Not confirmed either way in this pass — treat as clearnet-only by doctrine until checked |
| Erome / ThisVid / Motherless outbound descriptions | none found | No | — | — | Low — genuinely untouched surface | **GAP** — see gap list §3, item 4 |
| Watermark burn-in text | clearnet only (`TBCC_WATERMARK_TEXT`) | No, correctly | — | — | n/a | **SHIP as-is** — not a placement candidate (delivered media, gating it would be hostile) |

### Net-new placements — accept / reject

| Technique | Verdict | Why |
|---|---|---|
| Multi-link locker (reveal several files after one completion) | **Accept** — for zip-flywheel Vault bundles specifically; `wrap_pack_gates_on_ingest` already returns multiple gate URLs per destination, natural fit | Reject upstream of Telegram checkout |
| YouTube unlisted + locker | **Reject** | No YouTube pipeline exists; stands up a whole new content channel for unproven lift — out of scope for a 30-day recovery plan |
| Email/content-locker hybrid | **Reject** as primary | Historically worst-converting wall type for this audience; email collection adds a data-liability surface the brief didn't ask for |
| In-app browser vs. external | **Accept as a robustness check**, not a new placement | Telegram's in-app WebView can break scrape/Playwright-style flows tested on desktop — verify before assuming parity |
| Smartlink geo/device routing | **Accept** once volume justifies it | AdMaven/work.ink already support `sub_id`/override APIs — use them, don't build new |
| Custom pre-lander page | **Reject for now** | 200 total gate clicks/30d doesn't justify the build cost yet |
| Direct CPM | **Reject** | This business runs on completion-based CPA by design; a CPM banner network doesn't fit the Telegram-first surface set |
| Offer-wall vs. article-lock | Offer-wall: **already the model.** Article-lock: **reject** | No article/blog surface exists |
| QR on images | **Reject** | No physical/print distribution channel |
| Bio link tree (mixed gated/ungated) | **Accept as an audit**, not a build | `allmylinks.com` is already a classified URL category in `buffer_x_link_order.py` — a link-tree surface already exists; check what's on it before adding anything |
| RSS/description lockers on ThisVid/Erome/Motherless | **Accept** — highest-plausible-lift net-new item on this list | Reuses existing `wrap_gate_url` + existing browse/upload tooling; needs a caption template and a read of `docs/THISVID_TOS.md` / `docs/MOTHERLESS_TOS.md` first |
| Discord | **Reject** | Telegram-first per the brief's own instruction |

---

## 3. Industry gap list (ranked by expected incremental pennies with low Stars damage — not novelty)

No verifiable 2026 CPA/RPM benchmark source is available in this pass — any rate figure below would be invented, so this list is ranked **ordinally**, not by dollar estimate. Where a technique-level rate claim would normally appear, it's marked *industry folklore, unverified* rather than stated as fact.

1. **Fix the beacon-paste gap.** Not a new technique — but every ranking below is provisional until this is resolved, because right now nobody can tell whether LV is under-earning or simply unmeasured.
2. **Book LootLabs into the income ledger** (`SOURCE_LOOTLABS` + label + manual-entry path). Near-zero engineering cost; unlocks a provider that's already fully wired into the wrap layer and just can't be counted.
3. **AdMaven/Work.ink Smartlink `sub_id` geo/device tagging.** Code already supports `TBCC_ADMAVEN_SUB_ID` (7-char) — use it per lane/campaign instead of firing blind.
4. **ThisVid/Erome/Motherless description-locker line.** Reuses `wrap_gate_url` directly; gated on reading the two existing TOS docs first, not on new infrastructure.
5. **Multi-link locker for zip-flywheel Vault bundles.** Low build cost — `PackGateIngestResult` already carries multiple gate URLs per destination.
6. **Re-engagement lockers** (returning-user gate, distinct from first-touch). Plausible but no supporting infra exists today; rank low until items 1–5 land and there's a real baseline click volume to re-engage against.
7. **Premium publisher-tier applications** (LV/AdMaven higher RPM tiers). Worth applying for once a real volume/quality history exists — at 200 clicks/30d total, the account likely doesn't qualify yet. *Industry folklore, unverified: tier upgrades typically require sustained monthly volume thresholds most CPA networks don't publish.*
8. **Cloaking / domain spinning.** Not ranked — rejected outright, see red-line appendix.

---

## 4. Robustness plan

- **Rotation-seed bug:** `pick_gate_provider()` uses `providers[hash(seed) % len(providers)]`. CPython salts `str.__hash__` per process by default (`PYTHONHASHSEED`), so the same URL can pick a different provider across worker restarts — undermining any attempt to reason about "which provider handled this link" after a redeploy. Fix: swap to a stable hash (`hashlib.md5(seed.encode()).hexdigest()`), not Python's built-in `hash()`.
- **Failover order:** `pack_gate_wrap.py`'s `ingest_gate_provider_order()` (LV→AdMaven→work.ink) is real and env-driven. Confirm it's actually exercised everywhere by checking whether any callers pass an explicit `provider=` to `wrap_gate_url()` — that bypasses failover entirely for that call site.
- **Playwright:** `playwright install chromium` on the island — the confirmed root cause of the LV sync failure, one command.
- **Cookie rotation:** `_cookie_header()` in `income_sync.py` already supports file-based cookies (`TBCC_ADMAVEN_COOKIE_FILE`, `TBCC_WORKINK_COOKIE_FILE`) as an alternative to inline env vars — easier to rotate without a redeploy. Use this path, not the inline-env one, going forward.
- **Payout ledger:** `record_income_payout.py` / `record_manual_income()` already exist and are dry-run-by-default (`--execute` required) — good design, no changes needed. Needs: (a) LootLabs as a valid source (item 2 above), (b) a standing weekly cadence instead of ad hoc (see calendar).
- **Dead-link watchdog:** none exists today (verify in repo: no scheduled dead-link check found in this pass). Recommend a lightweight weekly job that HEAD-checks the 16 manual gate destination URLs in `aof_manual_gate_links.py` and pages on 404/redirect-loop — reuses the same `httpx` client pattern already in `income_sync.py`.
- **Health surface:** `GET /analytics/income/poll-status` and `/analytics/ops-picture` already expose everything needed for this. No new dashboard endpoint required — the underlying data (Playwright, cookies) is what's broken, not the visibility into it.

---

## 5. 30-day infra calendar — fixes before new networks

**Week 1 (days 1–7): fixes only. No new CPA network signups.**
- Day 1 — Paste real beacon URLs (`api.powercore.app/r/wk31-lv-*`) into all 16 LV dashboard slugs; verify each with a redirect check before/after (same method used in this report for the `ass` lane).
- Day 2 — `playwright install chromium` on island; re-run income poll; confirm LV sync returns a real cumulative number instead of the launch error.
- Day 3 — Add `SOURCE_LOOTLABS` to `income_ledger.py` + a manual-entry path; confirm `record_manual_income(source="lootlabs", ...)` no longer raises.
- Day 4 — Pull AdMaven/Work.ink dashboard cookies into `TBCC_ADMAVEN_COOKIE_FILE` / `TBCC_WORKINK_COOKIE_FILE` on island; re-run poll; confirm both flip from `skipped` to `ok`.
- Day 5 — Fix `pick_gate_provider()`'s seed hashing (stable hash, not built-in `hash()`).
- Day 6 — Investigate the 39-click/0-touch spicy-companion leak; confirm the caption's URL resolves to a working `?start=` deep link.
- Day 7 — Re-pull `/analytics/gate-funnel` and `/analytics/ops-picture`; diff against this report's snapshot. That diff is the real "week 1 impact" number — not a projection.

**Week 2 (days 8–14): coverage on surfaces that already exist.**
- Day 8 — Add `sub_id` geo/campaign tagging to AdMaven/Work.ink wraps on the 3 highest-click lanes.
- Days 9–10 — Wire a gate line into ThisVid/Erome/Motherless description templates, after reading `docs/THISVID_TOS.md` and `docs/MOTHERLESS_TOS.md`.
- Day 11 — Ship a multi-link locker on the next zip-flywheel Vault-style bundle.
- Days 12–13 — Investigate Goblin claims=0 despite drops=4 (separate root cause, shares the claim surface).
- Day 14 — Ledger review: is `external_usd` trending up now that instrumentation is fixed?

**Week 3 (days 15–21): robustness.**
- Day 15 — Build the dead-link watchdog (weekly HEAD-check on the 16 manual gate destinations).
- Day 16 — Confirm failover is actually invoked everywhere (no silent `provider=` bypasses).
- Days 17–18 — Apply the beacon-paste + destination-repair pattern to any manual gate key not yet covered.
- Days 19–21 — Standing weekly `record_income_payout.py` cadence begins (e.g., every Friday).

**Week 4 (days 22–30): only now consider net-new.**
- Days 22–24 — If, and only if, weeks 1–3 show LV/AdMaven/Work.ink volume genuinely can't grow further on existing surfaces, evaluate one additional network or a premium-tier application — not before.
- Days 25–30 — Full-month before/after comparison against this report's snapshot; feed into the next ops-picture report.

---

## 6. Red-line appendix — considered and rejected

| Technique | Verdict | Why |
|---|---|---|
| LV/AdMaven as the primary X/Buffer preview card | **Rejected** | `buffer_x_link_order.py`'s own docstrings record this exact failure already happening once (*"affiliate-first + spicy-first were sending Buffer clicks to partners with 0 bot_clicks"*), patched by pinning loot/spicy first. The live snapshot shows even that pin still leaking on one caption (39/0 spicy clicks). Putting a locker in that slot repeats the same failure at gate-completion cost instead of zero cost. |
| Cloaking / domain spinning | **Rejected** | Highest ban-risk technique on the list; directly works against the brief's own "resilient multi-provider over max RPM on one banned domain" instruction. No code path exists for it and none should be added. |
| Stacking two paid walls on one purchase | **Rejected — already structurally enforced.** | `prompt_gate_placement.py`'s `VIOLATION_CHANNEL_GATE_AND_PROMPT` / `VIOLATION_DUAL_LV` checks already block this. No action needed beyond confirming the guard holds. |
| Lane Pass ($3 door) | **Rejected** | Per `LOOT_LANE_ECONOMY.md` — lanes aren't shippable yet. Not invented here. |
| Fake claimed-counts / fake buyer counts | **Rejected** | No code path exists for this and none should be added. This report leaves Goblin's real `claims_in_range = 0` as-is rather than dressing it up. |
| Email-submit content lockers | **Rejected** as primary technique | See gap list §3 — worst-converting wall type for this audience, adds a data-handling liability not asked for. |
| Gating clearnet checkout / goblin claim / payment-bot deep links | **Rejected — already structurally enforced.** | `is_protected_clearnet_url()` / `VIOLATION_GATE_PROTECTED_URL` already block this. |
| A second Telegram bot process for any item above | **Rejected** | Per repo-root `CLAUDE.md` operator policy. Nothing in this plan requires it — every change here is an env var, a ledger schema addition, or existing worker logic. |

---

## Corrections to the brief's stated facts

- The brief describes the wrap order as "Linkvertise → AdMaven → work.ink" — confirmed correct (`pack_gate_wrap.py`'s `_INGEST_PROVIDER_ORDER`), but the brief doesn't mention that **LootLabs is a fourth, fully-coded provider** that's invisible in both the ingest order and the income ledger. That's a real gap the brief's own file-list didn't anticipate.
- The brief frames "Linkvertise ledger has historically shown ~$16 earned and paid out" as background color — live data confirms this exactly ($16.00 gross, $16.00 withdrawn 2026-07-30), and also confirms the ledger has produced **zero** new entries since that date, 16 days before this snapshot.
- The brief says "treat 'we don't see it in the dashboard' as instrumentation failure, not proof of $0" for owned fills — the same logic turns out to apply even harder to the gate side: the beacon-paste gap (§1) means the entire LV lane-click dataset in `gate_funnel` may be measuring nothing at all, not measuring low traffic.
