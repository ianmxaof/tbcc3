# TBCC Market Intel — multi-platform architecture

## Do the three Tampermonkey scripts "link together"?

**No direct coupling.** Do not modify Reddit++ (7k+ line webpack UI bundle) or XEnhancer (media-save UX) to talk to Erome Enhancer. That creates:

- Update conflicts when Greasy Fork authors push changes
- `@grant` / CSP mismatches (Reddit++ uses `GM_*`; Erome uses `@grant none`)
- Duplicate fetches on overlapping pages (none today — different `@match` domains)

### Correct pattern: **merge at TBCC backend**

```
┌─────────────┐  ┌──────────────┐  ┌─────────────────────┐
│ Erome TM    │  │ Reddit probe │  │ Buffer metrics sync │
│ v4.x intel  │  │ (PRAW/JSON)  │  │ (your X posts)      │
└──────┬──────┘  └──────┬───────┘  └──────────┬──────────┘
       │                │                      │
       └────────────────┼──────────────────────┘
                        ▼
           POST /analytics/market-intel  (platform field)
                        ▼
              market-intel.jsonl + timeseries.jsonl
                        ▼
     aggregate → content_signals → growth_hub / upload_policy / rank_pool_media
```

| Script | Purpose today | Intel role |
|--------|---------------|------------|
| **Erome Enhancer v4.x** (TBCC fork) | Grid sorts + browse intel | **Primary market collector** for Erome |
| **Reddit++** | UI cleanup, keyword filter | **Not an analytics script** — keep for browsing |
| **XEnhancer** | Save media, format timestamps | **Not trend analytics** — keep for browsing |
| **TBCC Reddit probe** (backend) | `market_intel_probe.py` | Scheduled subreddit hot/top JSON |
| **TBCC Buffer sync** (existing) | Your X post metrics | **Your** performance, not market |

Optional future: thin **TBCC Intel Bridge** userscript (`@grant GM_xmlhttpRequest`) on reddit/x that only POSTs scraped feed stats — separate from Reddit++/XEnhancer.

---

## Upload automation — what already exists

### Erome (Playwright) — **already shipped**

- `erome_upload_provision.py` — staging folder → Playwright → album URL
- `forum/erome-upload-from-bot` — album composer remote upload
- `erome_upload_policy.py` — rate limits, spam title guards
- `erome_upload_analytics.py` — upload ledger + view sync

**Intel feeds upload decisions** (tags, format, duration band) — it does not replace Playwright. Flow:

```
market intel → upload_policy hints → album composer caption/title/tags → upload_staged_folder()
```

### Reddit (PRAW) — **already shipped, dry-run default**

- `reddit_post_service.py` — plan + submit via PRAW
- `reddit_fanout.py` — mirror after Telegram scheduled send
- `aof_reddit_subreddit_registry.py` — preconfigured subs, cooldowns, tiers
- Enable live: `TBCC_REDDIT_EXECUTE=1` + API creds in `.env`

**Scheduling:** wire Celery beat → pick sub from registry using intel tag match → `fanout_reddit_teaser`.

### X — **Buffer (existing)**

- `buffer_graphql.py`, export flywheel surface routing
- Market trend on X = optional Playwright probe (defer); **your** ROI = Buffer metrics sync

---

## Schema (unified row)

All platforms normalize to:

```json
{
  "platform": "erome|reddit|x|telegram",
  "captured_at": "ISO8601",
  "entity_id": "album_id or post_id",
  "entity_url": "https://...",
  "context": { "subreddit": "...", "path": "/explore", "search_query": "..." },
  "views": 125000,
  "score": 842,
  "comments": 12,
  "engagement_bps": 674,
  "tags": ["milf"],
  "format_bucket": "multi_video",
  "uploaded_at_approx_days_ago": 2.0,
  "views_per_day_proxy": 10000.0,
  "uploader": "handle",
  "is_uploader_verified": false,
  "media_sequence": ["video", "image"]
}
```

Ledgers under `{tbcc_run}/erome-analytics/`:

| File | Role |
|------|------|
| `browse-intel.jsonl` | Daily dedupe snapshots (Erome + merged POST rows) |
| `market-intel-timeseries.jsonl` | Every snapshot (velocity deltas) |
| `upload_ledger.jsonl` | Our uploads (existing) |

---

## Growth hub consumption

| Lever | Intel input |
|-------|-------------|
| Pool `rank_pool_media` | Tag overlap with top-quartile Erome tags |
| `content_signals` | `erome_market_anomaly`, `reddit_tag_momentum` |
| Export flywheel | Format bucket → surface (Reddit gallery vs Buffer X short) |
| Growth hub interval | Tighten lane when tag velocity z-score high |
| Erome upload policy | Block saturated tags; prefer winning format bands |
| Reddit fanout | Pick subreddit from registry by tag + tier |

---

## Env flags

```env
TBCC_EROME_BROWSE_INTEL_ENABLED=1
TBCC_EROME_BROWSE_INTEL_RANK=1
TBCC_MARKET_INTEL_PROBE_ENABLED=1
TBCC_MARKET_INTEL_PROBE_SUBREDDITS=erome,amateur_milfs
TBCC_REDDIT_EXECUTE=0          # 1 when ready for live submit
TBCC_REDDIT_MIRROR_ON_SCHEDULED=1
```

---

## Sprint map (compressed)

| Day | Deliverable |
|-----|-------------|
| 1 | v4.2 Erome TM: uploader, age, velocity, media_sequence |
| 1 | Backend: platform field, timeseries append, normalize v4.2 |
| 2 | Reddit JSON probe worker + beat schedule |
| 2 | `content_signals` market anomaly stub |
| 3 | `erome_upload_policy.intel_upload_hints()` |
| 3 | Reddit scheduled fanout from intel tag (observe mode) |
| 4 | Erome probe pages (Playwright) top tags — optional |
| 5 | Growth hub observe proposals from intel summary |

Erome **upload automation** is not greenfield — connect intel → policy → existing Playwright path.
