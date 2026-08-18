# Secretary Format Engine (FE-LLMv4)

The **Format Engine** is TBCC's first-class operator-assist layer on `@aof_secretary_bot`. It combines persistent emotional context, RAG FAQ knowledge, a **sales coach** playbook, and a **human-in-the-loop draft workflow** so customers never see a bot reply until you approve it (Pilot) — or you flip a customer to Auto.

## Modes

| Mode | When | Customer sees | You see |
|------|------|---------------|---------|
| **Pilot (default)** | Per-customer `reply_mode=pilot`, or unset + env defaults (`TBCC_SECRETARY_AUTO_REPLY=0`, `TBCC_SECRETARY_SUGGEST_DIRECT=1`) | Nothing until you approve | Draft card DM with ✓ Send / ✗ Drop / ↻ tones / Pilot·Auto toggle |
| **Auto** | Per-customer `reply_mode=auto`, or Business with `TBCC_SECRETARY_AUTO_REPLY=1` / direct with `SUGGEST_DIRECT=0` | Immediate LLM reply | Optional new-lead ping only |
| **Admin live** | Your admin Telegram ids | Immediate FAQ / ops menus | — |

**Per-customer override** lives on `secretary_user_contexts.reply_mode` (`pilot` | `auto` | NULL). Toggle from any draft card; the **current** draft is not auto-sent when you flip to Auto — tap ✓ Send once; later turns follow the new mode.

**Telegram folders do not affect this.** Draft routing is server-side only.

## Surfaces

| Surface | Customer experience |
|---------|---------------------|
| **Personal + Business Chat Automation** | Customer DMs you; secretary drafts/replies via `business_connection_id` |
| **Direct bot DM** | Customer opens `@aof_secretary_bot` (or future inbound clones) |
| **Clone fleet (Phase 2)** | Extra BotFather skins, shared brain, inbound deep-links only — see `docs/handoffs/2026-08-01_secretary-fleet-phase2.md` |

## Draft workflow

1. A non-admin user messages the secretary (or your Business-connected account).
2. Format Engine + sales coach + FAQ RAG draft a reply — **customer sees silence** in Pilot.
3. You get an **instant admin DM** with the draft card (mode line, coach hint, inline buttons).
4. **✓ Send** — delivers to the customer chat (Business or direct DM).
5. **✗ Drop** — discard.
6. **↻ Pro / Casual / Short** — regenerate tone, then approve.
7. **Pilot / Auto** — persist mode for that customer uid.

**New lead:** first recorded user message also pushes inbox `meta.code=secretary_new_lead` (surface, phase, mode, preview).

CLI equivalents: `/drafts`, `/approve DRAFT_ID`, `/reject DRAFT_ID`, `/redo DRAFT_ID casual`.

**Admin test without a fourth account:** `/as_customer <message>` on the secretary bot — synthetic customer uid, draft card only.

## Sales coach

- Seed: `py -3.13 scripts/seed_secretary_sales_playbook.py` → `secretary_knowledge_entries` tagged `sales_strategy`.
- At reply time: `build_sales_coach_suffix` merges tagged knowledge + `funnel_rag` `surface=dm` into the LLM system suffix.
- Draft card shows a one-line **Coach** hint (top playbook title).

## Key env (tbcc/.env)

```env
# Draft mode for direct DMs (default on) — inherited when reply_mode is NULL
TBCC_SECRETARY_SUGGEST_DIRECT=1

# Business chats: 0 = pilot (default), 1 = auto-reply in customer thread
TBCC_SECRETARY_AUTO_REPLY=0

# Where draft cards land (defaults to ADMIN_TELEGRAM_ID)
ADMIN_TELEGRAM_ID=7787282561
TBCC_SECRETARY_SUGGEST_NOTIFY_CHAT_ID=

# Format Engine core
TBCC_FORMAT_ENGINE_ENABLED=1
TBCC_FORMAT_ENGINE_VERBOSITY=compact
TBCC_FORMAT_ENGINE_LLM_REFINE=0
TBCC_SECRETARY_RAG_ENABLED=1

# LLM wallet (Hcnsec Model Square credits — NOT CometAPI)
TBCC_LLM_BASE_URL=https://api.hcnsec.cn/v1
TBCC_LLM_API_KEY=sk-...
TBCC_LLM_MODEL=step-3.5-flash

# Extra admins for drafts + inbox
TBCC_SECRETARY_ADMIN_IDS=
```

LLM panel presets: **Hcnsec (env)** = funded gateway; OpenRouter/OpenAI/Comet are other wallets. Swap models with **Set model id** using a Model Square id — see `docs/handoffs/2026-08-01_hcnsec-gateway-models.md`.

**Important:** Open `@aof_secretary_bot` and tap **/start** once so instant inbox DMs are not blocked (Telegram 403).

## Code map

| Piece | Path |
|-------|------|
| Bot host + draft UI | `backend/bots/secretary_bot.py` |
| Per-customer Pilot/Auto | `backend/app/services/secretary_reply_mode.py` |
| Sales coach | `backend/app/services/secretary_sales_coach.py` |
| FE context + phases | `backend/app/services/format_engine.py` |
| LLM phase refine | `backend/app/services/format_engine_llm.py` |
| Clone registry (Phase 2) | `backend/app/services/secretary_bot_instances.py` |
| Dashboard settings | `backend/app/api/secretary.py`, `dashboard/.../SecretarySettingsPanel.tsx` |
| Admin inbox instant DMs | `backend/app/services/admin_inbox.py` |
| Tests | `backend/tests/test_format_engine.py`, `test_secretary_reply_mode.py`, `test_secretary_sales_coach.py`, `test_secretary_new_lead.py` |

## Ops commands

- `/formats` — live people cards in the secretary DM (quote-block format view)
- `/fe_stats` — FE + RAG stats (admin)
- `/mystatus` — user's thread phase (customer)
- `/as_customer` — simulate customer DM (admin)
- `/inbox` — payment/loot/ops history
- Dashboard → Automation → Secretary / Format Engine

## LLM failure behavior (Pilot)

If the LLM is down in Pilot, **no error is sent to the customer**. You get an inbox ping: "Secretary draft failed" — fix API key via `/config` or dashboard.
