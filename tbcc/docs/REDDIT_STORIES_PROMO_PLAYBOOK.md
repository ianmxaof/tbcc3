# Reddit + Telegram Stories promo playbook

Automated Reddit posts drive cold traffic to **@aofmainhub**. Telegram Stories amplify the same landing for people already in your TG graph. Together they recreate the manual “promo wave” that converted last time you were actively distributing.

**Erome is out** (operator IP ban) — circuit uses lane teasers (image/gallery) and text subs only.

---

## Circuit overview

```
Lane scheduler (Loot Room / VIP) → optional reddit_mirror
    → pick eligible sub (cooldown + global cap)
    → PRAW submit + comment beacon link
    → api.powercore.app/r/reddit-{sub} → @aofmainhub (UTM)
    → VIP pin / addlist / network lanes

Within 60 min (manual): Telegram Story → same mainhub CTA
```

---

## Operator go-live (island)

```powershell
cd tbcc/backend

# 1. Env (see .env.example Reddit block)
#    TBCC_REDDIT_ENABLED=1
#    TBCC_REDDIT_EXECUTE=0          # dry-run first
#    TBCC_CLICK_BEACON_PUBLIC_BASE=https://api.powercore.app
#    TBCC_REDDIT_USE_BEACON=1

py -3.13 scripts/reddit_go_live.py --seed --execute-beacons --enable-mirrors --dry-run-post

py -3.13 scripts/reddit_subreddit_audit.py telegramNSFW1818 --save

# Live (one sub first)
# TBCC_REDDIT_EXECUTE=1
py -3.13 scripts/reddit_post_dry_run.py --execute --teaser "AOF curated Telegram network"
```

Enable mirrors on schedulers (if not done):

```powershell
py -3.13 scripts/enable_vip_platform_mirrors.py --execute
```

---

## Stories timing (manual — high leverage)

| When | Action |
|------|--------|
| Reddit post goes live | Note time + sub in ops log |
| **+30–60 min** | Post Story on promo account → `telegram.me/aofmainhub` or pinned hub screenshot |
| +2–4 h | Check beacon hits (`reddit-telegramnsfw1818`) + GA4 `utm_source=reddit` |
| Spike | Optional second Story same day |

**Story copy shape:** one line hook + “full map on hub” — no Linkvertise on Story link.

---

## What automation enforces

| Guard | Env / code |
|-------|------------|
| Global daily cap | `TBCC_REDDIT_GLOBAL_MAX_POSTS_PER_DAY` (default 3) |
| Min gap between any Reddit post | `TBCC_REDDIT_GLOBAL_MIN_GAP_HOURS` (default 4) |
| Per-sub cooldown | `reddit_subreddit_profiles` |
| No Linkvertise in body | `reddit_surface_caption.py` |
| Beacon attribution | `TBCC_REDDIT_USE_BEACON=1` → `/r/reddit-{sub}` |
| Post ledger | `.tbcc-run/reddit-promo/post-ledger.jsonl` |

---

## Measurement

| Signal | Where |
|--------|--------|
| Reddit submits | `.tbcc-run/reddit-promo/post-ledger.jsonl` |
| Global cadence | `.tbcc-run/reddit-promo/global-state.json` |
| Hub clicks | Click beacon hits for slug `reddit-telegramnsfw1818` |
| GA4 | `utm_source=reddit`, campaigns `sched_*` or sub key |
| Sales | VIP checkout / Stars within 24h of ledger entry |

Tail ledger:

```powershell
Get-Content ..\.tbcc-run\reddit-promo\post-ledger.jsonl -Tail 10
```

---

## First sub: r/telegramNSFW1818 (only active sub — slow start)

`r/DailyTelegram` was a bad registry entry — **that subreddit does not exist**. We use **r/telegramNSFW1818** instead (real NSFW Telegram promo community).

All other registry subs are **paused** until you promote them in `aof_reddit_subreddit_registry.py` + `--seed --replace`.

- **Post kind:** text
- **Link:** first comment → beacon `reddit-telegramnsfw1818`
- **Status:** `active` in registry
- **Cadence:** max 1/day, 2/week, 72h cooldown

**Operator:** read sub rules before first live post (`reddit_subreddit_audit.py telegramNSFW1818 --save`).

Do **not** promote `@aof_spicybot` or generation bots on Reddit — shadowban lane.

---

## What gets posted (content)

When `reddit_mirror_enabled` fires after a **Loot Room / VIP lane scheduler** send:

| Piece | Source |
|-------|--------|
| **Subreddit** | Only `r/telegramNSFW1818` (until you activate more) |
| **Post type** | **Text** self-post (no image in slow-start config) |
| **Title** | Teaser from the Telegram post caption (URLs stripped), max ~280 chars |
| **Body** | Short intro: “AOF Network — curated Telegram network” + teaser hook + “Link in first comment.” |
| **First comment** | Beacon `https://api.powercore.app/r/reddit-telegramnsfw1818` → `@aofmainhub` with UTM |
| **NSFW flag** | Marked NSFW on submit |

**Not posted on Reddit (slow start):** Linkvertise, bot deep links (`?start=`), spicy/generation bots, Erome URLs.

**Later (when you unpause image subs):** gallery/image posts from scheduler attachment URLs — different subs, comment link same pattern.

Manual one-off test (no scheduler):

```powershell
py -3.13 scripts/reddit_post_dry_run.py --dry-run --teaser "Curated NSFW Telegram network — lanes, loot, VIP"
```

---

## Escalation order (after telegramNSFW1818 is stable)

1. Edit registry: change one sub `paused` → `probation` or `active`, restore `max_posts_per_week`
2. `py scripts/reddit_post_dry_run.py --seed --replace`
3. `py scripts/reddit_subreddit_audit.py <SubName> --save`
4. Manual test post before enabling mirror fan-out to that sub

Do **not** bulk-activate — one sub at a time. Scrolller suggestions stay paused by default.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `global_daily_cap_3` | Wait until next UTC day or lower cap consciously |
| `global_gap_4h` | Normal — automation spacing |
| `TBCC_REDDIT_ENABLED=0` | Flip env on island, restart workers |
| Comment link is localhost | Set `TBCC_CLICK_BEACON_PUBLIC_BASE` + seed beacons |
| Post removed | Pause sub in DB (`status=paused`), audit rules |

See also: `docs/AOF_PLACEMENT_DOCTRINE.md`, `docs/erome-enhancer/MARKET_INTEL_ARCHITECTURE.md` (Reddit section).
