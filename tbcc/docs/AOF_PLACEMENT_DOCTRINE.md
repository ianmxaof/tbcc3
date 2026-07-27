# AOF placement doctrine

Strategic rules for where checkout, promo, and outbound links appear. Every surface has one job — no accidental duplicate CTAs.

## Surface matrix

| Surface | Role | Checkout | Promo | Outbound X |
| ------- | ---- | -------- | ----- | ---------- |
| **@aofmainhub** | Top-of-funnel landing from X / Erome / ML / TV | **One** durable pinned 3-button CTA (Stars + Crypto + Gumroad) | Ephemeral pin pings (shuffled SFW poster, no checkout keyboard) | N/A (inbound target) |
| **Loot Room** | Live community + LINKS bulletin | Cadenced checkout on main scheduler (`TBCC_MAIN_GROUP_CHECKOUT_EVERY_N`) | Network liveness | Primary X mirror |
| **BOP / Taboo** | High-attention niche lanes | Rare / soft — route to hub or VIP | Pool content | **Mandatory wrapped links** (`TBCC_BUFFER_MIRROR_STRICT_NETWORK_KEYS`) |
| **AOF VIP** | Paid lane | Native Stars sub + pack CTAs | Premium drops | Secondary X (`TBCC_BUFFER_CHANNEL_ID_X_SECONDARY`) |

## Mainhub schedulers

| Scheduler | Cadence | Behavior |
| --------- | ------- | -------- |
| `AOF MAINHUB — VIP CTA (pinned)` | Weekly | Single SFW poster + 3-button VIP checkout; stays pinned |
| `AOF MAINHUB — pin liveness` | Every 8h (3×/day PT) | Shuffle SFW poster → pin → delete after 45s |

Apply: `py scripts/apply_mainhub_growth.py --execute`

## Duplicate checkout posts on mainhub

Not intentional. Legacy 2-button forwards beside newer payment-bot posts. Consolidate to **one durable pin**; delete or archive old forwards.

## X outbound links

**Default (v1):** `TBCC_X_USE_LINKVERTISE=0` — Linkvertise stays on **Telegram only** (channel manual gates + `prompt_gate` Text assets). Buffer/X/IG use clearnet hub (`telegram.me/aofmainhub` / `@aof_lootgod_bot`), revshare affiliates, and Gumroad VIP — filtered by `_caption_allowed_for_x` and `x_placement_violations()`.

- `TBCC_BUFFER_X_REQUIRE_GATE_WRAP=1` (default): legacy strict-wrap path for bare `t.me` on some mirrors; with `TBCC_X_USE_LINKVERTISE=0`, `wrap_url_for_x_outbound()` **passes through** bare Telegram URLs (affiliate-first previews).
- `TBCC_X_USE_LINKVERTISE=1`: optional island override — enables LV hosts on X captions and manual-gate overflow URLs.
- BOP/Taboo: mirror blocked if bare Telegram URL would leak (`TBCC_BUFFER_MIRROR_STRICT_NETWORK_KEYS`).

### Prompt gates (Telegram)

| Rule | Enforcement |
| ---- | ----------- |
| One LV destination per message | `prompt_gate_placement.telegram_placement_violations()` |
| Channel gate **or** prompt_gate Text slug — never both | Cannibalization guard + footer suppression on `AOF PROMPT DROP` rows |
| Goblin claim + checkout deep links | Clearnet only — never wrapped (`is_protected_clearnet_url`) |
| X/IG | No LV hosts when `TBCC_X_USE_LINKVERTISE=0` |

Service: `backend/app/services/prompt_gate_placement.py` · tests: `tests/test_prompt_gate_placement.py`

## Funnel strategy RAG

Playbook entries at `GET /funnel-strategies/` — seed via `POST /funnel-strategies/seed-defaults`.

**Hard rule:** never impersonate Telegram moderation / abuse team.

Patterns documented: flash Stars album urgency, bio→channel trap, FOMO scarcity, gated hub routing, high-attention wrap.

## Env reference

```
TBCC_BUFFER_X_REQUIRE_GATE_WRAP=1
TBCC_BUFFER_MIRROR_STRICT_NETWORK_KEYS=bop,taboo
TBCC_X_USE_LINKVERTISE=0
TBCC_GUMROAD_CHECKOUT_ENABLED=1
TBCC_REDDIT_EXECUTE=0   # set 1 only after subreddit registry review
```
