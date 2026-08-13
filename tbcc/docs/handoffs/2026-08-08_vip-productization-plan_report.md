# VIP Productization — Plan / Ask Report

**Date:** 2026-08-08
**Mode:** Plan / Ask — no production code touched this pass.
**Ask doc:** `2026-08-08_vip-productization-plan-ask.md`
**Verification (future phases):**
```bash
cd tbcc/backend
pytest tests/test_aof_vip_deal_copy.py tests/test_aof_vip_fulfillment.py tests/test_vip_intro_eligibility.py tests/test_aof_feed_rhythm_v2.py -q --tb=short
```

---

## Operator menu — pick P0–P6 for grind pass 2

| Phase | Scope | Effort | Codes-exist already? | Recommended |
|-------|-------|:------:|:---------------------|:-----------:|
| **P0** | Pinned comparison copy — @aofmainhub (code) + Loot Room (operator paste) | S | Pin mechanism exists, comparison content does not | ✅ |
| **P1** | Flip checkout default to full deal stack (kill `TBCC_VIP_CHECKOUT_CAPTION_MINIMAL`) | S | Full-stack renderer already written, just not default | ✅ |
| **P2** | VIP mention in daily channel spotlight + standard post footer | M | Spotlight has **zero** VIP mentions today; footer is bot-name-only | ✅ |
| **P3** | VIP-exclusive content policy (real vault content, not just bigger roll) | M — **judgment ⚠️** | `AOF VIP POOL` pool exists but nothing feeds or posts from it | ⚠️ needs operator call |
| **P4** | Friday mega ritual — public tease + delayed public wrap | M | Weekly mega drop to VIP is live; public-side tease is not | Recommend after P0–P2 land |
| **P5** | `/status` → VIP member home | M | `/status` is a bare plan+expiry list today | Recommend, medium priority |
| **P6** | Retention — companion drip, god-roll streak, renewal DMs | L | **Renewal DMs already shipped** (2026-08-02); only streak + companion drip are net-new | Recommend renewal-copy refresh now, streak/drip later |

**Fastest path to revenue signal:** P0 + P1 + P2 are all copy/config changes against code paths that already exist and are already tested elsewhere in the suite. They're the cheapest, least risky, and most directly answer the operator's own diagnosis ("perks exist in code but are invisible"). Recommend shipping P0+P1+P2 as grind pass 2, watching the 30-day metrics in §6, then deciding P3 (the only phase that requires new content operations, not just copy).

---

## 1. Current-state audit

### 1.1 What's implemented vs copy-only

| Pillar (strategic frame) | Status | Evidence |
|---|---|---|
| **① Unified Vault** (one feed vs scattered lanes) | Partially real | VIP channel exists (`AOF_VIP_IDENT`), receives a mirrored copy of every public network-lane post via `aof_vip_mirror.py`. But the "vault" is not a separate deeper pool — see §1.4. |
| **② Skip Button** (direct/ad-free links) | **Real, live** | `aof_vip_mirror.transform_caption_for_vip` / `transform_buttons_for_vip` rewrite gate/Linkvertise URLs to direct file-host links when a `LootModifier` mapping exists; falls back to keeping the gate link if no direct mapping is stocked. |
| **③ Daily God Roll** (`/viproll`) | **Real, live** | `cmd_viproll` in `backend/bots/loot_bot.py:596`, registered as a command handler (`loot_bot.py:1685`). |
| **④ Weekly Mega** (Friday direct folder) | **Real, live, but data-dependent** | `aof_vip_weekly_mega.py` + `app/workers/vip_weekly_mega_worker.py`, registered in Celery beat (`celery_app.py:241`, hourly tick, day/hour gate defaults Friday 17:00 UTC). Fires only if an active `LootModifier(kind="mega_pack")` row with a resolvable direct URL exists — this is an ops/content dependency, not a code gap. |
| **⑤ Companion bundle** (gate skip + bonus credits) | **Real, live** | `aof_vip_perks.grant_vip_subscription_perks` grants `TBCC_VIP_COMPANION_BONUS_CREDITS` (default 3) + `vip_subscriber` flag on fulfillment, idempotent per Stars `charge_id` via Redis. |

**Bottom line:** all five pillars have real, working code behind them. The operator's diagnosis is correct on the *marketing* side, not the *engineering* side — the gap is that none of this is visible at the moments that matter (checkout, public post, pin, `/status`).

### 1.2 Minimal checkout caption — where it hides the deal stack

`backend/app/services/aof_vip_deal_copy.py:110-116`:

```python
if minimal is None:
    raw = (os.getenv("TBCC_VIP_CHECKOUT_CAPTION_MINIMAL") or "1").strip().lower()
    minimal = raw not in ("0", "false", "no", "off")
...
if minimal:
    return minimal_checkout_caption_html(db, pid)
```

**The default is `"1"` (minimal=True) when the env var is unset.** The ask doc itself states this is live on island ("Checkout often shows minimal caption `TBCC_VIP_CHECKOUT_CAPTION_MINIMAL=1`"), and `.env.example:42` documents the same default in its comment (`# TBCC_VIP_CHECKOUT_CAPTION_MINIMAL=1  # One dense paragraph on Pay ⭐ bot reply (not bullet wall)`) — both confirm minimal is the intended, deployed default, not just a theoretical code fallback. The minimal renderer (`aof_main_group_copy.py:20-42`) is one dense sentence:

> 🎫 **AOF VIP** — 1500⭐/30d · skip the gates, daily god roll, weekly mega dump, @aof_spicybot_bot credits. Unwrapped lanes, bigger drops, VIP-only perks — public stays on the wrapped feed. *Tap Pay ⭐ — instant access.*

Compare to the **already-written, unused-by-default** full stack (`aof_vip_deal_copy.py:98-141`): 5 labeled bullets (Hall Pass, Daily God Roll, Weekly Mega, First Look, Companion), a "Public vs VIP" two-line comparison, and a rotating urgency line. This is the exact deal stack the operator wants at checkout — **it already exists, it's just gated off by a default.**

**Reach:** this caption function is called from `checkout_followup_caption_html()`, which is wired into `deliver_stars_checkout_bot_followup()` — called from **both** `scheduled_post_service.py` (every Telethon-sent scheduled/relay post across the whole network with checkout enabled) and `listening_relay_send.py`. This is not a niche surface; it's the Bot API reply that rides under most monetized posts network-wide.

### 1.3 Is weekly mega + early drop actually schedulable/smokeable?

- **Early drop:** `aof_vip_early_drop.py` — `TBCC_AOF_VIP_EARLY_DROP_ENABLED` default on, `TBCC_AOF_VIP_EARLY_DROP_MINUTES` default 60. Gate is `should_schedule_vip_early_drop()` → `is_vip_mirror_pool()`. This works off the *existing* scheduled-post pipeline (mirror fires before the public send), so yes — schedulable today, no missing plumbing.
- **Weekly mega:** live Celery beat task, hourly check against day/hour env vars, `LootModifier(kind="mega_pack")` lookup. **Smokeable today** with `queue_weekly_vip_mega_drop(db, force=True)` if at least one active mega_pack modifier exists (these are actively used elsewhere — `loot_pack_pool.py`, `seed_aof_packs_launch.py`, `erome_promo_wire.py` — so stock likely exists, but this plan cannot confirm island DB state without a query this pass).

### 1.4 What % of VIP content is mirror-only vs `AOF VIP POOL` exclusive

**This is the single most important audit finding.**

`aof_vip_pool.py`:
```python
def is_vip_mirror_pool(pool) -> bool:
    if str(pool.name) == AOF_VIP_POOL_NAME:
        return False
    return str(pool.name) in vip_mirror_pool_names()
```

`AOF_VIP_POOL_NAME = "AOF VIP POOL"` (`aof_network.py:31`) is explicitly *excluded* from the mirror-eligible set — meaning it's meant to be the separate, exclusive vault. But grepping the whole backend for `AOF_VIP_POOL_NAME`, the only consumers are:
- `scripts/ensure_aof_vip_channel.py` — creates the empty pool row if missing.
- `aof_feed_rhythm_v2.vip_social_proof_line()` — reads its approved-media count for a stat-tease line.
- `scripts/_island_inspect_vip.py` — an ops inspection script.

**No scheduler, worker, or ingestion path posts from `AOF VIP POOL`.** There is no robocopy/watch/import flow that deposits media into it (unlike the public lane pools, which are fed by the scrape → `MEDIA_GATEKEEPER` → approval pipeline). Every single VIP delivery mechanism (`aof_vip_mirror.py`, `feed rhythm interjection`, early drop) sources media from the **same public lane pools** subscribers already see, just with a bigger album roll (3–10 vs public's 1) and ad-free/early delivery.

**Effective VIP-exclusive content today: ~0%.** VIP is "more of the same lane, sooner, unwrapped, bigger album" — not "a different vault." This is *exactly* the free-lane-sub complaint the operator is diagnosing, and it's a real content-ops gap, not a marketing gap — see §3 P3.

Cross-reference: `docs/LANE_READINESS_AUDIT.md` (2026-07-17, stale but directionally useful) shows total network approved inventory ≈ 886 photos + 3,340 videos across 11 lanes, none meeting the 2,500/2,500 subtopic floor. With source pools this thin, a "bigger roll from the same pool" has a real ceiling — there often isn't much more to roll into a bigger album before repeats surface.

### 1.5 Doctrine conflict to flag ⚠️

`docs/LOOT_LANE_ECONOMY.md` §Watermark tiers states Glimpse/Promo tier should have **forwards enabled** ("leak = ad, free distribution"). But `telegram_content_protection.py` (`TBCC_CHANNEL_PROTECT_CONTENT`, default **on**) is applied unconditionally to every Telethon scheduled send (`scheduled_post_service.py:770,955` wrap **all** sends in `telethon_protect_context`, with no tier branch). This matches the operator's own stated "forwarding disabled on previews" scarcity win from the ask doc — so the code is doing what the operator wants in practice, but it now **contradicts the written doctrine table** in `LOOT_LANE_ECONOMY.md` (written 2026-07-17, before this scarcity move shipped). Recommend a docs-only fix: update the watermark-tier table in `LOOT_LANE_ECONOMY.md` to reflect "forwards off everywhere now" rather than changing code. Flagging per your instruction to surface doctrine conflicts — no code change proposed here.

---

## 2. Gap analysis

### 2.1 Why free lane subs don't feel pain

1. **Same pool, bigger roll isn't legible as "different."** A subscriber scrolling a public lane's addlist sees the same photos VIP would roll from — VIP is quantity/timing/link-friction, not a different collection. Nothing in the public post *tells them* the album they're looking at is a roll-truncated (size 1, `TBCC_NETWORK_ALBUM_SIZE` default) subset of a 3–10 VIP roll from the identical pool.
2. **Lane inventory is thin** (§1.4) — with ~250-600 approved items per lane, "VIP rolls bigger albums" reads as a small quantitative bump, not qualitatively different access, especially once a subscriber has scrolled the whole addlist once.
3. **No comparison artifact exists anywhere in the product.** Grepped the whole backend for a public-vs-VIP table/comparison copy block — the strategic frame's 6-row comparison table (`Where / Album size / Links / Timing / Daily pull / Weekly`) does not exist as shipped copy in any scheduler, pin, or bot reply. It's a spec in the ask doc, not a product surface. This is the direct engineering gap behind "value prop is abstract."

### 2.2 Which perks are invisible at the decision moment

| Surface | What a free-lane sub actually sees today | Evidence |
|---|---|---|
| **Checkout modal / Bot API follow-up** | One dense sentence (minimal caption, default on) | §1.2 |
| **@aofmainhub pin** | Weekly-refreshed single-paragraph CTA (`mainhub_growth.py:28-32`, `CTA_CAPTION`) — no comparison table, no pillar breakdown | `mainhub_growth.py` |
| **Daily channel spotlight** (`mainhub_channel_spotlight.py`) — the *daily* rotating promo through each lane, arguably the highest-frequency touchpoint a repeat visitor sees | **Zero VIP mentions.** Grepped the file for "VIP" — no matches. Spotlight sells the free lane, never contrasts it with VIP. | `mainhub_channel_spotlight.py` |
| **Standard per-post footer** (`build_addlist_footer`, used across most network lane posts) | `🗝 @bot · /loot · /subscribe · /referral` — bot username + bare command list, no value stack, no numbers | `aof_growth_hub.py:196-212` |
| **Feed rhythm interjection** (Loot Room only) | Does carry `vip_roll_tease_line` (public tease size vs VIP roll size) — but this is one scheduler, on one channel (the hub, not the individual lane channels where the "I already have the library" feeling forms) | `feed_rhythm.py:159-163` |
| **Network liveness** | Carries `vip_social_proof_line` — a photo/video-count stat comparing VIP pool vs main pool — but since `AOF VIP POOL` is empty (§1.4), this likely renders the generic fallback line ("standalone channel: bigger rolled albums...") rather than real numbers, which is a weaker claim than intended | `aof_feed_rhythm_v2.py:211-245` |
| **`/status`** | Plan name + expiry date, nothing else | `bots/payment_bot.py:2642-2680` |

**Synthesis:** the two most-trafficked surfaces (daily spotlight, standard post footer) say nothing about VIP at all. The two surfaces that do mention VIP (feed rhythm interjection, network liveness) live on the hub/commons channel, not on the individual lane channels where a free subscriber forms the "I already have this" belief. Checkout itself — the one moment someone is primed to decide — shows the least, not the most.

---

## 3. Phased implementation plan

### P0 — Public vs VIP comparison copy + pin strategy

**Scope:** Author the comparison table as real product copy; wire it into the @aofmainhub automated pin; hand the Loot Room variant to the operator for manual pin (that pin is operator-authored markdown, not code-driven — see `docs/loot-room-pinned-instructions.md`).

**Files:**
- `backend/app/services/mainhub_growth.py` — replace `CTA_CAPTION` (lines 28-32) with the new comparison copy (§4.A). Scheduler `MAINHUB_SCHED_CTA_NAME` already runs weekly (`interval_minutes=60*24*7`) and is already `pin_after_send=True` — no new scheduler needed, just new content.
- `docs/loot-room-pinned-instructions.md` — operator paste, new "AOF VIP vs free lanes" section (§4.A variant).

**New tests:** `backend/tests/test_mainhub_growth.py` (does not exist today) — assert `CTA_CAPTION` contains the 5 pillar keywords (Vault/Skip/God Roll/Mega/Companion) and stays within Telegram caption length limits (1024 chars for photo captions if the CTA ever attaches media; today it's `pool_id`-bound to a photo pool, so caption budget matters — check current `CTA_CAPTION` length and keep headroom).

**Env vars:** none new.

**Operator steps:** paste the Loot Room comparison block into the group and re-pin (manual — Loot Room pin is not scheduler-driven).

**⚠️ Verify before pinning — Skip Button (pillar ②) is stock-dependent, not unconditional.** `aof_vip_mirror.transform_caption_for_vip` / `direct_url_for_gate` only rewrite a gate link to a direct host when a matching `LootModifier` row (`bypass_vip=True`, or a resolvable `k2s`/target mapping) exists for that URL; otherwise the gate link is kept as-is in the VIP send (`aof_vip_mirror.py:142`, "No bypass mapping — keep the Linkvertise gate"). A pin that promises "VIP → direct, ad-free" unconditionally over-promises if coverage is thin, which is a churn/refund risk on a paid product. Before pinning, check direct-link coverage:
```python
# one-off check, run via backend shell / script — no DB write
from app.database.session import SessionLocal
from app.models.loot import LootModifier
db = SessionLocal()
total = db.query(LootModifier).filter(LootModifier.active.is_(True)).count()
direct = db.query(LootModifier).filter(LootModifier.active.is_(True), LootModifier.bypass_vip.is_(True)).count()
print(total, direct, f"{direct/total:.0%}" if total else "n/a")
```
§4.A already ships the conservative "direct where mapped" phrasing rather than an unconditional claim for this reason. If the check above shows coverage is high (rough guide: 80%+ of active modifiers), it's safe to tighten the line back to an unconditional "direct, ad-free" — but don't ship the stronger claim without running the check first.

**Rollback:** revert `CTA_CAPTION` string; scheduler content refreshes on its next weekly tick (or trigger `apply_mainhub_growth(db, execute=True, post_now=True)` to force immediate re-send + re-pin).

---

### P1 — Full checkout value stack

**Scope:** Flip the default so the deal-stack renderer (already fully built, §1.2) is what buyers see, without touching the render logic itself.

**Files:**
- `backend/app/services/aof_vip_deal_copy.py:110-112` — change the default fallback from `"1"` to `"0"`:
  ```python
  raw = (os.getenv("TBCC_VIP_CHECKOUT_CAPTION_MINIMAL") or "0").strip().lower()
  ```
- Add an **intro-month variant**: `build_vip_deal_caption_html` currently doesn't branch on whether `plan_id` resolves to the intro SKU (`VIP_INTRO_PLAN_NAME` in `aof_vip_membership.py`). Add an `is_vip_intro_plan()` check (reuse `vip_intro_eligibility.is_vip_intro_plan`) to swap the headline price line to intro framing (§4.B).

**New tests:** extend `tests/test_aof_vip_deal_copy.py` — add `test_build_vip_deal_caption_full_stack_is_default()` asserting `minimal` resolves `False` with the env var unset, and `test_build_vip_deal_caption_intro_variant()` asserting intro-plan copy differs from standard.

**Env vars:** `TBCC_VIP_CHECKOUT_CAPTION_MINIMAL` — default flips from effectively-on to effectively-off. `.env.example:42` already documents the flag (currently commented as `=1`) — update that comment to reflect the new default (`=0`, "full deal stack") so the reference file doesn't contradict the code, and so operator can still restore minimal per-surface if the fuller caption underperforms.

**Operator steps:** island deploy only — no manual data change. Watch Bot API follow-up caption on the next few scheduled sends to confirm length stays under Telegram's 1024-char caption / 4096-char message limits (the full stack + urgency line is ~700-900 chars in HTML — should be safe, but verify on a real send since HTML entity escaping adds bytes).

**Rollback:** set `TBCC_VIP_CHECKOUT_CAPTION_MINIMAL=1` in island `.env`, restart payment-adjacent services (no redeploy needed — it's read at call time via `os.getenv`).

---

### P2 — Public post footers (early + bigger + direct CTA)

**Scope:** Two separate insertion points — the daily spotlight (currently silent on VIP) and the standard per-post footer (currently bot-name-only).

**Files:**
- `backend/app/services/mainhub_channel_spotlight.py` — `build_spotlight_caption_html()` (line 77+): append a one-line VIP contrast after the lane hook, using the `{minutes_early}` / `{album_public}` / `{album_vip}` template (§4.C) fed by `vip_early_drop_minutes()`, `main_group_album_size()`, `vip_album_roll_min()/max()` from `aof_feed_rhythm_v2.py` (already-built helpers — no new state).
- `backend/app/services/aof_growth_hub.py` — `build_addlist_footer()` (line 196): add an optional VIP contrast line, gated by a new env flag so it can be A/B'd per-surface rather than forced everywhere at once (footer is used very broadly; a forced always-on change is higher blast radius than the operator likely wants for a first pass).

**New tests:**
- `backend/tests/test_mainhub_channel_spotlight.py` (exists) — add case asserting VIP line renders with correct placeholder substitution.
- `backend/tests/test_aof_growth_hub.py` — **does not exist today** (`ls tests` confirms no match) — new file, assert footer VIP line respects the new flag default and off-state.

**Env vars:** `TBCC_POST_FOOTER_VIP_CONTRAST` (new, default `1`) — lets operator kill this specific line network-wide without reverting the whole footer if it reads as spammy in testing.

**Verified: no VIP-mirror leak risk.** Checked whether the new footer/spotlight lines could get sold to paying VIP subscribers on their own mirrored posts:
- `build_addlist_footer()`'s entire output (including any new VIP-contrast line added inside it) sits after the `FOOTER_MARKER` — and `aof_vip_channel_copy.strip_vip_affiliate_blocks()` (called by `scrub_caption_for_vip_mirror()` on every VIP mirror send) explicitly cuts everything from `f"📌 <b>{FOOTER_MARKER}</b>"` onward (`aof_vip_channel_copy.py:54`). The whole footer block is already stripped before VIP delivery, so a new line inside it is stripped too — safe by construction, no new scrub rule needed.
- The daily spotlight posts to `MAINHUB_CHANNEL_IDENT`, which is **not** a member of `AOF_NETWORK_CHANNELS` (`aof_network.py:62+` — mainhub is the hub, distinct from the lane channels in that tuple) and its `SFW_X_PROMO_POOL_NAME` pool isn't a VIP-mirror-eligible pool either. `aof_vip_mirror.should_mirror_scheduled_post()` gates on `channel_id in _network_channel_ids(db)` first — mainhub posts fail that check and are never mirrored to VIP at all. No leak risk for the spotlight line either.

**Operator steps:** island deploy; watch 2-3 days of lane posts for caption-length overflow (adding a line to the highest-frequency footer is the biggest reach change in this plan — worth a manual spot check before P3).

**Rollback:** `TBCC_POST_FOOTER_VIP_CONTRAST=0`.

---

### P3 — VIP-exclusive drop policy ⚠️ judgment call

**Scope:** This is a **content-operations** decision, not a code gap — `AOF VIP POOL` and its ingestion are unbuilt (§1.4), and building them means committing scrape/import/robocopy capacity to a pool that competes with already-thin public lanes (§1.4, `LANE_READINESS_AUDIT.md`).

**Two paths, not mutually exclusive:**

1. **Vault_clean robocopy** (aligns with `LOOT_LANE_ECONOMY.md`'s existing three-way fan-out: `promo_heavy` / `lane_light` / `vault_clean`). The `robocopy_watermark.py` service already supports a clean tier — wiring its output into `AOF VIP POOL` (rather than leaving `vault_clean` output unrouted) is the smallest lift: reuse existing pipeline, new destination only.
2. **Curated-pack-style exclusivity** — reserve a rotating slice (e.g., newest N% of each lane's approved backlog) for VIP-only posting via `AOF VIP POOL`, delayed N days before it becomes eligible for public mirror. This directly answers "what should public lanes NEVER get" (see §5) without needing new scrape volume — it's a release-timing policy on existing inventory.

**Recommendation:** start with path 2 (timing-based exclusivity on existing inventory) — zero new scrape/ops burden, ships against current lane depth, and is reversible by changing a delay window. Path 1 (dedicated vault content) should wait until lane readiness audit (§1.4) shows healthier depth; committing scrape capacity to a *third* destination while public lanes sit at ~10-15% of subtopic floor risks starving the public funnel that feeds VIP in the first place.

**Files (path 2, if approved):** `aof_vip_pool.py` (new `is_vip_pool_eligible(media, *, delay_days)` helper), `aof_vip_mirror.py` (`should_mirror_scheduled_post` — exclude media newer than the delay window), `AOF VIP POOL` becomes the actual posting source for a new VIP-only scheduler (net-new, since nothing posts from it today).

**New tests:** `backend/tests/test_aof_vip_pool.py` (new file) — delay-window eligibility logic.

**Env vars:** `TBCC_VIP_EXCLUSIVE_DELAY_DAYS` (new), `TBCC_VIP_EXCLUSIVE_TARGET_PCT` (new, informational — used for reporting, not enforcement, in v1).

**Operator decision needed:** target % exclusive (recommend starting **10-15%** — newest approved items per lane, held back N days) and delay window (recommend **48-72h** — long enough to feel exclusive, short enough not to starve public cadence given thin inventory).

**Rollback:** set delay to `0` — mirror behavior reverts to today's "everything mirrors immediately."

---

### P4 — Friday mega ritual + public tease

**Scope:** Weekly mega delivery to VIP is live (§1.3). What's missing is the **public-side tease** that makes non-VIP subscribers feel the Friday ritual exists and is worth upgrading for.

**Files:**
- New scheduler in `backend/app/services/aof_vip_weekly_mega.py` — a public-lane tease post (gated version / delayed reveal) that fires alongside `queue_weekly_vip_mega_drop`, referencing the same `LootModifier` but withholding the direct link (public gets the gated/Linkvertise version per doctrine, or a delayed-by-N-days wrap, consistent with `LOOT_LANE_ECONOMY.md`'s "Sitting it out? It joins the Warehouse" framing).
- `backend/app/workers/vip_weekly_mega_worker.py` — call the new public-tease function after the VIP drop succeeds.

**New tests:** `backend/tests/test_aof_vip_weekly_mega.py` — **does not exist today** (`ls tests` confirms no match, despite `TEST_MAP.md`'s `test_aof_vip_*` glob implying coverage) — new file, covering both the existing `queue_weekly_vip_mega_drop` (currently untested) and the new public-tease caption builder.

**Env vars:** `TBCC_VIP_WEEKLY_MEGA_PUBLIC_TEASE_ENABLED` (new, default `1`), `TBCC_VIP_WEEKLY_MEGA_PUBLIC_DELAY_DAYS` (new, default matches P3's delay if shipped, else recommend `3`).

**Operator steps:** confirm at least one `mega_pack` `LootModifier` is always stocked (ops responsibility, not this plan's scope) so the ritual doesn't silently skip weeks.

**Rollback:** `TBCC_VIP_WEEKLY_MEGA_PUBLIC_TEASE_ENABLED=0` — VIP-side drop is unaffected either way (independent code paths).

---

### P5 — Payment bot `/status` → VIP member home

**Scope:** Replace the bare plan+expiry list with a pillar-framed home screen.

**Files:** `backend/bots/payment_bot.py` — `reply_status()` (lines 2642-2680). Add, when an active main-section (VIP) subscription is present:
- Days-left framing (already have `expires_at`, just needs `(expires_at - now).days` math and copy).
- God-roll-ready indicator — call into loot API to check today's `/viproll` claim state for this user (needs a lookup; loot_bot.py's claim logic should already track per-user per-day state for the daily god roll — reuse rather than duplicate).
- Mega countdown — next Friday `vip_weekly_mega_day_utc()`/`vip_weekly_mega_hour_utc()` minus now.
- Companion credits balance — `companion_access.get_access(uid)` already exists (used in `aof_vip_perks.py`) — surface the balance.

**New tests:** `backend/tests/test_payment_bot_status.py` — **no payment-bot test file exists today** (`ls tests` confirms no `test_payment_bot*` match) — new file, mock subscription + loot-claim + companion-access state, assert all four elements render for an active VIP user and gracefully degrade for non-VIP.

**Env vars:** none required; reuses existing.

**Operator steps:** none beyond deploy — this is a pure bot-command change.

**Rollback:** revert `reply_status()` to current plan+expiry-only rendering.

---

### P6 — Retention (companion drip, god-roll streak, renewal DMs)

**Scope correction from the ask doc:** renewal DMs are **already shipped** — `lifecycle_dm_copy.py` + `lifecycle_dm_outreach.py` + `app/workers/lifecycle_dm_worker.py`, live since 2026-08-02 per `SPRINT_STATE.md`, covering `PRE_EXPIRY_7D/3D/1D/0D` and `POST_EXPIRY_1D/7D` segments, plus loot re-engage and companion re-engage. This phase is **copy refresh + two net-new mechanics**, not a net-new build.

1. **Renewal copy refresh** (small): `lifecycle_dm_copy.py` `build_subscription_lifecycle_message()` — current copy ("Renew now to keep VIP lanes without a gap") doesn't reference the 5 pillars by name. Refresh to name what specifically lapses (god roll, mega, direct links) — loss-framing per pillar converts better than generic "access."
2. **God-roll streak** (net-new, **L** effort): needs a persistence layer for consecutive-day `/viproll` claims (Redis counter keyed by user, similar pattern to `aof_vip_perks._perks_key` idempotency keys) + a streak-broken re-engage segment added to `LootReengageSegment`.
3. **Companion drip** (net-new, **M** effort): monthly scheduled companion-bot message to VIP subscribers independent of inactivity (the existing `CompanionReengageSegment` is inactivity-triggered only) — new Celery beat entry + copy variant reusing `_COMPANION_COPY` rotation pattern.

**Files:** `backend/app/services/lifecycle_dm_copy.py`, `backend/app/services/lifecycle_dm_outreach.py`, `backend/app/workers/lifecycle_dm_worker.py`.

**New tests:** extend `backend/tests/test_lifecycle_dm_outreach.py` for streak + drip segments.

**Env vars:** `TBCC_VIP_GOD_ROLL_STREAK_ENABLED` (new), `TBCC_VIP_COMPANION_DRIP_ENABLED` (new), both default `0` until copy is validated (this phase touches DM send volume to paying subscribers — start conservative).

**Operator steps:** none for the copy refresh; streak/drip need a decision on cadence before building (weekly? monthly?) — recommend deferring 2 and 3 until P0-P2 metrics land, since they're the largest net-new build in this plan for the least-validated payoff.

**Rollback:** copy refresh — revert strings. Streak/drip — feature-flagged off by default, no rollback needed if never enabled.

---

## 4. Copy pack

All copy matches existing HTML style (`<b>`, `<i>`, `<code>`, inline emoji headers) from `aof_vip_deal_copy.py` / `aof_main_group_copy.py`. Telegram HTML parse mode does not support `<table>` — comparisons render as aligned bullet pairs, consistent with how `vip_roll_tease_line` already does it.

### A. Pinned comparison post (@aofmainhub + Loot Room variant)

```html
🎫 <b>AOF VIP — same network, five upgrades</b>

Free lanes and VIP pull from the same pipeline. The difference is what you get at the door:

📍 <b>Where</b>
Free → scattered lanes, addlist scroll
VIP → one feed, one door

🎲 <b>Album size</b>
Free → 1 (tease)
VIP → 3–10 rolled per drop

🔗 <b>Links</b>
Free → gated / wrapped
VIP → direct where mapped, ad-free — gate stays as fallback until every lane has a direct host

⏱ <b>Timing</b>
Free → public schedule
VIP → ~60 min early

🎰 <b>Daily pull</b>
Free → loot keys / tease
VIP → <code>/viproll</code> — guaranteed high-tier god roll, every day

📦 <b>Weekly</b>
Free → gated / delayed
VIP → direct mega folder, Fridays, VIP only

🤖 <b>Bonus</b> — @aof_spicybot_bot early access + bonus credits on join.

<i>Same content pipeline. VIP is the skip button.</i>
Tap Pay ⭐ or Crypto below — access starts instantly.
```

**Measured length:** 822 UTF-16 code units / 876 UTF-8 bytes (PowerShell `.Length` on the raw block above — UTF-16 code units is what Telegram's caption/message limits count). The @aofmainhub CTA scheduler is `pool_id`-bound with `album_size=1` (a photo send), so it's subject to Telegram's **1024-unit photo-caption cap**, not the 4096 message cap — this block clears it with ~200 units of headroom. The Loot Room variant (plain text, no attached photo) is subject to the 4096 cap and has much more room; the block above can be pasted as-is or extended with more context for that surface.

### B. Checkout caption — full stack (standard + intro variant)

**Standard** (this is what P1 makes the default — already implemented in `build_vip_deal_caption_html`, reproduced here for reference):

```html
🎫 <b>AOF VIP — THE HALL PASS</b> · <b>1500⭐</b> / 30d

One tap from the paid lane. Public stays gated on purpose — VIP is your hassle-free bypass.

<b>What you get:</b>
🚪 <b>Hall Pass</b> — direct hosts in VIP. Public lanes stay gated — that funds the network.
🎰 <b>Daily God Roll</b> — 1 guaranteed high-tier pull/day on @aof_lootgod_bot (<code>/viproll</code>).
📦 <b>Weekly Mega Pack</b> — 1 direct MEGA/TeraBox folder/week in VIP (rotating lane).
⚡ <b>First Look</b> — drops hit VIP ~1h before public · bigger albums · one clean feed.
🤖 <b>Companion early access</b> — @aof_spicybot_bot: 1 free reveal + <b>3 bonus credits</b> on join. More via Stars · /referral earns credits.

<b>Public vs VIP</b>
Public → wrapped links · slower cadence · scattered lanes
VIP → one channel · early · direct · daily roll · weekly mega · companion credits

📦 Next mega drop lands Friday in VIP only — public gets the gated version later.

<i>Tap Pay ⭐ or Crypto below — access starts instantly.</i>
```

**Intro variant** (net-new — swap headline + add urgency framing specific to first-timers):

```html
✨ <b>AOF VIP — FIRST MONTH, $10</b> · one-time intro rate for new members only

Every regular VIP perk, first month discounted. After that: standard ladder, cancel anytime.

<b>What you get:</b>
🚪 <b>Hall Pass</b> — direct hosts in VIP. Public lanes stay gated — that funds the network.
🎰 <b>Daily God Roll</b> — 1 guaranteed high-tier pull/day on @aof_lootgod_bot (<code>/viproll</code>).
📦 <b>Weekly Mega Pack</b> — 1 direct MEGA/TeraBox folder/week in VIP (rotating lane).
⚡ <b>First Look</b> — drops hit VIP ~1h before public · bigger albums · one clean feed.
🤖 <b>Companion early access</b> — @aof_spicybot_bot: 1 free reveal + <b>3 bonus credits</b> on join.

⏳ Intro pricing is one-time, first purchase only — locks in nothing beyond month one.

<i>Tap Pay ⭐ or Crypto below — access starts instantly.</i>
```

### C. Public post footer template (with placeholders)

For P2's spotlight/footer insertion — placeholders resolve from existing helpers (`vip_early_drop_minutes()`, `main_group_album_size()`, `vip_album_roll_min()/max()`):

```html
⭐ <b>VIP rolls {album_vip_min}–{album_vip_max} from this same lane</b> · ~{minutes_early}m early · direct links. This post: {album_public}. @aofsubscriptions_bot /subscribe
```

Rendered example (current defaults: public=1, VIP min/max=3/10, early=60):

```html
⭐ <b>VIP rolls 3–10 from this same lane</b> · ~60m early · direct links. This post: 1. @aofsubscriptions_bot /subscribe
```

### D. VIP welcome DM refresh

Current `vip_welcome_message_html()` (`aof_vip_fulfillment.py:68-88`) is functional but generic bullets. Refresh to name the pillars explicitly and set the first-session expectation (god roll today, mega countdown):

```html
✅ <b>AOF VIP unlocked</b>

👉 <a href="{invite_link}">Join AOF VIP channel</a>
Backup link: <a href="{backup_link}">one-time invite</a>

<b>Your five upgrades, starting now:</b>
🚪 Direct, ad-free links — no more gate hops
🎰 Today's god roll is ready — @aof_lootgod_bot <code>/viproll</code>
📦 Next weekly mega: Friday, VIP only
⚡ Drops hit here ~1h before public, rolled 3–10 per post
🤖 @aof_spicybot_bot — your bonus credits are already in your balance

<i>Keep the invite link as backup. Welcome to the vault.</i>
```

### E. Renewal / expiry nudge — 3 days before (refresh of existing `PRE_EXPIRY_3D`)

Current (`lifecycle_dm_copy.py:129-134`):
> ⏳ **3 days left** on {plan} (expires {exp}). Room access drops when the timer hits — same Stars checkout as before.

**Refreshed** (loss-framed per pillar, not generic "access"):

```html
⏳ <b>3 days left</b> on {plan} (expires {exp}).

When it lapses: no more daily god roll, no Friday mega, links go back to gated. Same Stars checkout — one tap keeps the streak alive.
```

---

## 5. VIP-exclusive content policy — recommendation

- **Target:** 10-15% of each lane's newest approved inventory held VIP-only for a delay window (see P3) — not a dedicated separately-scraped vault, given current lane depth (§1.4).
- **Delay window:** 48-72h. Long enough to read as a real head-start, short enough not to starve public cadence out of an already-thin pool.
- **Vault_clean robocopy → `AOF VIP POOL`:** defer until `docs/LANE_READINESS_AUDIT.md` shows healthier median depth (current snapshot: deepest lane ~642 approved items total, thresholds want 2,500+ per format). Building a third destination pipeline now competes for scrape/import capacity against the public funnel that VIP conversion depends on.
- **What public lanes should NEVER get** (extends `LOOT_LANE_ECONOMY.md`'s existing red lines):
  - The weekly mega direct link (public gets gated/Linkvertise version or delayed wrap only — already the code's behavior in `aof_vip_weekly_mega.py`, keep it that way).
  - Full clean/protected+forwardable combination (existing red line, unaffected by this plan).
  - Anything inside the P3 delay window, once shipped.

---

## 6. Metrics / success criteria (30 days)

Baseline: `docs/handoffs/2026-07-27_vip-reprice-baseline.md` — **~$72.74 / 30d total income, 13 transactions**; VIP-specific: 2 units / 1000⭐ (pre-reprice legacy pricing, captured before the $18 floor went live). Existing kill criterion: rollback to $12 floor if VIP revenue stays below ~$40/mo run-rate **and** key units are flat/down.

**Additional metrics to watch post-P0/P1/P2:**

| Metric | How to read | Target signal |
|---|---|---|
| VIP subscription Stars revenue (30d) | `subscription_stars` income source, VIP plan rows | Meaningfully above the $40/mo kill-criterion floor — ideally trending toward/past the pre-reprice $72.74 total-income baseline being majority-VIP rather than mixed sources |
| Intro-SKU conversion rate | New `VIP_INTRO_SKU` purchases / unique checkout-caption impressions (if beacon-trackable) | Any measurable uptick post-P1 (fuller caption) vs pre-P1 baseline |
| Checkout caption A/B | Compare Stars invoice completion rate in the ~1-2 weeks before/after P1 flips the default | Full stack should not *decrease* completion (risk: longer caption reads as harder sell) — watch for this explicitly |
| Renewal rate | `POST_EXPIRY_1D`/`7D` lifecycle DM click-through (already trackable via `lifecycle_dm_outreach.py` if instrumented) | Directional improvement after §4.E copy refresh |
| Weekly mega cadence | Count of successful `queue_weekly_vip_mega_drop` non-skipped runs over 4 Fridays | 4/4 — confirms ops keeps `mega_pack` modifiers stocked, not a code question |

**Suggested beacon:** if click-beacon infrastructure (`ZEUS_MENU.md` / `docs/GATE_LINK_AUDIT.md`) already tags checkout-surface origin, tag the P0 pin, P1 checkout caption, and P2 footer separately so a 30-day read can attribute which phase actually moved the needle — this plan does not add new beacon infra, just recommends using existing `click_links` tagging per-surface if not already granular.

---

## 7. Out of scope (explicit)

- **Lane Pass ($3) payment wiring** — still shelved per doctrine; not touched.
- **New SKU tiers** — no new pricing tiers proposed; P3's exclusivity policy operates on existing VIP SKU, not a new price point.
- **Supervisor panel rewrite** — not touched.
- **Live bot starts / tray ops** — no bot spawns, no `POST /bots/runtime/*/start` calls made or proposed.
- **Gumroad operator changes** — documented only where relevant (fiat checkout labels already avoid saying "Gumroad" in user copy per `fiat_checkout_labels.py`); no Gumroad dashboard changes proposed.

---

## Appendix — env flag inventory (current defaults, as read from source)

| Flag | Default (unset) | File |
|---|---|---|
| `TBCC_VIP_CHECKOUT_CAPTION_MINIMAL` | `1` (minimal caption) — **P1 target: flip to `0`** | `aof_vip_deal_copy.py:111` |
| `TBCC_NETWORK_ALBUM_SIZE` | `1` (public tease size) | `aof_feed_rhythm_v2.py:33` |
| `TBCC_AOF_VIP_ALBUM_ROLL` | `1` (roll enabled) | `aof_feed_rhythm_v2.py:67` |
| `TBCC_AOF_VIP_ALBUM_ROLL_MIN` / `_MAX` | `3` / `10` | `aof_feed_rhythm_v2.py:51,59` |
| `TBCC_AOF_VIP_EARLY_DROP_ENABLED` | `1` | `aof_vip_early_drop.py:16` |
| `TBCC_AOF_VIP_EARLY_DROP_MINUTES` | `60` | `aof_vip_early_drop.py:22` |
| `TBCC_AOF_VIP_MIRROR_ENABLED` | `1` | `aof_vip_mirror.py:26` |
| `TBCC_VIP_WEEKLY_MEGA_ENABLED` | `1` | `aof_vip_weekly_mega.py:28` |
| `TBCC_VIP_WEEKLY_MEGA_DAY_UTC` / `_HOUR_UTC` | `4` (Friday) / `17` | `aof_vip_weekly_mega.py:34,42` |
| `TBCC_VIP_PERKS_ENABLED` | `1` | `aof_vip_perks.py:20` |
| `TBCC_VIP_COMPANION_BONUS_CREDITS` | `3` | `aof_vip_perks.py:25` |
| `TBCC_VIP_COMPANION_SKIP_GATE` | `1` | `aof_vip_perks.py:33` |
| `TBCC_CHANNEL_PROTECT_CONTENT` | `1` (noforwards everywhere) | `telegram_content_protection.py:15` |
| `TBCC_MAINHUB_SPOTLIGHT_ENABLED` | `1` | `mainhub_channel_spotlight.py:47` |
| `TBCC_VIP_INTRO_USD` | `10` | `vip_intro_eligibility.py:15` |
| `TBCC_LIFECYCLE_DM_ENABLED` | see `lifecycle_dm_outreach.py` (already shipped, on per `SPRINT_STATE.md`) | — |
| `TBCC_POST_FOOTER_VIP_CONTRAST` | **new, proposed P2**, default `1` | — |
| `TBCC_VIP_EXCLUSIVE_DELAY_DAYS` | **new, proposed P3** | — |
| `TBCC_VIP_WEEKLY_MEGA_PUBLIC_TEASE_ENABLED` | **new, proposed P4**, default `1` | — |
| `TBCC_VIP_GOD_ROLL_STREAK_ENABLED` | **new, proposed P6**, default `0` | — |
| `TBCC_VIP_COMPANION_DRIP_ENABLED` | **new, proposed P6**, default `0` | — |

---

**STOP — awaiting operator ACK / phase selection.**
