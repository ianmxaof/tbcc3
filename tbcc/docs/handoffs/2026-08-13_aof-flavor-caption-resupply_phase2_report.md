# Phase 2 report — AOF flavor caption resupply (PACKS + lane flavor banks)

**Date:** 2026-08-13
**Scope:** `tbcc/backend/app/services/aof_packs_caption_templates.py`,
`tbcc/backend/app/services/aof_flavor_hooks.py` (new),
`tbcc/backend/app/services/aof_growth_hub.py`,
`tbcc/backend/app/services/loot_pack_pool.py` (docstring only),
`tbcc/backend/tests/test_aof_flavor_hooks.py`, `tbcc/backend/tests/test_aof_packs_send_time.py`
**Status:** done, tests green (43 passed, 0 known failures), STOP for Cursor ACK before Phase 3
**ACK received for Phase 1:** "GO for Phase 2 (code checks out; hold island resync until Phase 3 or a deliberate one-off sync)." No island resync performed in this phase — see "Refresh path" below for what to run when ready.

## 1. PACKS template bank: 50 → 101 unique hooks

Added 10 new strategies to `PACK_STRATEGIES` in `aof_packs_caption_templates.py` (51 new
hooks), on top of the existing 50: `delivery_pipeline` (the gold Planet Express / NEW
DELIVERY motif — one strategy among many, not the only opener), `no_apology_dump`,
`relay_fired`, `porn_first_blunt`, `curated_not_scraped`, `feed_moves_fast`,
`operator_receipt`, `goon_edge_blunt`, `mega_batch_flex`, `gate_confidence`. Total: 101
unique hooks, verified via `set()` — no duplicates.

`pack_caption_template_variations()` no longer caps at 50. It now returns every distinct
hook across `PACK_STRATEGIES` (currently 101), with a `MIN_PACK_TEMPLATES = 100` floor
constant and a defensive pad loop kept only as a safety net if the strategy set ever
shrinks below the floor (not exercised today — 101 > 100 already).

```
python -c "from app.services.aof_packs_caption_templates import pack_caption_template_variations; v=pack_caption_template_variations(); print(len(v), len(set(v)))"
101 101
```

### Bug found and fixed while touching this file
`test_pack_template_leaves_body_placeholder_for_gates` was failing on the **pre-existing**
50-hook bank (documented and deliberately left alone in the Phase 1 report, since Phase 1
never touched this file). Phase 2 does touch it, so leaving a self-caused red test in the
suite would be wrong. Root cause: the `addlist_punch` strategy's two hooks literally said
"...you addlist" / "The addlist unlocks the rest" — hook text duplicating what the footer
already says, which is exactly the invariant the test guards (gate/footer vocabulary
belongs in `PACK_BODY`/footer, not the hook). Reworded both hooks to reference "the stack"
/ "the full stack link" instead of the literal word "addlist" — same meaning, no footer
structure touched, footer marker text unchanged. Suite is now fully green.

## 2. New module: `aof_flavor_hooks.py`

**Deviation from architecture requirement B, deliberate:** the brief suggested
`pack_delivery_hooks()` live in this new module and get "integrated into
PACK_STRATEGIES." Instead, the new PACKS strategies were added directly to
`PACK_STRATEGIES` in `aof_packs_caption_templates.py` (§1 above) — that tuple *is* the
hook bank architecture already in place; adding a second, parallel hook source in a
different module would fragment one bank into two for no benefit. `aof_flavor_hooks.py`
instead holds the three banks that don't already have a home: lane hooks, VIP hooks, gate
hooks.

### `lane_flavor_hooks(network_key) -> list[str]`
52 shared hook templates (`LANE_FLAVOR_HOOK_TEMPLATES`), each with a `{lane}` placeholder,
colored per lane via `net_ch.display_name`. This is the "shared bank + lane-colored
openers" option the brief names as an alternative to hand-writing 40-60 bespoke hooks per
lane (13 lanes × 50 = 650 lines of duplicated wording). The wording *structure* is shared;
the output text is not — every lane's hook set is fully disjoint from every other lane's
(verified: `lane_flavor_hooks("ai")` and `lane_flavor_hooks("goon")` share zero strings),
because the lane name is embedded in the string, not just prepended. Includes the gold
Planet Express / NEW DELIVERY template verbatim, colored per lane (`"...Another curated
{lane} dump cleared the pipeline — no apology."`).

### `vip_flavor_hooks() -> list[str]` (16 hooks) / `gate_flavor_hooks() -> list[str]` (15 hooks)
Both meet the ≥15-all-used requirement. `gate_flavor_hooks()` wraps the existing
`aof_gate_promo_copy.gate_fomo_post_bodies()` (5, already fully used since Phase 1) plus
10 new bodies — this fully replaces the old `_append_gate_fomo_variations` call site (see
§3). `vip_flavor_hooks()` is a separate, larger bank from
`aof_main_group_copy.vip_promo_minimal_bodies()` (3 bodies, expanded to full use in
Phase 1) — that one stays tied to the Gumroad bare-URL preview-card mechanic
(`_gumroad_vip_promo_variations`), unchanged; `vip_flavor_hooks()` is general-purpose VIP
rotation copy with no URL-embed dependency.

None of these three banks touch `FOOTER_MARKER`, invent new bot usernames, or claim false
scarcity quotas — verified by test and by construction (only `@aofsubscriptions_bot`,
`@aof_lootgod_bot`, `@aof_secretary_bot` appear, and only where the existing voice already
used them).

## 3. Wiring into `sync_network_schedulers`

Three new append helpers in `aof_growth_hub.py`, following the same "one hook, one footer"
pattern `_select_promo_footer` established in Phase 1 (never clone a hook across every
affiliate footer):

- **`_append_gate_flavor_variations`** — replaces the deleted `_append_gate_fomo_variations`
  (single call site, confirmed via grep before deletion). Uses the expanded 15-body
  `gate_flavor_hooks()` instead of the plain 5-body `gate_fomo_post_bodies()`.
- **`_append_vip_flavor_variations`** — new. All 16 `vip_flavor_hooks()` bodies, each
  paired with the base footer.
- **`_append_lane_flavor_variations`** — new, the mechanism that gets each lane to its
  ≥50-hook floor. Adds all `lane_flavor_hooks(network_key)` (52), each paired with **one**
  footer via `_select_promo_footer(footer_variants, seed=f"{network_key}:{i}")` — seeded
  per hook index, not per lane, so sponsor exposure spreads across the 52 hooks instead of
  cloning any single one across every affiliate (the exact bug Phase 1 fixed for the single
  promo slot, generalized here to a 52-hook set).

**Affiliate exposure surface, stated explicitly:** because `_select_promo_footer` only
excludes the base footer with probability `1/len(footer_variants)`, roughly
`(len(footer_variants)-1)/len(footer_variants)` of the 52 lane hooks will carry a sponsor
line once real affiliate candidates exist (e.g. with 2 real candidates, ~26 of 52 hooks
sponsor-free vs ~26 sponsored; with 5 candidates, ~10 sponsor-free vs ~42 sponsored). Before
Phase 2, a lane had ~13 total variations with a sponsor line on at most 1 of them. This is
a substantially larger affiliate surface than before — arithmetically the intended result
of "spread sponsors across more hooks instead of cloning one," but the operator should see
the ratio stated rather than derive it from the code.

Call order in `sync_network_schedulers` (bulletin/promo unchanged from Phase 1, then):
`_append_gate_flavor_variations` → `_append_gumroad_vip_variations` →
`_append_vip_flavor_variations` → `_append_lane_flavor_variations` → goblin teaser
injection → (AI lane only) prompt-drop injection → `_sanitize_variations` →
`_dedupe_by_flavor_hook` (unchanged from Phase 1 — still the final structural guarantee).

### Verified end-to-end (synthetic pipeline, not live DB — see caveat below)
Reimplemented the per-lane merge sequence in a test helper
(`_build_full_lane_pipeline`, `test_aof_flavor_hooks.py`) covering every step except the
two DB-only injections (goblin teaser, AI prompt-drop), and ran it for every lane key:

```
main   before 90 after 90 unique_hooks 90
ai     before 90 after 90 unique_hooks 90
... (all 13 lanes) ... unique_hooks 90
```

All 13 lanes reach 90 unique hooks (≥50 target met with margin) with **before == after**,
i.e. zero variations lost to dedupe under normal conditions — confirming the "one hook,
one footer" design doesn't reintroduce padding even with 6 synthetic sponsor candidates in
the footer pool (`test_full_lane_pipeline_stable_variation_count_with_many_sponsor_candidates`).
Separately re-ran the real Phase-1 regression scenario at this larger scale: 40 fake
padded rows (one old hook × 40 sponsor URLs) seeded into `existing`, then run through the
same pipeline — collapses to 91 unique slots, proving the dedupe pass still prunes
island-realistic stale data once the lane bank is this much bigger
(`test_full_lane_pipeline_collapses_real_padded_existing_rows`).

**Caveat, stated plainly:** `_build_full_lane_pipeline` is a test-only reimplementation of
`sync_network_schedulers`'s per-lane sequence, not a call into the real function — it
doesn't stand up a full `Channel`/`ContentPool`/`ScheduledTextPost`/`SubscriptionPlan`
fixture set, which `sync_network_schedulers` requires. Two consequences:
- The real per-lane number on a live sync will be **90 + 1 (goblin, most lanes) + N
  (AI lane's prompt-drop rows)** — not exactly 90 everywhere.
- If `sync_network_schedulers`'s call order is edited later without updating this test
  helper to match, the test will keep passing on stale logic. Accepted gap for Phase 2;
  Phase 3's `resync_flavor_captions.py` dry-run against a real (or seeded) DB is the
  place that will show the actual number, not a reimplementation of it.

### Known consequence: goblin-teaser exposure drops proportionally
`inject_goblin_teaser_variations(merged, [goblin_teaser], every_nth=6)` has
`if teaser not in out` — with a single teaser body, it inserts **exactly once** into the
list, regardless of list length (confirmed in the Phase 1 report already). At the old
~13-variation scale that was roughly 1-in-13 exposure in a sequential rotation; at the new
~90+-variation scale it's roughly 1-in-90. This is a real, unrequested-but-implied side
effect of growing the rotation and was not offset by adding more goblin teaser bodies (out
of scope for this phase — goblin teaser copy lives in `aof_loot_goblin_promo.py`, not
touched here). Flagging for the operator: if goblin-game visibility matters, either pass
more teaser bodies into that call or lower `every_nth`. Not fixed in Phase 2.

## 4. Refresh path (documented, not run)

Per the Phase 1 ACK ("hold island resync until Phase 3 or a deliberate one-off sync"), no
live sync was executed. Two existing endpoints already pick up the expanded banks with no
further code changes — Phase 2 only changed what these functions build, not their
signatures or call sites elsewhere:

- **Lane schedulers:** `POST /growth-hub/sync-schedulers` → `sync_network_schedulers(db, execute=True)`
  (`app/api/growth_hub.py:102`). This is the function wired to `lane_flavor_hooks` /
  `vip_flavor_hooks` / `gate_flavor_hooks` in §3.
- **PACKS scheduler:** `POST /loot/pack-pool/refresh-scheduler` → `refresh_aof_packs_scheduler(db)`
  (`app/api/loot.py:260`). Picks up the expanded `pack_caption_template_variations()`
  (101 hooks) automatically — the function body wasn't changed, only its docstring
  (`~50` → `100+`).

Phase 3 will wrap both in `backend/scripts/resync_flavor_captions.py` with `--dry-run` /
`--execute`, per the working agreement. Until then, either endpoint above is the
documented manual path if a one-off sync is wanted before Phase 3 ships.

## Tests

`tests/test_aof_flavor_hooks.py` grew from 14 (Phase 1) to 24 tests. New in Phase 2:
- Per-lane `lane_flavor_hooks()` floor (≥50) and no-duplicates check, for all 13 lanes
- Cross-lane disjointness (shared-bank design still produces genuinely distinct text)
- Gold Planet Express / NEW DELIVERY line present
- No footer marker or invented bot usernames in raw hooks
- `vip_flavor_hooks()` / `gate_flavor_hooks()` floor + "all used, not `[:1]`" (via the
  append helpers returning exactly `len(hooks)` new entries from an empty list)
- Lane-bank padding regression: N hooks × 6 sponsor footers → N variations, not N×6
- Full synthetic pipeline: all 13 lanes reach ≥50 unique hooks, stable count under more
  sponsor candidates, and collapses 40 fake padded existing rows correctly

`tests/test_aof_packs_send_time.py`: old `test_pack_caption_templates_reach_fifty`
(hardcoded `== 50`) replaced with `test_pack_caption_templates_reach_minimum_floor`
(`>= MIN_PACK_TEMPLATES`, all distinct) + new
`test_pack_caption_templates_include_gold_planet_express_delivery_motif` (present, but not
on every line).

### Verification run (exact commands from the brief)
```
cd tbcc/backend && py -3.13 -m pytest tests/test_aof_flavor_hooks.py tests/test_aof_packs_send_time.py -x -q --tb=short
31 passed in 0.66s

python -c "from app.services.aof_packs_caption_templates import pack_caption_template_variations; v=pack_caption_template_variations(); print(len(v), len(set(v)))"
101 101
```
Also ran the wider pack/growth-hub suite for regressions:
```
py -3.13 -m pytest tests/test_aof_flavor_hooks.py tests/test_aof_packs_send_time.py tests/test_aof_growth_hub.py tests/test_aof_packs_post_copy.py tests/test_aof_packs_vocabulary.py -q --tb=short
43 passed, 1 warning in 0.88s
```
Warning is an unrelated pre-existing SQLAlchemy `datetime.utcnow()` deprecation notice
from a fixture, not from this change. No full-repo `pytest -q` run was attempted this
phase — same honest-scope caveat as Phase 1: this covers the touched files plus a grep
confirming `_append_gate_fomo_variations` (deleted) has no remaining references.

## For Phase 3
- Buffer X hook stem expansion — not started.
- `backend/scripts/resync_flavor_captions.py` with `--dry-run`/`--execute` — not started;
  §4 above gives the two functions it needs to call.
- Consider whether goblin-teaser exposure (§3 caveat) needs addressing alongside the
  Buffer X work, or is accepted as-is.

## STOP
Awaiting Cursor `/cc-report` ACK before starting Phase 3 (Buffer X refresh + resync
script + dry-run docs).
