# Report: Revenue island ops — pack ladder smoke + companion post-credit keyboard — Phase 1

**Against:** `tbcc/docs/handoffs/2026-08-29_revenue-island-pack-companion.md`, Phase 1 ("ACTIVE for /cc-run" block)
**Date:** 2026-08-28
**Session:** cold-start via `/cc-run` — this block was the only source of truth

## Summary

Read the ACTIVE block cold and audited the code before touching anything, because most of I3/I4's described symptoms ("dead-end keyboard", "VIP intro not surfaced") already had infrastructure in place from earlier work. Found the actual, narrower gap and fixed it:

- **I1 (confirmed root cause, fixed):** `traffic_attribution.payload_to_source_ref()` had no mapping for the `subscribe`, `companion`, or `companion_<sku>` `?start=` payloads — every one of these is a live CTA (companion exhaustion keyboard's VIP button, the credit-pack buttons) but each hit `record_traffic_touch`'s `skipped: unmapped_payload` early return, so first-touch was never recorded despite the generic recording call already firing on every `/start` payload. Added mappings for all three.
- **I3/I4 (found a second, more serious bug hiding behind the same symptom):** the companion exhaustion keyboard's "⭐ AOF VIP — skip gates" button links to `https://t.me/<payment_bot>?start=subscribe`. `cmd_start` in `payment_bot.py` had no branch for `payload == "subscribe"` — it fell through to the generic welcome screen (`main_menu_keyboard`), not the VIP catalog. That's the real dead-end: the button worked (didn't error), but never showed VIP plans or the intro SKU. Added the missing branch. Once routed to `send_subscription_catalog_message`, VIP Intro is already surfaced automatically (pre-existing `fetch_plans` logic sorts intro-eligible plans first and filters it out for ineligible users) — no separate I4 code change was needed once routing was fixed.
- **I2/I5:** no code gap found; documented operator smoke steps below (Phase 2 is deploy-gated per Working agreement).

## Done

- **I1** — `app/services/traffic_attribution.py`: `payload_to_source_ref()` now maps `subscribe` → `src_vip_subscribe`, `companion` → `src_companion_catalog`, `companion_<sku>` → `src_companion_pack_<sku>` (e.g. `companion_5` → `src_companion_pack_5`, matching the live `COMPANION_CREDIT_PACKS` SKUs). Added `tests/test_traffic_attribution.py::test_payload_to_source_ref_subscribe_and_companion_packs` plus two `record_traffic_touch` tests asserting the result is no longer `skipped: unmapped_payload` for these payloads.
- **I3/I4** — `bots/payment_bot.py::cmd_start`: added a `payload == "subscribe"` branch (next to the existing `companion`/`companion_` branch) that calls `send_subscription_catalog_message(msg, context, section="main")` instead of falling through to the generic welcome. This is the fix for the actual post-credit dead-end — the loot/VIP *keyboard* itself (`companion_monetize_cta.py`, `companion_reveal_paywall.py`) already had loot + VIP buttons; the VIP button's *destination* was the dead end.
- Verified (did not need to change): `companion_exhaustion_inline_keyboard_rows()` and `reveal_paywall_keyboard()` already include both loot and VIP buttons — `tests/test_companion_reveal_paywall.py::test_reveal_paywall_keyboard_has_loot_and_vip` already covers I3's stated verification criterion and passes unmodified.
- Verified (did not need to change): `fetch_plans(section="main", telegram_user_id=...)` in `payment_bot.py` already sorts the VIP Intro plan first and filters it for already-subscribed users (`app/services/vip_intro_eligibility.py`), so routing `?start=subscribe` to the real catalog is sufficient to surface intro pricing — no separate intro-specific deep link needed.

## Not done / explicitly out of scope this phase

- **Pricing/Gumroad PRODUCT_MAP** — untouched, per judgment_ceiling. Operator smoke step below covers verification.
- **`handle_menu_callback`'s `menu_subscribe` inline button** (the *main* `/start` menu's Subscribe button, separate from the companion exhaustion CTA) passes `msg = query.message` into `send_subscription_catalog_message`, which derives the buyer id from `msg.from_user` — for a callback-query message that's the **bot's own user**, not the clicking user, so intro-eligibility there may silently resolve against the wrong id. This is a pre-existing, separate latent bug, not part of I1–I5 and not touched here — flagging for a future slice since it sits right next to the code this phase touched.
- Island deploy — Phase 2, operator-gated.

## Files

**Modified:**
- `tbcc/backend/app/services/traffic_attribution.py` — +7/−0, `payload_to_source_ref()` mapping additions.
- `tbcc/backend/bots/payment_bot.py` — +3/−0, `cmd_start` routing branch.
- `tbcc/backend/tests/test_traffic_attribution.py` — +25/−0, 3 new tests.

Scope note: `traffic_attribution.py` isn't named explicitly in the forward directive's scope list, but the directive's `payment_bot.py` line says "`?start=` attribution where applicable" — `payload_to_source_ref` is the single mapping table that line's fix has to land in. Flagging explicitly per Working agreement in case Cursor disagrees with folding it in.

## Verification

```
cd tbcc/backend
py -3.13 -m pytest tests/test_aof_vip_membership.py tests/test_companion_menu.py tests/test_companion_reveal_paywall.py tests/test_traffic_attribution.py -x -q --tb=short
25 passed
```

Broader regression sweep (payment/companion/subscription/traffic keyword filter, 135 tests):
```
py -3.13 -m pytest tests/ -k "payment or subscri or companion or traffic" -q --tb=short
5 failed, 130 passed
```
The 5 failures (`test_companion_access.py` ×2, `test_companion_gate_health.py` ×2, `test_traffic_pulse.py` ×1) are **pre-existing on this branch** — reproduced identically with this session's changes fully `git stash`ed, unrelated to `payload_to_source_ref`/`cmd_start` (root cause looks like unregistered `pytest.mark.asyncio` / an unrelated fixture issue). Not introduced by this phase; not fixed by this phase (out of scope).

Local grep/evidence: `companion_exhaustion_inline_keyboard_rows()` (companion_monetize_cta.py:23) and `reveal_paywall_keyboard()` (companion_reveal_paywall.py:46) both already emit loot + VIP button rows — confirmed by reading the existing passing test, not just grep.

## Operator smoke checklist (I2 — run after Phase 2 deploy, not self-reported)

1. **Pack funnel attribution (I1):** on the live island, tap the companion bot's "📦 5 reveals" button (or any `companion_5/15/50` CTA) from a fresh test account → `GET` the `UserFunnelTouch` row for that Telegram user id (or hit whatever admin/API surface reads it) → confirm `first_source_ref == "src_companion_pack_5"` (or matching SKU), not null/unmapped.
2. **VIP CTA routing (I3/I4):** exhaust a test account's free companion credits → tap "⭐ AOF VIP — skip gates" in the resulting keyboard → confirm the payment bot now shows the VIP plan catalog with **AOF VIP — Intro Month ($10)** listed first (for a first-time buyer), not the generic welcome/main-menu screen.
3. **Gumroad PRODUCT_MAP (I4, operator-only):** confirm `TBCC_GUMROAD_PRODUCT_MAP` on the island includes a `price:1000` key mapped to the intro SKU — this report does not verify or change island env config.
4. **Pack subs baseline (I2):** re-check `companion_photos_sold` / pack subscription count after ~48h of traffic post-deploy to see if the attribution + routing fixes move it off zero. Not provable in this session (no live traffic).

## Next steps

| What | Unblocks | Reversibility | Evidence |
|------|----------|----------------|----------|
| Cursor `/cc-report` ACK on this report | Phase 2 island deploy | trivial-revert (nothing shipped yet) | this file |
| Phase 2 — deploy + operator smoke (checklist above) | closes SPRINT_STATE.md Module A "0 pack subscriptions" line | trivial-revert (`hot-patch-island.ps1` or redeploy) | `curl https://api.powercore.app/health` + smoke steps 1–2 above |
| Fix `menu_subscribe` callback's wrong-user-id bug (flagged above) | orthogonal — separate latent bug found adjacent to this slice | trivial-revert | new unit test asserting `send_subscription_catalog_message` receives the clicking user's id, not the bot's |
| Commit these 3 files as a focused slice (not the branch's other ~60 unrelated dirty files) | deploy, Cursor review | trivial-revert (pre-push) | `git status` shows only the 3 files above staged |

**STOP** — Phase 1 done. Waiting for Cursor `/cc-report` ACK before Phase 2 island deploy, per Working agreement. Not starting Phase 2 in this session.
