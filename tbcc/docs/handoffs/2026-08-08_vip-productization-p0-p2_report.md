# VIP Productization P0–P2 + P6-E — Implementation Report

**Date:** 2026-08-08  
**Plan:** `2026-08-08_vip-productization-plan_report.md`  
**Status:** Complete (local) — **island deploy pending operator**

---

## Shipped

| Phase | What changed |
|-------|----------------|
| **P0** | `mainhub_growth.CTA_CAPTION` → full 5-pillar comparison (≤1024 chars). Loot Room paste block in `docs/loot-room-pinned-instructions.md`. |
| **P1** | `TBCC_VIP_CHECKOUT_CAPTION_MINIMAL` default **0** (full deal stack). Intro-month caption variant via `is_vip_intro_plan_name`. `.env.example` updated. |
| **P2** | `build_vip_post_contrast_line_html()` + `TBCC_POST_FOOTER_VIP_CONTRAST` (default on). Wired into `build_addlist_footer` and `build_spotlight_caption_html`. |
| **P6-E** | `PRE_EXPIRY_3D` lifecycle DM — loss-framed god roll + Friday mega copy. |

## Files touched

- `backend/app/services/mainhub_growth.py`
- `backend/app/services/aof_vip_deal_copy.py`
- `backend/app/services/aof_growth_hub.py`
- `backend/app/services/mainhub_channel_spotlight.py`
- `backend/app/services/lifecycle_dm_copy.py`
- `.env.example`
- `docs/loot-room-pinned-instructions.md`
- `backend/tests/test_mainhub_growth.py` (new)
- `backend/tests/test_aof_growth_hub.py` (new)
- `backend/tests/test_aof_vip_deal_copy.py` (extended)
- `backend/tests/test_mainhub_channel_spotlight.py` (extended)
- `backend/tests/test_lifecycle_dm_outreach.py` (extended)

## Tests

```bash
cd tbcc/backend
PYTHONPATH=. pytest tests/test_aof_vip_deal_copy.py tests/test_aof_vip_fulfillment.py tests/test_vip_intro_eligibility.py tests/test_aof_feed_rhythm_v2.py tests/test_mainhub_channel_spotlight.py tests/test_mainhub_growth.py tests/test_aof_growth_hub.py tests/test_lifecycle_dm_outreach.py::test_subscription_copy_pre_expiry_3d -q --tb=short
```

**Result:** 38 passed.

## Operator steps (post-deploy)

1. **Island deploy:** `tbcc/scripts/revenue-island/deploy-island-live.ps1`
2. **Refresh @aofmainhub pin:** run `apply_mainhub_growth(db, execute=True, post_now=True)` on island **or** wait for weekly CTA scheduler tick — new `CTA_CAPTION` updates on next seed/upsert.
3. **Loot Room:** paste VIP comparison section from `docs/loot-room-pinned-instructions.md` and re-pin manually.
4. **Optional rollback:** `TBCC_VIP_CHECKOUT_CAPTION_MINIMAL=1` and/or `TBCC_POST_FOOTER_VIP_CONTRAST=0` in island `.env` (no redeploy if only env).
5. **Watch:** checkout completion rate 7d post-P1; caption length on 2–3 lane posts post-P2.

## Not in scope (deferred)

- P3 exclusive content policy
- P4 Friday mega public tease
- P5 `/status` VIP home
- P6 streak + companion drip
