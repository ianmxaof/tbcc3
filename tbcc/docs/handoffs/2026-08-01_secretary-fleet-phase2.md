# Secretary fleet Phase 2 — inbound clones (locked topology)

**Status:** Schema + registry helpers shipped (alembic `111`, `secretary_bot_instances`, `app/services/secretary_bot_instances.py`). Multi-app host not wired to tray/compose yet.

## Doctrine

- Clones are **inbound only** (ads / channels / undress deep-link → `t.me/<clone>?start=…`).
- No Telethon cold outbound.
- Shared brain: Format Engine, FAQ RAG, sales coach, per-customer `reply_mode`.
- Personal + Business secretary remains the primary closer; clones are volume skins.

## Next implementation slice

1. Dashboard PATCH to upsert clone tokens (mirror loot bot_token mask pattern).
2. Extend `zeus_multi_app.run_applications` host: factory builds N secretary `Application`s from `tokens_for_host(db)`.
3. Prefix draft cards / inbox titles with `@clone_username`.
4. Single island `secretary_bot` process hosts N tokens (no N containers).

## Smoke later

- Insert second BotFather token via `upsert_instance`.
- Confirm both poll without 409.
- Customer `/start` on clone → same FE/CRM as primary.
