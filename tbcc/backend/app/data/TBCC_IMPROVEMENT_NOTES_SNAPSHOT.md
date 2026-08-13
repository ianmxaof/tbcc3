# TBCC improvement notes (tracking)

This file tracks user-requested improvements: what was implemented in code vs what remains planned.

## Implemented (recent pass)

| Area | Change |
|------|--------|
| Agent workflow v3.0 | GSP v2.1; sprint state + bottom line rubric; completion gates + TBCC dev-ops rules; protocols `/sprint-start`, `/preflight`, `/session-close`, `/handoff-cc`; `TEST_MAP.md` |
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

## Buffer — Instagram carousel media failures

### Incident 2026-07-04 (archiveoffilthx)

- **When:** Jul 3 ~10:51 PM PT (`dueAt` 2026-07-04T05:51:19Z)
- **Buffer post id:** `6a489f576917141d453a64c1` — **deleted** via Buffer MCP
- **Error:** *There is an issue with the media included. Please remove it and try to upload it again.*
- **Channel:** Instagram `archiveoffilthx` (scheduled_mirror carousel, 5 slides)
- **Not a ban:** Later carousel + story posts succeeded (~3:04 AM PT Jul 4). X `wizardstick69` unaffected.

**Carousel slides (promo hash → source file under `TBCC_AOF_LOGOS_DIR`):**

| Slide | Promo file | Source |
|-------|------------|--------|
| 1 (CTA) | `aof-logo-c4cc32b3974e-cta.jpg` (1000×1000) | `AOF LOGOS\be633567131c1c6ad853b2b087cab565 (1).png` |
| 2 | `aof-logo-c95c2a17829e.jpg` (364×500) | `AOF LOGOS\Fixed2\AOF_Mega_Packs_Variant_3.png` |
| 3 | `aof-logo-cb4e0976be46.jpg` (376×512) | `AOF LOGOS\AOF_Mega_Packs_Variations\Fixed\AOF_Mega_Packs_Variant_2.png` |
| 4 | `aof-logo-dd99e51c5cb5.jpg` (376×512) | `AOF LOGOS\Fixed2\AOF_AI_renamepass0918ariant_7.png` |
| 5 | `aof-logo-e1960ce697b3.jpg` (376×512) | `AOF LOGOS\AOF_Mega_Packs_Variations\Fixed\AOF_Mega_Packs_Variant_1.png` |

**Likely cause:** Instagram rejected one slide or the mixed-aspect carousel batch (1000×1000 CTA lead + portrait slides). Intermittent fetch from ngrok at publish time is a secondary suspect.

**Prevention checklist (before blaming “Buffer is broken”):**

1. Keep `TBCC_PROMO_PUBLIC_BASE_URL` (ngrok/tunnel) up when IG mirrors run — Buffer must GET every slide URL.
2. Prefer consistent aspect ratios in carousel rotations (all portrait ~4:5 or all square); avoid mixing 1000×1000 CTA lead with tall portrait slides when possible.
3. After an IG `error` post, delete it in Buffer (MCP `delete_post` or dashboard) so it does not block queue hygiene.
4. Suspect source: `be633567131c1c6ad853b2b087cab565 (1).png` — awkward filename; was slide 1 with CTA watermark when this failed. Re-export or remove from `TBCC_AOF_LOGOS_DIR` if it fails again.
5. **Deferred:** pre-flight IG carousel validator (fetch each URL, check dimensions/mime, quarantine slide on prior Buffer error).

### X posts and images

X **can** attach images (`create_post(..., image_url=…)`). Current lanes are **text-only by design**:

| Lane | Images? | Why |
|------|---------|-----|
| Native X queue refill (`buffer_native_queue_refill.py`) | No | Hub + affiliate link posts; no asset fetch |
| Pool export flywheel (`pool_surface_mirror.py`) | No | Teaser + Telegram invite only |
| Ship log / milestone scripts | No | Build-in-public text |
| Scheduled Telegram→Buffer mirror | **Optional** | Uses `buffer_x_queue[].image_url` or first public promo URL on the post |
| Armory queue (`seed_aof_buffer_armory.py`) | **Optional** | Gravatar or `TBCC_BUFFER_IG_DEFAULT_IMAGE_URL` / promo basename |

To add images to automated X posts: extend native refill or armory entries with `image_url`, or attach promo URLs on scheduled posts with `buffer_mirror_enabled`.
