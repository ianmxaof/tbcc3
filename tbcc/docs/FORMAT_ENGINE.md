# Secretary Format Engine (FE-LLMv4)

The **Format Engine** is TBCC's first-class operator-assist layer on `@aof_secretary_bot`. It combines persistent emotional context, RAG FAQ knowledge, and a **human-in-the-loop draft workflow** so customers never see a bot reply until you approve it.

## Modes

| Mode | When | Customer sees | You see |
|------|------|---------------|---------|
| **Suggest (default)** | Business chats + direct DMs from non-admins | Nothing until you approve | Draft card DM with ✓ Send / ✗ Drop / ↻ Pro·Casual·Short |
| **Auto FAQ** | Admin testing, or `TBCC_SECRETARY_SUGGEST_DIRECT=0` | Immediate LLM reply | — |
| **Business auto-reply** | `TBCC_SECRETARY_AUTO_REPLY=1` | Immediate in-thread reply | — |

**Telegram folders do not affect this.** Draft routing is server-side only.

## Draft workflow (what you had before)

1. A non-admin user messages `@aof_secretary_bot` (or your Business-connected account).
2. Secretary + Format Engine drafts a reply — **customer sees silence**.
3. You get an **instant admin DM** with the draft card and inline buttons.
4. **✓ Send** — delivers to the customer chat (Business or direct DM).
5. **✗ Drop** — discard.
6. **↻ Pro / Casual / Short** — regenerate tone, then approve.

CLI equivalents: `/drafts`, `/approve DRAFT_ID`, `/reject DRAFT_ID`, `/redo DRAFT_ID casual`.

## Key env (tbcc/.env)

```env
# Draft mode for direct DMs (default on)
TBCC_SECRETARY_SUGGEST_DIRECT=1

# Business chats: 0 = suggest-only (default), 1 = auto-reply in customer thread
TBCC_SECRETARY_AUTO_REPLY=0

# Where draft cards land (defaults to ADMIN_TELEGRAM_ID)
ADMIN_TELEGRAM_ID=7787282561
TBCC_SECRETARY_SUGGEST_NOTIFY_CHAT_ID=

# Format Engine core
TBCC_FORMAT_ENGINE_ENABLED=1
TBCC_FORMAT_ENGINE_VERBOSITY=compact
TBCC_FORMAT_ENGINE_LLM_REFINE=0

# Extra admins for drafts + inbox
TBCC_SECRETARY_ADMIN_IDS=
```

**Important:** Open `@aof_secretary_bot` and tap **/start** once so instant inbox DMs are not blocked (Telegram 403).

## Code map

| Piece | Path |
|-------|------|
| Bot host + draft UI | `backend/bots/secretary_bot.py` |
| FE context + phases | `backend/app/services/format_engine.py` |
| LLM phase refine | `backend/app/services/format_engine_llm.py` |
| Dashboard settings | `backend/app/api/secretary.py`, `dashboard/.../SecretarySettingsPanel.tsx` |
| Admin inbox instant DMs | `backend/app/services/admin_inbox.py` |
| Tests | `backend/tests/test_format_engine.py` |

## Ops commands

- `/fe_stats` — FE + RAG stats (admin)
- `/mystatus` — user's thread phase (customer)
- `/inbox` — payment/loot/ops history
- Dashboard → Automation → Secretary / Format Engine

## LLM failure behavior (suggest mode)

If the LLM is down in suggest mode, **no error is sent to the customer**. You get an inbox ping: "Secretary draft failed" — fix API key via `/config` or dashboard.
