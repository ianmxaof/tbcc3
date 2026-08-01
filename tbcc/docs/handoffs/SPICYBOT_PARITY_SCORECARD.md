# Spicybot vs Aifasteditbot — parity scorecard

**Purpose:** Decide when to dial back `{affiliate}` / Aifastedit promotion in Buffer X and lead with `@aof_spicybot_bot` only.

**Review cadence:** weekly (or after any deploy that changes photo/chat/Stars).

---

## Scoring (1–5 each; **≥4 on all rows** = parity; **≥4 average + Stars row ≥4** = supersede affiliate on X)

| Dimension | Aifastedit (affiliate) | @aof_spicybot_bot (owned) | Score (1–5) | Notes |
|-----------|------------------------|---------------------------|-------------|-------|
| **Photo quality** | Baseline | Same source image A/B | | Undress API vs their stack |
| **Speed to result** | | | | Upload → DM photo latency |
| **Chat quality** | N/A or weak | LLM persona | | hcnsec / custom model |
| **Monetization** | Revshare USD (slow) | Stars + gate → loot/payment | | `conversions_by_source` |
| **Operator cost** | $0 API | API credits + LLM $ | | undress balance + proxy spend |
| **Funnel depth** | Dead-end affiliate | Gate, VIP skip, referrals | | |
| **Attribution** | External dashboard | `src_spicy_*` in funnel API | | |

**Evidence commands**

```bash
# Island
curl -fsS https://api.powercore.app/companion/ops
curl -fsS https://api.powercore.app/analytics/bots/funnel   # conversions_by_source

# Local / island container
cd backend && py -3.13 scripts/smoke_companion_island.py --verify-llm
```

---

## Dial-back rules (when to cut Aifastedit share in X armory)

| Signal | Action |
|--------|--------|
| Spicy **photo score ≥4** for 2 consecutive weeks | Drop pure-affiliate-only armory lines to ≤25% of pool |
| **`src_spicy_x` or `src_spicy_goblin` conversions** ≥ affiliate-led Stars/month | Make spicy primary CTA; affiliate = footer only |
| **Operator undress balance** draining faster than affiliate coins refill | Lower `TBCC_COMPANION_FREE_TRIAL_PHOTOS`; push affiliate after trial |
| **Spicy score &lt;3** on photo or chat | Keep dual-lane; do not reduce `{affiliate}` |

---

## Current funnel surfaces (dual-lane)

| Surface | Affiliate | Spicy |
|---------|-----------|-------|
| Buffer X armory | `{affiliate}` | `?start=src_spicy_x` |
| Goblin spawn | — | `?start=src_spicy_goblin_<drop_id>` |
| Post-trial DM | — | `TBCC_COMPANION_AFFILIATE_UNDRESS_URL` |

---

## Operator checklist (go-live)

1. `tbcc/.env` — `TBCC_COMPANION_BOT_TOKEN`, `TBCC_UNDRESS_TOOL_API_KEY`, LLM custom block (hcnsec).
2. `.\scripts\revenue-island\seed-island-env-from-home.ps1`
3. `.\scripts\revenue-island\deploy-island-live.ps1`
4. Telegram: `/start` on `@aof_spicybot_bot` with `?start=src_spicy_x`
5. Wait for goblin spawn → tap **Free spicy trial** button
6. Fill scorecard row 1–7 after first real user week
