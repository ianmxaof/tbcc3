# Kimi K2.7 Code — Operator TUI / rotator setup

Moonshot Kimi slots into the **existing custom-provider path** (`llm_model_index` + Operator TUI Ask). No new runtime. Default to **K2.7 Code** (`kimi-k2.7-code`) — not K3 (halo pricing).

**API:** OpenAI-compatible · `https://api.moonshot.ai/v1`  
**Key:** [platform.kimi.ai/console/api-keys](https://platform.kimi.ai/console/api-keys)

## Path A — CLI (fastest)

```powershell
cd tbcc/backend

# 1) Register provider (hidden key prompt)
py -3.13 scripts/tbcc_cli.py llm keys add moonshot --base-url https://api.moonshot.ai/v1

# 2) Pull model catalog
py -3.13 scripts/tbcc_cli.py llm refresh

# 3) Pin sticky to K2.7 Code (Ask pane + `llm ask` use this)
py -3.13 scripts/tbcc_cli.py llm sticky set moonshot kimi-k2.7-code

# 4) Smoke
py -3.13 scripts/tbcc_cli.py llm ask "Reply with exactly: kimi-ok"
py -3.13 scripts/tbcc_cli.py operator tui
```

Status check: `py -3.13 scripts/tbcc_cli.py llm status` → `sticky: moonshot`.

**Alternate one-shot pin:** `llm ask -p moonshot -m kimi-k2.7-code "hello"` sets sticky on success (no separate `sticky set`).

## Path B — Operator TUI Keys tab

| Field | Value |
|-------|--------|
| Paste | raw Moonshot API key |
| Id | `moonshot` |
| Auth env key | `TBCC_MOONSHOT_API_KEY` |
| Endpoint | `https://api.moonshot.ai/v1` |

Register → **Test selected** → Models tab **Refresh** → Ask tab.

LLM-category keys with a base URL auto-bridge into the rotator (`tools_slots.register_slot_from_paste`).

## Path C — OpenRouter (already-native)

If you already use OpenRouter, add a Moonshot slug there — no custom provider needed. Rotator cycles via existing `openrouter` hop; pick the K2.7 slug in Models or pass `-m` on `llm ask`.

## Operator checklist

1. **Spend cap** in Moonshot console before unattended agent loops.
2. **K3 is not the cheap path** — `$3/$15` per M; keep K2.7 as default sticky.
3. **Hybrid stack** (optional): Kimi for daily Ask volume; keep one frontier seat for hard 5% (see starmex Kimi cost map).
4. **Claude Code** (outside rotator): Anthropic-compatible base `https://api.moonshot.ai/anthropic` — separate from Operator TUI.

## Done-condition (slice A)

- `llm status` shows `sticky: moonshot` with model `kimi-k2.7-code`
- Operator TUI Ask returns a reply; status line shows `moonshot/kimi-k2.7-code`
- Forced quota on moonshot → rotator cycles to next provider (existing `ask_with_rotation` tests)

## Not in scope

- Self-hosting K3 weights (~1.56TB)
- Island / secretary / `/zeus/v1/ask` (rotator stays PC-local per doctrine)
- FreeToken / FlashML edge MoE stack
