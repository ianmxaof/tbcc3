# Zeus menu (Phase 1)

Secretary hub IA: **Network | Inbox | Ops | More**. Host bot remains `@aof_secretary_bot` (token unchanged).

## Callbacks

| New (`zeus:`) | Legacy alias (`sec:menu:`) |
|---------------|----------------------------|
| `zeus:home` | `sec:menu:home` |
| `zeus:net:home` | `sec:menu:cat:net` |
| `zeus:inbox:home` | `sec:menu:cat:inbox` |
| `zeus:ops:home` | `sec:menu:cat:ops` |
| `zeus:more:home` | `sec:menu:cat:more` |
| `zeus:ops:stack` | `sec:menu:run:stack` |

All other inbox/ops actions map through `bots/zeus_menu.py` → shared `on_menu_callback` in `secretary_bot.py`.

## Commands

| Command | Who | Effect |
|---------|-----|--------|
| `/menu` | All | Zeus root (admin) or Network deep links (user) |
| `/stack` | Admin | Tray `GET`-equivalent stack status (`tbcc-stack-cli Status`) |

## Design rules

- Stars checkout stays on the **payment** bot token (URL deep links only).
- Loot / companion are URL buttons (`TBCC_LOOT_BOT_USERNAME`, `TBCC_COMPANION_BOT_USERNAME`).
- Restarts are **not** in Zeus — use tray or `tbcc-stack-cli.ps1`.
- Telethon work stays on API/Celery; Zeus only triggers existing secretary ops handlers.

## Code

- `tbcc/backend/bots/zeus_menu.py` — keyboards, normalize, stack HTML
- `tbcc/backend/bots/secretary_bot.py` — `/menu`, `/stack`, callback handler
- Tests: `tests/test_zeus_menu.py`

## Later phases (not shipped)

2. Merge macro search into secretary process  
3. Inline mode (`@secretary shop`)  
4. Content / commerce-ops admin triggers  
