# ThisVid Enhancer — Sleazy Fork paste kit (community 1.0.0)

Operator intel + R2 upload library stay in the TBCC extension. Upload **only** `tbcc/tools/thisvid-enhancer/thisvid-enhancer-community.user.js`.

Rebuild:

```powershell
py -3.13 tbcc/tools/thisvid-enhancer/build_community.py
```

---

## 1 · Title

```
ThisVid Enhancer
```

---

## 2 · Short description

```
ThisVid browsing: title include/exclude, privacy and duration/views sort, infinite scroll with RAM caps, download buttons, and mass-friend helpers. Community build — no analytics, no upload library.
```

---

## 3 · Code

Upload:

```
tbcc/tools/thisvid-enhancer/thisvid-enhancer-community.user.js
```

- Confirm Code UI has no Intel tab / Upload library / `media.powercore.app` as a default queue (operator strings may still exist in dead branches — community run path skips them).
- Brand cue: `@homepageURL` → `@aofsubscriptions_bot`. Keep `@namespace` stable after first publish.

---

## 4 · Additional info (English)

```markdown
## ThisVid Enhancer

Grid filters, capped infinite scroll, downloads, and optional friend helpers — one **TV ▸** chevron.

**Community build** — settings stay in your browser. No analytics export, no third-party upload queue.

### What it does

- **Filters** — title include/exclude, public/private, duration/views sort, video-only habits
- **Infinite scroll** — extra pages with a hard card/RAM cap (won’t eat the tab)
- **Downloads** — per-clip helpers on watch pages
- **Friends / Grow** — mass-friend tools (you start them; no baked-in promo channel)

### Quick start

1. Install with Tampermonkey or Violentmonkey.
2. Open ThisVid → **TV ▸** on the right edge.
3. If you also run the TBCC Chrome extension, turn off its ThisVid module so the two don’t double-inject.

### Privacy

- `@grant none` — no privileged Tampermonkey APIs
- Fetches go to `thisvid.com`
- Nothing is sent to AOF/TBCC from this community build

### Credits

Community packaging by **Altar of Flesh (AOF)**.

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

Optional. Chevron + filters. No flyer art.

---

## 7 · Changelog

```markdown
### 1.0.0 — community packaging

- Public ThisVid enhancer: filters, capped infinite scroll, downloads, friend helpers
- **No** browse-intel, **no** R2/upload library, **no** baked ThisVid promo channel
- Maintainer credit: Altar of Flesh (AOF)
```

---

## 8 · Script type

```
Public user script
```

---

## 9 · Adult content

Sleazy Fork assumed. Do **not** post on Greasy Fork.
