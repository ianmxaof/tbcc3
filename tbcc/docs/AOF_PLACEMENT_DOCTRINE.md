# AOF placement doctrine

Strategic rules for where checkout, promo, and outbound links appear. Every surface has one job — no accidental duplicate CTAs.

## Surface matrix

**2026-08-22 ACK locks (forum-as-library, Week-1):** paid library moves to a **new private twin forum** — Loot Room itself is *not* paywalled this track. Game/vault (VIP) is **not ACK'd as product** — deferred until vault inventory is named. See `tbcc/docs/handoffs/2026-08-22_loot-forum-twin-week1.md` for full directive.

| Surface | Role | Checkout | Promo | Outbound X |
| ------- | ---- | -------- | ----- | ---------- |
| **@aofmainhub** | Top-of-funnel landing from X / Erome / ML / TV | **One** durable pinned 3-button CTA (Stars + Crypto + Gumroad) | Ephemeral pin pings (shuffled SFW poster, no checkout keyboard) | N/A (inbound target) |
| **Loot Room** | **Hangout** — free live community + LINKS bulletin. Stays free until a later hard-cutover ACK; not the paid destination. | None this track (library checkout moved to twin) | Network liveness | Primary X mirror |
| **AOF Library — Archive of Filth (twin)** | **Library** — new private forum, the paid destination for forum-as-library. Week-1: **scheduled auto-feed is AI topic (thread 57) only**; remixer (`/rebundle`) oversees **all** twin subtopics (album-composer bot admins the whole forum, not just AI). | Twin membership (Stars sub / ledger seat) — **not** the 24h loot key (rolls-only, no seat) | AI topic scheduled feed + `/rebundle` curation on every subtopic | N/A (private forum, no outbound) |
| **Free lanes** (ai/ass/big_tits/milf/abg/goon/packs/voyeur/taboo/blowjob/bop) | **Party boards** — shallow-live teaser cadence (CADENCE track: 288min / ~5 posts day) | None | Network liveness | Lane invites via LV |
| **BOP / Taboo** | High-attention niche lanes | Rare / soft — route to hub or twin | Pool content | **Mandatory wrapped links** (`TBCC_BUFFER_MIRROR_STRICT_NETWORK_KEYS`) |
| **AOF VIP** | **Deferred game/vault lane** — not ACK'd as product; existing native Stars sub stays live but is not this track's target | Native Stars sub + pack CTAs (unchanged, not touched this track) | Premium drops | Secondary X (`TBCC_BUFFER_CHANNEL_ID_X_SECONDARY`) |
| **Loot God bot** (`@aof_lootgod_bot`) | **Taste** — free sampler/teaser funnel; 24h loot key is **rolls-only** (no forum seat granted) | None (key ≠ seat) | Roll cadence | Only bot CTA |

## Library access rules (Week-1 ACK, forum-as-library)

- **24h loot key = rolls-only.** The Loot God bot's 24h key grants roll cadence (taste/sampler), **never** a twin forum seat. Key redemption and library membership are separate ledgers — do not wire the loot key flow to auto-seat the twin.
- **Grandfather = yes.** Existing active AOF VIP (main-section) subscribers are auto-seated into the twin at cutover/beta — no separate purchase. Week-1 only *documents* the dry-run count (see Phase 3 of the directive); no mass invite executes without a later explicit operator ACK.
- **No hard cutover this track.** Loot Room is not paywalled, `+97f4…` public invite is not killed, and no addlist surgery happens under this ACK — see Scope in `tbcc/docs/handoffs/2026-08-22_loot-forum-twin-week1.md`.

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
