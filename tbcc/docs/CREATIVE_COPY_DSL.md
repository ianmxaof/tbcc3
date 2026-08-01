# Creative Copy DSL

TBCC social copy templates support **static placeholders** (resolved by `fill_armory_template`) and **dynamic tokens** (resolved by `template_expand.expand_template_tokens` first).

## Pipeline order

1. `expand_template_tokens()` — dates, lanes, prompt gates
2. `fill_armory_template(for_x=True)` — hub, affiliates, bots
3. `finalize_buffer_x_caption()` — link order, 280-char fit
4. `append_x_hashtags()` — conditional `#erome`, `#nsfw`

## Static placeholders (`fill_armory_template`)

| Token | Resolves to |
|-------|-------------|
| `{hub}` | Primary hub CTA (`TBCC_AOF_HUB_INVITE_URL` or lootgod profile) |
| `{lootgod}` | Bare `@aof_lootgod_bot` profile URL |
| `{lootgod_free}` | Loot god with `?start=loot_free` |
| `{spicy}` | Spicy companion bot URL (beacon-wrapped when configured) |
| `{affiliate}` / `{affiliate2}` | Rotating `promo_affiliate_links` for `x_buffer` |
| `{allmylinks}` | Tracked allmylinks map |
| `{gumroad_vip}` | VIP Gumroad ladder |
| `{gravatar}` | Profile / fallback affiliate |

## Dynamic tokens (`template_expand`)

| Token | Example | Notes |
|-------|---------|-------|
| `{date:%Y%m%d}` | `20260801` | Python `strftime` on local now |
| `{weekday}` | `Friday` | Full weekday name |
| `{lane:abg}` | Gate URL | From `aof_manual_gate_links` |
| `{prompt_lv:key}` | LV Text slug | Telegram-safe; requires DB provision |
| `{prompt_teaser:key}` | `prompt pack → @aofmainhub (key)` | X-safe — no raw LV host |

## Surface policy

- **X / Buffer:** `TBCC_X_USE_LINKVERTISE=0` (default) blocks raw Linkvertise hosts in captions. Use `{prompt_teaser:…}` on X.
- **Telegram:** `{prompt_lv:…}` for gated prompt SKUs.

## Rotation

`social_copy_templates` rows demote to queue tail after `max_uses_before_demote` (default 2). Categories rotate via `TBCC_BUFFER_X_COPY_ROTATION_CATEGORIES` (default `paired,lootgod,spicy,network,affiliate`).

## Seed

```powershell
cd tbcc/backend
py -3.13 scripts/generate_buffer_x_copy_catalog.py
py -3.13 scripts/seed_social_copy_templates.py --import-dir ../docs/samples/buffer_x_copy --execute
```
