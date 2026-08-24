# Erome Enhancer — Sleazy Fork paste kit (community 4.3.0)

Operator intel stays private (`erome-enhancer.user.js`). Upload **only** `erome-enhancer-community.user.js`.

Rebuild: `py -3.13 tbcc/tools/erome-enhancer/build_community.py`

Form order matches Sleazy Fork Update / New script. Each block is copy-paste as-is (no fences on SF).

---

## 1 · Title

Keep the live title (update continuity):

```
Erome Enhancer extended sort options
```

---

## 2 · Short description

(Original listing blurb — keep this wording.)

```
Enhanced Erome browsing: Sort albums by views/videos/duration, filter by content type & duration, infinite scroll with auto-load, like counts display, hide watched albums, duration badges, deleted album display, and more!
```

---



## 3 · Code

- Prefer **Or upload** → choose:

```
tbcc/tools/erome-enhancer/erome-enhancer-community.user.js
```

- Or paste the full file into the source editor.
- Syntax highlighting: optional.
- Confirm Code has **no** `Browse Intel`, `tbccApiUrl`, or `browse-intel`.
- **Do not change** `@name` or `@namespace` from the live listing (`Erome Enhancer extended sort options` + `http://violentmonkey.net/`) — TM identity for updates.
- Brand cue for attentive readers: `@homepageURL` → `@aofsubscriptions_bot` (safe to change; not part of install identity).

---



## 4 · Additional info (default / English)

Markdown mode · Write tab · paste entire block (original structure + soft AOF trio):

```markdown
## Erome Enhancer (alpha) — extended sort edition

Fork of **Erome Enhancer** by LisaTurtlesCuck (MIT). Same browsing upgrades, plus **more sort dimensions** on explore/search/profile grids.

**Community build** — no analytics export, no third-party API calls. Settings and “viewed” history stay in your browser (`localStorage`).

### What it does

**Grid pages** (explore, search, user feed/liked/saved, profiles):

- **Sort bar** — one-click descending sort: Views, Likes, Engagement (likes÷views), Videos, Images, Total items, Total duration, Average clip length, Longest clip
- **Unwatched** — albums you have not opened yet; **Reset** restores site order
- **Like counts** — fetches each album page and overlays heart counts (rate-limited; retries on 429)
- **Duration badges** — total / average runtime on thumbnails
- **Filters** — videos only, images only, hide already-viewed, minimum average clip length
- **Infinite scroll** — auto-loads next pages with visible page separators
- **Deleted albums** — clear overlay when an album returns 404

**Album pages** (`/a/...`): hide clips below your minimum duration; Enhancer settings modal (gear).

### Privacy

- `@grant none` — no Tampermonkey privileged APIs
- Fetches only `erome.com` (extra requests when like counts are enabled)
- Nothing is sent to AOF/TBCC from this community build

### Credits

Based on **Erome Enhancer (alpha)** by LisaTurtlesCuck — MIT. Extended sorts + community packaging by **Altar of Flesh (AOF)**.

---

*Same crew, different surface — if this script earns its keep:*

- Free pull: [Loot God](https://telegram.me/aof_lootgod_bot?start=loot_free) (`@aof_lootgod_bot`)
- VIP / checkout: [@aofsubscriptions_bot](https://telegram.me/aofsubscriptions_bot)
- Network map: [AOF Main Hub](https://telegram.me/aofmainhub)

*The script itself does not phone home.*
```

---



## 5 · Localized additional info

**Leave blank** unless you maintain a real translation.

Optional Spanish stub (only if you add locale `es`):

```markdown
## Erome Enhancer (alpha) — edición con más ordenamientos

Fork de **Erome Enhancer** (LisaTurtlesCuck, MIT). Mismos upgrades de navegación, más dimensiones de ordenamiento en explore/search/perfiles.

Compilación **comunitaria**: sin analítica ni APIs externas. Datos en `localStorage`.

Créditos: LisaTurtlesCuck + empaquetado **AOF**.

- Loot: [Loot God](https://telegram.me/aof_lootgod_bot?start=loot_free)
- VIP: [@aofsubscriptions_bot](https://telegram.me/aofsubscriptions_bot)
- Hub: [AOF Main Hub](https://telegram.me/aofmainhub)
```

---



## 6 · Images (optional)

Max 5 · PNG/GIF/JPEG/WebP · < 1 MB each.

Suggested: sort bar · duration/like badges · filters modal. No AOF flyer art. Skip if none ready.

---



## 7 · Changelog

```markdown

```

---



## 8 · Script type

```
Public user script
```

---



## 9 · Adult content

Assumed on Sleazy Fork. Do **not** post on Greasy Fork.

---



## Operator checklist

1. [ ] Code = `erome-enhancer-community.user.js` (4.3.0) — `@namespace` still `http://violentmonkey.net/`; brand on `@homepageURL`
2. [ ] Title unchanged
3. [ ] Short description = **original** blurb (§2)
4. [ ] Additional info = original structure + Loot / subs / hub trio (§4)
5. [ ] Localized left empty (or real translation only)
6. [ ] Changelog pasted
7. [ ] Public + submit / update — **do not** “Save anyway” if SF warns about `@namespace` change
8. [ ] Spot-check: three Telegram links; Code has no intel strings



## Do not publish


| File                               | Why                        |
| ---------------------------------- | -------------------------- |
| `erome-enhancer.user.js`           | Operator intel + TBCC POST |
| `erome-enhancer-v3.3-base.user.js` | Build input (`@name base`) |


