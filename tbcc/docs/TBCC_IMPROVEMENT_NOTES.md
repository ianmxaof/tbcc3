# TBCC improvement notes (tracking)

This file tracks user-requested improvements: what was implemented in code vs what remains planned.

## Implemented (recent pass)

| Area | Change |
|------|--------|
| Favicon | New favicon set from `5-30-26favicon_io` copied to `extension/icons/`, `extension/icons/transparent/`, dashboard `public/`, supervisor `.ico` path unchanged |
| Notifications | Click actions for Saved Messages, master archive, inbox, gallery panel, dest; side panel opens when extension was closed |
| Notification style | Options → Notifications: full / app name / body only / minimal |
| Inbox UX | **Go** (was Run), **Archive checked** button, clearer canonical-archive copy |
| Current tab | **Current** re-pins capture to last browsed http(s) tab before rescan |
| Downloads | Default **buffered** mode: TBCC progress → browser save; **direct** stream in Options |
| Lightbox | Filename, format, dimensions, host, source page overlay |
| Context menu | Smaller/darker menu; reverse image + Saved Messages; nested Select / Export / More |
| Erome/video ZIP | Session fetch passes gallery `tabId` into background (`tbcc-content-fetch-bytes`) for side-panel ZIP/download |

## Canonical master archive

**Dashboard → Master Archive** (Postgres + API) is canonical. The extension mirror is for capture, tagging, filters, and hygiene; `syncFromServer` merges when API is up. Clearing “local only” in the extension does not delete server rows.

## Scraper concurrency

- **Ingest sources**: Each source can be scheduled; Celery runs `run_scrape` tasks on the `scrape` queue. Practical limit is **one Telethon `admin.session`** — only one heavy scraper process should hold that file at a time (see `media.py` / ops docs). You can queue many sources, but parallel runs risk session lock errors.
- **Per-run caps**: Import/crawler limits vary by endpoint (e.g. album crawl `limit`, pool import max 200). Check Automation → Ingest and `scrape_run_service.py`.

## Deferred / needs design

| Item | Notes |
|------|--------|
| Content distribution schedule | Product/strategy doc + Scheduler/campaign integration — not a single UI toggle |
| Album poster bot | Telegram-native album cycling/promo — extend `album_service` + poster worker |
| Collected gallery workflow | **Implemented** — see workflow below |
| X.com scraper bot | New adapter in `crawler_resolver` / scraper sources (ToS + rate limits) |
| Erome anti-scraping deep dive | Use DevTools on blocked album: compare cookies, `Referer`, CDN 403, age gate; extend `fetchEromeCdnWithRetries` / tab prewarm |
| Local OS auto-tag service | Standalone CLI using same enrichment stack as backend (`auto_tag_enrich`, CLIP) — separate from extension pipeline |
| Zipping “pattern” | Failures are usually **CDN 403** (especially `.mp4`), not ZIP format; fix fetch path (album tab open, session) before compression |

## Erome fetch troubleshooting

1. Open the **album** tab; complete 18+ gate; play a video once.
2. Refresh TBCC gallery on **Current** tab.
3. For ZIP/download, ensure items have `tabId` / `detailPageUrl` from that album.
4. If only `.mp4` fail, check background log for `Erome CDN 403` — wait and retry; do not clear Erome cookies.

## Collected gallery workflow

1. **Main gallery** — select tiles → toolbar **＋** or right-click **Add to Collected** (optional batch name).
2. **Collected** tab — filter by batch pill; set tags/note; **Apply to selected**; choose route (Saved / pool / channel / forum).
3. **Open Dest panel** — stages selection on main grid, merges tags + caption, opens Send settings.
4. **Send** (or **Dest + Send**) — uses the normal TBCC send pipeline (session fetch, albums, Telegram).

Storage: `chrome.storage.local` key `tbcc_collected` (cap 200), shared module `tbcc-collected-lib.js`.

Successful pool imports may still append to Collected as a send log (`fromSend: true`).

## Reload after icon change

Reload the extension in `chrome://extensions` and hard-refresh the dashboard so favicons and manifests pick up new PNGs.
