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

- `TBCC_BUFFER_X_REQUIRE_GATE_WRAP=1` (default): Buffer/X captions use Linkvertise gates, not bare `t.me`.
- `TBCC_X_USE_LINKVERTISE=1` on island recommended.
- BOP/Taboo: mirror blocked if bare Telegram URL would leak.

## Funnel strategy RAG

Playbook entries at `GET /funnel-strategies/` — seed via `POST /funnel-strategies/seed-defaults`.

**Hard rule:** never impersonate Telegram moderation / abuse team.

Patterns documented: flash Stars album urgency, bio→channel trap, FOMO scarcity, gated hub routing, high-attention wrap.

## Env reference

```
TBCC_BUFFER_X_REQUIRE_GATE_WRAP=1
TBCC_BUFFER_MIRROR_STRICT_NETWORK_KEYS=bop,taboo
TBCC_X_USE_LINKVERTISE=1
TBCC_GUMROAD_CHECKOUT_ENABLED=1
TBCC_REDDIT_EXECUTE=0   # set 1 only after subreddit registry review
```
