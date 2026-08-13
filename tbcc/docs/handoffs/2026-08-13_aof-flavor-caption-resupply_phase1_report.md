# Phase 1 report — AOF flavor caption resupply (structure + unique-hook helper)

**Date:** 2026-08-13
**Scope:** `tbcc/backend/app/services/aof_growth_hub.py`, `tbcc/backend/tests/test_aof_flavor_hooks.py`
**Status:** done, tests green, STOP for Cursor ACK before Phase 2 (mass hook expansion)

## What was actually broken

`sync_network_schedulers` built each lane's `content_variations` as: bulletin, then one
`promo_html + footer` slot per **affiliate footer variant** returned by
`build_telegram_footer_variants`. `promo_html` is a single fixed string per lane
(`AOF_NETWORK_CHANNELS[i].promo_html`), so every one of those slots opened with the
*identical* hook text — only the trailing sponsor line / URL differed. With N eligible
affiliates that's N near-duplicate variations for a single real flavor, which is exactly
the "~440–520 variations, ~13–25 unique hooks" symptom measured on the island. Rotation is
sequential, so a scheduler could post the same opening line for dozens of sends in a row
before the affiliate footer finally changed anything a reader would notice.

Separately, `_gumroad_vip_promo_variations` only used `vip_promo_minimal_bodies()[:1]` —
2 of 3 VIP minimal bodies were dead weight, never entering rotation.

## Changes made

### `unique_flavor_hook(caption: str) -> str` (new, public)
Returns everything before `FOOTER_MARKER` ("Join the full AOF stack"), using the same
prefix-split technique already used internally by `_refresh_variation_footer` (split on
the last `\n\n` before the marker, falling back to the last `\n`). Deliberately
conservative — returns the **whole** pre-footer body, not just the first line/emoji, so
it never collapses two genuinely different posts that happen to open with the same emoji.
This is the definition used everywhere else in this change (dedupe, entry stats, and
whatever Phase 3's dry-run script counts) — one definition, not two, so numbers reported
here will match numbers the resync script prints later.

### `_dedupe_by_flavor_hook(variations: list[str]) -> list[str]` (new, private)
Order-preserving, keeps the first occurrence of each `unique_flavor_hook`. Wired in as the
last step of `sync_network_schedulers` per lane, right after `_sanitize_variations`, so
it's the single place that prunes duplicate-hook padding regardless of which upstream
function produced it (sponsor footer, stale legacy rows carried over from `existing`,
future lane-hook banks in Phase 2). Verified it does **not** disturb:
- the bulletin at slot 0 (no `FOOTER_MARKER` in bulletin text → its hook is the whole
  bulletin, always unique)
- the goblin-teaser injection cadence (`inject_goblin_teaser_variations` already
  self-guards against inserting the same teaser twice via `if teaser not in out`, so
  there was nothing for the dedupe pass to break)
- idempotence — running it twice on the same list is a no-op (tested)

### `_select_promo_footer(footer_variants, *, seed) -> str` (new, private) replaces `_append_sponsor_promo_variations` (deleted)
This is the deliberate design call flagged for the operator: **Phase 1 does not drop
affiliate sponsor exposure to zero, and does not force a sponsor onto every lane either.**
Instead of cloning the promo hook once per sponsor footer (the bug), the single promo slot
now picks **one** footer — base (sponsor-free) or sponsor — deterministically per lane,
via `zlib.crc32(net_ch.key) % len(footer_variants)`. Index 0 (the sponsor-free base
footer) is a reachable outcome, on purpose: the goal's explicit "affiliate/links stay
untouched" constraint means this change should shift *which* lane occasionally shows a
sponsor line, not upgrade every lane's primary post to always carrying one — an earlier
draft of this function excluded index 0 and was corrected after review. Verified both
outcomes are reachable across the real lane key set, and confirmed via a DB-backed test
(seeded `PromoAffiliateLink` row, default `copy_template`) that a selected sponsor footer
actually survives `_sanitize_variations` → `_refresh_variation_footer`'s extract/re-inject
round trip. That test proves the round trip for the **default `💰 {link}` template only**
— `PromoAffiliateLink.copy_template` also supports `{url}`/`{label}`-only templates
(model comment, `promo_affiliate_link.py:27`), and a custom template using only those
placeholders with no leading 💰/🎨 would not contain `href=` and would not be recognized by
`_extract_footer_sponsor_line`, so it would silently drop at sanitize time. Not tested
here — flagging as a known gap for whoever edits `copy_template` values in the dashboard.
Same lane always picks the same footer until the affiliate candidate list itself changes
(idempotent re-sync). Net effect: same variation count as before per lane (bulletin + 1
promo slot), zero duplicate-hook padding, sponsor exposure redistributed across lanes
instead of multiplied within one lane.

`_append_sponsor_promo_variations` is deleted outright — it had no callers outside this
file (confirmed via grep) and its only purpose was the multiplication being removed here.

### `vip_promo_minimal_bodies()[:1]` → full list
`_gumroad_vip_promo_variations` now uses all 3 minimal bodies + the 2 existing inline
bodies = 5 distinct VIP variations (was 3). Checked max caption length across all 5:
longest is 574 chars, well under Telegram's 1024-char media-caption limit — no truncation
risk from the expansion.

## What Phase 1 deliberately did NOT touch
- No new hook banks (PACKS, lane-specific, VIP/gate expansion) — that's Phase 2.
- `_scrub_all_scheduler_captions` (walks every scheduler in the DB) was left alone. It
  does not dedupe by hook today. The dedupe pass added here only reaches lanes iterated by
  `sync_network_schedulers` (the 13 `AOF_NETWORK_CHANNELS` minus `packs`). Existing padded
  rows on **other** schedulers (PACKS seed rotation, liveness, cross-channel) are not
  pruned by this change — Phase 3's `resync_flavor_captions.py` is the intended place to
  close that gap network-wide.
- Gate FOMO bodies (`gate_fomo_post_bodies()`, 5 distinct) were already fully used — no
  change needed there.

## Tests

New file: `tbcc/backend/tests/test_aof_flavor_hooks.py` — 14 tests:
- `unique_flavor_hook` splits correctly on the footer marker, returns full body when no
  footer is present, and treats footer/URL-tail differences as irrelevant to the hook
- `_dedupe_by_flavor_hook`: collapses an 8-copy padded list (mirrors the real bug shape)
  down to 1, preserves order + keeps first occurrence, is idempotent, and confirms the
  bulletin survives at slot 0 through the pass
- `_select_promo_footer`: falls back to the sole footer when there's nothing to rotate,
  always resolves to one of the valid footer variants, **can land on the base
  (sponsor-free) footer** (not just sponsor variants), is deterministic per seed, and
  spreads picks across lane seeds
- `_gumroad_vip_promo_variations`: now returns 5 distinct variations (was 3), all under
  the 1024-char caption limit
- `test_selected_sponsor_footer_survives_sanitize_round_trip` (DB-backed, uses the `db`
  fixture + a real `PromoAffiliateLink` row): builds a real footer set via
  `build_telegram_footer_variants`, picks a sponsor footer via `_select_promo_footer`,
  and proves the sponsor line is still present after `_refresh_variation_footer` —
  without this, the whole design would be cosmetic (sponsor picked but silently
  stripped at sanitize time)

### Verification run
```
cd tbcc/backend && py -3.13 -m pytest tests/test_aof_flavor_hooks.py -x -q --tb=short
14 passed in 0.45s
```

Also ran together with the existing packs/growth-hub suites:
```
py -3.13 -m pytest tests/test_aof_flavor_hooks.py tests/test_aof_packs_send_time.py tests/test_aof_growth_hub.py -q --tb=short
1 failed, 23 passed, 1 warning in 0.76s
```
The 1 failure (`test_pack_template_leaves_body_placeholder_for_gates`) is a **pre-existing
baseline failure**, confirmed by `git stash` + re-running against unmodified HEAD before
any Phase 1 edits — same failure, same assertion, untouched by this change. Left as-is;
not in Phase 1 scope (PACKS template bank is Phase 2 territory).

**Scope of verification, stated honestly:** the two files above plus a grep across
`tests/` confirming no other test file imports `sync_network_schedulers`,
`vip_promo_minimal_bodies`, `_gumroad_vip_promo_variations`, or the deleted
`_append_sponsor_promo_variations`. A full-repo `pytest -q` run was started but did not
finish producing output in this session; it was not used as evidence for this report. If
Cursor wants full-suite coverage before ACK, re-run it — the changed surface area here is
narrow and file-local, but that run has not actually been observed to pass.

## For Phase 2 (not started)
- `_select_promo_footer`'s single-slot design means Phase 2's lane hook banks need their
  own plan for pairing multiple hooks against multiple sponsor footers without
  reintroducing multiplication — e.g. one footer pick per hook (same crc32 seeding
  approach, keyed on `lane_key + hook_index`) rather than the cartesian product removed
  here.
- `entry["variations_before_dedupe"]` and `entry["unique_hooks"]` were added to
  `sync_network_schedulers`'s per-lane report row so Phase 2/3 tooling (and the resync
  script) can print before/after counts without recomputing.
- `entry["sponsor_footers"]` was renamed to `entry["sponsor_footers_available"]` — the old
  name implied "N sponsor variations were added," which was true before this change but
  is no longer (now: N candidates exist, exactly 1 is used per lane). Confirmed via grep
  that nothing outside `aof_growth_hub.py` reads this field (no test, no dashboard code),
  so the rename is safe.

## STOP
Awaiting Cursor `/cc-report` ACK before starting Phase 2 (PACKS + lane flavor bank
expansion).
