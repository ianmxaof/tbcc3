# Telegram post aesthetics compendium

Living reference for **loot overseer** tier styling: how Telegram tiles media, how send order affects layout, and how TBCC maps patterns to code.

**Dashboard:** Emoji packs → sketchbook → **Post aesthetics compendium** (filterable).

**Source of truth (IDs + tier hints):** `tbcc/dashboard/src/lib/telegramPostAesthetics.ts`

## Your screenshot pattern

| ID | What you see |
|----|----------------|
| `document_then_album` | Small `.mp4` file bubble **above** |
| `album_2_horizontal` | Two videos **side-by-side** in one media group below |

Reproduce: send document first, then `send_media_group` with two videos (same session, poster account).

## TBCC loot wiring

- Media grouping: `backend/app/services/loot_media_layout.py` → `plan_media_send_groups`
- Delivery order: `backend/app/services/loot_preview_delivery.py` → `send_loot_preview_to_chat`
- Tier headers: `loot_tier_banner.py` + custom emoji presets (`source_note`: `loot_tier:N`)

Future: map compendium `id` → per-tier layout profile in loot config (DB).
