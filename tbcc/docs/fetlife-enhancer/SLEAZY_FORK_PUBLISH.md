# FetLife Enhancer — Sleazy Fork paste kit (community 1.0.0)

Operator intel + social-proof stay in the TBCC extension suite. Upload **only** `tbcc/userscripts/community/fetlife-suite-community.user.js`.

Rebuild:

```powershell
cd tbcc/userscripts
npm run build:nobump
```

Form order matches Sleazy Fork New script. Copy fences off before paste.

---

## 1 · Title

```
FetLife Enhancer
```

---

## 2 · Short description

```
FetLife browsing: masonry home feed, story type filter, mute, ASL/gender filter, auto-follow, place kinksters nav, infinite scroll, and privacy presets. Community build — no analytics, no phone-home.
```

---

## 3 · Code

Upload:

```
tbcc/userscripts/community/fetlife-suite-community.user.js
```

- Confirm Code has **no** `overlay-intel`, `tbccApiUrl`, or `Push to TBCC`.
- Brand cue: `@homepageURL` → `@aofsubscriptions_bot` (do not put the hub in `@namespace` — that breaks TM updates later).

---

## 4 · Additional info (English)

```markdown
## FetLife Enhancer

Masonry feed, story filters, mute, ASL, auto-follow, and kinksters scroll — one chevron panel.

**Community build** — settings stay in your browser. No analytics export, no third-party API calls from the script.

### What it does

- **Home feed** — masonry layout + filter pills
- **Story types** — client-side hide/show on the activity feed
- **Mute** — mute comment authors locally
- **ASL / gender filter** — hide male / FTM, optional location needles
- **Auto-follow** — paced Follow on kinksters lists (you start it)
- **Place nav** — jump to a city’s kinksters listing
- **Infinite scroll** — fills gaps on kinksters pages
- **FLConsole** — privacy presets (browser-side)

### Quick start

1. Install with Tampermonkey or Violentmonkey.
2. Open FetLife → **FL ▸** chevron on the right edge.
3. Disable duplicate FetLife userscripts so only one suite runs.

### Privacy

- Storage is local (`GM_*` / localStorage)
- Fetches go to `fetlife.com` only
- Nothing is sent to AOF/TBCC from this community build

### Credits

Home-feed masonry adapted from [FetLife Suite - Home Feed](https://sleazyfork.org/scripts/558357) (RYSTA, MIT) and other MIT/gist sources — see repo `NOTICE.md`. Community packaging by **Altar of Flesh (AOF)**.

---

*Same crew, different surface — if this script earns its keep:*

- Free pull: [Loot God](https://telegram.me/aof_lootgod_bot?start=loot_free) (`@aof_lootgod_bot`)
- VIP / checkout: [@aofsubscriptions_bot](https://telegram.me/aofsubscriptions_bot)
- Network map: [AOF Main Hub](https://telegram.me/aofmainhub)

*The script itself does not phone home.*
```

---

## 5 · Localized additional info

Leave blank.

---

## 6 · Images

Optional. Chevron panel + masonry feed. No AOF flyer art.

---

## 7 · Changelog

```markdown
### 1.0.0 — community packaging

- Public FetLife enhancer: feed masonry, stories, mute, ASL, auto-follow, place nav, infinite scroll, privacy presets
- **No** context-intel, **no** TBCC ingest, **no** profile count padding
- Maintainer credit: Altar of Flesh (AOF); upstream attributions in NOTICE
```

---

## 8 · Script type

```
Public user script
```

---

## 9 · Adult content

Sleazy Fork assumed. Do **not** post on Greasy Fork.
