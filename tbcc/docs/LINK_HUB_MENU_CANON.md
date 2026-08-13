# Link Hub + Creator Recruitment — canonical copy & assets

Single source of truth for AOF `@aofmainhub` interactive menus and Loot Room `/model` recruitment.

## What lives where

| Asset | Path | Regenerate |
|-------|------|------------|
| HTML menu builders (v1–v4) | `backend/app/services/aof_links_hub_menu_variants.py` | Edit + pytest |
| Creator `/model` variations | `backend/app/services/loot_creator_recruitment_posts.py` | Edit + pytest |
| Human-readable creator copy | `docs/samples/loot_creator_recruitment/COPY_VARIATIONS.md` | Sync from service |
| Menu PNGs | `docs/samples/link_hub_menus/images/` | See image prompts below |
| Image prompts (live button order) | `docs/samples/link_hub_menus/IMAGE_PROMPTS.md` | `build_link_hub_image_prompts.py --write-md` |
| Button tree JSON | `docs/samples/link_hub_menus/button_tree_and_prompts.json` | `build_link_hub_image_prompts.py` |
| Affiliate seed (order + blurbs) | `backend/scripts/seed_promo_affiliate_links.py` | Island seed after edit |

## Menu variants (14 total)

### Button-tree fit (v5–v7) — **use on @aofmainhub**

**1280×960 (4:3)** — edge-to-edge width matches Telegram 2-column inline keyboard (yellow-box spec).

| Variant | AI style | Channel style |
|---------|----------|---------------|
| v5 | BUTTON-TREE REVEAL (✓ 2-col) | NETWORK REVEAL |
| v6 | BUTTON-TREE DARK PANEL | NETWORK DARK PANEL |
| v7 | BUTTON-TREE MATRIX | NETWORK MATRIX |

Deploy network set only:

```powershell
python scripts/deploy_mainhub_link_menus.py --network-only --execute
```

### Channel menus (`kind=channels`)

| Variant | Style | PNG |
|---------|-------|-----|
| v1 | Classic orange panel, box frame | `channels_v1_classic_orange_panel.png` |
| v2 | Neon grid blockquote | `channels_v2_neon_grid.png` |
| v3 | VHS broadcast guide | `channels_v3_vhs_broadcast.png` |
| v4 | Uniform rails `—— LANE ——` | `channels_v4_uniform_rails.png` |
| v5 | Network reveal 2-col | `channels_v5_network_reveal.png` |
| v6 | Network dark panel 2-col | `channels_v6_network_dark_panel.png` |
| v7 | Network matrix 2-col | `channels_v7_network_matrix.png` |

### AI partner menus (`kind=ai`)

| Variant | Style | PNG |
|---------|-------|-----|
| v1 | Dark panel, orange frame | `ai_v1_dark_panel.png` |
| v2 | Reveal board, ✓ + dot trails | `ai_v2_reveal_board.png` |
| v3 | Uniform grid table | `ai_v3_uniform_grid.png` |
| v4 | Storage matrix green `>>>` | `ai_v4_storage_matrix.png` |
| v5 | Button-tree reveal 2-col | `ai_v5_button_tree_reveal.png` |
| v6 | Button-tree dark panel 2-col | `ai_v6_button_tree_dark_panel.png` |
| v7 | Button-tree matrix 2-col | `ai_v7_button_tree_matrix.png` |

**Support footer (all AI v2+):** `/loot` · `/subscribe` · `/refer` · [Email list](https://powercore.kit.com/) (replaces Buy Me a Coffee).

## Posting commands

```powershell
# One interactive menu (photo + inline buttons)
cd tbcc/backend
python scripts/post_links_hub_interactive_menu.py --kind ai --variant v4 --execute

# All 8 to @aofmainhub
python scripts/deploy_mainhub_link_menus.py --execute

# Creator recruitment (manual)
python scripts/post_loot_creator_recruitment.py --variant G --execute
```

## Daily schedulers (Celery beat)

| Task | Default UTC hour | Target |
|------|------------------|--------|
| `send_mainhub_channel_spotlight` | 15 (`TBCC_MAINHUB_SPOTLIGHT_HOUR_UTC`) | @aofmainhub — channel of the day |
| `send_loot_room_creator_recruitment` | 14 (`TBCC_CREATOR_RECRUITMENT_LOOT_HOUR_UTC`) | AOF LOOT ROOM |
| `send_random_lane_creator_recruitment` | 20 (`TBCC_CREATOR_RECRUITMENT_LANE_HOUR_UTC`) | One content lane/day (ai, bop, taboo, …) |

Env (spotlight):

- `TBCC_MAINHUB_SPOTLIGHT_ENABLED=1` — daily window-shop post (SFW X promo pool album + wrapped lane CTA)
- `TBCC_MAINHUB_SPOTLIGHT_HOUR_UTC=15`
- `TBCC_MAINHUB_SPOTLIGHT_ALBUM_SIZE=3`
- `TBCC_LANE_OF_DAY_ALIGN=1` — Loot Room liveness spotlight + drop ticker follow the same UTC lane as mainhub

Lane-of-the-day refresh: midnight UTC beat + after each mainhub spotlight send. Re-seed: `POST /growth-hub/apply-liveness`.

Force smoke on island:

```bash
docker compose exec -T api celery -A app.workers.celery_app call app.workers.mainhub_channel_spotlight_worker.send_mainhub_channel_spotlight --kwargs='{"force": true}'
```

## Loot Room growth menu (pinned)

Permanent interactive board in **AOF LOOT ROOM** — bare invite + 18+ in caption; monetization + lane shortcut buttons.

| Variant | Style | PNG |
|---------|-------|-----|
| v5 | Growth reveal 2-col | `loot_v5_growth_reveal.png` |
| v6 | Growth dark panel 2-col | `loot_v6_growth_dark_panel.png` |
| v7 | Growth matrix 2-col | `loot_v7_growth_matrix.png` |

```powershell
cd tbcc/backend
python scripts/deploy_loot_room_link_menu.py --execute --variant v5
```

Regenerate image prompts (includes loot):

```powershell
python scripts/build_link_hub_image_prompts.py --write-md
```

Env (creator recruitment):

- `TBCC_CREATOR_RECRUITMENT_BUFFER_MIRROR=1` — also queue X line via Buffer (requires loot buffer mirror enabled)
- Beat runs hourly; only configured hour sends (same pattern as loot daily promo)

Force smoke (creator recruitment):

```bash
docker compose exec -T api celery -A app.workers.celery_app call app.workers.loot_creator_recruitment_worker.send_loot_room_creator_recruitment --kwargs='{"force": true}'
```

## Image ↔ button sync law

Telegram PNGs are **decorative**; clicks are inline keyboard buttons. Image prompts must still list partners in **exact keyboard order** (top→bottom, left→right, 2 columns default).

```powershell
cd tbcc/backend
python scripts/build_link_hub_image_prompts.py --write-md
```

Then regenerate PNGs from `IMAGE_PROMPTS.md` (Gemini MCP or manual). Copy to island:

`/docs/samples/link_hub_menus/images/` inside api container.

## Creator recruitment variants

Rotated daily: `G`, `H`, `I`, `J`, `V4_ORANGE`, `V4_MATRIX`, `V4_REVEAL`, `V4_DARK`.

Code: `loot_creator_recruitment_posts.py` · docs: `COPY_VARIATIONS.md` sections G–K + V4_*.

X one-liner: `build_x_recruitment_line(variant=...)`.

## Affiliate order

`priority_tier` in `seed_promo_affiliate_links.py` → `list_candidates(db, "links_hub_ai")` → buttons + image prompts + HTML menus all match.

After seed change: re-run prompt export, regenerate PNGs, redeploy menus.
