# Erome Enhancer — Sleazy Fork publish kit

## Title

`Erome Enhancer — Extended Sorts + Browse Intel`

## Short description (`@description`)

Sort Erome grids by views, likes, engagement, duration, and more. Infinite scroll, like counts, duration badges, video/image filters, hide-watched, browse-intel JSONL export for TBCC pool ranking.

## Full listing (paste into Sleazy Fork)

### What it does

**Grid pages** (explore, search, user feed/liked/saved, profiles):

- **Sort bar** — Views, Likes, Engagement, Videos, Images, Items, Duration, Avg, Longest, Unwatched, Reset
- **Like counts** — per-album fetch with 429 retry
- **Duration badges** on thumbnails
- **Filters** — videos only, images only, hide viewed, min avg clip length
- **Infinite scroll** with page separators
- **Deleted album** overlay on 404

**Album pages** (`/a/...`): hide clips below min duration; Enhancer settings modal.

**Browse Intel (v4)** — while loading likes, records views/likes/tags/duration/format into `localStorage`. Export `browse-intel-drop.jsonl` or push to a local TBCC API for pool ranking.

### v4.0 changes

- Browse intel collector + JSONL export + optional TBCC POST
- Removed third-party `@updateURL` / `@downloadURL` (self-hosted fork)
- Extended sorts from v3.3 fork (likes, engagement, images, items, avg/longest duration, unwatched)

### Privacy

- `@grant none` — no Tampermonkey privileged APIs
- Data stays in browser unless you export or push to your own TBCC URL
- Fetches only `erome.com` (more requests when like counts enabled)

### Credits

Based on **Erome Enhancer (alpha)** by LisaTurtlesCuck — MIT. v3.3 sort extensions + v4 intel by TBCC fork.

### Adult content

**Yes** — check the adult box on Sleazy Fork.

## Install source file

Copy from repo:

`tbcc/tools/erome-enhancer/erome-enhancer.user.js`

## Before publishing

1. Disable duplicate `Erome Enhancer (alpha)` in Tampermonkey — keep only this script.
2. Confirm script header has **no** `@updateURL` / `@downloadURL`.
3. Post to [sleazyfork.org/scripts/new](https://sleazyfork.org/en/scripts/new) (not Greasy Fork).
