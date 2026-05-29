const API_BASE = "http://localhost:8000";
const TBCC_API_HEALTH_URL = API_BASE + "/health";

/** Cached API reachability — avoids hammering :8000 when backend is down. */
let _tbccApiReachableCache = { ok: null, at: 0 };

function isTbccConnectionError(err) {
  const msg = String((err && err.message) || err || "").toLowerCase();
  return (
    err instanceof TypeError ||
    msg.includes("failed to fetch") ||
    msg.includes("networkerror") ||
    msg.includes("connection refused") ||
    msg.includes("err_connection_refused")
  );
}

async function probeTbccApiReachable(force) {
  const now = Date.now();
  if (!force && _tbccApiReachableCache.ok != null && now - _tbccApiReachableCache.at < 12000) {
    return _tbccApiReachableCache.ok;
  }
  const ac = typeof AbortController !== "undefined" ? new AbortController() : null;
  const timer = ac ? setTimeout(() => ac.abort(), 2500) : null;
  try {
    const r = await fetch(TBCC_API_HEALTH_URL, { cache: "no-store", signal: ac ? ac.signal : undefined });
    const ok = r.ok;
    _tbccApiReachableCache = { ok, at: now };
    return ok;
  } catch (_) {
    _tbccApiReachableCache = { ok: false, at: now };
    return false;
  } finally {
    if (timer) clearTimeout(timer);
  }
}

function invalidateTbccApiReachableCache() {
  _tbccApiReachableCache = { ok: null, at: 0 };
}

function setTbccApiOfflineBanner(visible, detail) {
  const el = document.getElementById("tbccApiOfflineBanner");
  const text = document.getElementById("tbccApiOfflineBannerText");
  if (!el) return;
  el.hidden = !visible;
  if (text && visible) {
    text.textContent =
      detail ||
      "TBCC API offline — start the backend (localhost:8000). Capture still works; pools, tags, and Telegram send need the API.";
  }
}

async function refreshTbccApiOfflineBanner() {
  const ok = await probeTbccApiReachable(false);
  setTbccApiOfflineBanner(!ok);
  return ok;
}

function markPoolSelectOffline() {
  const mark = (sel, label) => {
    if (!sel) return;
    sel.innerHTML = "";
    const o = document.createElement("option");
    o.value = "";
    o.textContent = label;
    sel.appendChild(o);
  };
  mark(poolSelect, "(API offline)");
  mark(savedUrlInboxDefaultPool, "(API offline)");
}

/**
 * Gallery items may retain dashboard preview URLs (Vite :5173 + /api prefix).
 * Server-side import must hit the API directly (:8000, /media/...) to avoid proxy recursion/502.
 */
function normalizeTbccMediaUrlForImport(url) {
  if (!url || typeof url !== "string") return url;
  try {
    const u = new URL(url);
    const h = (u.hostname || "").toLowerCase();
    if (h !== "localhost" && h !== "127.0.0.1") return url;
    const path = u.pathname || "";
    const m = path.match(/\/api\/(media\/\d+\/(?:thumbnail|file))(?:\/|$)/i);
    if (m) {
      u.port = "8000";
      u.pathname = "/" + m[1];
      return u.toString();
    }
    if (path.includes("/media/") && (path.includes("/thumbnail") || path.includes("/file"))) {
      u.port = "8000";
      return u.toString();
    }
  } catch (_) {}
  return url;
}

/** Sidebar is extension-origin; some CDNs require browser-session fetch to avoid hotlink/CORS failures. */
function hostNeedsGalleryThumbProxy(url) {
  try {
    const h = (new URL(url).hostname || "").toLowerCase();
    return (
      h.includes("fetlife") ||
      h === "onlyfans.com" ||
      h.endsWith(".onlyfans.com") ||
      h === "erome.com" ||
      h.endsWith(".erome.com") ||
      h.includes("bunkr") ||
      h.includes("bunkrr") ||
      h.endsWith("scdn.st") ||
      h.endsWith(".scdn.st")
    );
  } catch (_) {
    return false;
  }
}

function thumbReferrerPolicyForUrl(url) {
  try {
    const h = (new URL(url).hostname || "").toLowerCase();
    if (h.includes("fetlife") || h === "onlyfans.com" || h.endsWith(".onlyfans.com")) {
      return "strict-origin-when-cross-origin";
    }
  } catch (_) {}
  return "no-referrer";
}

/**
 * Hosts where a direct <img src> fetch from the sidebar origin is guaranteed
 * to fail (CORS, Cloudflare bot check, missing referrer, signed-URL trickery,
 * or net::ERR_INSUFFICIENT_RESOURCES once parallel load exceeds Chrome's
 * per-renderer socket budget). For these we go session-fetch *only* — if the
 * background proxy can't satisfy, we leave the <img> empty so the
 * placeholder takes over instead of triggering another doomed fetch.
 */
function thumbProxyIsHardRequirement(url) {
  try {
    const h = (new URL(url).hostname || "").toLowerCase();
    return (
      h === "onlyfans.com" ||
      h.endsWith(".onlyfans.com") ||
      h.includes("bunkr") ||
      h.includes("bunkrr") ||
      h.endsWith(".scdn.st") ||
      h.endsWith("scdn.st")
    );
  } catch (_) {
    return false;
  }
}

function loadThumbViaSession(url, imgEl) {
  if (!url || !imgEl) return;
  void (async () => {
    try {
      const resp = await new Promise((resolve) => {
        try {
          chrome.runtime.sendMessage({ action: "tbcc-proxy-thumb", url }, (r) => {
            if (chrome.runtime.lastError) resolve(null);
            else resolve(r);
          });
        } catch (_) {
          resolve(null);
        }
      });
      if (resp && resp.ok && resp.dataUrl) {
        imgEl.src = resp.dataUrl;
        imgEl.removeAttribute("referrerpolicy");
        return;
      }
    } catch (_) {}
    /**
     * For hosts where direct fetch is hopeless, do NOT fall back to a raw
     * <img src> — that would just queue another net::ERR_INSUFFICIENT_RESOURCES
     * request and make the tile flicker. Mark it failed; the placeholder path
     * will draw a stub.
     */
    if (thumbProxyIsHardRequirement(url)) {
      try {
        noteThumbLoadResult(url, false);
        imgEl.dispatchEvent(new Event("error"));
      } catch (_) {}
      return;
    }
    imgEl.referrerPolicy = thumbReferrerPolicyForUrl(url);
    imgEl.src = url;
  })();
}

const STORAGE_COLLECTED = "tbcc_collected";
const STORAGE_SETTINGS = "tbcc_gallery_settings";
const STORAGE_SELECTION = "tbccSelectionUrls";
const STORAGE_UI_STATE = "tbcc_gallery_ui_state";
/** Comma-free list of tag display names to merge onto media after pool Send */
const STORAGE_SEND_TAGS = "tbccGallerySendTags";
const STORAGE_AUTO_TAG_ON_EXPORT = "tbccAutoTagOnExport";
/** Per-URL manual crop, blur regions, text overlays (gallery session). */
const STORAGE_IMAGE_EDITS = "tbcc_gallery_image_edits";
/** TBCC Lite: max items per send batch (Pro = unlimited). */
const TBCC_LITE_BATCH_CAP = 20;

let imageList = [];
let selectedUrls = new Set();
/** For folded video groups: group key → chosen URL (best default if unset). */
const videoGroupPick = new Map();
/** Index in getDisplayRows() for shift+click range selection anchor */
let lastSelectionAnchorIndex = 0;
/** After ctrl+drag marquee or ctrl+click-from-marquee path, suppress duplicate click */
let suppressNextGridClick = false;
let activeTab = "current";
let currentTabId = null;
let settings = {
  format: "original",
  autoRefresh: true,
  cropBottomEnabled: false,
  cropBottomPercent: 8,
  cropInsetMode: "all",
  /** Capture: include resource-timing images on non–OnlyFans pages (more URLs). */
  resourceTimingAllImages: false,
  /** Delay before running capture (ms) so lazy images can load; 0 = off. */
  captureLazyDelayMs: 0,
  /** Fold multiple MP4 URLs that look like the same asset (different resolutions) into one tile. */
  foldVideoVariants: true,
  /** If enabled, clear previous selections each time the panel opens. */
  clearSelectionOnOpen: false,
  /**
   * When true (default), ↻ / R also reloads pools, channels, forum topics, and embedded iframes
   * (Collected / Tools / Options) before rescanning — same work as closing and reopening the side panel.
   * When false, ↻ only runs a tab rescan (legacy behavior).
   */
  refreshHard: true,
  /**
   * When false (default), stored selections for URLs that don't match the current tab page (different SPA route /
   * different origin) are NOT synthesized back into the grid on refresh — fixes "orphan tiles from previous page".
   * When true, previous behavior: every URL in stored selection is re-added even if the current page doesn't show it.
   */
  preserveOrphanSelections: false,
  /** Log per-tile render/load/error events to the console (use for flicker diagnostics; costs CPU when on). */
  debugTileRender: false,
  /** Phase 2: in-panel sub-tab history for in-tab navigation. */
  subtabEnabled: true,
  subtabCap: 3,
  subtabAutoCapture: true,
  /** Phase 3: grid sort / details view. */
  gridSortMode: "default",
  gridViewMode: "grid",
  /** Completion notifications (toast + optional system notification). */
  notifyUseSystem: true,
  notifyOnZipComplete: true,
  notifyOnSendTbccComplete: true,
  notifyOnSendSavedComplete: true,
  notifyOnSendChannelComplete: true,
};
let tbccLightboxVideoObjectUrl = "";
/** Tracks which item the lightbox is currently showing so wheel/arrow steps can compute next/prev. */
let currentLightboxItem = null;
/** Throttle wheel-driven navigation: trackpads spam wheel events 60+/s. */
let _tbccLightboxWheelLastMs = 0;
const TBCC_LIGHTBOX_WHEEL_MIN_MS = 160;
/** Avoid retry-loop flicker for URLs that repeatedly fail thumbnail load in current panel session. */
const thumbLoadFailUntilMs = new Map();
const THUMB_FAIL_COOLDOWN_MS = 30000;

function shouldSkipThumbUrl(url) {
  if (!url) return false;
  const until = thumbLoadFailUntilMs.get(url);
  return Number.isFinite(until) && until > Date.now();
}

function noteThumbLoadResult(url, ok) {
  if (!url) return;
  if (ok) {
    thumbLoadFailUntilMs.delete(url);
    return;
  }
  thumbLoadFailUntilMs.set(url, Date.now() + THUMB_FAIL_COOLDOWN_MS);
}

const tabCurrentBtn = document.getElementById("tabCurrent");
const tabGroupBtn = document.getElementById("tabGroup");
const tabAllBtn = document.getElementById("tabAll");
const btnGalleryPopOut = document.getElementById("btnGalleryPopOut");
const btnGalleryDock = document.getElementById("btnGalleryDock");
const galleryDockBanner = document.getElementById("galleryDockBanner");
const btnRefresh = document.getElementById("btnRefresh");
const btnCrawlTab = document.getElementById("btnCrawlTab");
const crawlerTabUrl = document.getElementById("crawlerTabUrl");
const crawlerStatus = document.getElementById("crawlerStatus");
const btnFilterToggle = document.getElementById("btnFilterToggle");
const filterOverlay = document.getElementById("filterOverlay");
const btnFilterReset = document.getElementById("btnFilterReset");
const btnFilterDone = document.getElementById("btnFilterDone");
const filterType = document.getElementById("filterType");
const filterMinW = document.getElementById("filterMinW");
const filterMinH = document.getElementById("filterMinH");
const filterUrl = document.getElementById("filterUrl");
const filterHideUiClutter = document.getElementById("filterHideUiClutter");
const selectAllCb = document.getElementById("selectAll");
const selectionChip = document.getElementById("selectionChip");
const btnGalleryHelp = document.getElementById("btnGalleryHelp");
const btnOpenCaptureSettings = document.getElementById("btnOpenCaptureSettings");
const galleryActionBar = document.getElementById("galleryActionBar");
const btnTelegramSheetOpen = document.getElementById("btnTelegramSheetOpen");
const btnTelegramSheetDone = document.getElementById("btnTelegramSheetDone");
const telegramSheet = document.getElementById("telegramSheet");
const telegramSheetBackdrop = document.getElementById("telegramSheetBackdrop");
const cropPopover = document.getElementById("cropPopover");
const btnCropOverflow = document.getElementById("btnCropOverflow");
const btnCropDone = document.getElementById("btnCropDone");
const btnAddFilesOverflow = document.getElementById("btnAddFilesOverflow");
const toastContainer = document.getElementById("toastContainer");
const poolSelect = document.getElementById("poolSelectSheet");
const forumPostEnabled = document.getElementById("forumPostEnabled");
const autoTagOnExport = document.getElementById("autoTagOnExport");
const postDestMode = document.getElementById("postDestMode");
const sendSilent = document.getElementById("sendSilent");
const sendSilentRow = document.getElementById("sendSilentRow");
const STORAGE_SEND_SILENT = "tbccSendSilent";
const forumChannelSelect = document.getElementById("forumChannelSelect");
const forumTopicSelect = document.getElementById("forumTopicSelect");
const forumTopicRow = document.getElementById("forumTopicRow");
const forumAlbumCaption = document.getElementById("forumAlbumCaption");
const btnAutoCap = document.getElementById("btnAutoCap");
const btnAlwaysIncludeToggle = document.getElementById("btnAlwaysIncludeToggle");
const alwaysIncludePopover = document.getElementById("alwaysIncludePopover");
const alwaysIncludeCustomLabel = document.getElementById("alwaysIncludeCustomLabel");
const alwaysIncludeCustomUrl = document.getElementById("alwaysIncludeCustomUrl");
const btnAlwaysIncludeCustomAdd = document.getElementById("btnAlwaysIncludeCustomAdd");
const btnCaptionLibraryOpen = document.getElementById("btnCaptionLibraryOpen");
const captionLibraryModal = document.getElementById("captionLibraryModal");
const captionLibraryBackdrop = document.getElementById("captionLibraryBackdrop");
const captionLibraryClose = document.getElementById("captionLibraryClose");
const captionLibTitle = document.getElementById("captionLibTitle");
const captionLibBody = document.getElementById("captionLibBody");
const btnCaptionLibSave = document.getElementById("btnCaptionLibSave");
const captionLibList = document.getElementById("captionLibList");
const autoTagOnExportLabel = document.getElementById("autoTagOnExportLabel");
const btnForumTopicsRefresh = document.getElementById("btnForumTopicsRefresh");
const telegramPostBody = document.getElementById("telegramPostBody");
const btnSend = document.getElementById("btnSend");
const btnDownload = document.getElementById("btnDownload");
const btnDownloadZip = document.getElementById("btnDownloadZip");
const btnCopyJd = document.getElementById("btnCopyJd");
const fileInput = document.getElementById("fileInput");
const loadingEl = document.getElementById("loading");
const gridEl = document.getElementById("grid");
const galleryDropZone = document.getElementById("galleryDropZone");
const importQueueEl = document.getElementById("importQueue");
const tbccLightbox = document.getElementById("tbccLightbox");
const tbccLightboxImg = document.getElementById("tbccLightboxImg");
const tbccLightboxVideo = document.getElementById("tbccLightboxVideo");
const tbccLightboxVideoErr = document.getElementById("tbccLightboxVideoErr");
const tbccLightboxClose = document.getElementById("tbccLightboxClose");
const progressEl = document.getElementById("progress");
const progressTitle = document.getElementById("progressTitle");
const progressFill = document.getElementById("progressFill");
const progressStatus = document.getElementById("progressStatus");
const progressError = document.getElementById("progressError");
const btnToggleOverlay = document.getElementById("btnToggleOverlay");
const btnSelectAllOnPage = document.getElementById("btnSelectAllOnPage");
const cropBottomEnabled = document.getElementById("cropBottomEnabled");
const cropBottomPercent = document.getElementById("cropBottomPercent");
const cropInsetMode = document.getElementById("cropInsetMode");
const cropToolMode = document.getElementById("cropToolMode");
const cropTextInput = document.getElementById("cropTextInput");
const cropTextFont = document.getElementById("cropTextFont");
const cropTextColor = document.getElementById("cropTextColor");
const cropTextToolRow = document.getElementById("cropTextToolRow");
const btnCropClearImage = document.getElementById("btnCropClearImage");
const btnCropClearSelected = document.getElementById("btnCropClearSelected");
const cropStudioThumbs = document.getElementById("cropStudioThumbs");
const cropStudioEmptyHint = document.getElementById("cropStudioEmptyHint");
const cropPreviewShell = document.getElementById("cropPreviewShell");
const cropPreviewFrame = document.getElementById("cropPreviewFrame");
const cropPreviewImg = document.getElementById("cropPreviewImg");
const cropOverlayCanvas = document.getElementById("cropOverlayCanvas");
const galleryScanStrip = document.getElementById("galleryScanStrip");
const galleryScanFill = document.getElementById("galleryScanFill");
const galleryScanLabel = document.getElementById("galleryScanLabel");
const btnToggleFoldVariants = document.getElementById("btnToggleFoldVariants");
const btnSelectToggle = document.getElementById("btnSelectToggle");
const btnSelectAnchorToggle = document.getElementById("btnSelectAnchorToggle");
const tagChipRow = document.getElementById("tagChipRow");
const tagCatalogComboboxMount = document.getElementById("tagCatalogComboboxMount");
let tagCatalogCombobox = null;
const btnTagSuggest = document.getElementById("btnTagSuggest");
const btnTagsCatalogReload = document.getElementById("btnTagsCatalogReload");
const tagNewName = document.getElementById("tagNewName");
const tagNewSlug = document.getElementById("tagNewSlug");
const tagNewCategory = document.getElementById("tagNewCategory");
const btnSavedUrlInboxOpen = document.getElementById("btnSavedUrlInboxOpen");
const btnSavedUrlInboxDone = document.getElementById("btnSavedUrlInboxDone");
const savedUrlInboxSheet = document.getElementById("savedUrlInboxSheet");
const savedUrlInboxBackdrop = document.getElementById("savedUrlInboxBackdrop");
const savedUrlInboxList = document.getElementById("savedUrlInboxList");
const savedUrlInboxStatus = document.getElementById("savedUrlInboxStatus");
const savedUrlInboxDefaultDest = document.getElementById("savedUrlInboxDefaultDest");
const savedUrlInboxDefaultPoolWrap = document.getElementById("savedUrlInboxDefaultPoolWrap");
const savedUrlInboxDefaultPool = document.getElementById("savedUrlInboxDefaultPool");
const savedUrlInboxManualUrl = document.getElementById("savedUrlInboxManualUrl");
const STORAGE_INBOX_DEFAULT_DEST = "tbccInboxDefaultDestV1";
const btnSavedUrlInboxAdd = document.getElementById("btnSavedUrlInboxAdd");
const btnSavedUrlInboxImportSel = document.getElementById("btnSavedUrlInboxImportSel");
const btnSavedUrlInboxRemoveSel = document.getElementById("btnSavedUrlInboxRemoveSel");
const btnSavedUrlInboxClearImported = document.getElementById("btnSavedUrlInboxClearImported");
let cachedPoolsForInbox = [];
const btnTagCreate = document.getElementById("btnTagCreate");
const btnTagsClear = document.getElementById("btnTagsClear");
const tagCatalogFilterNote = document.getElementById("tagCatalogFilterNote");
const btnDestMacroPool = document.getElementById("btnDestMacroPool");
const btnDestMacroSaved = document.getElementById("btnDestMacroSaved");
const btnDestMacroForum = document.getElementById("btnDestMacroForum");
const btnDestMacroChannel = document.getElementById("btnDestMacroChannel");
const telegramDestSummary = document.getElementById("telegramDestSummary");
const telegramDestHint = document.getElementById("telegramDestHint");
const telegramDestDetailShell = document.getElementById("telegramDestDetailShell");
const telegramPoolSection = document.getElementById("telegramPoolSection");
const importSheetCaptionSection = document.getElementById("importSheetCaptionSection");
const importSheetCaptionOutcome = document.getElementById("importSheetCaptionOutcome");
const importSheetTagsOutcome = document.getElementById("importSheetTagsOutcome");
const viewMainEl = document.getElementById("view-main");
const galleryCtxMenu = document.getElementById("tbccGalleryCtxMenu");
const tbccSubtabBar = document.getElementById("tbccSubtabBar");
const tbccSubtabStrip = document.getElementById("tbccSubtabStrip");
const tbccMemHud = document.getElementById("tbccMemHud");
const tbccSubtabSettingsBtn = document.getElementById("tbccSubtabSettings");
const tbccSubtabPopover = document.getElementById("tbccSubtabPopover");
const tbccSubtabEnabledCb = document.getElementById("tbccSubtabEnabled");
const tbccSubtabCapInput = document.getElementById("tbccSubtabCap");
const tbccSubtabAutoCaptureCb = document.getElementById("tbccSubtabAutoCapture");
const tbccSubtabClearAllBtn = document.getElementById("tbccSubtabClearAll");
const tbccSubtabPopoverDoneBtn = document.getElementById("tbccSubtabPopoverDone");
const tbccSortSelect = document.getElementById("tbccSortSelect");
const tbccSortDetailsToggle = document.getElementById("tbccSortDetailsToggle");

let tagCatalog = [];
/** Ordered display names for tags applied on next pool Send */
let gallerySendTags = [];
/** url → { manualCrop?, blurs?, texts? } for export pipeline */
let imageEdits = {};
let cropStudioActiveUrl = null;
let cropStudioDrag = null;

const STORAGE_ALWAYS_INCLUDE_CAPTION = "tbccAlwaysIncludeCaptionV1";
const STORAGE_CAPTION_BASE = "tbccCaptionBase";

/** Last /channels JSON for invite_link resolution (always-include block). */
let tbccChannelsCacheLast = [];

let alwaysIncludeCaptionState = { channelIds: [], custom: [] };

/** Caption body without appended TBCC link block — synced into `forumAlbumCaption` by `syncCaptionFieldFromBase`. */
let captionBaseText = "";

function telegramPublicLinkFromIdentifier(identRaw) {
  const ident = String(identRaw || "").trim();
  if (/^https?:\/\/t\.me\//i.test(ident)) return ident.split("#")[0].split("?")[0];
  const m = ident.match(/^@([a-zA-Z_][a-zA-Z0-9_]{3,})/);
  if (m) return `https://t.me/${m[1]}`;
  return "";
}

/** Invite URL from TBCC channel row, or public t.me/@username when invite_link absent. */
function captionLinkForChannelRow(c) {
  const inv = String((c && c.invite_link) || "").trim();
  if (inv) return inv;
  return telegramPublicLinkFromIdentifier(c && c.identifier);
}

function normalizeAlwaysIncludeState(raw) {
  const ch = Array.isArray(raw?.channelIds)
    ? [...new Set(raw.channelIds.map((n) => parseInt(n, 10)).filter((x) => Number.isFinite(x)))]
    : [];
  const custom = Array.isArray(raw?.custom)
    ? raw.custom
        .filter((c) => c && String(c.url || "").trim())
        .map((c) => ({
          id: String(c.id || "").trim() || "c_" + Date.now(),
          label: String(c.label || "").trim() || "Link",
          url: String(c.url || "").trim(),
          enabled: c.enabled !== false,
        }))
    : [];
  return { channelIds: ch, custom };
}

async function loadAlwaysIncludeCaptionState() {
  try {
    const x = await chrome.storage.local.get(STORAGE_ALWAYS_INCLUDE_CAPTION);
    alwaysIncludeCaptionState = normalizeAlwaysIncludeState(x[STORAGE_ALWAYS_INCLUDE_CAPTION]);
  } catch (_) {}
}

async function saveAlwaysIncludeCaptionState(next) {
  alwaysIncludeCaptionState = normalizeAlwaysIncludeState(next);
  await chrome.storage.local.set({ [STORAGE_ALWAYS_INCLUDE_CAPTION]: alwaysIncludeCaptionState });
  syncCaptionFieldFromBase();
  await persistCaptionSlicesToStorage();
}

function buildAlwaysIncludeLinksLines() {
  const lines = [];
  const want = new Set(alwaysIncludeCaptionState.channelIds || []);
  for (const c of tbccChannelsCacheLast || []) {
    const id = parseInt(c.id, 10);
    if (!Number.isFinite(id) || !want.has(id)) continue;
    const link = captionLinkForChannelRow(c);
    if (link) lines.push(link);
  }
  for (const c of alwaysIncludeCaptionState.custom || []) {
    if (c.enabled === false) continue;
    const link = String(c.url || "").trim();
    if (link) lines.push(link);
  }
  return lines;
}

function stripTrailingLinkBlock(full, lines) {
  let t = String(full || "").replace(/\r\n/g, "\n");
  if (!lines || !lines.length) return t.trimEnd();
  const block = lines.join("\n");
  const suffix = "\n\n" + block;
  if (t.endsWith(suffix)) return t.slice(0, -suffix.length).replace(/\s+$/u, "");
  const suffix2 = "\n" + block;
  if (t.endsWith(suffix2)) return t.slice(0, -suffix2.length).replace(/\s+$/u, "");
  if (t.trimEnd() === block) return "";
  return t.trimEnd();
}

function syncCaptionFieldFromBase() {
  if (!forumAlbumCaption) return;
  const lines = buildAlwaysIncludeLinksLines();
  const block = lines.length ? lines.join("\n") : "";
  const base = String(captionBaseText || "").replace(/\r\n/g, "\n").trimEnd();
  forumAlbumCaption.value = block ? (base ? `${base}\n\n${block}` : block) : base;
}

async function persistCaptionSlicesToStorage() {
  try {
    await chrome.storage.local.set({
      [STORAGE_CAPTION_BASE]: captionBaseText,
      tbccForumAlbumCaption: forumAlbumCaption ? forumAlbumCaption.value || "" : "",
    });
  } catch (_) {}
}

function renderAlwaysIncludeCustomList() {
  const host = document.getElementById("alwaysIncludeCustomList");
  if (!host) return;
  host.innerHTML = "";
  const items = alwaysIncludeCaptionState.custom || [];
  if (!items.length) {
    host.innerHTML = '<p class="tbcc-always-include__empty">No custom links yet.</p>';
    return;
  }
  for (const c of items) {
    const row = document.createElement("label");
    row.className = "tbcc-always-include__row";
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.checked = c.enabled !== false;
    cb.addEventListener("change", async () => {
      const nextCustom = (alwaysIncludeCaptionState.custom || []).map((x) =>
        x.id === c.id ? { ...x, enabled: cb.checked } : x
      );
      await saveAlwaysIncludeCaptionState({ ...alwaysIncludeCaptionState, custom: nextCustom });
    });
    const lab = document.createElement("span");
    const u = String(c.url || "");
    lab.textContent = `${c.label} — ${u.length > 44 ? u.slice(0, 41) + "…" : u}`;
    const del = document.createElement("button");
    del.type = "button";
    del.textContent = "×";
    del.className = "tbcc-always-include__del";
    del.title = "Remove";
    del.addEventListener("click", async (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      const nextCustom = (alwaysIncludeCaptionState.custom || []).filter((x) => x.id !== c.id);
      await saveAlwaysIncludeCaptionState({ ...alwaysIncludeCaptionState, custom: nextCustom });
      renderAlwaysIncludeCustomList();
    });
    row.appendChild(cb);
    row.appendChild(lab);
    row.appendChild(del);
    host.appendChild(row);
  }
}

function renderAlwaysIncludeChannelList() {
  const host = document.getElementById("alwaysIncludeChannelList");
  if (!host) return;
  host.innerHTML = "";
  const selected = new Set(alwaysIncludeCaptionState.channelIds || []);
  const rows = tbccChannelsCacheLast || [];
  if (!rows.length) {
    host.innerHTML =
      '<p class="tbcc-always-include__empty">No TBCC channels loaded — check API / dashboard Channels.</p>';
    return;
  }
  for (const c of rows) {
    const id = parseInt(c.id, 10);
    if (!Number.isFinite(id)) continue;
    const link = captionLinkForChannelRow(c);
    const row = document.createElement("label");
    row.className = "tbcc-always-include__row" + (link ? "" : " tbcc-always-include__row--disabled");
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.checked = selected.has(id);
    cb.disabled = !link;
    cb.addEventListener("change", async () => {
      const set = new Set(alwaysIncludeCaptionState.channelIds || []);
      if (cb.checked) set.add(id);
      else set.delete(id);
      await saveAlwaysIncludeCaptionState({ ...alwaysIncludeCaptionState, channelIds: [...set] });
    });
    const name = document.createElement("span");
    name.textContent = (c.name || c.identifier || "#" + id).slice(0, 44);
    row.appendChild(cb);
    row.appendChild(name);
    if (!link) {
      const meta = document.createElement("span");
      meta.className = "tbcc-always-include__row-meta";
      meta.textContent = "no link";
      row.appendChild(meta);
    }
    host.appendChild(row);
  }
}

async function fetchCaptionSnippetsFromApi() {
  try {
    const r = await fetch(API_BASE + "/caption-snippets/", { cache: "no-store" });
    if (!r.ok) return [];
    const j = await r.json();
    return Array.isArray(j) ? j : [];
  } catch (_) {
    return [];
  }
}

function insertSnippetTextIntoCaption(body) {
  if (!forumAlbumCaption) return;
  const t = String(body || "").trim();
  if (!t) return;
  const cur = captionBaseText.trim();
  captionBaseText = cur ? `${cur}\n\n${t}` : t;
  syncCaptionFieldFromBase();
  void persistCaptionSlicesToStorage();
}

function setCaptionLibraryModalOpen(open) {
  if (!captionLibraryModal) return;
  captionLibraryModal.hidden = !open;
}

async function renderCaptionLibraryModalList() {
  if (!captionLibList) return;
  const items = await fetchCaptionSnippetsFromApi();
  captionLibList.innerHTML = "";
  if (!items.length) {
    const li = document.createElement("li");
    li.className = "tbcc-caption-lib-modal__empty";
    li.style.cssText = "font-size:11px;color:var(--tbcc-text-muted,#94a3b8);list-style:none;";
    li.textContent = "No saved captions yet.";
    captionLibList.appendChild(li);
    return;
  }
  for (const s of items) {
    const li = document.createElement("li");
    li.className = "tbcc-caption-lib-modal__item";
    const head = document.createElement("div");
    head.className = "tbcc-caption-lib-modal__item-head";
    const tit = document.createElement("div");
    tit.className = "tbcc-caption-lib-modal__item-title";
    tit.textContent =
      (s.title && String(s.title).trim()) ||
      String(s.body || "")
        .split(/\r?\n/)
        .find((l) => l.trim())
        ?.slice(0, 48) ||
      "Untitled";
    const actions = document.createElement("div");
    actions.className = "tbcc-caption-lib-modal__item-actions";
    const ins = document.createElement("button");
    ins.type = "button";
    ins.className = "tbcc-btn-secondary tbcc-btn--sheet-compact";
    ins.textContent = "Insert";
    ins.title = "Append to destination caption";
    ins.addEventListener("click", () => {
      insertSnippetTextIntoCaption(s.body);
      setCaptionLibraryModalOpen(false);
      showToast("Caption inserted.", "success");
    });
    const del = document.createElement("button");
    del.type = "button";
    del.className = "tbcc-btn-secondary tbcc-btn--sheet-compact";
    del.textContent = "Delete";
    del.addEventListener("click", async () => {
      try {
        const r = await fetch(API_BASE + "/caption-snippets/" + s.id, { method: "DELETE" });
        if (!r.ok) throw new Error(await r.text());
        await renderCaptionLibraryModalList();
      } catch (e) {
        showToast("Could not delete: " + (e.message || String(e)), "error");
      }
    });
    const cpy = document.createElement("button");
    cpy.type = "button";
    cpy.className = "tbcc-btn-secondary tbcc-btn--sheet-compact";
    cpy.textContent = "Copy";
    cpy.title = "Copy caption to clipboard";
    cpy.addEventListener("click", () => {
      const clip = globalThis.TbccClipboard;
      if (clip && clip.copyText) {
        void clip.copyText(String(s.body || ""), { anchor: cpy });
      } else {
        void navigator.clipboard.writeText(String(s.body || "")).then(() => showToast("Copied!", "success"));
      }
    });
    actions.appendChild(ins);
    actions.appendChild(cpy);
    actions.appendChild(del);
    head.appendChild(tit);
    head.appendChild(actions);
    const pre = document.createElement("pre");
    pre.textContent = String(s.body || "");
    li.appendChild(head);
    li.appendChild(pre);
    captionLibList.appendChild(li);
  }
}

function persistCaptionClear() {
  captionBaseText = "";
  if (!forumAlbumCaption) return;
  forumAlbumCaption.value = "";
  void chrome.storage.local.set({
    [STORAGE_CAPTION_BASE]: "",
    tbccForumAlbumCaption: "",
  });
}

/** Same caption box as Telegram post — also attached to each album sent to Saved Messages. */
function getAlbumCaptionForSend() {
  return forumAlbumCaption && forumAlbumCaption.value ? String(forumAlbumCaption.value).trim() : "";
}
function appendCaptionToSavedForm(form, captionOverride) {
  const c =
    captionOverride != null && String(captionOverride).trim() !== ""
      ? String(captionOverride).trim()
      : getAlbumCaptionForSend();
  if (c) form.append("caption", c);
}

/** Saved send: never block uploads longer than this on tag API (local tags apply immediately). */
const SAVED_CAPTION_API_MS = 6000;
const SEND_ENRICH_CACHE_TTL_MS = 120000;
const _sendEnrichCache = new Map();

function sendEnrichCacheKey(items) {
  const pages = [
    ...new Set(
      (items || [])
        .map((it) => {
          const u = (it && (it.tbccSourcePageUrl || it.pageUrl)) || "";
          return u && /^https?:\/\//i.test(u) ? normalizeSourcePageKey(u) : "";
        })
        .filter(Boolean)
    ),
  ].sort();
  const manual = (gallerySendTags || []).map((t) => String(t).toLowerCase()).sort().join(",");
  return pages.join("|") + "::" + manual;
}

/** Instant local tags (semantic page URLs + manual chips) — no tab inject, no backend. */
function applyLocalSavedCaptionTags(tagSet, lookup, selectedItems) {
  const items = Array.isArray(selectedItems) ? selectedItems : [];
  for (const t of gallerySendTags) addAutoTagToSet(tagSet, lookup, t, false);
  const sourcePages = [
    ...new Set(
      items
        .map((it) => (it && (it.tbccSourcePageUrl || it.pageUrl)) || "")
        .filter((u) => u && /^https?:\/\//i.test(String(u)))
    ),
  ];
  for (const sp of sourcePages) extractAutoTagsFromUrl(sp, lookup, tagSet);
  for (const it of items) {
    const src = (it && (it.tbccSourcePageUrl || it.pageUrl)) || "";
    collectPerItemAutoTags(it, lookup, src).forEach((t) => tagSet.add(t));
  }
}

/** Lustpress + NSFW + page heuristics via TBCC backend (no Media row). */
async function fetchApiSendTagEnrich(selectedItems, opts) {
  const options = opts && typeof opts === "object" ? opts : {};
  const fast = options.fast !== false;
  const timeoutMs = Math.min(Math.max(Number(options.timeoutMs) || (fast ? SAVED_CAPTION_API_MS : 12000), 1500), 45000);
  const items = (Array.isArray(selectedItems) ? selectedItems : []).map((it) => ({
    source_page_url: (it && (it.tbccSourcePageUrl || it.pageUrl)) || "",
    media_url: (it && it.url) || "",
    page_host: (it && it.pageHost) || "",
  }));
  const cacheKey = sendEnrichCacheKey(items);
  const cached = _sendEnrichCache.get(cacheKey);
  if (cached && Date.now() - cached.at < SEND_ENRICH_CACHE_TTL_MS) return cached.data;

  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), timeoutMs);
  try {
    const r = await fetch(`${API_BASE}/tags/enrich-send`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        items,
        manual_tags: gallerySendTags || [],
        fast,
        max_lustpress_pages: fast ? 1 : 2,
        max_nsfw_samples: fast ? 1 : 2,
      }),
      signal: ac.signal,
    });
    const text = await r.text();
    let j = {};
    try {
      j = text ? JSON.parse(text) : {};
    } catch (_) {}
    if (!r.ok) return null;
    const data = j && j.ok !== false ? j : null;
    if (data) _sendEnrichCache.set(cacheKey, { at: Date.now(), data });
    return data;
  } catch (_) {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

/** Run lustpress/NSFW enrich on imported library rows (sync fallback when Celery is idle). */
async function syncEnrichImportedMedia(mediaIds) {
  const ids = [...new Set((mediaIds || []).filter((x) => Number.isFinite(x)))];
  if (!ids.length) return null;
  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), 120000);
  try {
    const r = await fetch(`${API_BASE}/tags/bulk/enrich-sync`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ids, max: Math.min(ids.length, 16) }),
      signal: ac.signal,
    });
    const text = await r.text();
    let j = {};
    try {
      j = text ? JSON.parse(text) : {};
    } catch (_) {}
    if (!r.ok) throw new Error((j && (j.detail || j.error)) || text || `HTTP ${r.status}`);
    return j;
  } finally {
    clearTimeout(timer);
  }
}

/** Saved Messages: caption field + optional hashtags (TBCC tags are not stored without pool import). */
async function getCaptionForSavedMessagesSend(selectedItems) {
  let cap = getAlbumCaptionForSend();
  const useAutoTag = !!(autoTagOnExport && autoTagOnExport.checked);
  const hasManualTags = gallerySendTags.length > 0;
  if (!useAutoTag && !hasManualTags) return cap;

  const lookup = buildTagCatalogLookup();
  const tagSet = new Set();
  const items = Array.isArray(selectedItems) ? selectedItems : [];
  applyLocalSavedCaptionTags(tagSet, lookup, items);

  if (useAutoTag || hasManualTags) {
    try {
      const api = await fetchApiSendTagEnrich(items, { fast: true, timeoutMs: SAVED_CAPTION_API_MS });
      if (api && Array.isArray(api.labels)) {
        for (const lbl of api.labels) {
          if (shouldHideTraceSourceInCaption(lbl)) continue;
          addAutoTagToSet(tagSet, lookup, lbl, false);
        }
      }
      if (!cap.trim() && api && api.caption_line) cap = String(api.caption_line).trim();
    } catch (_) {}
  }

  for (const perf of extractCamPerformerFromTitle(cap)) {
    addAutoTagToSet(tagSet, lookup, perf, false);
  }

  const tagLine = buildHashtagLineFromTagsAndHints([...tagSet], []);
  if (tagLine) {
    cap = cap ? `${cap.trim()}\n\n${tagLine}` : tagLine;
  }
  if (cap.length > TBCC_TELEGRAM_CAPTION_MAX) cap = cap.slice(0, TBCC_TELEGRAM_CAPTION_MAX);
  return cap;
}

/** Title-only from gallery tab (3s cap) — avoids double full caption passes. */
async function fetchPageTitleQuick() {
  const tid = await resolveTargetTabId();
  if (tid == null) return "";
  try {
    const exec = await Promise.race([
      chrome.scripting.executeScript({
        target: { tabId: tid },
        func: () => {
          try {
            return (document.title || "").trim().slice(0, 200);
          } catch (_) {
            return "";
          }
        },
      }),
      new Promise((_, reject) => setTimeout(() => reject(new Error("timeout")), 3000)),
    ]);
    const title = exec && exec[0] && exec[0].result;
    return title && String(title).trim() ? String(title).trim() : "";
  } catch (_) {
    return "";
  }
}

/** Saved send: caption + hashtags; optionally pre-fill title when empty (one pass). */
async function ensureSavedMessagesCaption(selectedItems) {
  if (!getAlbumCaptionForSend().trim()) {
    const wantTitle =
      !!(autoTagOnExport && autoTagOnExport.checked) || gallerySendTags.length > 0;
    if (wantTitle) {
      try {
        const title = await fetchPageTitleQuick();
        if (title && forumAlbumCaption) forumAlbumCaption.value = title;
      } catch (_) {}
    }
  }
  return getCaptionForSavedMessagesSend(selectedItems);
}

const MAX_COLS = 5;
const CELL_MIN_PX = 80;
const MARQUEE_MOVE_THRESHOLD_PX = 5;

function rectsIntersect(a, b) {
  return !(a.right < b.left || a.left > b.right || a.bottom < b.top || a.top > b.bottom);
}

/** Pointer interaction on a grid cell (checkbox or cell body). */
function handleCellSelectionPointer(e, row, displayIdx) {
  if (suppressNextGridClick) {
    e.preventDefault();
    e.stopPropagation();
    return;
  }
  const rows = getDisplayRows();
  const url = getUrlForDisplayRow(row);
  if (e.shiftKey) {
    e.preventDefault();
    e.stopPropagation();
    const a = Math.min(lastSelectionAnchorIndex, displayIdx);
    const b = Math.max(lastSelectionAnchorIndex, displayIdx);
    selectedUrls.clear();
    for (let i = a; i <= b; i++) {
      if (rows[i]) selectedUrls.add(getUrlForDisplayRow(rows[i]));
    }
    renderGrid();
    updateCountAndSendPersist();
    return;
  }
  if (e.ctrlKey || e.metaKey) {
    e.preventDefault();
    e.stopPropagation();
    if (selectedUrls.has(url)) selectedUrls.delete(url);
    else selectedUrls.add(url);
    renderGrid();
    updateCountAndSendPersist();
    return;
  }
  lastSelectionAnchorIndex = displayIdx;
  if (selectedUrls.has(url)) selectedUrls.delete(url);
  else selectedUrls.add(url);
  renderGrid();
  updateCountAndSendPersist();
}

let marqueeDrag = null;

function finishMarqueeDragListeners() {
  document.removeEventListener("mousemove", onMarqueeMove);
  document.removeEventListener("mouseup", onMarqueeUp);
  document.body.classList.remove("tbcc-marquee-dragging");
}

function onMarqueeMove(e) {
  if (!marqueeDrag) return;
  const dx = e.clientX - marqueeDrag.sx;
  const dy = e.clientY - marqueeDrag.sy;
  if (!marqueeDrag.moved && (Math.abs(dx) > MARQUEE_MOVE_THRESHOLD_PX || Math.abs(dy) > MARQUEE_MOVE_THRESHOLD_PX)) {
    marqueeDrag.moved = true;
    marqueeDrag.box = document.createElement("div");
    marqueeDrag.box.className = "tbcc-marquee";
    document.body.appendChild(marqueeDrag.box);
    document.body.classList.add("tbcc-marquee-dragging");
  }
  if (marqueeDrag.moved && marqueeDrag.box) {
    const x1 = Math.min(marqueeDrag.sx, e.clientX);
    const y1 = Math.min(marqueeDrag.sy, e.clientY);
    const w = Math.abs(e.clientX - marqueeDrag.sx);
    const h = Math.abs(e.clientY - marqueeDrag.sy);
    Object.assign(marqueeDrag.box.style, {
      position: "fixed",
      left: x1 + "px",
      top: y1 + "px",
      width: w + "px",
      height: h + "px",
      zIndex: "10000",
      pointerEvents: "none",
    });
  }
  e.preventDefault();
}

function onMarqueeUp(e) {
  if (!marqueeDrag) return;
  finishMarqueeDragListeners();
  const md = marqueeDrag;
  marqueeDrag = null;

  suppressNextGridClick = true;
  setTimeout(() => {
    suppressNextGridClick = false;
  }, 0);

  if (md.moved && md.box) {
    const r = md.box.getBoundingClientRect();
    md.box.remove();
    const rows = getDisplayRows();
    gridEl.querySelectorAll(".cell").forEach((cell) => {
      const cr = cell.getBoundingClientRect();
      if (!rectsIntersect(cr, r)) return;
      const i = parseInt(cell.dataset.cellIndex, 10);
      if (!Number.isNaN(i) && rows[i]) selectedUrls.add(getUrlForDisplayRow(rows[i]));
    });
    renderGrid();
    updateCountAndSendPersist();
    return;
  }

  if (md.box) md.box.remove();
  const cell = md.startTarget && md.startTarget.closest && md.startTarget.closest(".cell");
  if (cell && gridEl.contains(cell)) {
    const i = parseInt(cell.dataset.cellIndex, 10);
    const rows = getDisplayRows();
    const row = rows[i];
    if (row) {
      const u = getUrlForDisplayRow(row);
      if (selectedUrls.has(u)) selectedUrls.delete(u);
      else selectedUrls.add(u);
      renderGrid();
      updateCountAndSendPersist();
    }
  }
}

function onGridCtrlMarqueeMouseDown(e) {
  if (!gridEl || !gridEl.contains(e.target)) return;
  if (!e.ctrlKey && !e.metaKey) return;
  if (e.button !== 0) return;
  marqueeDrag = {
    sx: e.clientX,
    sy: e.clientY,
    moved: false,
    box: null,
    startTarget: e.target,
  };
  e.preventDefault();
  document.addEventListener("mousemove", onMarqueeMove, { passive: false });
  document.addEventListener("mouseup", onMarqueeUp, { passive: false });
}

function setsEqual(a, b) {
  if (a.size !== b.size) return false;
  for (const x of a) if (!b.has(x)) return false;
  return true;
}

/** Selection count that matches the current grid (filtered list only). */
function selectedCountInFilteredList() {
  const rows = getDisplayRows();
  let n = 0;
  for (const row of rows) {
    const u = getUrlForDisplayRow(row);
    if (selectedUrls.has(u)) n++;
  }
  return n;
}

function guessMediaType(url) {
  const u = (url || "").toLowerCase();
  if (/\.(mp4|webm|mov|m4v|mkv)(\?|$)/i.test(u)) return "video";
  return "image";
}

function mergeUrlsIntoImageListFromSelection() {
  if (activeTab !== "current") return;
  const have = new Set(imageList.map((i) => i.url));
  for (const u of selectedUrls) {
    if (!u || have.has(u)) continue;
    if (!/^https?:\/\//i.test(u)) continue;
    const mt = guessMediaType(u);
    imageList.push({
      url: u,
      mediaType: mt,
      tagName: mt === "video" ? "video" : "img",
      tabId: currentTabId,
    });
    have.add(u);
  }
}

function tbccSendUrlScore(url) {
  const u = String(url || "");
  if (!u) return -999;
  if (u.startsWith("data:image/")) return 300 + Math.min(u.length / 8000, 80);
  if (u.startsWith("blob:")) return 200;
  if (typeof tbccIsPerchanceBadHttpUrl === "function" && tbccIsPerchanceBadHttpUrl(u)) return -500;
  return 60;
}

function selectionRefForItem(it) {
  if (!it) return "";
  const u = it.url || "";
  if (u.startsWith("data:") || u.startsWith("blob:")) {
    if (it.tbccPerchanceSlot) return "slot:" + it.tbccPerchanceSlot;
    if (it.tbccCaptureSeq != null) return "seq:" + String(it.tbccCaptureSeq);
    return "hash:" + String(u.length) + ":" + u.slice(12, 48);
  }
  return u.length > 900 ? u.slice(0, 900) : u;
}

function resolveSelectionRefToUrl(ref) {
  if (!ref || typeof ref !== "string") return "";
  if (ref.startsWith("slot:")) {
    const slot = ref.slice(5);
    let best = "";
    let bestSc = -999;
    for (const row of imageList) {
      if (row.tbccPerchanceSlot !== slot) continue;
      const sc = tbccSendUrlScore(row.url);
      if (sc > bestSc) {
        bestSc = sc;
        best = row.url || "";
      }
    }
    return best;
  }
  if (ref.startsWith("seq:")) {
    const seq = parseInt(ref.slice(4), 10);
    if (!Number.isFinite(seq)) return "";
    const row = imageList.find((i) => i.tbccCaptureSeq === seq);
    return row && row.url ? row.url : "";
  }
  if (ref.startsWith("hash:")) return "";
  return ref;
}

function expandSelectionRefs(refs) {
  const out = new Set();
  for (const r of refs || []) {
    const u = resolveSelectionRefToUrl(r);
    if (u) out.add(u);
    else if (r && typeof r === "string" && !/^(slot:|seq:|hash:)/.test(r)) out.add(r);
  }
  return out;
}

function pickBestSendItem(items) {
  if (!items || !items.length) return null;
  let best = items[0];
  let bestSc = tbccSendUrlScore(best.url);
  for (let i = 1; i < items.length; i++) {
    const sc = tbccSendUrlScore(items[i].url);
    if (sc > bestSc) {
      bestSc = sc;
      best = items[i];
    }
  }
  if (typeof tbccIsPerchanceBadHttpUrl === "function" && tbccIsPerchanceBadHttpUrl(best.url)) {
    const alt = items.find((x) => x.url && tbccSendUrlScore(x.url) > 0);
    return alt || null;
  }
  if (bestSc < 0) return null;
  return best;
}

/** One tile per Perchance slot; prefer data:/blob: over CDN thumbs / embed URLs. */
function prepareSelectedForSavedSend(rawSelected) {
  const bySlot = new Map();
  const loose = [];
  for (const it of rawSelected) {
    const slot = it && it.tbccPerchanceSlot;
    if (slot) {
      if (!bySlot.has(slot)) bySlot.set(slot, []);
      bySlot.get(slot).push(it);
    } else loose.push(it);
  }
  const out = [];
  for (const group of bySlot.values()) {
    const best = pickBestSendItem(group);
    if (best) out.push(best);
  }
  for (const it of loose) {
    const best = pickBestSendItem([it]);
    if (best) out.push(best);
  }
  return out;
}

function serializeGalleryItemForStorage(i) {
  const u = String((i && i.url) || "");
  const heavy = u.startsWith("data:") || u.startsWith("blob:");
  const out = {
    mediaType: i.mediaType,
    tagName: i.tagName,
    thumbUrl: i.thumbUrl,
    posterUrl: i.posterUrl,
    width: i.width,
    height: i.height,
    naturalWidth: i.naturalWidth,
    naturalHeight: i.naturalHeight,
    durationSec: i.durationSec,
    tbccCaptureSource: i.tbccCaptureSource,
    tbccSourcePageUrl: i.tbccSourcePageUrl,
    tbccPerchanceSlot: i.tbccPerchanceSlot,
    tbccCaptureSeq: i.tbccCaptureSeq,
    tbccCaptureFrameId: i.tbccCaptureFrameId,
    tabId: i.tabId,
    url: heavy ? "" : u.length > 900 ? u.slice(0, 900) : u,
    tbccSelRef: heavy ? selectionRefForItem(i) : "",
  };
  if (i.tbccStreamManifest) out.tbccHasStream = true;
  return out;
}

async function tbccStoragePruneHeavy() {
  try {
    await chrome.storage.local.remove(["tbccSelectionMeta", STORAGE_COLLECTED, STORAGE_IMAGE_EDITS]);
    const keys = await chrome.storage.local.get(null);
    const toRemove = [];
    for (const k of Object.keys(keys || {})) {
      if (k.startsWith("tbcc_gallery_subtabs:")) toRemove.push(k);
    }
    if (toRemove.length) await chrome.storage.local.remove(toRemove);
  } catch (_) {}
}

async function tbccStorageLocalSet(obj) {
  try {
    await chrome.storage.local.set(obj);
    return true;
  } catch (e) {
    const msg = String(e && e.message ? e.message : e);
    if (!/quota/i.test(msg)) throw e;
    await tbccStoragePruneHeavy();
    try {
      await chrome.storage.local.set(obj);
      return true;
    } catch (e2) {
      const sel = obj && obj[STORAGE_SELECTION];
      if (obj && (Array.isArray(sel) || obj.tbccSelectionGen != null)) {
        const refs = Array.isArray(sel) ? sel : [];
        for (const cap of [80, 40, 20, 0]) {
          try {
            const slim = { [STORAGE_SELECTION]: cap > 0 ? refs.slice(-cap) : [] };
            if (obj.tbccSelectionGen != null) slim.tbccSelectionGen = obj.tbccSelectionGen;
            await chrome.storage.local.set(slim);
            return true;
          } catch (_) {}
        }
      }
      return false;
    }
  }
}

function persistSelection() {
  const refs = [];
  for (const u of selectedUrls) {
    const it = imageList.find((row) => row.url === u);
    const ref = it ? selectionRefForItem(it) : u.startsWith("data:") || u.startsWith("blob:") ? "" : u;
    if (ref) refs.push(ref);
  }
  const gen = ++gallerySelectionPersistGen;
  return tbccStorageLocalSet({
    [STORAGE_SELECTION]: refs.slice(-SELECTION_PERSIST_MAX_REFS),
    tbccSelectionGen: gen,
  });
}

/** Clear in-memory selection and storage so the next capture does not restore old URLs (e.g. after Refresh on a new tab). */
async function clearSelectionForNewCapture() {
  selectedUrls.clear();
  lastSelectionAnchorIndex = 0;
  await persistSelection();
}

function getSendTagsCsv() {
  return gallerySendTags.join(", ");
}

function renderTagChipRow() {
  if (!tagChipRow) return;
  tagChipRow.innerHTML = "";
  gallerySendTags.forEach((t) => {
    const span = document.createElement("span");
    span.className = "tag-chip";
    span.appendChild(document.createTextNode(t));
    const rm = document.createElement("button");
    rm.type = "button";
    rm.setAttribute("aria-label", "Remove tag");
    rm.textContent = "×";
    rm.addEventListener("click", () => removeGallerySendTag(t));
    span.appendChild(rm);
    tagChipRow.appendChild(span);
  });
}

function persistGallerySendTags() {
  void tbccStorageLocalSet({ [STORAGE_SEND_TAGS]: gallerySendTags });
  renderTagChipRow();
}

function addGallerySendTag(raw) {
  const s = String(raw || "").trim();
  if (!s || s.length > 128) return;
  const low = s.toLowerCase();
  if (gallerySendTags.some((x) => x.toLowerCase() === low)) return;
  if (gallerySendTags.length >= 32) return;
  gallerySendTags.push(s);
  persistGallerySendTags();
}

function removeGallerySendTag(name) {
  const low = String(name).toLowerCase();
  gallerySendTags = gallerySendTags.filter((x) => x.toLowerCase() !== low);
  persistGallerySendTags();
}

function clearGallerySendTags() {
  gallerySendTags = [];
  persistGallerySendTags();
  if (tagCatalogCombobox) tagCatalogCombobox.clear();
  if (tagNewName) tagNewName.value = "";
  if (tagNewSlug) tagNewSlug.value = "";
  if (tagNewCategory) tagNewCategory.value = "";
}

function looksLikeBareDomain(s) {
  return /^[\w.-]+\.[a-z]{2,}$/i.test(String(s).trim()) && !String(s).includes(" ");
}

/** Junk slug/name rows (hex IDs, etc.) — hide from catalog picker; DB rows unchanged. */
function isJunkCatalogTagRow(t) {
  const name = (t.name != null && String(t.name).trim()) || "";
  const slug = (t.slug != null && String(t.slug).trim()) || "";
  const primary = name || slug;
  return isJunkAutoTagToken(primary);
}

const AUTO_TAG_SHORT_OK = new Set([
  "jpg",
  "jpeg",
  "png",
  "gif",
  "webp",
  "mp4",
  "webm",
  "mov",
  "m4v",
  "mkv",
  "nsfw",
  "sfw",
  "hd",
  "4k",
  "uhd",
  "pic",
  "vid",
  "of",
  "user",
  "data",
]);

/**
 * Reject CDN path segments, content hashes, and numeric IDs — not crypto wallets.
 * (40-char hex is usually SHA-1; BTC addresses are base58/bech32, not long lowercase hex strings.)
 */
function isJunkAutoTagToken(raw) {
  if (typeof TbccAutoTagUtils !== "undefined" && TbccAutoTagUtils.isJunkAutoTagToken) {
    return TbccAutoTagUtils.isJunkAutoTagToken(raw);
  }
  const primary = String(raw || "")
    .trim()
    .replace(/^#+/u, "");
  if (!primary || primary.length < 2) return true;
  const low = primary.toLowerCase();
  if (AUTO_TAG_SHORT_OK.has(low)) return false;
  const compact = primary.replace(/[\s_\-]/g, "");
  if (/^0x[0-9a-f]+$/i.test(compact)) return true;
  if (compact.length <= 2 && /^[0-9a-f]+$/i.test(compact)) return true;
  if (compact.length >= 8 && /^[0-9a-f]+$/i.test(compact)) return true;
  const alnum = primary.replace(/[^a-z0-9]/gi, "");
  if (!alnum) return true;
  if (/^[0-9]{10,}$/.test(alnum)) return true;
  if (alnum.length >= 12) {
    const hexish = (alnum.match(/[0-9a-f]/gi) || []).length;
    if (hexish / alnum.length >= 0.82) return true;
    if (!/[aeiou]/i.test(alnum)) return true;
  }
  if (alnum.length >= 8 && alnum.length <= 11 && !/[aeiou]/i.test(alnum) && hexishRatio(alnum) >= 0.65) return true;
  return false;
}

function filterReadablePageHints(hints) {
  if (typeof TbccAutoTagUtils !== "undefined" && TbccAutoTagUtils.filterReadableTagHints) {
    return TbccAutoTagUtils.filterReadableTagHints(hints);
  }
  return (hints || []).filter((h) => h && !isJunkAutoTagToken(h));
}

function hexishRatio(alnum) {
  if (!alnum) return 0;
  return (alnum.match(/[0-9a-f]/gi) || []).length / alnum.length;
}

const TRACE_SOURCE_NSFW_HINT_SUBSTR = [
  "erome",
  "onlyfans",
  "motherless",
  "coomer",
  "kemono",
  "redgifs",
  "motherlessmedia",
  "fapello",
  "bunkr",
  "bunkrr",
  "spankbang",
  "bestcam",
  "cumcams",
  "chaturbate",
  "stripchat",
  "bongacams",
  "cam4",
  "livejasmin",
  "myfreecams",
  "camsoda",
  "camwhores",
  "recurbate",
];

/** Model/creator token from cam-site titles (e.g. "Newest Michellesexxy Cam videos"). */
function extractCamPerformerFromTitle(title) {
  const out = [];
  const seen = new Set();
  const re =
    /(?:newest|latest|best|free|private|premium|hot|top)?\s*([A-Za-z][A-Za-z0-9_.-]{3,28})\s+cam\b/gi;
  let m;
  while ((m = re.exec(String(title || "")))) {
    const name = (m[1] || "").trim();
    if (!name || isJunkAutoTagToken(name)) continue;
    const k = name.toLowerCase();
    if (seen.has(k)) continue;
    seen.add(k);
    out.push(name);
  }
  return out;
}

/** Omit scrape-site style tokens from Auto cap hashtags (metadata stays in TBCC elsewhere). */
function shouldHideTraceSourceInCaption(tagOrHint) {
  const raw = String(tagOrHint || "")
    .trim()
    .toLowerCase()
    .replace(/^#+/u, "")
    .replace(/\s+/gu, "");
  if (!raw) return false;
  if (looksLikeBareDomain(tagOrHint)) return true;
  for (const s of TRACE_SOURCE_NSFW_HINT_SUBSTR) {
    if (raw.includes(s)) return true;
  }
  return false;
}

function catalogRowsForPicker(rows) {
  const full = Array.isArray(rows) ? rows : [];
  const kept = full.filter((t) => !isJunkCatalogTagRow(t));
  return { kept, filteredCount: full.length - kept.length };
}

async function loadTagCatalog() {
  if (!(await probeTbccApiReachable(false))) return;
  const urls = [`${API_BASE}/tags/`, `${API_BASE}/tags`];
  let lastErr = null;
  for (const url of urls) {
    try {
      const r = await fetch(url, { cache: "no-store" });
      if (!r.ok) throw new Error(await r.text());
      tagCatalog = await r.json();
      const { kept, filteredCount } = catalogRowsForPicker(tagCatalog);
      if (tagCatalogFilterNote) {
        tagCatalogFilterNote.hidden = filteredCount === 0;
        tagCatalogFilterNote.textContent =
          filteredCount > 0 ? filteredCount + " ID-like catalog entr" + (filteredCount === 1 ? "y" : "ies") + " hidden." : "";
      }
      if (tagCatalogCombobox) tagCatalogCombobox.setItems(kept);
      return;
    } catch (e) {
      lastErr = e;
      if (!isTbccConnectionError(e)) break;
    }
  }
  if (lastErr && isTbccConnectionError(lastErr)) {
    invalidateTbccApiReachableCache();
    setTbccApiOfflineBanner(true);
  } else if (lastErr) {
    console.warn("TBCC loadTagCatalog:", lastErr);
  }
}

async function createTagOnServer() {
  const name = tagNewName && tagNewName.value.trim();
  const slug = tagNewSlug && tagNewSlug.value.trim();
  const category = tagNewCategory && tagNewCategory.value.trim();
  if (!name) {
    showToast("Enter a tag name.", "info");
    return;
  }
  try {
    const r = await fetch(`${API_BASE}/tags`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name,
        ...(slug ? { slug } : {}),
        ...(category ? { category } : {}),
      }),
    });
    const text = await r.text();
    let data = {};
    try {
      data = text ? JSON.parse(text) : {};
    } catch (_) {}
    if (!r.ok) throw new Error(typeof data.detail === "string" ? data.detail : text || r.statusText);
    addGallerySendTag(data.name || name);
    tagNewName.value = "";
    if (tagNewSlug) tagNewSlug.value = "";
    if (tagNewCategory) tagNewCategory.value = "";
    await loadTagCatalog();
    showToast("Tag created and added to Send list.", "success");
  } catch (e) {
    showToast(e.message || String(e), "error");
  }
}

function onCatalogTagPicked(label, row) {
  const v = String(label || "").trim();
  if (!v) return;
  addGallerySendTag(row ? (row.name && String(row.name).trim()) || row.slug || v : v);
}

async function suggestTagsFromPage() {
  const tid = await resolveTargetTabId();
  if (!tid) {
    showToast("Open a normal https page tab to scan.", "info");
    return;
  }
  let hints = [];
  try {
    await chrome.scripting.executeScript({ target: { tabId: tid }, files: ["media-url-guards.js", "auto-tag-utils.js", "capture.js"] });
    const exec = await chrome.scripting.executeScript({
      target: { tabId: tid },
      func: () => (typeof window.__tbccCollectTagHints === "function" ? window.__tbccCollectTagHints() : []),
    });
    hints = (exec && exec[0] && exec[0].result) || [];
  } catch (e) {
    showToast("Cannot scan page: " + (e.message || String(e)), "error");
    return;
  }
  if (!hints.length) {
    showToast("No hints found (title, hashtags, keywords).", "info");
    return;
  }
  const lookup = new Map();
  for (const t of tagCatalog) {
    const nm = t.name != null ? String(t.name) : "";
    if (nm) lookup.set(nm.toLowerCase(), nm);
    if (t.slug != null && String(t.slug)) lookup.set(String(t.slug).toLowerCase(), nm || String(t.slug));
  }
  let n = 0;
  for (const h of hints) {
    if (gallerySendTags.length >= 32) break;
    const k = h.toLowerCase();
    if (looksLikeBareDomain(h) && !lookup.has(k)) continue;
    const canonical = lookup.get(k);
    const before = gallerySendTags.length;
    addGallerySendTag(canonical || h);
    if (gallerySendTags.length > before) n++;
  }
  showToast(n ? `Added ${n} suggestion(s). Remove chips you don't need.` : "No new tags (already listed or skipped).", n ? "success" : "info");
}

const AUTO_TAG_STOPWORDS = new Set([
  "www",
  "com",
  "net",
  "org",
  "the",
  "and",
  "for",
  "with",
  "from",
  "this",
  "that",
  "photo",
  "image",
  "images",
  "video",
  "videos",
  "media",
  "thumb",
  "thumbs",
  "thumbnail",
  "gallery",
  "post",
  "posts",
  "files",
  "file",
  "profilepage",
  "profile page",
  "large",
  "small",
  "original",
  "cdn",
  "static",
  "content",
]);

function normalizeAutoTagCandidate(raw) {
  if (typeof TbccAutoTagUtils !== "undefined" && TbccAutoTagUtils.normalizeAutoTagCandidate) {
    const fromUtils = TbccAutoTagUtils.normalizeAutoTagCandidate(raw);
    if (!fromUtils) return "";
    const low = fromUtils.toLowerCase();
    if (AUTO_TAG_STOPWORDS.has(low)) return "";
    return fromUtils;
  }
  const s = String(raw || "")
    .trim()
    .replace(/^#+/u, "")
    .replace(/[_\-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  if (!s || s.length < 2 || s.length > 64) return "";
  const low = s.toLowerCase();
  if (AUTO_TAG_STOPWORDS.has(low)) return "";
  if (/^\d+$/u.test(s)) return "";
  if (isJunkAutoTagToken(s)) return "";
  return s;
}

function buildTagCatalogLookup() {
  const lookup = new Map();
  for (const t of tagCatalog || []) {
    const name = t && t.name != null ? String(t.name).trim() : "";
    const slug = t && t.slug != null ? String(t.slug).trim() : "";
    if (name) lookup.set(name.toLowerCase(), name);
    if (slug) lookup.set(slug.toLowerCase(), name || slug);
  }
  return lookup;
}

function addAutoTagToSet(set, lookup, raw, skipUnknownDomains) {
  const normalized = normalizeAutoTagCandidate(raw);
  if (!normalized) return;
  const low = normalized.toLowerCase();
  if (skipUnknownDomains && looksLikeBareDomain(normalized) && !lookup.has(low)) return;
  const display = lookup.get(low) || normalized;
  if (isJunkAutoTagToken(display)) return;
  set.add(display);
}

function normTabId(x) {
  const n = Number(x);
  return Number.isFinite(n) ? n : null;
}

async function fetchTagHintsInTab(tabId) {
  const tid = normTabId(tabId);
  if (tid == null) return [];
  try {
    await chrome.scripting.executeScript({ target: { tabId: tid }, files: ["media-url-guards.js", "auto-tag-utils.js", "capture.js"] });
    const exec = await chrome.scripting.executeScript({
      target: { tabId: tid },
      func: () => (typeof window.__tbccCollectTagHints === "function" ? window.__tbccCollectTagHints() : []),
    });
    const hints = (exec && exec[0] && exec[0].result) || [];
    return Array.isArray(hints) ? hints : [];
  } catch (_) {
    return [];
  }
}

/** Semantic page tags only — never scrape CDN/media path hash segments. */
function extractAutoTagsFromUrl(rawUrl, lookup, set) {
  const sem =
    typeof TbccAutoTagUtils !== "undefined" && TbccAutoTagUtils.extractSemanticTagsFromUrl
      ? TbccAutoTagUtils.extractSemanticTagsFromUrl(rawUrl)
      : [];
  for (const t of sem) addAutoTagToSet(set, lookup, t, false);
}

function collectPerItemAutoTags(item, lookup, resolvedSourcePage) {
  const out = new Set();
  const pageFromCapture =
    (item && item.tbccSourcePageUrl && String(item.tbccSourcePageUrl)) ||
    (item && item.pageUrl && String(item.pageUrl)) ||
    (resolvedSourcePage && String(resolvedSourcePage)) ||
    "";
  if (item) {
    addAutoTagToSet(out, lookup, item.pageHost || "", true);
    if (pageFromCapture) extractAutoTagsFromUrl(pageFromCapture, lookup, out);
  } else if (pageFromCapture) {
    extractAutoTagsFromUrl(pageFromCapture, lookup, out);
  }
  return out;
}

async function collectPageHintsByTabId(tabIds) {
  const out = new Map();
  const list = [...new Set((tabIds || []).map(normTabId).filter((x) => x != null))];
  await Promise.all(
    list.map(async (tabId) => {
      out.set(tabId, await fetchTagHintsInTab(tabId));
    })
  );
  return out;
}

function csvForTagSet(tags) {
  return [...tags].map((x) => String(x).trim()).filter(Boolean).join(", ");
}

function normalizeSourcePageKey(url) {
  try {
    const u = new URL(String(url).trim().split("#")[0]);
    const path = (u.pathname || "").replace(/\/+$/, "") || "/";
    return u.origin + path;
  } catch (_) {
    return String(url || "").trim().split("#")[0];
  }
}

async function findTabIdForSourcePageUrl(sourcePageUrl) {
  const clean = String(sourcePageUrl || "").trim().split("#")[0];
  if (!clean || !/^https?:\/\//i.test(clean)) return null;
  let wantHost = "";
  let wantPath = "";
  try {
    const u = new URL(clean);
    wantHost = u.hostname.toLowerCase();
    wantPath = (u.pathname || "").replace(/\/+$/, "") || "/";
  } catch (_) {
    return null;
  }
  const tabs = await chrome.tabs.query({});
  let sameHostId = null;
  let pathMatchId = null;
  for (const t of tabs) {
    if (t.id == null || !t.url || !/^https?:\/\//i.test(t.url)) continue;
    try {
      const u = new URL(String(t.url).split("#")[0]);
      if (u.hostname.toLowerCase() !== wantHost) continue;
      if (sameHostId == null) sameHostId = t.id;
      const p = (u.pathname || "").replace(/\/+$/, "") || "/";
      if (wantPath && (p === wantPath || p.startsWith(wantPath + "/"))) {
        pathMatchId = t.id;
        break;
      }
    } catch (_) {}
  }
  return pathMatchId != null ? pathMatchId : sameHostId;
}

async function collectPageHintsBySourcePageUrls(sourceUrls) {
  const out = new Map();
  const uniq = [...new Set((sourceUrls || []).filter(Boolean))];
  await Promise.all(
    uniq.map(async (sp) => {
      const key = normalizeSourcePageKey(sp);
      if (out.has(key)) return;
      const tabId = await findTabIdForSourcePageUrl(sp);
      out.set(key, tabId == null ? [] : await fetchTagHintsInTab(tabId));
    })
  );
  return out;
}

async function resolveSourcePageUrlForAutoTagRecord(rec) {
  const it = rec && rec.item;
  if (it && it.tbccSourcePageUrl && /^https?:\/\//i.test(String(it.tbccSourcePageUrl))) {
    return String(it.tbccSourcePageUrl).split("#")[0];
  }
  if (it && it.pageUrl && /^https?:\/\//i.test(String(it.pageUrl))) {
    return String(it.pageUrl).split("#")[0];
  }
  const ref = it ? await tbccRefererPageForItem(it) : "";
  if (ref && /^https?:\/\//i.test(ref)) return ref.split("#")[0];
  const tid = normTabId(rec && rec.tabId);
  if (tid != null) {
    try {
      const tab = await chrome.tabs.get(tid);
      if (tab && tab.url && /^https?:\/\//i.test(tab.url)) return String(tab.url).split("#")[0];
    } catch (_) {}
  }
  return "";
}

async function applyAutoTaggingForImportedMedia(importedRecords) {
  const rows = Array.isArray(importedRecords) ? importedRecords : [];
  if (!rows.length) return;
  const lookup = buildTagCatalogLookup();
  const byId = new Map();
  for (const row of rows) {
    if (!row || !Number.isFinite(row.mediaId)) continue;
    byId.set(row.mediaId, row);
  }
  const records = [...byId.values()];
  if (!records.length) return;

  const baseSendTags = new Set();
  for (const t of gallerySendTags || []) {
    addAutoTagToSet(baseSendTags, lookup, t, false);
  }

  const enriched = await Promise.all(
    records.map(async (rec) => ({
      ...rec,
      sourcePage: await resolveSourcePageUrlForAutoTagRecord(rec),
    }))
  );

  const uniqueSources = [...new Set(enriched.map((r) => r.sourcePage).filter(Boolean))];
  const hintsBySourcePage = await collectPageHintsBySourcePageUrls(uniqueSources);
  const tabIdsForFallback = [...new Set(enriched.map((r) => normTabId(r.tabId)).filter((x) => x != null))];
  const pageHintsByTab = await collectPageHintsByTabId(tabIdsForFallback);

  const csvToIds = new Map();
  for (const rec of enriched) {
    const tags = new Set(baseSendTags);
    const srcKey = rec.sourcePage ? normalizeSourcePageKey(rec.sourcePage) : "";
    let pageHints =
      srcKey && hintsBySourcePage.has(srcKey) ? hintsBySourcePage.get(srcKey) : null;
    if (!pageHints || !pageHints.length) {
      const tid = normTabId(rec.tabId);
      pageHints = tid != null ? pageHintsByTab.get(tid) || [] : [];
    }
    filterReadablePageHints(pageHints).forEach((h) => addAutoTagToSet(tags, lookup, h, true));
    if (rec.sourcePage) extractAutoTagsFromUrl(rec.sourcePage, lookup, tags);
    const perItem = collectPerItemAutoTags(rec.item || null, lookup, rec.sourcePage);
    perItem.forEach((t) => tags.add(t));
    const csv = csvForTagSet(tags);
    if (!csv) continue;
    if (!csvToIds.has(csv)) csvToIds.set(csv, []);
    csvToIds.get(csv).push(rec.mediaId);
  }

  for (const [csv, idsRaw] of csvToIds.entries()) {
    const ids = [...new Set((idsRaw || []).filter((x) => Number.isFinite(x)))];
    if (!ids.length) continue;
    const r = await fetch(`${API_BASE}/media/bulk/tags`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ids, tags: csv, tags_merge: true }),
    });
    const text = await r.text();
    let j = {};
    try {
      j = text ? JSON.parse(text) : {};
    } catch (_) {}
    if (!r.ok || j.error) throw new Error(j.error || j.detail || text || `HTTP ${r.status}`);
  }

  const captureGroups = new Map();
  for (const rec of enriched) {
    if (!rec || !Number.isFinite(rec.mediaId)) continue;
    const srcPage = rec.sourcePage ? String(rec.sourcePage).trim() : "";
    let siteHost = "";
    if (srcPage) {
      try {
        siteHost = new URL(srcPage).hostname.replace(/^www\./i, "");
      } catch (_) {}
    }
    if (!siteHost && !srcPage) continue;
    const capKey = `${siteHost}\n${srcPage}`;
    if (!captureGroups.has(capKey)) captureGroups.set(capKey, { site_host: siteHost, source_page: srcPage, ids: [] });
    captureGroups.get(capKey).ids.push(rec.mediaId);
  }
  for (const [, grp] of captureGroups) {
    const ids = [...new Set((grp.ids || []).filter((x) => Number.isFinite(x)))];
    if (!ids.length) continue;
    try {
      const r = await fetch(`${API_BASE}/media/bulk/gallery-capture-meta`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ids,
          site_host: grp.site_host || null,
          source_page: grp.source_page || null,
        }),
      });
      const text = await r.text();
      let j = {};
      try {
        j = text ? JSON.parse(text) : {};
      } catch (_) {}
      if (!r.ok || j.error) console.warn("TBCC gallery-capture-meta:", j.error || text || r.status);
    } catch (e) {
      console.warn("TBCC gallery-capture-meta failed", e);
    }
  }
}

/** Inbox pool import: same heuristic auto-tag as gallery export (URL paths + ref page + open tab hints). */
async function applyAutoTaggingForInboxImportedMedia(inboxRecords) {
  const rows = Array.isArray(inboxRecords) ? inboxRecords : [];
  if (!rows.length) return;
  const lookup = buildTagCatalogLookup();
  const byId = new Map();
  for (const row of rows) {
    if (!row || !Number.isFinite(row.mediaId) || row.autoTag === false) continue;
    byId.set(row.mediaId, row);
  }
  const records = [...byId.values()];
  if (!records.length) return;

  const uniqueSources = [
    ...new Set(records.map((r) => (r.ref && String(r.ref).trim()) || "").filter(Boolean)),
  ];
  const hintsBySourcePage = await collectPageHintsBySourcePageUrls(uniqueSources);

  const csvToIds = new Map();
  const captureGroups = new Map();

  for (const rec of records) {
    const tags = new Set();
    if (rec.tagsCsv) {
      for (const t of String(rec.tagsCsv).split(",")) {
        addAutoTagToSet(tags, lookup, t.trim(), false);
      }
    }
    const refPage = rec.ref ? String(rec.ref).trim() : "";
    const srcKey = refPage ? normalizeSourcePageKey(refPage) : "";
    let pageHints = srcKey && hintsBySourcePage.has(srcKey) ? hintsBySourcePage.get(srcKey) : [];
    if ((!pageHints || !pageHints.length) && refPage) {
      const tabId = await findTabIdForSourcePageUrl(refPage);
      if (tabId != null) pageHints = await fetchTagHintsInTab(tabId);
    }
    filterReadablePageHints(pageHints || []).forEach((h) => addAutoTagToSet(tags, lookup, h, true));
    const pseudoItem = { url: rec.url, pageUrl: refPage || undefined, pageHost: "" };
    if (refPage) {
      try {
        pseudoItem.pageHost = new URL(refPage).hostname.replace(/^www\./i, "");
      } catch (_) {}
    }
    collectPerItemAutoTags(pseudoItem, lookup, refPage || rec.url).forEach((t) => tags.add(t));
    const csv = csvForTagSet(tags);
    if (!csv) continue;
    if (!csvToIds.has(csv)) csvToIds.set(csv, []);
    csvToIds.get(csv).push(rec.mediaId);

    const srcPage = refPage || "";
    let siteHost = pseudoItem.pageHost || "";
    if (!siteHost && srcPage) {
      try {
        siteHost = new URL(srcPage).hostname.replace(/^www\./i, "");
      } catch (_) {}
    }
    if (siteHost || srcPage) {
      const capKey = `${siteHost}\n${srcPage}`;
      if (!captureGroups.has(capKey)) captureGroups.set(capKey, { site_host: siteHost, source_page: srcPage, ids: [] });
      captureGroups.get(capKey).ids.push(rec.mediaId);
    }
  }

  for (const [csv, idsRaw] of csvToIds.entries()) {
    const ids = [...new Set((idsRaw || []).filter((x) => Number.isFinite(x)))];
    if (!ids.length) continue;
    const r = await fetch(`${API_BASE}/media/bulk/tags`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ids, tags: csv, tags_merge: true }),
    });
    const text = await r.text();
    let j = {};
    try {
      j = text ? JSON.parse(text) : {};
    } catch (_) {}
    if (!r.ok || j.error) throw new Error(j.error || j.detail || text || `HTTP ${r.status}`);
  }

  for (const [, grp] of captureGroups) {
    const ids = [...new Set((grp.ids || []).filter((x) => Number.isFinite(x)))];
    if (!ids.length) continue;
    try {
      const r = await fetch(`${API_BASE}/media/bulk/gallery-capture-meta`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ids,
          site_host: grp.site_host || null,
          source_page: grp.source_page || null,
        }),
      });
      const text = await r.text();
      let j = {};
      try {
        j = text ? JSON.parse(text) : {};
      } catch (_) {}
      if (!r.ok || j.error) console.warn("TBCC inbox gallery-capture-meta:", j.error || text || r.status);
    } catch (e) {
      console.warn("TBCC inbox gallery-capture-meta failed", e);
    }
  }
}

const TBCC_TELEGRAM_CAPTION_MAX = 1024;

/** Turn a TBCC tag or hint string into a single Telegram-style #hashtag token. */
function displayTagToHashtag(tag) {
  const raw = String(tag || "")
    .trim()
    .replace(/^#+/u, "");
  if (!raw || isJunkAutoTagToken(raw)) return "";
  const compact = raw.replace(/\s+/gu, "");
  if (!compact) return "";
  const capped = compact.length > 42 ? compact.slice(0, 42) : compact;
  return "#" + capped;
}

/** Chosen send tags first, then extra page hints (deduped; domain / scrape-source tokens skipped). */
function buildHashtagLineFromTagsAndHints(sendTags, pageHints) {
  const seen = new Set();
  const out = [];
  for (const t of sendTags || []) {
    if (looksLikeBareDomain(t)) continue;
    if (shouldHideTraceSourceInCaption(t)) continue;
    const h = displayTagToHashtag(t);
    if (!h) continue;
    const k = h.toLowerCase();
    if (seen.has(k)) continue;
    seen.add(k);
    out.push(h);
  }
  const maxExtra = 14;
  let n = 0;
  for (const hint of pageHints || []) {
    if (n >= maxExtra) break;
    if (isJunkAutoTagToken(hint)) continue;
    if (looksLikeBareDomain(hint)) continue;
    if (shouldHideTraceSourceInCaption(hint)) continue;
    const h = displayTagToHashtag(hint);
    if (!h || h.length < 3) continue;
    const k = h.toLowerCase();
    if (seen.has(k)) continue;
    seen.add(k);
    out.push(h);
    n++;
  }
  return out.join(" ");
}

function descriptionOverlapsTitle(title, description) {
  if (!title || !description) return false;
  const a = title.slice(0, 40).toLowerCase();
  const b = description.slice(0, 40).toLowerCase();
  if (a.includes(b) || b.includes(a)) return true;
  return false;
}

/** Optional: fill caption from page title/meta + hashtags from Tags on Send and page hints. */
async function autoCapFromPage() {
  const tid = await resolveTargetTabId();
  if (!tid) {
    showToast("Open a normal https page tab.", "info");
    return;
  }
  let bundle = { title: "", description: "" };
  let hints = [];
  try {
    await chrome.scripting.executeScript({ target: { tabId: tid }, files: ["media-url-guards.js", "auto-tag-utils.js", "capture.js"] });
    const exec = await chrome.scripting.executeScript({
      target: { tabId: tid },
      func: () => ({
        bundle:
          typeof window.__tbccGetCaptionBundle === "function"
            ? window.__tbccGetCaptionBundle()
            : { title: "", description: "" },
        hints: typeof window.__tbccCollectTagHints === "function" ? window.__tbccCollectTagHints() : [],
      }),
    });
    const res = exec && exec[0] && exec[0].result;
    if (res) {
      bundle = res.bundle || bundle;
      hints = filterReadablePageHints(Array.isArray(res.hints) ? res.hints : []);
    }
  } catch (e) {
    showToast("Cannot read page: " + (e.message || String(e)), "error");
    return;
  }
  const lines = [];
  if (bundle.title) lines.push(String(bundle.title).trim());
  const desc = String(bundle.description || "").trim();
  if (desc && !descriptionOverlapsTitle(bundle.title, desc)) lines.push(desc);
  const tagLine = buildHashtagLineFromTagsAndHints(gallerySendTags, hints);
  if (tagLine) {
    if (lines.length) lines.push("");
    lines.push(tagLine);
  }
  let cap = lines.join("\n").trim();
  if (!cap) {
    showToast("No title, description, or tags to build caption.", "info");
    return;
  }
  if (cap.length > TBCC_TELEGRAM_CAPTION_MAX) cap = cap.slice(0, TBCC_TELEGRAM_CAPTION_MAX);
  captionBaseText = cap;
  syncCaptionFieldFromBase();
  await persistCaptionSlicesToStorage();
  showToast("Caption filled — edit if needed.", "success");
}

async function applySendTagsToImportedMedia(mediaIds) {
  const csv = getSendTagsCsv().trim();
  if (!csv || !mediaIds || !mediaIds.length) return;
  const ids = [...new Set(mediaIds.map((x) => parseInt(x, 10)).filter((x) => Number.isFinite(x)))];
  if (!ids.length) return;
  const r = await fetch(`${API_BASE}/media/bulk/tags`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ids, tags: csv, tags_merge: true }),
  });
  const text = await r.text();
  let j = {};
  try {
    j = text ? JSON.parse(text) : {};
  } catch (_) {}
  if (!r.ok || j.error) throw new Error(j.error || j.detail || text || `HTTP ${r.status}`);
}

async function syncOverlayToggleButton() {
  if (!btnToggleOverlay) return;
  const { tbccOverlayMode } = await chrome.storage.local.get("tbccOverlayMode");
  const on = !!tbccOverlayMode;
  btnToggleOverlay.classList.toggle("active", on);
  btnToggleOverlay.setAttribute("aria-pressed", on ? "true" : "false");
}

async function ensureOverlayScriptReady(tabId) {
  try {
    await chrome.tabs.sendMessage(tabId, { action: "tbcc-overlay-refresh" });
    return true;
  } catch (_) {}
  try {
    await chrome.scripting.executeScript({ target: { tabId, allFrames: true }, files: ["page-overlay.js"] });
    await chrome.tabs.sendMessage(tabId, { action: "tbcc-overlay-refresh" });
    return true;
  } catch (_) {
    return false;
  }
}

async function notifyOverlayRefresh() {
  const tid = await resolveTargetTabId();
  if (!tid) return;
  await ensureOverlayScriptReady(tid);
}

/** Parse a positive integer from a filter input; empty / invalid → NaN (no filter on that axis). */
function parsePositiveIntInput(el) {
  if (!el) return NaN;
  const n = parseInt(String(el.value || "").trim(), 10);
  return Number.isFinite(n) && n > 0 ? n : NaN;
}

function itemDimsForFilter(i) {
  const w = i.naturalWidth || i.width || 0;
  const h = i.naturalHeight || i.height || 0;
  return { w, h };
}

/** SVG / data-URL vectors and small square-ish UI assets (favicons, sprites) often clutter the grid. */
const TBCC_FILTER_UI_CLUTTER_MAX_PX = 128;

function urlLooksLikeSvgAsset(url) {
  const s = String(url || "").trim();
  const low = s.toLowerCase();
  if (low.startsWith("data:image/svg+xml")) return true;
  const path = s.split(/[?#]/)[0].toLowerCase();
  return /\.svg(\?|$)/i.test(path) || path.endsWith(".svg");
}

function itemMatchesUiClutterHeuristic(i) {
  if (urlLooksLikeSvgAsset(i.url)) return true;
  const { w, h } = itemDimsForFilter(i);
  if (w > 0 && h > 0 && w <= TBCC_FILTER_UI_CLUTTER_MAX_PX && h <= TBCC_FILTER_UI_CLUTTER_MAX_PX) return true;
  return false;
}

let _filterDimRerenderTimer = null;
/** Min W/H filters depend on lazy dimensions; debounce full rebuilds so clicks are not lost to DOM churn. */
function cancelPendingFilterDimRerender() {
  if (_filterDimRerenderTimer) {
    clearTimeout(_filterDimRerenderTimer);
    _filterDimRerenderTimer = null;
  }
}
function scheduleFilterRerenderFromLazyDims() {
  const minW = parsePositiveIntInput(filterMinW);
  const minH = parsePositiveIntInput(filterMinH);
  const hideUi = filterHideUiClutter && filterHideUiClutter.checked;
  if (Number.isNaN(minW) && Number.isNaN(minH) && !hideUi) return;
  cancelPendingFilterDimRerender();
  _filterDimRerenderTimer = setTimeout(() => {
    _filterDimRerenderTimer = null;
    renderGrid();
  }, 400);
}

function getFilteredList() {
  let list = imageList.slice();
  const typeVal = (filterType && filterType.value) || "";
  if (typeVal) {
    if (typeVal === "video") list = list.filter((i) => ((i.mediaType || (i.tagName || "").toLowerCase()) === "video"));
    else if (typeVal === "image") list = list.filter((i) => ((i.mediaType || (i.tagName || "").toLowerCase()) !== "video"));
    else list = list.filter((i) => (i.url || "").toLowerCase().includes(typeVal));
  }
  const minW = parsePositiveIntInput(filterMinW);
  const minH = parsePositiveIntInput(filterMinH);
  if (!Number.isNaN(minW)) {
    list = list.filter((i) => {
      const w = itemDimsForFilter(i).w;
      if (w <= 0) return true;
      return w >= minW;
    });
  }
  if (!Number.isNaN(minH)) {
    list = list.filter((i) => {
      const h = itemDimsForFilter(i).h;
      if (h <= 0) return true;
      return h >= minH;
    });
  }
  const urlSub = filterUrl && filterUrl.value.trim();
  if (urlSub) list = list.filter((i) => (i.url || "").includes(urlSub));
  if (filterHideUiClutter && filterHideUiClutter.checked) {
    list = list.filter((i) => !itemMatchesUiClutterHeuristic(i));
  }
  return applyGridSort(list);
}

/**
 * Sort mode is persisted in settings.gridSortMode. Kept stable (the user's capture order is the default).
 * Unknown dimensions sort last within their bucket so incomplete metadata doesn't fight with complete tiles.
 */
function applyGridSort(list) {
  const mode = String((settings && settings.gridSortMode) || "default");
  if (!list || mode === "default" || mode === "") return list;
  const fileName = (u) => String((u || "").split(/[?#]/)[0].split("/").pop() || "");
  const area = (i) => {
    const w = Number(i.naturalWidth || i.width || 0);
    const h = Number(i.naturalHeight || i.height || 0);
    return w > 0 && h > 0 ? w * h : 0;
  };
  const dur = (i) => (Number.isFinite(i.durationSec) && i.durationSec > 0 ? i.durationSec : 0);
  const size = (i) => (i && i.file && Number.isFinite(i.file.size) ? i.file.size : 0);
  const typeRank = (i) => (itemLooksLikeVideo(i) ? 1 : 0);
  const sorted = list.slice();
  const cmp = (a, b) => {
    switch (mode) {
      case "resDesc": {
        const d = area(b) - area(a);
        if (d !== 0) return d;
        return (area(b) === 0 ? 1 : 0) - (area(a) === 0 ? 1 : 0);
      }
      case "resAsc": {
        const aA = area(a);
        const aB = area(b);
        if (aA === 0 && aB !== 0) return 1;
        if (aB === 0 && aA !== 0) return -1;
        return aA - aB;
      }
      case "durDesc":
        return dur(b) - dur(a);
      case "durAsc": {
        const dA = dur(a);
        const dB = dur(b);
        if (dA === 0 && dB !== 0) return 1;
        if (dB === 0 && dA !== 0) return -1;
        return dA - dB;
      }
      case "type": {
        const t = typeRank(a) - typeRank(b);
        if (t !== 0) return t;
        return area(b) - area(a);
      }
      case "sizeDesc":
        return size(b) - size(a);
      case "nameAsc":
        return fileName(a.url).localeCompare(fileName(b.url));
      case "nameDesc":
        return fileName(b.url).localeCompare(fileName(a.url));
      default:
        return 0;
    }
  };
  sorted.sort(cmp);
  return sorted;
}

/**
 * Extra capture passes so late resource-timing / webRequest URLs appear without manual refresh.
 * Shorter gaps feel much snappier; stagnant passes still exit early when two runs add nothing.
 */
const SCAN_MERGE_DELAYS_MS = [0, 400, 1000];
/** OnlyFans chat/gallery: lazy carousels + CDN bursts — extra merge passes pick up late resource timing / webRequest. */
const SCAN_MERGE_DELAYS_MS_ONLYFANS = [0, 400, 1000, 2000, 3200, 4800];
/** Perchance generators paint new tiles over many seconds — keep merging while the scan strip runs. */
const SCAN_MERGE_DELAYS_MS_PERCHANCE = [0, 400, 900, 1600, 2600, 4000, 6000, 8500, 11500];
const PERCHANCE_POLL_MS = 1800;
const PERCHANCE_POLL_MAX_PASSES = 45;
let perchancePollTimer = null;
/** Bumped on gallery-initiated selection writes so onChanged does not clear in-memory selection. */
let gallerySelectionPersistGen = 0;

function stopPerchancePoll() {
  if (perchancePollTimer) {
    clearInterval(perchancePollTimer);
    perchancePollTimer = null;
  }
}

function startPerchancePoll(tabId) {
  stopPerchancePoll();
  if (!Number.isFinite(tabId)) return;
  let passes = 0;
  perchancePollTimer = setInterval(async () => {
    passes++;
    if (passes > PERCHANCE_POLL_MAX_PASSES || activeTab !== "current" || currentTabId !== tabId) {
      stopPerchancePoll();
      return;
    }
    try {
      const merged = await appendMergedCapture(tabId);
      if (merged > 0) {
        await persistSelection();
        renderGrid();
        await notifyOverlayRefresh();
      }
    } catch (_) {}
  }, PERCHANCE_POLL_MS);
}

function setScanStripVisible(visible) {
  if (!galleryScanStrip) return;
  if (visible) {
    galleryScanStrip.hidden = false;
    galleryScanStrip.setAttribute("aria-hidden", "false");
  } else {
    galleryScanStrip.hidden = true;
    galleryScanStrip.setAttribute("aria-hidden", "true");
    if (galleryScanFill) galleryScanFill.style.width = "0%";
  }
}

function setScanProgress(fraction, label) {
  if (galleryScanFill) {
    const pct = Math.max(0, Math.min(100, Math.round((fraction || 0) * 100)));
    galleryScanFill.style.width = pct + "%";
  }
  if (galleryScanLabel && label) galleryScanLabel.textContent = label;
}

function itemLooksLikeVideo(item) {
  if (!item) return false;
  const ulow = String(item.url || "").toLowerCase();
  return (
    (item.mediaType || item.tagName || "").toLowerCase() === "video" ||
    /\.(mp4|webm|m3u8|mpd|mov|m4v)(\?|$)/i.test(ulow)
  );
}

function urlPathLooksLikeDirectVideo(url) {
  const p = String(url || "").split(/[?#]/)[0].toLowerCase();
  return /\.(mp4|webm|mov|m4v|m3u8|mpd|mkv|ogv)(\?|$)/i.test(p);
}

function urlPathLooksLikeRasterImage(url) {
  const p = String(url || "").split(/[?#]/)[0].toLowerCase();
  return /\.(jpe?g|png|gif|webp|avif|bmp)(\?|$)/i.test(p);
}

function galleryItemMarkedVideo(item) {
  return (
    (item.mediaType || "").toLowerCase() === "video" || (item.tagName || "").toLowerCase() === "video"
  );
}

function tbccPageLooksLikeTwitterX(pageUrl) {
  if (!pageUrl || typeof pageUrl !== "string") return false;
  try {
    const h = new URL(pageUrl).hostname.toLowerCase();
    return /(^|\.)x\.com$/i.test(h) || /(^|\.)twitter\.com$/i.test(h);
  } catch (_) {
    return false;
  }
}

/** Ordinal among blob <video> rows from the same tab (for pairing with network-captured MP4 order). */
function twitterBlobVideoOrdinalSameTab(item) {
  let n = 0;
  const tid = Number(item && item.tabId);
  if (!Number.isFinite(tid)) return 0;
  for (const x of imageList) {
    if (x === item) return n;
    if (
      x &&
      galleryItemMarkedVideo(x) &&
      String(x.url || "").startsWith("blob:") &&
      Number(x.tabId) === tid
    )
      n++;
  }
  return n;
}

async function tbccTwitterNetMediaListsInOrder(tabId) {
  const tid = Number(tabId);
  const mp4s = [];
  const m3u8s = [];
  if (!Number.isFinite(tid)) return { mp4s, m3u8s };
  const key = `tbcc_net_media_${tid}`;
  try {
    const sess = await chrome.storage.session.get(key);
    const netUrls = Array.isArray(sess[key]) ? sess[key] : [];
    for (const u of netUrls) {
      if (!u || typeof u !== "string") continue;
      try {
        const p = new URL(u);
        if (p.hostname.toLowerCase() !== "video.twimg.com") continue;
        const path = p.pathname.toLowerCase();
        if (/\.mp4(\?|$)/i.test(path)) mp4s.push(u);
        else if (/\.m3u8(\?|$)/i.test(path)) m3u8s.push(u);
      } catch (_) {}
    }
  } catch (_) {}
  return { mp4s, m3u8s };
}

/** Resolve page blob: video to video.twimg.com using tab URL + session net log (ZIP / download / retry). */
async function tbccTryResolveBlobVideoViaTwitterNet(item) {
  if (!item || !galleryItemMarkedVideo(item) || !String(item.url || "").startsWith("blob:")) return "";
  if (item.tabId == null || !Number.isFinite(Number(item.tabId))) return "";
  let onTwitter = tbccPageLooksLikeTwitterX(String(item.tbccSourcePageUrl || ""));
  if (!onTwitter) {
    try {
      const t = await chrome.tabs.get(Number(item.tabId));
      onTwitter = tbccPageLooksLikeTwitterX(String((t && t.url) || ""));
    } catch (_) {}
  }
  if (!onTwitter) return "";
  const { mp4s, m3u8s } = await tbccTwitterNetMediaListsInOrder(item.tabId);
  const ord = twitterBlobVideoOrdinalSameTab(item);
  return mp4s[ord] || m3u8s[ord] || "";
}

async function tbccUpgradeTwitterBlobVideosInCapture(tabId, deduped, pageUrl, seenKeys) {
  if (!tbccPageLooksLikeTwitterX(pageUrl) || !Number.isFinite(Number(tabId)) || !Array.isArray(deduped)) return;
  const { mp4s, m3u8s } = await tbccTwitterNetMediaListsInOrder(tabId);
  let bix = 0;
  const upgraded = new Set();
  for (const it of deduped) {
    if (!it || !String(it.url || "").startsWith("blob:")) continue;
    if (!galleryItemMarkedVideo(it)) continue;
    const next = mp4s[bix] || m3u8s[bix] || "";
    bix++;
    if (!next) continue;
    upgraded.add(next);
    const oldKey = String(it.url || "").slice(0, 400);
    if (seenKeys && seenKeys.has(oldKey)) seenKeys.delete(oldKey);
    it.url = next;
    it.mediaType = "video";
    it.tagName = "video";
    const nk = next.slice(0, 400);
    if (seenKeys) seenKeys.add(nk);
  }
  if (!upgraded.size) return;
  for (let i = deduped.length - 1; i >= 0; i--) {
    const it = deduped[i];
    if (it && it.tbccCaptureSource === "web-request" && upgraded.has(it.url)) {
      deduped.splice(i, 1);
      if (seenKeys) seenKeys.delete(String(it.url || "").slice(0, 400));
    }
  }
}

/**
 * Detail-page resolve occasionally sets `url` to og:image (.webp) while `thumbUrl` still holds the real stream * from the <video> element — downloads must follow the stream URL.
 */
function bestHttpMediaUrlForItem(it) {
  if (!it || !it.url) return "";
  const primary = String(it.url);
  const thumb = it.thumbUrl && String(it.thumbUrl);
  if (
    galleryItemMarkedVideo(it) &&
    urlPathLooksLikeRasterImage(primary) &&
    thumb &&
    urlPathLooksLikeDirectVideo(thumb)
  ) {
    return thumb;
  }
  return primary;
}

function normalizeVideoStemForGroup(url) {
  try {
    const u = new URL(url);
    let base = (u.pathname || "").split("/").pop() || "";
    base = base.replace(/\.[^.]+$/, "");
    base = base
      .replace(/[._-](?:\d{3,4})x(?:\d{3,4})(?:p)?$/i, "")
      .replace(/[._-](?:\d{2,4})p$/i, "")
      .replace(/[._-](?:480|540|720|1080|1440|2160|4k)(?:p)?$/i, "");
    return ((u.hostname || "") + "/" + base).toLowerCase();
  } catch (_) {
    return String(url || "").split("?")[0];
  }
}

function videoIdentityKey(item) {
  if (!itemLooksLikeVideo(item)) return "";
  const dur =
    item.durationSec != null && Number.isFinite(item.durationSec) && item.durationSec > 0
      ? Math.round(item.durationSec * 100) / 100
      : 0;
  return normalizeVideoStemForGroup(item.url) + "|d:" + dur;
}

function sortVideoItemsByScore(items) {
  const fn = typeof tbccScoreVideoUrl === "function" ? tbccScoreVideoUrl : () => 0;
  return [...items].sort((a, b) => fn(b.url) - fn(a.url));
}

function buildDisplayRows(list) {
  if (!settings.foldVideoVariants) {
    return list.map((item) => ({ type: "one", item }));
  }
  const keyToItems = new Map();
  for (const item of list) {
    const k = videoIdentityKey(item);
    if (!k || !itemLooksLikeVideo(item)) continue;
    if (!keyToItems.has(k)) keyToItems.set(k, []);
    keyToItems.get(k).push(item);
  }
  const foldable = new Set();
  for (const [k, arr] of keyToItems) {
    if (arr.length >= 2) foldable.add(k);
  }
  const seenFolded = new Set();
  const rows = [];
  for (const item of list) {
    const k = videoIdentityKey(item);
    if (!k || !foldable.has(k) || !itemLooksLikeVideo(item)) {
      rows.push({ type: "one", item });
      continue;
    }
    if (seenFolded.has(k)) continue;
    seenFolded.add(k);
    rows.push({ type: "group", key: k, items: sortVideoItemsByScore(keyToItems.get(k) || []) });
  }
  return rows;
}

function getDisplayRows() {
  return buildDisplayRows(getFilteredList());
}

function getUrlForDisplayRow(row) {
  if (row.type === "one") return row.item.url;
  const items = row.items;
  const pick = videoGroupPick.get(row.key);
  if (pick && items.some((i) => i.url === pick)) return pick;
  return items[0].url;
}

function getItemForDisplayRow(row) {
  if (row.type === "one") return row.item;
  const url = getUrlForDisplayRow(row);
  return row.items.find((i) => i.url === url) || row.items[0];
}

function pruneVideoGroupPick() {
  const rows = getDisplayRows();
  const valid = new Set();
  for (const r of rows) {
    if (r.type === "group") valid.add(r.key);
  }
  for (const k of [...videoGroupPick.keys()]) {
    if (!valid.has(k)) videoGroupPick.delete(k);
  }
}

function showLoading(show) {
  if (loadingEl) loadingEl.classList.toggle("hidden", !show);
}

function syncPoolSelectTooltip() {
  if (!poolSelect) return;
  const opt = poolSelect.selectedOptions && poolSelect.selectedOptions[0];
  poolSelect.title = opt ? "Pool: " + (opt.textContent || "") : "Pool";
}

function fillPoolSelectElement(sel, pools, selectedId, withPlaceholder) {
  if (!sel) return;
  sel.innerHTML = "";
  if (withPlaceholder) {
    const ph = document.createElement("option");
    ph.value = "";
    ph.textContent = "— pick pool —";
    sel.appendChild(ph);
  }
  (pools || []).forEach((p) => {
    const o = document.createElement("option");
    o.value = String(p.id);
    o.textContent = p.name || "Pool " + p.id;
    sel.appendChild(o);
  });
  if (selectedId != null && selectedId !== "") sel.value = String(selectedId);
}

async function loadPools() {
  if (!(await probeTbccApiReachable(false))) {
    markPoolSelectOffline();
    return;
  }
  try {
    const r = await fetch(API_BASE + "/pools");
    const pools = await r.json();
    cachedPoolsForInbox = Array.isArray(pools) ? pools : [];
    const { tbccPoolId } = await chrome.storage.local.get("tbccPoolId");
    if (poolSelect) {
      fillPoolSelectElement(poolSelect, cachedPoolsForInbox, tbccPoolId, false);
      syncPoolSelectTooltip();
    }
    if (savedUrlInboxDefaultPool) {
      fillPoolSelectElement(savedUrlInboxDefaultPool, cachedPoolsForInbox, tbccPoolId, false);
    }
    if (savedUrlInboxDefaultDest) {
      const stored = await chrome.storage.local.get([STORAGE_INBOX_DEFAULT_DEST]);
      const d = stored[STORAGE_INBOX_DEFAULT_DEST] === "loot_modifier" ? "loot_modifier" : "pool";
      savedUrlInboxDefaultDest.value = d;
      syncInboxDefaultDestUi();
    }
  } catch (e) {
    if (isTbccConnectionError(e)) {
      invalidateTbccApiReachableCache();
      markPoolSelectOffline();
      setTbccApiOfflineBanner(true);
    }
  }
}

async function reloadForumTopicsIfNeeded() {
  try {
    if (!forumPostEnabled || !forumPostEnabled.checked) return;
    if (postDestMode && postDestMode.value !== "forum") return;
    const ch = forumChannelSelect && forumChannelSelect.value;
    if (!ch) return;
    await loadForumTopics(parseInt(ch, 10));
  } catch (_) {}
}

/** Collected / Tools / Options iframes only set `src` once; bump `src` to fully reload like a new panel open. */
function reloadEmbeddedPanelIframes() {
  ["iframe-collected", "iframe-tools", "iframe-options"].forEach((id) => {
    const el = document.getElementById(id);
    if (!el) return;
    const src = el.getAttribute("src");
    if (src) el.src = src;
  });
}

/**
 * Full sidebar refresh: optional API + iframe reload, then tab capture (↻ / R).
 * Closing the side panel runs init(), which repeats loadPools / loadChannels / forum topics / doRefresh — refresh alone used to skip the first three and iframe reloads.
 */
async function refreshPanelOrHardScan() {
  await clearSelectionForNewCapture();
  if (settings.refreshHard !== false) {
    invalidateTbccApiReachableCache();
    const apiOk = await refreshTbccApiOfflineBanner();
    if (!apiOk) {
      await Promise.all([loadPools(), loadChannelsForForum()]);
    } else {
      await Promise.all([loadTagCatalog(), loadPools(), loadChannelsForForum()]);
    }
    await reloadForumTopicsIfNeeded();
    reloadEmbeddedPanelIframes();
  } else {
    invalidateTbccApiReachableCache();
    await refreshTbccApiOfflineBanner();
  }
  await doRefresh();
}

async function loadChannelsForForum() {
  if (!forumChannelSelect) return;
  if (!(await probeTbccApiReachable(false))) {
    forumChannelSelect.innerHTML = '<option value="">(API offline)</option>';
    return;
  }
  try {
    const r = await fetch(API_BASE + "/channels");
    const channels = await r.json();
    tbccChannelsCacheLast = Array.isArray(channels) ? channels : [];
    renderAlwaysIncludeChannelList();
    syncCaptionFieldFromBase();
    const keep = forumChannelSelect.value;
    forumChannelSelect.innerHTML = "";
    const z = document.createElement("option");
    z.value = "";
    z.textContent = "— channel —";
    forumChannelSelect.appendChild(z);
    (channels || []).forEach((c) => {
      const o = document.createElement("option");
      o.value = String(c.id);
      o.textContent = (c.name || c.identifier || "#" + c.id).slice(0, 36);
      forumChannelSelect.appendChild(o);
    });
    const { tbccForumChannelId } = await chrome.storage.local.get("tbccForumChannelId");
    if (keep && [...forumChannelSelect.options].some((op) => op.value === keep)) forumChannelSelect.value = keep;
    else if (tbccForumChannelId != null) forumChannelSelect.value = String(tbccForumChannelId);
  } catch (e) {
    tbccChannelsCacheLast = [];
    forumChannelSelect.innerHTML = '<option value="">(API offline)</option>';
    renderAlwaysIncludeChannelList();
    syncCaptionFieldFromBase();
    if (isTbccConnectionError(e)) {
      invalidateTbccApiReachableCache();
      setTbccApiOfflineBanner(true);
    }
  }
}

function setForumTopicOptions(topics, preferredTopicId) {
  if (!forumTopicSelect) return;
  const keep = preferredTopicId != null ? String(preferredTopicId) : forumTopicSelect.value;
  forumTopicSelect.innerHTML = "";
  const z = document.createElement("option");
  z.value = "";
  z.textContent = "— topic —";
  forumTopicSelect.appendChild(z);
  (topics || []).forEach((t) => {
    const o = document.createElement("option");
    o.value = String(t.id);
    const title = (t.title || "Topic " + t.id).slice(0, 40);
    o.textContent = title;
    forumTopicSelect.appendChild(o);
  });
  if (keep && [...forumTopicSelect.options].some((op) => op.value === keep)) forumTopicSelect.value = keep;
}

async function loadForumTopics(channelId) {
  if (!forumTopicSelect || !channelId) {
    setForumTopicOptions([], null);
    updateTelegramPostControls();
    return;
  }
  forumTopicSelect.disabled = true;
  try {
    const r = await fetch(API_BASE + "/channels/" + channelId + "/forum-topics");
    const data = await r.json();
    const { tbccForumTopicId } = await chrome.storage.local.get("tbccForumTopicId");
    setForumTopicOptions(data.topics || [], tbccForumTopicId);
  } catch (e) {
    setForumTopicOptions([], null);
  }
  forumTopicSelect.disabled = false;
  updateTelegramPostControls();
}

function syncDestMacroButtons() {
  const pool = btnDestMacroPool;
  const saved = btnDestMacroSaved;
  const forum = btnDestMacroForum;
  const chan = btnDestMacroChannel;
  if (!pool || !saved || !forum || !chan) return;
  [pool, saved, forum, chan].forEach((b) => b.classList.remove("tbcc-dest-macro--active"));
  const on = forumPostEnabled && forumPostEnabled.checked;
  const mode = (postDestMode && postDestMode.value) || "channel";
  if (!on) pool.classList.add("tbcc-dest-macro--active");
  else if (mode === "saved") saved.classList.add("tbcc-dest-macro--active");
  else if (mode === "forum") forum.classList.add("tbcc-dest-macro--active");
  else chan.classList.add("tbcc-dest-macro--active");
}

function updateTelegramDestSummary() {
  if (!telegramDestSummary || !telegramDestHint) return;
  const on = forumPostEnabled && forumPostEnabled.checked;
  const mode = (postDestMode && postDestMode.value) || "channel";
  if (!on) {
    telegramDestSummary.textContent = "→ TBCC library only (step 3 tags on media rows).";
    telegramDestHint.textContent = "Pick Saved, Topic, or Channel to also message Telegram.";
    return;
  }
  if (mode === "saved") {
    telegramDestSummary.textContent = "→ Telegram Saved Messages (skips library).";
    telegramDestHint.textContent = "Use steps 2–3 for caption and #hashtags.";
    return;
  }
  const ch = forumChannelSelect && forumChannelSelect.selectedOptions[0];
  const chLabel = ch ? String(ch.textContent || "").trim() : "";
  if (mode === "forum") {
    const tp = forumTopicSelect && forumTopicSelect.selectedOptions[0];
    const tLabel = tp ? String(tp.textContent || "").trim() : "";
    telegramDestSummary.textContent = chLabel
      ? tLabel
        ? `Pool → ${chLabel} · ${tLabel}`
        : `Pool → ${chLabel} — pick topic`
      : "Pool → group topic — pick channel & topic";
    telegramDestHint.textContent = "Imports to pool first, then posts to the topic.";
  } else {
    telegramDestSummary.textContent = chLabel ? `Pool → ${chLabel} (main)` : "Pool → channel — pick channel";
    telegramDestHint.textContent = "Imports to pool first, then posts to the channel.";
  }
}

async function applyDestMacro(which) {
  if (!forumPostEnabled || !postDestMode) return;
  if (which === "pool") {
    forumPostEnabled.checked = false;
    await chrome.storage.local.set({ tbccForumPostEnabled: false });
  } else {
    forumPostEnabled.checked = true;
    await chrome.storage.local.set({ tbccForumPostEnabled: true });
    if (which === "saved") postDestMode.value = "saved";
    else if (which === "forum") postDestMode.value = "forum";
    else postDestMode.value = "channel";
    await chrome.storage.local.set({ tbccPostDestMode: postDestMode.value });
  }
  updateTelegramPostControls();
  if (forumPostEnabled.checked && postDestMode.value === "forum" && forumChannelSelect && forumChannelSelect.value) {
    await loadForumTopics(parseInt(forumChannelSelect.value, 10));
  }
}

function applyTelegramPostSectionCollapsed(collapsed) {
  /* Sheet UI: collapsed=true means sheet closed */
  setTelegramSheetOpen(!collapsed);
}

function updateImportSheetLayout() {
  const on = forumPostEnabled && forumPostEnabled.checked;
  const mode = (postDestMode && postDestMode.value) || "channel";
  const savedMode = mode === "saved";
  const poolOnly = !on;

  if (importSheetCaptionSection) {
    importSheetCaptionSection.hidden = poolOnly;
  }
  if (telegramPoolSection) {
    telegramPoolSection.hidden = savedMode;
  }

  if (importSheetCaptionOutcome) {
    if (poolOnly) {
      importSheetCaptionOutcome.textContent = "";
    } else if (savedMode) {
      importSheetCaptionOutcome.textContent =
        "Telegram shows this on each album (first item per group of up to 10). Step 3 tags are appended as #hashtags here.";
    } else if (mode === "forum") {
      importSheetCaptionOutcome.textContent =
        "Caption for the Telegram post after files land in the library pool. Tags in step 3 stay on library rows only.";
    } else {
      importSheetCaptionOutcome.textContent =
        "Caption for the channel post after library import. Tags in step 3 stay on library rows only.";
    }
  }

  if (importSheetTagsOutcome) {
    if (savedMode) {
      importSheetTagsOutcome.textContent =
        "Saved mode: chips + auto-fill become #hashtags in the caption (step 2). Nothing is written to the TBCC library.";
    } else if (poolOnly) {
      importSheetTagsOutcome.textContent =
        "Library mode: chips + auto-fill merge onto each imported file (Dashboard → Media). No Telegram caption.";
    } else {
      importSheetTagsOutcome.textContent =
        "Library mode: tags on each imported file. Caption (step 2) is only for the Telegram post — not duplicated as tags.";
    }
  }

  if (autoTagOnExportLabel) {
    autoTagOnExportLabel.textContent = savedMode
      ? "Auto-fill: add page/URL hints as #hashtags in the caption"
      : "Auto-fill: add page tab, site, and URL path hints to your tags";
  }
}

function updateSendButtonLabel() {
  if (!btnSend) return;
  const savedMode = postDestMode && postDestMode.value === "saved";
  const on = forumPostEnabled && forumPostEnabled.checked;
  if (savedMode && on) {
    btnSend.textContent = "Send to Saved Messages";
  } else {
    btnSend.textContent = "Send to TBCC";
  }
}

function updateTelegramPostControls() {
  const on = forumPostEnabled && forumPostEnabled.checked;
  const savedMode = postDestMode && postDestMode.value === "saved";
  const forumMode = postDestMode && postDestMode.value === "forum";
  const channelMode = postDestMode && postDestMode.value === "channel";

  if (telegramDestDetailShell) {
    telegramDestDetailShell.hidden = !(on && !savedMode && (forumMode || channelMode));
  }
  if (sendSilentRow) {
    sendSilentRow.hidden = !(on && !savedMode && (forumMode || channelMode));
  }

  if (forumChannelSelect) {
    forumChannelSelect.disabled = !on || savedMode;
    forumChannelSelect.style.display = savedMode ? "none" : "";
  }
  if (forumTopicRow) forumTopicRow.style.display = forumMode ? "flex" : "none";
  const ch = forumChannelSelect && forumChannelSelect.value;
  if (forumTopicSelect) forumTopicSelect.disabled = !on || !ch || !forumMode;
  if (btnForumTopicsRefresh) btnForumTopicsRefresh.disabled = !on || !ch || !forumMode;
  updateSendButtonLabel();
  updateActionBarSubtitle();
  syncDestMacroButtons();
  updateTelegramDestSummary();
  updateImportSheetLayout();
}

async function getPoolId() {
  if (poolSelect && poolSelect.value) return parseInt(poolSelect.value, 10);
  const { tbccPoolId } = await chrome.storage.local.get("tbccPoolId");
  return tbccPoolId != null ? tbccPoolId : 1;
}

/** Content scripts cannot run on chrome://, brave://, extension pages, etc. */
function isInjectablePageUrl(url) {
  if (!url || typeof url !== "string") return false;
  return /^https?:\/\//i.test(url);
}

async function runCaptureInTab(tabId) {
  const st = await new Promise((r) => chrome.storage.local.get(STORAGE_SETTINGS, (o) => r(o[STORAGE_SETTINGS])));
  const capSettings = st && typeof st === "object" ? { ...settings, ...st } : settings;
  const lazyMs = Math.max(0, Math.min(3000, parseInt(String(capSettings.captureLazyDelayMs || 0), 10) || 0));
  if (lazyMs) await new Promise((res) => setTimeout(res, lazyMs));
  let rtAll = capSettings.resourceTimingAllImages === true;
  try {
    const tabHint = await chrome.tabs.get(tabId);
    if (tabHint && tabHint.url && /perchance\.org/i.test(tabHint.url)) rtAll = true;
  } catch (_) {}
  const inject = async (allFrames) => {
    await chrome.scripting.executeScript({
      target: { tabId, allFrames },
      func: (flag) => {
        try {
          window.__tbccResourceTimingAllImages = !!flag;
        } catch (_) {}
      },
      args: [rtAll],
    });
    await chrome.scripting.executeScript({
      target: { tabId, allFrames },
      files: ["media-url-guards.js", "auto-tag-utils.js", "capture.js"],
    });
    return chrome.scripting.executeScript({
      target: { tabId, allFrames },
      func: () => {
        try {
          if (typeof window.__tbccGetImageList === "function") return { list: window.__tbccGetImageList() };
        } catch (err) {
          return { error: String(err.message || err) };
        }
        return { error: "TBCC capture not ready; click Refresh." };
      },
    });
  };
  let results;
  try {
    results = await inject(true);
  } catch (e) {
    try {
      results = await inject(false);
    } catch (e2) {
      return { tabId, list: [], error: e2.message || e.message };
    }
  }
  const mergedList = [];
  let firstErr = null;
  for (const fr of results || []) {
    const payload = fr && fr.result;
    if (!payload) continue;
    if (payload.error) {
      if (!firstErr) firstErr = payload.error;
      continue;
    }
    if (payload.list && payload.list.length) {
      const frameId = fr.frameId != null ? fr.frameId : 0;
      for (let li = 0; li < payload.list.length; li++) {
        const row = payload.list[li];
        if (!row || typeof row !== "object") continue;
        mergedList.push({
          ...row,
          tbccCaptureFrameId: row.tbccCaptureFrameId != null ? row.tbccCaptureFrameId : frameId,
        });
      }
    }
  }
  if (!mergedList.length && firstErr) return { tabId, list: [], error: firstErr };
  let topPageUrl = "";
  try {
    const tab = await chrome.tabs.get(tabId);
    if (tab && tab.url && /^https?:\/\//i.test(tab.url)) topPageUrl = String(tab.url).split("#")[0];
  } catch (_) {}
  const seenKeys = new Set();
  const deduped = [];
  for (const it of mergedList) {
    const k = (it.url || "").slice(0, 400);
    if (seenKeys.has(k)) continue;
    seenKeys.add(k);
    deduped.push(it);
  }
  const mergeNet =
    typeof window !== "undefined" &&
    window.tbccGalleryAdapters &&
    typeof window.tbccGalleryAdapters.mergeOnlyfansWebRequestUrls === "function"
      ? window.tbccGalleryAdapters.mergeOnlyfansWebRequestUrls
      : null;
  if (mergeNet) await mergeNet(tabId, deduped, seenKeys);
  await tbccUpgradeTwitterBlobVideosInCapture(tabId, deduped, topPageUrl, seenKeys);
  return {
    tabId,
    list: deduped.map((i) => ({
      ...i,
      tabId,
      tbccSourcePageUrl: (i && i.tbccSourcePageUrl) || topPageUrl || "",
    })),
  };
}

function resolveTabIdFromGalleryItems() {
  if (!Array.isArray(imageList) || !imageList.length) return null;
  const ids = new Set();
  for (const it of imageList) {
    if (it && it.tabId != null && Number.isFinite(it.tabId)) ids.add(it.tabId);
  }
  if (ids.size === 1) return [...ids][0];
  return null;
}

function guessTabHostnameFromGallery() {
  if (!Array.isArray(imageList) || !imageList.length) return "";
  for (const it of imageList) {
    if (!it || !it.url || !/^https?:\/\//i.test(it.url)) continue;
    try {
      return new URL(it.url).hostname.toLowerCase();
    } catch (_) {}
  }
  return "";
}

/** Pinned capture tab — gallery does not follow the active tab while docked. */
let galleryDockedTab = null;

async function loadGalleryDockState() {
  try {
    const resp = await chrome.runtime.sendMessage({ action: "tbcc-gallery-dock-get" });
    if (resp && resp.docked && resp.dock && resp.dock.tabId != null) {
      galleryDockedTab = resp.dock;
      currentTabId = resp.dock.tabId;
      syncGalleryDockUi();
      return true;
    }
    galleryDockedTab = null;
    syncGalleryDockUi();
  } catch (_) {
    galleryDockedTab = null;
    syncGalleryDockUi();
  }
  return false;
}

function syncGalleryDockUi() {
  const docked = !!(galleryDockedTab && galleryDockedTab.tabId != null);
  if (btnGalleryDock) {
    btnGalleryDock.classList.toggle("is-active", docked);
    btnGalleryDock.title = docked
      ? `Docked to ${galleryDockedTab.hostname || galleryDockedTab.title || "tab"} — click to undock`
      : "Dock gallery to the current capture tab (stays on this tab while you browse other tabs)";
    btnGalleryDock.setAttribute("aria-pressed", docked ? "true" : "false");
  }
  if (galleryDockBanner) {
    if (docked) {
      galleryDockBanner.hidden = false;
      const label =
        galleryDockedTab.title || galleryDockedTab.hostname || `Tab ${galleryDockedTab.tabId}`;
      galleryDockBanner.textContent = `Docked: ${label}`;
      galleryDockBanner.title = galleryDockedTab.url || label;
    } else {
      galleryDockBanner.hidden = true;
      galleryDockBanner.textContent = "";
    }
  }
}

async function setGalleryTabDock(enable, explicitTabId) {
  if (!enable) {
    try {
      await chrome.runtime.sendMessage({ action: "tbcc-gallery-dock-set", clear: true });
    } catch (_) {}
    galleryDockedTab = null;
    syncGalleryDockUi();
    showToast("Undocked", "info");
    return;
  }
  let tabId = explicitTabId;
  if (tabId == null) {
    tabId = await resolveTargetTabIdUncached();
  }
  if (tabId == null) {
    showToast("Open an http(s) page to dock the gallery", "error");
    return;
  }
  try {
    const r = await chrome.runtime.sendMessage({ action: "tbcc-gallery-dock-set", tabId });
    if (r && r.ok && r.dock) {
      galleryDockedTab = r.dock;
      currentTabId = r.dock.tabId;
      syncGalleryDockUi();
      void refreshCrawlerTabUrlLabel();
      showToast(`Docked to ${r.dock.hostname || "tab"}`, "success");
      return;
    }
    showToast((r && r.error) || "Could not dock", "error");
  } catch (e) {
    showToast(String(e.message || e), "error");
  }
}

/** resolveTargetTabId without using the dock pin (for picking which tab to dock). */
async function resolveTargetTabIdUncached() {
  const saved = galleryDockedTab;
  galleryDockedTab = null;
  try {
    return await resolveTargetTabId();
  } finally {
    galleryDockedTab = saved;
  }
}

async function resolveTargetTabId() {
  if (galleryDockedTab && galleryDockedTab.tabId != null) {
    try {
      const t = await chrome.tabs.get(galleryDockedTab.tabId);
      if (t && t.id && isInjectablePageUrl(t.url)) {
        currentTabId = t.id;
        return t.id;
      }
      galleryDockedTab = null;
      syncGalleryDockUi();
      void chrome.runtime.sendMessage({ action: "tbcc-gallery-dock-set", clear: true }).catch(() => {});
    } catch (_) {
      galleryDockedTab = null;
      syncGalleryDockUi();
    }
  }
  if (currentTabId != null) {
    try {
      const t = await chrome.tabs.get(currentTabId);
      if (t && t.id && isInjectablePageUrl(t.url)) return t.id;
    } catch (_) {}
  }
  const glId = resolveTabIdFromGalleryItems();
  if (glId != null) {
    try {
      const t = await chrome.tabs.get(glId);
      if (t && t.id && isInjectablePageUrl(t.url)) return t.id;
    } catch (_) {}
  }
  /**
   * Side panel: `currentWindow` / `lastFocusedWindow` queries can miss the browser window that holds the page.
   * Last-focused window + its active tab matches what the user was browsing when they opened the panel.
   */
  try {
    const w = await chrome.windows.getLastFocused();
    if (w && w.id != null) {
      const [aw] = await chrome.tabs.query({ windowId: w.id, active: true });
      if (aw && aw.id && isInjectablePageUrl(aw.url)) return aw.id;
    }
  } catch (_) {}
  /** Prefer visible active tab before storage: activeTab only allows scripting that tab when the user opens the side panel. */
  const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  if (tab && tab.id && isInjectablePageUrl(tab.url)) return tab.id;
  const [tab2] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (tab2 && tab2.id && isInjectablePageUrl(tab2.url)) return tab2.id;
  const { tbccLastActiveTabId } = await chrome.storage.local.get("tbccLastActiveTabId");
  if (tbccLastActiveTabId != null) {
    try {
      const t = await chrome.tabs.get(tbccLastActiveTabId);
      if (t && t.id && isInjectablePageUrl(t.url)) return t.id;
    } catch (_) {}
  }
  const inLast = await chrome.tabs.query({ lastFocusedWindow: true });
  const hintedHost = guessTabHostnameFromGallery();
  if (hintedHost) {
    const norm = (h) => String(h || "").replace(/^www\./, "");
    const want = norm(hintedHost);
    for (const t of inLast) {
      if (!t.id || !t.url || !isInjectablePageUrl(t.url)) continue;
      try {
        if (norm(new URL(t.url).hostname) === want) return t.id;
      } catch (_) {}
    }
  }
  for (const t of inLast) {
    if (t.id && isInjectablePageUrl(t.url)) return t.id;
  }
  return null;
}

async function captureCurrentTab() {
  const tid = await resolveTargetTabId();
  if (!tid) return [];
  currentTabId = tid;
  void refreshCrawlerTabUrlLabel();
  const { list, error } = await runCaptureInTab(tid);
  if (error) console.warn("Capture error:", error);
  return list;
}

async function captureAllTabs() {
  const tabs = await chrome.tabs.query({ currentWindow: true });
  const injectable = tabs.filter((t) => t.id && isInjectablePageUrl(t.url));
  const results = await Promise.all(injectable.map((t) => runCaptureInTab(t.id)));
  const merged = [];
  results.forEach((r) => (r.list || []).forEach((i) => merged.push(i)));
  return merged;
}

/** Chrome tab group id for the gallery target tab, or null if the tab is not grouped. */
async function getTargetTabChromeGroupId() {
  const tid = await resolveTargetTabId();
  if (!tid) return null;
  try {
    const t = await chrome.tabs.get(tid);
    const gid = typeof t.groupId === "number" ? t.groupId : -1;
    return gid >= 0 ? gid : null;
  } catch (_) {
    return null;
  }
}

/** Like captureAllTabs, but only tabs in the given Chrome tab group (same window). */
async function captureTabsInChromeGroup(groupId) {
  if (groupId == null || groupId < 0) return [];
  const tabs = await chrome.tabs.query({ currentWindow: true });
  const injectable = tabs.filter((t) => {
    if (!t.id || !isInjectablePageUrl(t.url)) return false;
    const g = typeof t.groupId === "number" ? t.groupId : -1;
    return g === groupId;
  });
  const results = await Promise.all(injectable.map((t) => runCaptureInTab(t.id)));
  const merged = [];
  results.forEach((r) => (r.list || []).forEach((i) => merged.push(i)));
  return merged;
}

/**
 * Called when an overlay-added URL isn't in the fresh capture. Meta (from page-overlay.js or older capture runs)
 * can supply poster/thumb/duration/dimensions so the synthesized tile behaves like a native video cell.
 */
function synthesizeRowFromOverlayMeta(url, meta) {
  const mt =
    (meta && (meta.mediaType || meta.tagName || "")).toLowerCase() === "video"
      ? "video"
      : guessMediaType(url);
  const row = {
    url,
    mediaType: mt,
    tagName: mt === "video" ? "video" : "img",
    tabId: currentTabId,
    tbccCaptureSource: "overlay-checkbox",
  };
  if (meta) {
    if (meta.posterUrl && /^https?:\/\//i.test(meta.posterUrl)) row.posterUrl = meta.posterUrl;
    if (meta.thumbUrl && /^https?:\/\//i.test(meta.thumbUrl)) row.thumbUrl = meta.thumbUrl;
    if (typeof meta.durationSec === "number" && isFinite(meta.durationSec) && meta.durationSec > 0)
      row.durationSec = meta.durationSec;
    if (Number.isFinite(meta.width) && meta.width > 0) row.width = meta.width;
    if (Number.isFinite(meta.height) && meta.height > 0) row.height = meta.height;
    if (Number.isFinite(meta.naturalWidth) && meta.naturalWidth > 0) row.naturalWidth = meta.naturalWidth;
    if (Number.isFinite(meta.naturalHeight) && meta.naturalHeight > 0) row.naturalHeight = meta.naturalHeight;
    if (meta.pageUrl) row.tbccSourcePageUrl = meta.pageUrl;
  }
  return row;
}

function metaPageMatchesCurrentTab(meta, currentPageUrl) {
  if (!meta || !meta.pageUrl || !currentPageUrl) return false;
  try {
    const a = new URL(meta.pageUrl);
    const b = new URL(currentPageUrl);
    if (a.hostname !== b.hostname) return false;
    return a.pathname.split("#")[0] === b.pathname.split("#")[0];
  } catch (_) {
    return false;
  }
}

async function getCurrentTabUrl() {
  if (currentTabId == null) return "";
  try {
    const t = await chrome.tabs.get(currentTabId);
    return (t && t.url) || "";
  } catch (_) {
    return "";
  }
}

async function pruneOrphanSelections(currentPageUrl) {
  try {
    const { tbccSelectionUrls = [], tbccSelectionMeta = {} } = await chrome.storage.local.get([
      "tbccSelectionUrls",
      "tbccSelectionMeta",
    ]);
    const urlsInList = new Set(imageList.map((i) => i.url));
    const metaMap = tbccSelectionMeta && typeof tbccSelectionMeta === "object" ? tbccSelectionMeta : {};
    const kept = [];
    const keptMeta = {};
    for (const u of tbccSelectionUrls) {
      if (urlsInList.has(u)) {
        kept.push(u);
        if (metaMap[u]) keptMeta[u] = metaMap[u];
        continue;
      }
      const meta = metaMap[u];
      if (meta && metaPageMatchesCurrentTab(meta, currentPageUrl)) {
        kept.push(u);
        keptMeta[u] = meta;
      }
    }
    if (kept.length !== tbccSelectionUrls.length || Object.keys(keptMeta).length !== Object.keys(metaMap).length) {
      await tbccStorageLocalSet({ tbccSelectionUrls: kept, tbccSelectionMeta: keptMeta });
    }
  } catch (_) {}
}

async function applySelectionFromStorage(storedSel) {
  const urlsInList = new Set(imageList.map((i) => i.url));
  const thumbToFull = new Map();
  imageList.forEach((i) => {
    if (!i || !i.thumbUrl) return;
    const prev = thumbToFull.get(i.thumbUrl);
    if (prev == null) thumbToFull.set(i.thumbUrl, i.url);
    else if (Array.isArray(prev)) {
      if (prev[prev.length - 1] !== i.url) prev.push(i.url);
    } else if (prev !== i.url) thumbToFull.set(i.thumbUrl, [prev, i.url]);
  });
  selectedUrls = expandSelectionRefs(storedSel);
  for (const u of storedSel) {
    if (urlsInList.has(u)) selectedUrls.add(u);
    else if (thumbToFull.has(u)) {
      const mapped = thumbToFull.get(u);
      if (Array.isArray(mapped)) mapped.forEach((x) => selectedUrls.add(x));
      else selectedUrls.add(mapped);
    }
  }
  if (activeTab !== "current") return;
  let metaMap = {};
  try {
    const got = await chrome.storage.local.get("tbccSelectionMeta");
    if (got && got.tbccSelectionMeta && typeof got.tbccSelectionMeta === "object") metaMap = got.tbccSelectionMeta;
  } catch (_) {}
  const currentPageUrl = await getCurrentTabUrl();
  const preserveAll = !!settings.preserveOrphanSelections;
  for (const u of storedSel) {
    if (urlsInList.has(u) || !/^https?:\/\//i.test(u)) continue;
    const meta = metaMap[u];
    const fromThisPage = metaPageMatchesCurrentTab(meta, currentPageUrl);
    if (!preserveAll && !fromThisPage) continue;
    const row = synthesizeRowFromOverlayMeta(u, meta);
    imageList.push(row);
    urlsInList.add(u);
    selectedUrls.add(u);
  }
}

/* =========================================================
 * Sub-tab history (Phase 2)
 * =========================================================
 * Keeps up to settings.subtabCap snapshots of (pageUrl → imageList + selectionUrls)
 * for the currently-attached browser tab. Switching chips swaps the grid state
 * but does NOT navigate the browser tab. Snapshots hold URL strings + metadata
 * only (no decoded image data), so a 300-item snapshot is ~50-150KB of JSON.
 */

const SUBTAB_STORAGE_PREFIX = "tbcc_gallery_subtabs:";
const SUBTAB_MAX_IMAGES_PER_SNAPSHOT = 240;
const SELECTION_PERSIST_MAX_REFS = 120;
/** In-memory state; authoritative copy is mirrored into chrome.storage.session. */
let galleryTabs = [];
let activeGalleryTabId = null;
let subtabSaveTimer = null;
let subtabRestoredForTabId = null;

function subtabStorageKey() {
  if (currentTabId == null) return "";
  return SUBTAB_STORAGE_PREFIX + String(currentTabId);
}

function makeSubtabId() {
  return "st-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 8);
}

function normalizePageKey(url) {
  try {
    const u = new URL(url);
    return (u.host + u.pathname.replace(/\/+$/, "")).toLowerCase() || u.host.toLowerCase();
  } catch (_) {
    return String(url || "")
      .split("#")[0]
      .toLowerCase();
  }
}

function prettySubtabLabel(url) {
  try {
    const u = new URL(url);
    const host = u.hostname.replace(/^www\./i, "");
    const seg = (u.pathname || "/")
      .split("/")
      .filter(Boolean)
      .pop();
    if (!seg) return host;
    return host + "/" + decodeURIComponent(seg).slice(0, 28);
  } catch (_) {
    return String(url || "").slice(0, 40);
  }
}

function recomputeSubtabLabelSuffixes() {
  const buckets = new Map();
  for (const t of galleryTabs) {
    const key = (t.pageHost || "") + "|" + prettySubtabLabel(t.pageUrl);
    if (!buckets.has(key)) buckets.set(key, []);
    buckets.get(key).push(t);
  }
  for (const arr of buckets.values()) {
    if (arr.length === 1) {
      arr[0].suffix = "";
      continue;
    }
    arr.sort((a, b) => (a.capturedAt || 0) - (b.capturedAt || 0));
    arr.forEach((t, idx) => {
      t.suffix = "(" + (idx + 1) + ")";
    });
  }
}

function snapshotCurrentStateIntoActiveSubtab() {
  if (!settings.subtabEnabled || activeGalleryTabId == null) return;
  const t = galleryTabs.find((x) => x.id === activeGalleryTabId);
  if (!t) return;
  const src = Array.isArray(imageList) ? imageList : [];
  if (src.length === 0 && (t.imageListSnapshot || []).length > 0) return;
  const trimmed = src.length > SUBTAB_MAX_IMAGES_PER_SNAPSHOT ? src.slice(0, SUBTAB_MAX_IMAGES_PER_SNAPSHOT) : src;
  t.imageListSnapshot = trimmed.map((i) => serializeGalleryItemForStorage(i));
  t.selectionUrls = Array.from(selectedUrls).map((u) => {
    const it = imageList.find((row) => row.url === u);
    return it ? selectionRefForItem(it) : u;
  });
  t.lastActivatedAt = Date.now();
  scheduleSubtabSave();
}

function scheduleSubtabSave() {
  const forTabId = currentTabId;
  if (subtabSaveTimer) clearTimeout(subtabSaveTimer);
  subtabSaveTimer = setTimeout(() => {
    subtabSaveTimer = null;
    if (forTabId !== currentTabId) return;
    void persistSubtabs(forTabId);
  }, 250);
}

async function persistSubtabs(forTabId) {
  if (forTabId == null) forTabId = currentTabId;
  if (forTabId == null || forTabId !== currentTabId) return;
  const key = SUBTAB_STORAGE_PREFIX + String(forTabId);
  if (!key) return;
  try {
    const payload = {
      v: 1,
      activeId: activeGalleryTabId,
      tabs: galleryTabs.map((t) => ({
        id: t.id,
        pageUrl: t.pageUrl,
        pageHost: t.pageHost,
        pagePath: t.pagePath,
        capturedAt: t.capturedAt,
        lastActivatedAt: t.lastActivatedAt,
        suffix: t.suffix,
        selectionUrls: t.selectionUrls || [],
        imageListSnapshot: t.imageListSnapshot || [],
      })),
    };
    if (chrome.storage.session && chrome.storage.session.set) {
      await chrome.storage.session.set({ [key]: payload });
    } else {
      await tbccStorageLocalSet({ [key]: payload });
    }
  } catch (_) {}
}

async function restoreSubtabsForCurrentTab() {
  const key = subtabStorageKey();
  if (!key) return;
  try {
    const store = chrome.storage.session && chrome.storage.session.get ? chrome.storage.session : chrome.storage.local;
    const got = await new Promise((r) => store.get(key, (o) => r(o)));
    const payload = got && got[key];
    if (!payload || !Array.isArray(payload.tabs)) return;
    galleryTabs = payload.tabs.map((t) => ({
      id: t.id || makeSubtabId(),
      pageUrl: t.pageUrl || "",
      pageHost: t.pageHost || "",
      pagePath: t.pagePath || "",
      capturedAt: t.capturedAt || Date.now(),
      lastActivatedAt: t.lastActivatedAt || t.capturedAt || Date.now(),
      suffix: t.suffix || "",
      selectionUrls: Array.isArray(t.selectionUrls) ? t.selectionUrls : [],
      imageListSnapshot: Array.isArray(t.imageListSnapshot) ? t.imageListSnapshot : [],
    }));
    activeGalleryTabId = payload.activeId || (galleryTabs[0] && galleryTabs[0].id) || null;
  } catch (_) {}
}

function evictOverCapSubtabs() {
  const cap = Math.max(1, Math.min(5, parseInt(String(settings.subtabCap || 3), 10) || 3));
  if (galleryTabs.length <= cap) return;
  galleryTabs.sort((a, b) => (b.lastActivatedAt || 0) - (a.lastActivatedAt || 0));
  galleryTabs = galleryTabs.slice(0, cap);
  if (!galleryTabs.find((x) => x.id === activeGalleryTabId)) {
    activeGalleryTabId = (galleryTabs[0] && galleryTabs[0].id) || null;
  }
}

async function ensureSubtabForCurrentPage() {
  if (!settings.subtabEnabled) return null;
  if (currentTabId == null) return null;
  if (subtabRestoredForTabId !== currentTabId) {
    galleryTabs = [];
    activeGalleryTabId = null;
    await restoreSubtabsForCurrentTab();
    subtabRestoredForTabId = currentTabId;
  }
  const url = await getCurrentTabUrl();
  if (!url) return null;
  const key = normalizePageKey(url);
  let match = galleryTabs.find((t) => normalizePageKey(t.pageUrl) === key);
  if (match) {
    if (activeGalleryTabId !== match.id) snapshotCurrentStateIntoActiveSubtab();
    match.lastActivatedAt = Date.now();
    activeGalleryTabId = match.id;
    scheduleSubtabSave();
    return match;
  }
  snapshotCurrentStateIntoActiveSubtab();
  let host = "",
    path = "";
  try {
    const u = new URL(url);
    host = u.hostname;
    path = u.pathname;
  } catch (_) {}
  match = {
    id: makeSubtabId(),
    pageUrl: url,
    pageHost: host,
    pagePath: path,
    capturedAt: Date.now(),
    lastActivatedAt: Date.now(),
    suffix: "",
    selectionUrls: [],
    imageListSnapshot: [],
  };
  galleryTabs.push(match);
  activeGalleryTabId = match.id;
  evictOverCapSubtabs();
  recomputeSubtabLabelSuffixes();
  scheduleSubtabSave();
  return match;
}

async function switchToSubtab(id) {
  const target = galleryTabs.find((t) => t.id === id);
  if (!target || target.id === activeGalleryTabId) return;
  snapshotCurrentStateIntoActiveSubtab();
  activeGalleryTabId = target.id;
  target.lastActivatedAt = Date.now();
  imageList = (target.imageListSnapshot || []).map((i) => ({ ...i }));
  selectedUrls = expandSelectionRefs(target.selectionUrls || []);
  await persistSelection();
  renderSubtabBar();
  renderGrid();
  updateCountAndSend();
  scheduleSubtabSave();
}

async function closeSubtab(id) {
  const idx = galleryTabs.findIndex((t) => t.id === id);
  if (idx < 0) return;
  const wasActive = galleryTabs[idx].id === activeGalleryTabId;
  galleryTabs.splice(idx, 1);
  if (wasActive) {
    galleryTabs.sort((a, b) => (b.lastActivatedAt || 0) - (a.lastActivatedAt || 0));
    activeGalleryTabId = (galleryTabs[0] && galleryTabs[0].id) || null;
    if (activeGalleryTabId) {
      const target = galleryTabs.find((t) => t.id === activeGalleryTabId);
      imageList = (target.imageListSnapshot || []).map((i) => ({ ...i }));
      selectedUrls = expandSelectionRefs(target.selectionUrls || []);
      await persistSelection();
      renderGrid();
      updateCountAndSend();
    } else {
      imageList = [];
      selectedUrls = new Set();
      renderGrid();
    }
  }
  recomputeSubtabLabelSuffixes();
  renderSubtabBar();
  scheduleSubtabSave();
}

function renderSubtabBar() {
  if (!tbccSubtabBar || !tbccSubtabStrip) return;
  if (!settings.subtabEnabled || galleryTabs.length === 0) {
    tbccSubtabBar.hidden = true;
    return;
  }
  tbccSubtabBar.hidden = false;
  tbccSubtabStrip.innerHTML = "";
  const ordered = galleryTabs.slice().sort((a, b) => (a.capturedAt || 0) - (b.capturedAt || 0));
  for (const t of ordered) {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "tbcc-subtab-chip" + (t.id === activeGalleryTabId ? " is-active" : "");
    chip.dataset.subtabId = t.id;
    chip.setAttribute("role", "tab");
    chip.setAttribute("aria-selected", t.id === activeGalleryTabId ? "true" : "false");
    chip.title = t.pageUrl;
    const label = document.createElement("span");
    label.className = "tbcc-subtab-chip__label";
    label.textContent = prettySubtabLabel(t.pageUrl) + (t.suffix ? " " + t.suffix : "");
    chip.appendChild(label);
    const count = document.createElement("span");
    count.className = "tbcc-subtab-chip__count";
    const nItems = (t.imageListSnapshot || []).length;
    const nSel = (t.selectionUrls || []).length;
    count.textContent = nSel > 0 ? nItems + "·" + nSel : String(nItems);
    chip.appendChild(count);
    const close = document.createElement("button");
    close.type = "button";
    close.className = "tbcc-subtab-chip__close";
    close.title = "Close sub-tab";
    close.textContent = "×";
    close.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      void closeSubtab(t.id);
    });
    chip.addEventListener("click", () => {
      void switchToSubtab(t.id);
    });
    chip.appendChild(close);
    tbccSubtabStrip.appendChild(chip);
  }
  updateMemHud();
}

function fmtBytes(n) {
  if (!Number.isFinite(n) || n <= 0) return "0";
  if (n < 1024) return n + "B";
  if (n < 1024 * 1024) return (n / 1024).toFixed(0) + "K";
  if (n < 1024 * 1024 * 1024) return (n / (1024 * 1024)).toFixed(1) + "M";
  return (n / (1024 * 1024 * 1024)).toFixed(2) + "G";
}

function updateMemHud() {
  if (!tbccMemHud) return;
  try {
    const pm = performance && performance.memory ? performance.memory : null;
    if (pm && pm.usedJSHeapSize) {
      const used = pm.usedJSHeapSize;
      const lim = pm.jsHeapSizeLimit || 0;
      const pct = lim ? used / lim : 0;
      tbccMemHud.textContent = "heap " + fmtBytes(used) + (lim ? " / " + fmtBytes(lim) : "") + "  · " + galleryTabs.length + " sub";
      tbccMemHud.classList.toggle("is-warn", pct >= 0.55 && pct < 0.8);
      tbccMemHud.classList.toggle("is-hot", pct >= 0.8);
    } else {
      tbccMemHud.textContent = galleryTabs.length + " sub · heap n/a";
      tbccMemHud.classList.remove("is-warn", "is-hot");
    }
  } catch (_) {}
}

function openSubtabPopover(open) {
  if (!tbccSubtabPopover) return;
  if (open) {
    if (tbccSubtabEnabledCb) tbccSubtabEnabledCb.checked = !!settings.subtabEnabled;
    if (tbccSubtabCapInput) tbccSubtabCapInput.value = String(settings.subtabCap || 3);
    if (tbccSubtabAutoCaptureCb) tbccSubtabAutoCaptureCb.checked = !!settings.subtabAutoCapture;
    tbccSubtabPopover.hidden = false;
  } else {
    tbccSubtabPopover.hidden = true;
  }
}

async function clearAllSubtabs() {
  galleryTabs = [];
  activeGalleryTabId = null;
  await persistSubtabs();
  renderSubtabBar();
}

async function wireSubtabUi() {
  if (!tbccSubtabSettingsBtn) return;
  tbccSubtabSettingsBtn.addEventListener("click", () => {
    openSubtabPopover(tbccSubtabPopover && tbccSubtabPopover.hidden);
  });
  tbccSubtabPopoverDoneBtn &&
    tbccSubtabPopoverDoneBtn.addEventListener("click", () => {
      openSubtabPopover(false);
    });
  tbccSubtabEnabledCb &&
    tbccSubtabEnabledCb.addEventListener("change", () => {
      settings.subtabEnabled = !!tbccSubtabEnabledCb.checked;
      persistSettingsNow();
      renderSubtabBar();
    });
  tbccSubtabCapInput &&
    tbccSubtabCapInput.addEventListener("change", () => {
      const n = parseInt(tbccSubtabCapInput.value, 10);
      settings.subtabCap = Math.max(1, Math.min(5, isNaN(n) ? 3 : n));
      tbccSubtabCapInput.value = String(settings.subtabCap);
      evictOverCapSubtabs();
      recomputeSubtabLabelSuffixes();
      persistSettingsNow();
      scheduleSubtabSave();
      renderSubtabBar();
    });
  tbccSubtabAutoCaptureCb &&
    tbccSubtabAutoCaptureCb.addEventListener("change", () => {
      settings.subtabAutoCapture = !!tbccSubtabAutoCaptureCb.checked;
      persistSettingsNow();
    });
  tbccSubtabClearAllBtn && tbccSubtabClearAllBtn.addEventListener("click", () => void clearAllSubtabs());
  document.addEventListener("click", (e) => {
    if (!tbccSubtabPopover || tbccSubtabPopover.hidden) return;
    if (tbccSubtabPopover.contains(e.target) || (tbccSubtabSettingsBtn && tbccSubtabSettingsBtn.contains(e.target))) return;
    openSubtabPopover(false);
  });
  setInterval(updateMemHud, 3000);
}

function persistSettingsNow() {
  try {
    chrome.storage.local.set({ [STORAGE_SETTINGS]: settings });
  } catch (_) {}
}

function tbccItemPixelArea(it) {
  if (!it) return 0;
  const w = it.naturalWidth || it.width || 0;
  const h = it.naturalHeight || it.height || 0;
  return w > 0 && h > 0 ? w * h : 0;
}

function tbccUrlIsHighResSession(u) {
  const s = String(u || "");
  return s.startsWith("blob:") || s.startsWith("data:image/");
}

async function appendMergedCapture(tabId) {
  const { list } = await runCaptureInTab(tabId);
  if (!list || !list.length) return 0;
  const seen = new Set(imageList.map((i) => i.url));
  let n = 0;
  for (const it of list) {
    if (!it || !it.url) continue;
    if (it.tbccPerchanceSlot) {
      const slotIdx = imageList.findIndex((x) => x && x.tbccPerchanceSlot === it.tbccPerchanceSlot);
      if (slotIdx >= 0) {
        const prev = imageList[slotIdx];
        const prevArea = tbccItemPixelArea(prev);
        const nextArea = tbccItemPixelArea(it);
        const prevHi = tbccUrlIsHighResSession(prev.url);
        const nextHi = tbccUrlIsHighResSession(it.url);
        if (nextHi && !prevHi) {
          const oldUrl = prev.url;
          imageList[slotIdx] = { ...it, tabId: it.tabId != null ? it.tabId : tabId };
          if (selectedUrls.has(oldUrl)) {
            selectedUrls.delete(oldUrl);
            selectedUrls.add(it.url);
          }
          seen.add(it.url);
          n++;
          continue;
        }
        if (nextArea > prevArea * 1.12) {
          const oldUrl = prev.url;
          imageList[slotIdx] = { ...it, tabId: it.tabId != null ? it.tabId : tabId };
          if (selectedUrls.has(oldUrl)) {
            selectedUrls.delete(oldUrl);
            selectedUrls.add(it.url);
          }
          seen.add(it.url);
          n++;
          continue;
        }
        seen.add(it.url);
        continue;
      }
    }
    if (seen.has(it.url)) continue;
    seen.add(it.url);
    imageList.push({ ...it, tabId: it.tabId != null ? it.tabId : tabId });
    n++;
  }
  return n;
}

async function doRefresh() {
  showLoading(true);
  let scanStripHandled = false;
  const prevImageList = Array.isArray(imageList) ? imageList.slice() : [];
  const prevSelection = new Set(selectedUrls);
  const { [STORAGE_SELECTION]: storedArr = [] } = await chrome.storage.local.get(STORAGE_SELECTION);
  const storedSel = new Set(Array.isArray(storedArr) ? storedArr : []);
  if (settings.subtabEnabled && activeGalleryTabId != null) snapshotCurrentStateIntoActiveSubtab();
  try {
    if (activeTab === "all") {
      imageList = await captureAllTabs();
    } else if (activeTab === "group") {
      const gid = await getTargetTabChromeGroupId();
      if (gid == null) {
        imageList = [];
        showToast("Active tab is not in a Chrome tab group — add it to a tab group to use Group capture.", "info");
      } else {
        imageList = await captureTabsInChromeGroup(gid);
      }
    } else {
      const tid = await resolveTargetTabId();
      currentTabId = tid;
      if (!tid) {
        imageList = [];
      } else {
        imageList = await captureCurrentTab();
        if (imageList.length === 0) {
          await new Promise((r) => setTimeout(r, 700));
          const retry = await captureCurrentTab();
          if (retry.length) imageList = retry;
        }
      }
    }
    if (window.tbccGalleryAdapters && typeof window.tbccGalleryAdapters.runGalleryResolvePipeline === "function") {
      imageList = await window.tbccGalleryAdapters.runGalleryResolvePipeline(imageList);
    }
    if (settings.subtabEnabled && settings.subtabAutoCapture && activeTab === "current") {
      await ensureSubtabForCurrentPage();
    }
    await applySelectionFromStorage(storedSel);
    if (!settings.preserveOrphanSelections && activeTab === "current") {
      await pruneOrphanSelections(await getCurrentTabUrl());
    }
    await persistSelection();
    renderSubtabBar();

    if (activeTab === "current" && currentTabId != null) {
      setScanStripVisible(true);
      setScanProgress(0.28, "Scanning…");
      showLoading(false);
      renderGrid();
      await notifyOverlayRefresh();
      let scanDelays = SCAN_MERGE_DELAYS_MS;
      let perchanceTab = false;
      try {
        const tab = await chrome.tabs.get(currentTabId);
        const u = (tab && tab.url) || "";
        if (/onlyfans\.com/i.test(u)) scanDelays = SCAN_MERGE_DELAYS_MS_ONLYFANS;
        else if (/perchance\.org/i.test(u)) {
          scanDelays = SCAN_MERGE_DELAYS_MS_PERCHANCE;
          perchanceTab = true;
        }
      } catch (_) {}
      let stagnantPass = 0;
      for (let p = 0; p < scanDelays.length; p++) {
        setScanProgress(0.28 + ((p + 1) / scanDelays.length) * 0.68, "Scanning…");
        await new Promise((r) => setTimeout(r, scanDelays[p]));
        const before = imageList.length;
        const merged = await appendMergedCapture(currentTabId);
        if (merged > 0) {
          await applySelectionFromStorage(storedSel);
          await persistSelection();
          renderGrid();
        }
        if (imageList.length === before) stagnantPass++;
        else stagnantPass = 0;
        if (stagnantPass >= 2) break;
      }
      setScanProgress(1, "Done");
      setTimeout(() => setScanStripVisible(false), 480);
      scanStripHandled = true;
      await notifyOverlayRefresh();
      if (perchanceTab) startPerchancePoll(currentTabId);
      else stopPerchancePoll();
      if (settings.subtabEnabled) snapshotCurrentStateIntoActiveSubtab();
      return;
    }
    stopPerchancePoll();
  } catch (e) {
    console.warn("TBCC gallery refresh failed", e);
    imageList = prevImageList;
    selectedUrls = prevSelection;
  } finally {
    showLoading(false);
    if (!scanStripHandled) setScanStripVisible(false);
  }
  renderGrid();
  if (settings.subtabEnabled) snapshotCurrentStateIntoActiveSubtab();
  await notifyOverlayRefresh();
}

function addLocalFiles(files) {
  const newItems = [];
  for (const f of Array.from(files || [])) {
    if (!f) continue;
    const url = URL.createObjectURL(f);
    newItems.push({ url, file: f, name: f.name, type: f.type || "", mediaType: f.type && f.type.startsWith("video") ? "video" : "image" });
  }
  imageList = imageList.concat(newItems);
  newItems.forEach((i) => selectedUrls.add(i.url));
  renderGrid();
}

function setCrawlerStatus(text, kind) {
  if (!crawlerStatus) return;
  crawlerStatus.textContent = text || "";
  crawlerStatus.style.color =
    kind === "error" ? "var(--tbcc-error)" : kind === "success" ? "var(--tbcc-success)" : "var(--tbcc-text-muted)";
}

function setCrawlerTabUrlLabel(url) {
  if (!crawlerTabUrl) return;
  const u = (url || "").trim();
  crawlerTabUrl.textContent = u ? u.replace(/^https?:\/\//i, "") : "";
  crawlerTabUrl.title = u || "Active tab URL";
}

async function refreshCrawlerTabUrlLabel() {
  const u = await getCurrentTabUrl();
  setCrawlerTabUrlLabel(u);
  return u;
}

/** Hosts where TBCC should forward browser cookies to the backend crawler. */
function crawlerShouldUseCookiesForUrl(url) {
  const hint = detectCrawlerAdapterHint(url);
  if (hint === "onlyfans" || hint === "bunkr") return true;
  try {
    const h = new URL(url).hostname.toLowerCase();
    if (
      h.includes("kemono.") ||
      h.includes("coomer.") ||
      h.endsWith(".fansly.com") ||
      h === "fansly.com" ||
      h.includes("filecrypt.") ||
      h.includes("missav.")
    ) {
      return true;
    }
  } catch (_) {}
  return false;
}

function crawlerItemToGalleryItem(item, sourceUrl, adapter) {
  const url = item && item.url ? String(item.url) : "";
  const mediaType = item && item.media_type === "video" ? "video" : guessMediaType(url);
  const row = {
    url,
    mediaType,
    tagName: mediaType === "video" ? "video" : "img",
    tabId: currentTabId,
    name: (item && item.filename) || filenameFromUrl(url),
    tbccSourcePageUrl: sourceUrl || "",
    tbccCaptureSource: "crawler:" + (adapter || "auto"),
  };
  if (item && item.thumbnail_url) {
    row.thumbUrl = item.thumbnail_url;
    row.posterUrl = item.thumbnail_url;
  }
  return row;
}

async function getCrawlerCookiesForUrl(url, useCookies) {
  if (!useCookies) return null;
  try {
    const cookies = await chrome.cookies.getAll({ url });
    if (!cookies || !cookies.length) return null;
    return cookies.map((c) => `${c.name}=${c.value}`).join("; ");
  } catch (_) {
    return null;
  }
}

/**
 * For adapters whose backend resolver hits multiple hosts (e.g. Bunkr's
 * apidl.bunkr.ru and get.bunkrr.su, separate from the album host), collect
 * cookies for every involved host and merge them with name-precedence given
 * to the first list (so e.g. cf_clearance from the user-facing host wins).
 */
async function getCrawlerCookiesForHosts(adapterHint, primaryUrl, useCookies) {
  if (!useCookies) return null;
  const seen = new Map();
  const sources = [primaryUrl];
  if (adapterHint === "bunkr") {
    sources.push("https://apidl.bunkr.ru/", "https://get.bunkrr.su/");
  }
  for (const src of sources) {
    try {
      const cookies = await chrome.cookies.getAll({ url: src });
      for (const c of cookies || []) {
        if (!seen.has(c.name)) seen.set(c.name, c.value);
      }
    } catch (_) {}
  }
  if (!seen.size) return null;
  return Array.from(seen.entries())
    .map(([name, value]) => `${name}=${value}`)
    .join("; ");
}

function detectCrawlerAdapterHint(url) {
  try {
    const h = new URL(url).hostname.toLowerCase();
    if (h === "erome.com" || h.endsWith(".erome.com")) return "erome";
    if (/^(?:app\.)?bunkr+\.\w+$/.test(h)) return "bunkr";
    if (h === "onlyfans.com" || h.endsWith(".onlyfans.com")) return "onlyfans";
  } catch (_) {}
  return "auto";
}

/**
 * OnlyFans harvest path.
 *
 * OF is a SPA — full-resolution media URLs only appear inside JSON
 * responses to /api2/v2/... requests, never in the page's <img> elements
 * (those are 300×300 thumbnails). Backend HTML scraping cannot see them.
 *
 * Instead we drive the user's actual OF tab: ensure the page-world hook
 * (of-api-hook.js, registered via manifest with world: MAIN) is active and
 * capture.js (isolated world) is injected, then auto-scroll the SPA so OF
 * itself fetches the full media inventory. Each captured JSON is mined
 * for source-quality image URLs and best-quality video URLs, and the
 * results are pushed into the sidebar.
 */
async function deployOnlyFansFromActiveTab(url, adapterHint) {
  let tid = await resolveTargetTabId();
  let tabUrl = "";
  if (tid != null) {
    try { const t = await chrome.tabs.get(tid); tabUrl = (t && t.url) || ""; } catch (_) {}
  }
  let isOfTab = (() => {
    try { const h = new URL(tabUrl).hostname.toLowerCase(); return h === "onlyfans.com" || h.endsWith(".onlyfans.com"); }
    catch (_) { return false; }
  })();

  if (!isOfTab) {
    setCrawlerStatus("Open OnlyFans tab", "error");
    showToast(
      "OnlyFans crawl requires the page open in your active tab. " +
        "Open " + url + " in a tab, then click Crawl again.",
      "info"
    );
    return;
  }

  /**
   * Inject the page-world API hook AND the isolated-world harvest collector.
   * The static manifest entries cover fresh page loads, but for tabs that were
   * already open before the extension was (re)loaded, neither static script
   * ran. We re-inject both here. Each file has its own idempotency guard so
   * repeat injections are safe.
   *
   * Note: of-api-hook.js patches window.fetch / XMLHttpRequest after the page
   * has booted. It only sees API calls that fire *after* injection. The
   * autoscroll loop below intentionally triggers new pagination fetches to
   * surface high-resolution URLs.
   */
  try {
    await chrome.scripting.executeScript({
      target: { tabId: tid },
      files: ["of-api-hook.js"],
      world: "MAIN",
    });
  } catch (e) {
    console.warn("[TBCC] of-api-hook injection (MAIN) failed:", e);
  }
  try {
    await chrome.scripting.executeScript({
      target: { tabId: tid },
      files: ["of-harvest.js"],
    });
  } catch (e) {
    throw new Error("Could not inject of-harvest.js into OnlyFans tab: " + (e && e.message ? e.message : e));
  }

  setCrawlerStatus("Scrolling OnlyFans...", "info");
  showToast(
    "Scrolling the OnlyFans page to harvest full-resolution URLs. Don't switch tabs until it finishes.",
    "info"
  );

  let result;
  try {
    result = await chrome.tabs.sendMessage(tid, {
      action: "tbcc-of-harvest-autoscroll",
      options: { tickMs: 800, idleTicks: 7, hardCapMs: 240000 },
    });
  } catch (e) {
    throw new Error(
      "OnlyFans harvest failed: " + (e && e.message ? e.message : e) +
      ". Reload the OnlyFans tab (Ctrl+F5) and try again."
    );
  }

  if (!result || result.ok === false) {
    const m = (result && result.error) || "no response from harvest collector";
    throw new Error("OnlyFans harvest failed: " + m);
  }

  const list = Array.isArray(result.list) ? result.list : [];
  const summary = result.summary || {};
  const apiSeen = (summary.meta && summary.meta.apiResponses) || 0;
  const hookSeen = (summary.meta && summary.meta.hookSeen) || 0;
  const apiSamples = (summary.meta && summary.meta.apiUrlSamples) || [];
  console.log(
    `[TBCC] OF harvest: ${list.length} media, ${apiSeen} api responses, hook ${hookSeen} msgs, samples:`,
    apiSamples
  );
  if (!list.length) {
    if (!apiSeen) {
      throw new Error(
        "Harvested 0 API responses. The page-world hook installed mid-page and didn't see any fetches. " +
        "Reload the OnlyFans tab (Ctrl+F5) so it captures the initial requests, then click Crawl again."
      );
    }
    throw new Error(
      "Harvested " + apiSeen + " API responses but no media nodes were found. " +
      "Try a /photos or /videos profile URL, or open a single post first."
    );
  }

  const have = new Set(imageList.map((i) => i && i.url).filter(Boolean));
  const previewUrlIndex = new Map();
  imageList.forEach((row, idx) => {
    const t = row && (row.thumbUrl || row.posterUrl || "");
    if (t) previewUrlIndex.set(String(t).split(/[?#]/)[0], idx);
  });

  let added = 0;
  let upgraded = 0;
  for (const it of list) {
    const u = it && it.url;
    if (!u) continue;
    if (have.has(u)) continue;

    /** Promote: if a previously captured low-res thumb matches this item's preview URL, replace it in place. */
    let replaced = false;
    const previewKey = it.thumbUrl ? String(it.thumbUrl).split(/[?#]/)[0] : "";
    if (previewKey && previewUrlIndex.has(previewKey)) {
      const idx = previewUrlIndex.get(previewKey);
      const prev = imageList[idx];
      if (prev && prev.url !== u) {
        const oldUrl = prev.url;
        prev.url = u;
        prev.mediaType = it.mediaType || prev.mediaType;
        prev.tagName = (prev.mediaType === "video") ? "video" : "img";
        if (it.thumbUrl) prev.thumbUrl = it.thumbUrl;
        if (it.posterUrl) prev.posterUrl = it.posterUrl;
        if (it.width) { prev.width = it.width; prev.naturalWidth = it.width; }
        if (it.height) { prev.height = it.height; prev.naturalHeight = it.height; }
        prev.tbccCaptureSource = "crawler:onlyfans";
        prev.tbccOfMediaId = it.tbccOfMediaId || prev.tbccOfMediaId || "";
        prev.tbccSourcePageUrl = url;
        if (selectedUrls.has(oldUrl)) {
          selectedUrls.delete(oldUrl);
          selectedUrls.add(u);
        }
        have.add(u);
        upgraded++;
        replaced = true;
      }
    }
    if (replaced) continue;

    const row = {
      url: u,
      mediaType: it.mediaType || "image",
      tagName: it.mediaType === "video" ? "video" : "img",
      tabId: currentTabId,
      name: filenameFromUrl(u),
      thumbUrl: it.thumbUrl || u,
      posterUrl: it.posterUrl || it.thumbUrl || "",
      width: it.width || 0,
      height: it.height || 0,
      naturalWidth: it.width || 0,
      naturalHeight: it.height || 0,
      tbccCaptureSource: "crawler:onlyfans",
      tbccSourcePageUrl: url,
      tbccOfMediaId: it.tbccOfMediaId || "",
      tbccOfPostId: it.tbccOfPostId || "",
    };
    imageList.push(row);
    selectedUrls.add(row.url);
    have.add(row.url);
    added++;
  }

  /**
   * Post-pass: any pre-existing imageList row whose `thumbUrl` is huge (it's
   * the same full-res CDN URL the page rendered) blows up the thumb proxy
   * with 3 MB fetches. If we have a harvest entry whose `url` matches the
   * row's `url`, swap in the harvest's small 300×300 preview as thumbUrl.
   *
   * Also: walk every OF row and if thumbUrl looks like a multi-MB variant
   * (path contains /<largeN>x<largeN>/ where N >= 720), prefer any harvested
   * tiny preview that shares the same media id.
   */
  let downgraded = 0;
  const harvestByUrl = new Map();
  const harvestByMediaId = new Map();
  for (const it of list) {
    if (it && it.url) harvestByUrl.set(it.url, it);
    if (it && it.tbccOfMediaId) harvestByMediaId.set(String(it.tbccOfMediaId), it);
  }
  for (const row of imageList) {
    if (!row || !row.url) continue;
    let isOf = false;
    try {
      const hh = new URL(row.url).hostname.toLowerCase();
      isOf = hh.indexOf("onlyfans.com") >= 0 || hh.indexOf("ofcdn") >= 0;
    } catch (_) {}
    if (!isOf) continue;
    const thumb = row.thumbUrl || row.posterUrl || "";
    let looksHuge = !thumb || thumb === row.url;
    if (!looksHuge) {
      const m = thumb.match(/\/(\d{3,4})x(\d{3,4})\//);
      if (m && (Number(m[1]) >= 720 || Number(m[2]) >= 720)) looksHuge = true;
    }
    if (!looksHuge) continue;
    const cand =
      harvestByUrl.get(row.url) ||
      (row.tbccOfMediaId && harvestByMediaId.get(String(row.tbccOfMediaId)));
    if (cand && cand.thumbUrl && cand.thumbUrl !== row.url) {
      row.thumbUrl = cand.thumbUrl;
      if (cand.posterUrl) row.posterUrl = cand.posterUrl;
      downgraded++;
    }
  }

  await persistSelection();
  if (settings.subtabEnabled && activeGalleryTabId != null) snapshotCurrentStateIntoActiveSubtab();
  renderGrid();

  const elapsed = result.summary && result.summary.elapsedMs ? Math.round(result.summary.elapsedMs / 1000) + "s" : "";
  setCrawlerStatus(`+${added} / ${upgraded}↑ / ${downgraded}↓ via onlyfans`, "success");
  showToast(
    `Crawler (onlyfans) added ${added}, upgraded ${upgraded} to full-res, swapped ${downgraded} thumbs to previews${elapsed ? " in " + elapsed : ""}.`,
    "success"
  );
}

async function mergeCrawlerItemsIntoGallery(items, sourceUrl, adapterUsed) {
  const have = new Set(imageList.map((i) => i && i.url).filter(Boolean));
  const added = [];
  for (const item of items) {
    if (!item || !item.url || have.has(item.url)) continue;
    const row = crawlerItemToGalleryItem(item, sourceUrl, adapterUsed);
    imageList.push(row);
    selectedUrls.add(row.url);
    have.add(row.url);
    added.push(row);
  }
  if (added.length) {
    await persistSelection();
    if (settings.subtabEnabled && activeGalleryTabId != null) snapshotCurrentStateIntoActiveSubtab();
    renderGrid();
  }
  return added;
}

async function tryCrawlViaMyjd(url) {
  try {
    const r = await fetch(API_BASE + "/jd/resolve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    const text = await r.text();
    let data = {};
    try {
      data = text ? JSON.parse(text) : {};
    } catch (_) {}
    if (!r.ok) return null;
    const items = Array.isArray(data.items) ? data.items : [];
    if (!items.length) return null;
    const added = await mergeCrawlerItemsIntoGallery(items, data.source_url || url, data.adapter || "myjd");
    setCrawlerStatus(added.length + " via JDownloader", "success");
    showToast(`JDownloader added ${added.length} link(s).`, "success");
    return added;
  } catch (_) {
    return null;
  }
}

async function tbccGalleryHasBlockingImportJobs() {
  const remote = await new Promise((resolve) => {
    chrome.runtime.sendMessage({ action: "tbcc-gallery-job-list" }, (r) => {
      if (chrome.runtime.lastError) resolve([]);
      else resolve((r && r.jobs) || []);
    });
  });
  return remote.some(
    (j) =>
      j &&
      !tbccIsLocalImportJobTerminal(j) &&
      (j.type === "send-batch" ||
        j.stage === "telegram" ||
        j.stage === "queued" ||
        j.stage === "processing" ||
        (j.status === "running" && j.stage === "stored"))
  );
}

async function crawlActiveTab() {
  if (!btnCrawlTab) return;
  const url = await getCurrentTabUrl();
  setCrawlerTabUrlLabel(url);
  if (!url || !/^https?:\/\//i.test(url)) {
    setCrawlerStatus("No http(s) tab", "error");
    showToast("Open a normal https page in the tab you are capturing from, then click Crawl tab.", "info");
    return;
  }
  if (await tbccGalleryHasBlockingImportJobs()) {
    setCrawlerStatus("Wait — pool/saved send in progress", "error");
    showToast("Finish the active TBCC send/import before crawling (reduces Telegram lock storms).", "info");
    return;
  }
  const jobId = await beginGalleryJob("crawl-tab", "Crawl tab");
  btnCrawlTab.disabled = true;
  try {
    const adapterHint = detectCrawlerAdapterHint(url);
    const useCookies = crawlerShouldUseCookiesForUrl(url);
    setCrawlerStatus(
      (adapterHint === "bunkr" ? "Resolving…" : "Crawling…") + (useCookies ? " · cookies" : ""),
      "info"
    );

    /** OnlyFans gets a fully different path: SPA harvest via content script. */
    if (adapterHint === "onlyfans") {
      try {
        await deployOnlyFansFromActiveTab(url, adapterHint);
      } finally {
        btnCrawlTab.disabled = false;
      }
      return;
    }

    const payload = { url, adapter: adapterHint, limit: 500 };
    const finalCookies = await getCrawlerCookiesForHosts(adapterHint, url, useCookies);
    if (finalCookies) payload.cookies = finalCookies;

    const r = await fetch(API_BASE + "/crawler/resolve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const text = await r.text();
    let data = {};
    try {
      data = text ? JSON.parse(text) : {};
    } catch (_) {}
    if (!r.ok) {
      const jd = await tryCrawlViaMyjd(url);
      if (jd && jd.length) return;
      throw new Error((data && data.detail) || text || r.statusText);
    }
    const items = Array.isArray(data.items) ? data.items : [];
    const adapterUsed = data.adapter || adapterHint;
    if (!items.length) {
      const jd = await tryCrawlViaMyjd(url);
      if (jd && jd.length) return;
      const warning = Array.isArray(data.warnings) && data.warnings.length ? data.warnings[0] : "No media found.";
      throw new Error(warning);
    }
    if (Array.isArray(data.warnings)) {
      data.warnings.forEach((w) => showToast(w, "info"));
    }
    const added = await mergeCrawlerItemsIntoGallery(items, data.source_url || url, adapterUsed);
    setCrawlerStatus(added.length + " via " + adapterUsed, "success");
    showToast(
      `Crawler (${adapterUsed}) added ${added.length} media item(s). ` +
        "Use Dest, Send, ZIP, or Download next.",
      "success"
    );
  } catch (e) {
    const msg = e && e.message ? e.message : String(e);
    setCrawlerStatus("Failed", "error");
    showToast("Crawler failed: " + msg, "error");
  } finally {
    btnCrawlTab.disabled = false;
    endGalleryJob(jobId);
  }
}

function formatDimsLabel(item) {
  const w = item.naturalWidth || item.width || 0;
  const h = item.naturalHeight || item.height || 0;
  if (w > 0 && h > 0) return `${w}×${h}`;
  return "…";
}

function formatDurationSeconds(sec) {
  if (sec == null || !Number.isFinite(sec) || sec < 0) return "";
  const s = Math.floor(sec % 60);
  const m = Math.floor((sec / 60) % 60);
  const h = Math.floor(sec / 3600);
  if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  return `${m}:${String(s).padStart(2, "0")}`;
}

/** Video tiles: duration (from schema or element) + dimensions, same pattern for every video cell. */
function formatVideoCellLabel(item, videoEl) {
  let dur = "";
  if (videoEl && Number.isFinite(videoEl.duration) && videoEl.duration > 0) {
    dur = formatDurationSeconds(videoEl.duration);
  } else if (item.durationSec != null && Number.isFinite(item.durationSec) && item.durationSec > 0) {
    dur = formatDurationSeconds(item.durationSec);
  }
  const w = videoEl && videoEl.videoWidth ? videoEl.videoWidth : item.naturalWidth || item.width || 0;
  const h = videoEl && videoEl.videoHeight ? videoEl.videoHeight : item.naturalHeight || item.height || 0;
  const dim = w > 0 && h > 0 ? `${w}×${h}` : "";
  if (dur && dim) return `${dur} · ${dim}`;
  if (dur) return dur;
  if (dim) return dim;
  return "…";
}

function mediaFormatLabel(item, isVideo) {
  const ulow = String(item.url || "").toLowerCase();
  const tlow = String(item.thumbUrl || "").toLowerCase();
  const mime = String(item.type || item.mimeType || "").toLowerCase();
  const name = String(item.name || "").toLowerCase();
  const attachmentExt = extractAttachmentExt(item.url || "") || extractAttachmentExt(item.thumbUrl || "");
  if (attachmentExt) return attachmentExt.toUpperCase();
  if (mime.includes("jpeg") || mime.includes("jpg")) return "JPG";
  if (mime.includes("png")) return "PNG";
  if (mime.includes("webp")) return "WEBP";
  if (mime.includes("gif")) return "GIF";
  if (mime.includes("mp4")) return "MP4";
  if (mime.includes("webm")) return "WEBM";
  if (/\.jpe?g$/i.test(name)) return "JPG";
  if (/\.png$/i.test(name)) return "PNG";
  if (/\.webp$/i.test(name)) return "WEBP";
  if (/\.gif$/i.test(name)) return "GIF";
  if (/\.mp4$/i.test(name)) return "MP4";
  if (/\.webm$/i.test(name)) return "WEBM";
  if (/\.mp4(\?|$)/i.test(ulow)) return "MP4";
  if (/\.webm(\?|$)/i.test(ulow)) return "WEBM";
  if (/\.webp(\?|$)/i.test(ulow)) return "WEBP";
  if (/\.png(\?|$)/i.test(ulow)) return "PNG";
  if (/\.(jpe?g)(\?|$)/i.test(ulow)) return "JPG";
  if (/\.gif(\?|$)/i.test(ulow)) return "GIF";
  if (/\.webp(\?|$)/i.test(tlow)) return "WEBP";
  if (/\.png(\?|$)/i.test(tlow)) return "PNG";
  if (/\.(jpe?g)(\?|$)/i.test(tlow)) return "JPG";
  if (/\.gif(\?|$)/i.test(tlow)) return "GIF";
  if (isVideo) return "VIDEO";
  return "Media";
}

function extractAttachmentExt(rawUrl) {
  try {
    const p = new URL(String(rawUrl || "")).pathname.toLowerCase();
    const m = p.match(/-(jpe?g|png|gif|webp|avif|bmp|mp4|webm|mov|m4v|mkv)\.\d+\/?$/i);
    return m && m[1] ? (m[1] === "jpeg" ? "jpg" : m[1].toLowerCase()) : "";
  } catch (_) {
    return "";
  }
}

function thumbUrlLooksUsable(url) {
  if (!url || typeof url !== "string") return false;
  return /^https?:\/\//i.test(url) || /^blob:/i.test(url) || /^data:/i.test(url);
}

/**
 * Video grid tiles: poster and/or thumb image only. Do not mount a <video> per cell — Chrome caps
 * WebMediaPlayer count (~75+ per document); large grids hit that and previews break entirely.
 * Full playback stays in the lightbox single <video>.
 */
function appendVideoMediaToCell(div, item, dimsEl) {
  const wrap = document.createElement("div");
  wrap.className = "cell-media-wrap";
  let triedThumb = false;

  const markDimsFromImg = (_img) => {
    /**
     * Intentionally do NOT copy poster dimensions onto the item. Posters
     * (e.g. Bunkr's 200×150 thumbs) are unrelated to the underlying video
     * resolution, and previously this leaked tiny dims onto the tile and
     * the filter sort. The real video dims arrive when <video> loads
     * metadata; until then we leave the dims label blank-ish.
     */
    dimsEl.textContent = formatVideoCellLabel(item, null);
    scheduleFilterRerenderFromLazyDims();
  };

  function appendPlaceholder() {
    if (wrap.querySelector(".placeholder")) return;
    const ph = document.createElement("div");
    ph.className = "placeholder";
    ph.textContent = "Video";
    wrap.appendChild(ph);
    dimsEl.textContent = formatVideoCellLabel(item, null);
  }

  function tryThumbOrPlaceholder() {
    const thumb = item.thumbUrl;
    if (!triedThumb && thumb && thumbUrlLooksUsable(thumb) && thumb !== item.posterUrl) {
      triedThumb = true;
      addStill(thumb);
      return;
    }
    appendPlaceholder();
  }

  function addStill(url) {
    if (shouldSkipThumbUrl(url)) {
      tryThumbOrPlaceholder();
      return;
    }
    /** Page `blob:` URLs are not loadable from the extension document — avoids error/flicker loops. */
    if (String(url).startsWith("blob:")) {
      tryThumbOrPlaceholder();
      return;
    }
    const img = document.createElement("img");
    img.className = "cell-video-poster";
    img.alt = "";
    img.loading = "lazy";
    img.decoding = "async";
    img.addEventListener(
      "load",
      () => {
        noteThumbLoadResult(url, true);
        img.classList.add("tbcc-thumb-ready");
        markDimsFromImg(img);
      },
      { once: true }
    );
    img.addEventListener(
      "error",
      () => {
        noteThumbLoadResult(url, false);
        try {
          img.remove();
        } catch (_) {}
        tryThumbOrPlaceholder();
      },
      { once: true }
    );
    if (hostNeedsGalleryThumbProxy(url)) loadThumbViaSession(url, img);
    else {
      img.referrerPolicy = thumbReferrerPolicyForUrl(url);
      img.src = url;
    }
    wrap.appendChild(img);
  }

  if (item.posterUrl && thumbUrlLooksUsable(item.posterUrl)) {
    addStill(item.posterUrl);
  } else if (item.thumbUrl && thumbUrlLooksUsable(item.thumbUrl)) {
    triedThumb = true;
    addStill(item.thumbUrl);
  } else {
    appendPlaceholder();
  }
  div.appendChild(wrap);
}

let __tbccRenderGridCount = 0;
function renderGrid() {
  if (!gridEl) return;
  __tbccRenderGridCount++;
  cancelPendingFilterDimRerender();
  pruneVideoGroupPick();
  const list = getFilteredList();
  const displayRows = getDisplayRows();
  if (settings.debugTileRender) {
    try {
      const stack = new Error().stack || "";
      const caller = stack.split("\n").slice(2, 4).join(" ← ").trim();
      console.log("[tbcc-tile] renderGrid", {
        seq: __tbccRenderGridCount,
        total: imageList.length,
        filtered: list.length,
        rows: displayRows.length,
        selected: selectedUrls.size,
        caller,
      });
    } catch (_) {}
  }
  const gridWidth = gridEl.clientWidth || 280;
  const cols = Math.max(1, Math.min(MAX_COLS, Math.floor(gridWidth / CELL_MIN_PX) || 1));
  gridEl.style.setProperty("--cols", String(cols));
  gridEl.innerHTML = "";
  displayRows.forEach((row, idx) => {
    const item = getItemForDisplayRow(row);
    const activeUrl = getUrlForDisplayRow(row);
    const div = document.createElement("div");
    div.className =
      "cell" +
      (selectedUrls.has(activeUrl) ? " selected" : "") +
      (row.type === "group" ? " cell--folded-video" : "");
    div.dataset.cellIndex = String(idx);
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.className = "cell-check";
    cb.checked = selectedUrls.has(activeUrl);
    // Block native checkbox toggle (otherwise browser + our handler both flip state → inconsistent UI).
    cb.addEventListener("mousedown", (e) => {
      e.preventDefault();
      e.stopPropagation();
    });
    cb.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      e.stopImmediatePropagation();
      handleCellSelectionPointer(e, row, idx);
    });
    div.appendChild(cb);

    if (row.type === "group") {
      const badge = document.createElement("div");
      badge.className = "cell-variant-badge";
      badge.textContent = row.items.length + "×";
      div.appendChild(badge);
    }

    const ulow = String(item.url || "").toLowerCase();
    const isVideo = itemLooksLikeVideo(item);
    const fmt = mediaFormatLabel(item, isVideo);

    const dimsEl = document.createElement("div");
    dimsEl.className = "cell-dims";
    dimsEl.textContent = isVideo ? formatVideoCellLabel(item, null) : formatDimsLabel(item);

    if (isVideo) {
      const play = document.createElement("button");
      play.type = "button";
      play.className = "cell-play";
      play.textContent = "▶";
      play.title = "Preview in lightbox";
      play.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        e.stopImmediatePropagation();
        openLightboxForItem(getItemForDisplayRow(row));
      });
      div.appendChild(play);
      appendVideoMediaToCell(div, item, dimsEl);

      if (row.type === "group") {
        const vr = document.createElement("div");
        vr.className = "cell-variant-row";
        const sel = document.createElement("select");
        sel.className = "cell-variant-select";
        sel.title = "Pick resolution / file";
        for (const it of row.items) {
          const opt = document.createElement("option");
          opt.value = it.url;
          const w = it.naturalWidth || it.width || 0;
          const h = it.naturalHeight || it.height || 0;
          opt.textContent = w > 0 && h > 0 ? `${w}×${h}` : (String(it.url || "").split("/").pop() || "variant").slice(0, 36);
          sel.appendChild(opt);
        }
        sel.value = activeUrl;
        sel.addEventListener("click", (e) => e.stopPropagation());
        sel.addEventListener("mousedown", (e) => e.stopPropagation());
        sel.addEventListener("change", () => {
          const prev = getUrlForDisplayRow(row);
          const next = sel.value;
          videoGroupPick.set(row.key, next);
          if (selectedUrls.has(prev)) {
            selectedUrls.delete(prev);
            selectedUrls.add(next);
          }
          renderGrid();
          updateCountAndSendPersist();
        });
        const allBtn = document.createElement("button");
        allBtn.type = "button";
        allBtn.className = "cell-variants-all";
        allBtn.title = "Select every variant URL";
        allBtn.textContent = "⊞";
        allBtn.addEventListener("click", (e) => {
          e.stopPropagation();
          e.preventDefault();
          for (const it of row.items) selectedUrls.add(it.url);
          renderGrid();
          updateCountAndSendPersist();
        });
        vr.appendChild(sel);
        vr.appendChild(allBtn);
        div.appendChild(vr);
      }
    } else {
      const img = document.createElement("img");
      img.className = "cell-media";
      img.alt = "";
      img.loading = "lazy";
      /**
       * Image rows can carry both `url` and `thumbUrl`; prefer thumbUrl when primary looks like
       * a tiny variant path (e.g. /300x300/), otherwise use primary URL.
       */
      const primaryUrl = String(item.url || "");
      const tinyVariantPath = /\/\d{2,4}x\d{2,4}\//i.test(primaryUrl) || /_\d{2,4}x\d{2,4}\./i.test(primaryUrl);
      const chosenUrl = tinyVariantPath && thumbUrlLooksUsable(item.thumbUrl) ? item.thumbUrl : primaryUrl;
      const skipKnownFail = shouldSkipThumbUrl(chosenUrl);
      if (!skipKnownFail) {
        img.referrerPolicy = thumbReferrerPolicyForUrl(chosenUrl);
        if (hostNeedsGalleryThumbProxy(chosenUrl)) loadThumbViaSession(chosenUrl, img);
        else img.src = chosenUrl;
      }
      applyInsetPreviewStyle(img, item.url);
      if (settings.debugTileRender) {
        try {
          console.log("[tbcc-tile] mount", { url: item.url, mt: item.mediaType, src: img.src, ts: Date.now() });
        } catch (_) {}
      }
      img.onload = () => {
        noteThumbLoadResult(chosenUrl, true);
        if (img.naturalWidth && img.naturalHeight) {
          dimsEl.textContent = `${img.naturalWidth}×${img.naturalHeight}`;
          item.naturalWidth = img.naturalWidth;
          item.naturalHeight = img.naturalHeight;
          if (!item.width || item.width < img.naturalWidth) item.width = img.naturalWidth;
          if (!item.height || item.height < img.naturalHeight) item.height = img.naturalHeight;
          scheduleFilterRerenderFromLazyDims();
          if (settings.debugTileRender) {
            try {
              console.log("[tbcc-tile] load-ok", {
                url: item.url,
                nw: img.naturalWidth,
                nh: img.naturalHeight,
                ts: Date.now(),
              });
            } catch (_) {}
          }
        }
      };
      img.onerror = () => {
        noteThumbLoadResult(chosenUrl, false);
        if (settings.debugTileRender) {
          try {
            console.warn("[tbcc-tile] load-err", { url: item.url, src: img.src, ts: Date.now() });
          } catch (_) {}
        }
        const ph = document.createElement("div");
        ph.className = "placeholder";
        ph.textContent = "—";
        div.appendChild(ph);
        img.remove();
      };
      if (skipKnownFail) {
        const ph = document.createElement("div");
        ph.className = "placeholder";
        ph.textContent = "—";
        div.appendChild(ph);
      } else {
        div.appendChild(img);
      }
    }
    const hover = document.createElement("div");
    hover.className = "cell-hover-meta";
    const sm = document.createElement("strong");
    sm.textContent = fmt;
    hover.appendChild(sm);
    hover.appendChild(document.createElement("br"));
    hover.appendChild(document.createTextNode(dimsEl.textContent || "…"));
    if (item.file && item.file.size) {
      hover.appendChild(document.createElement("br"));
      hover.appendChild(document.createTextNode(Math.round(item.file.size / 1024) + " KB"));
    }
    div.appendChild(hover);
    const nameEl = document.createElement("span");
    nameEl.className = "tbcc-details-name";
    const fn = String((item.url || "").split(/[?#]/)[0].split("/").pop() || "");
    nameEl.textContent = fn || item.url || "";
    const sub = document.createElement("small");
    const subBits = [];
    if (fmt) subBits.push(fmt);
    if (Number.isFinite(item.durationSec) && item.durationSec > 0) subBits.push(formatDurationSeconds(item.durationSec));
    subBits.push(dimsEl.textContent || "…");
    sub.textContent = subBits.filter(Boolean).join(" · ");
    nameEl.appendChild(sub);
    div.appendChild(nameEl);
    div.appendChild(dimsEl);
    div.addEventListener("click", (e) => {
      if (e.target === cb || (cb && cb.contains && cb.contains(e.target))) return;
      if (e.target.closest && e.target.closest(".cell-variant-row")) return;
      /**
       * Selection click can re-render the grid immediately, which can prevent native dblclick
       * from firing on the same DOM node. Use click.detail===2 as a stable fallback.
       */
      if (e.detail >= 2) {
        e.preventDefault();
        e.stopPropagation();
        openLightboxForItem(getItemForDisplayRow(row));
        return;
      }
      handleCellSelectionPointer(e, row, idx);
    });
    div.addEventListener("dblclick", (e) => {
      if (e.target === cb || (cb && cb.contains && cb.contains(e.target))) return;
      if (e.target.closest && e.target.closest(".cell-variant-row")) return;
      e.preventDefault();
      e.stopPropagation();
      openLightboxForItem(getItemForDisplayRow(row));
    });
    gridEl.appendChild(div);
  });
  updateCountAndSend();
  const selInView = selectedCountInFilteredList();
  if (selectAllCb) selectAllCb.checked = list.length > 0 && selInView === list.length;
  if (selectAllCb) selectAllCb.indeterminate = list.length > 0 && selInView > 0 && selInView < list.length;
  syncFoldToggleLabel();
}

function updateCountAndSend(opts) {
  const rows = getDisplayRows();
  const selInView = selectedCountInFilteredList();
  if (selectionChip) selectionChip.textContent = selInView + " / " + rows.length + " selected";
  if (btnSend) btnSend.disabled = selInView === 0;
  if (btnDownload) btnDownload.disabled = selInView === 0;
  if (btnDownloadZip) btnDownloadZip.disabled = selInView === 0;
  if (btnCopyJd) btnCopyJd.disabled = selInView === 0;
  if (btnSelectToggle) {
    btnSelectToggle.disabled = rows.length === 0;
    const allSelected = rows.length > 0 && selInView === rows.length;
    btnSelectToggle.textContent = allSelected ? "Deselect all" : "Select all";
    btnSelectToggle.title = allSelected
      ? "Clear selection from visible items"
      : "Select all visible items";
  }
  if (btnSelectAnchorToggle) {
    btnSelectAnchorToggle.disabled = rows.length === 0;
    const idx = rows.length ? Math.min(Math.max(0, lastSelectionAnchorIndex), rows.length - 1) : 0;
    const anchorUrl = rows.length ? getUrlForDisplayRow(rows[idx]) : "";
    const anchorOn = !!(anchorUrl && selectedUrls.has(anchorUrl));
    btnSelectAnchorToggle.title = rows.length
      ? anchorOn
        ? "Deselect anchor tile (row " + (idx + 1) + " of " + rows.length + ")"
        : "Select anchor tile (row " + (idx + 1) + " of " + rows.length + ")"
      : "Toggle selection on anchor tile (last clicked row)";
  }
  updateSendButtonLabel();
  updateTelegramPostControls();
  updateActionBarVisibility();
  updateActionBarSubtitle();
  syncCropOverflowLabel();
  if (cropPopover && cropPopover.classList.contains("visible")) initCropStudioPanel();
  if (opts && opts.persistSelection) persistSelection();
}

function updateCountAndSendPersist() {
  updateCountAndSend({ persistSelection: true });
}

function runSelectToggle() {
  const rows = getDisplayRows();
  if (!rows.length) return;
  const urls = rows.map((row) => getUrlForDisplayRow(row)).filter(Boolean);
  if (!urls.length) return;
  const selInView = selectedCountInFilteredList();
  const allSelected = selInView === urls.length;
  if (allSelected) {
    urls.forEach((u) => selectedUrls.delete(u));
    lastSelectionAnchorIndex = 0;
  } else {
    urls.forEach((u) => selectedUrls.add(u));
  }
  renderGrid();
  updateCountAndSendPersist();
}

function runSelectAnchorToggle() {
  const rows = getDisplayRows();
  if (!rows.length) return;
  const idx = Math.min(Math.max(0, lastSelectionAnchorIndex), rows.length - 1);
  const url = getUrlForDisplayRow(rows[idx]);
  if (!url) return;
  if (selectedUrls.has(url)) selectedUrls.delete(url);
  else selectedUrls.add(url);
  renderGrid();
  updateCountAndSendPersist();
}

function galleryCtxMenuIgnoresTarget(target) {
  if (!target || !target.closest) return true;
  if (target.closest("input, textarea, select")) return true;
  if (target.closest("[contenteditable='true']")) return true;
  if (target.closest(".gallery-panel-nav")) return true;
  return false;
}

/** Chromium blocks aria-hidden while a descendant has focus; clear focus first. */
function releaseFocusFromContainer(container) {
  if (!container) return;
  const ae = document.activeElement;
  if (!ae || !container.contains(ae)) return;
  try {
    ae.blur();
  } catch (_) {}
}

function closeGalleryContextMenu() {
  if (!galleryCtxMenu) return;
  releaseFocusFromContainer(galleryCtxMenu);
  galleryCtxMenu.hidden = true;
  galleryCtxMenu.setAttribute("aria-hidden", "true");
}

function syncGalleryContextMenuItems() {
  if (!galleryCtxMenu) return;
  const syncDisabled = (ctx, btn) => {
    const el = galleryCtxMenu.querySelector(`[data-ctx="${ctx}"]`);
    if (el && btn) el.disabled = !!btn.disabled;
  };
  syncDisabled("download", btnDownload);
  syncDisabled("zip", btnDownloadZip);
  syncDisabled("copyJd", btnCopyJd);
  syncDisabled("send", btnSend);
  syncDisabled("selectToggle", btnSelectToggle);
  syncDisabled("selectAnchorToggle", btnSelectAnchorToggle);
  const st = galleryCtxMenu.querySelector('[data-ctx="selectToggle"]');
  if (st && btnSelectToggle) st.textContent = btnSelectToggle.textContent || "Select all";
}

function openGalleryContextMenu(clientX, clientY) {
  if (!galleryCtxMenu) return;
  syncGalleryContextMenuItems();
  galleryCtxMenu.hidden = false;
  galleryCtxMenu.setAttribute("aria-hidden", "false");
  galleryCtxMenu.style.left = `${clientX}px`;
  galleryCtxMenu.style.top = `${clientY}px`;
  const place = () => {
    const inner = galleryCtxMenu.querySelector(".tbcc-gallery-ctx-menu__inner");
    const rect = (inner || galleryCtxMenu).getBoundingClientRect();
    const w = rect.width;
    const h = rect.height;
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    let left = clientX;
    let top = clientY;
    if (left + w > vw - 6) left = Math.max(6, vw - w - 6);
    if (top + h > vh - 6) top = Math.max(6, vh - h - 6);
    if (left < 6) left = 6;
    if (top < 6) top = 6;
    galleryCtxMenu.style.left = `${left}px`;
    galleryCtxMenu.style.top = `${top}px`;
  };
  requestAnimationFrame(() => requestAnimationFrame(place));
}

function onGalleryContextMenuAction(key) {
  closeGalleryContextMenu();
  switch (key) {
    case "refresh":
      btnRefresh && btnRefresh.click();
      return;
    case "overlay":
      btnToggleOverlay && btnToggleOverlay.click();
      return;
    case "selectToggle":
      btnSelectToggle && btnSelectToggle.click();
      return;
    case "selectAnchorToggle":
      btnSelectAnchorToggle && !btnSelectAnchorToggle.disabled && runSelectAnchorToggle();
      return;
    case "selectAllPage":
      btnSelectAllOnPage && btnSelectAllOnPage.click();
      return;
    case "download":
      btnDownload && btnDownload.click();
      return;
    case "zip":
      btnDownloadZip && btnDownloadZip.click();
      return;
    case "copyJd":
      btnCopyJd && btnCopyJd.click();
      return;
    case "send":
      btnSend && btnSend.click();
      return;
    case "filter":
      btnFilterToggle && btnFilterToggle.click();
      return;
    case "fold":
      btnToggleFoldVariants && btnToggleFoldVariants.click();
      return;
    case "crop":
      btnCropOverflow && btnCropOverflow.click();
      return;
    case "addFiles":
      btnAddFilesOverflow && btnAddFilesOverflow.click();
      return;
    case "telegram":
      btnTelegramSheetOpen && btnTelegramSheetOpen.click();
      return;
    case "inbox":
      openSavedUrlInboxSheet(true);
      return;
    case "options":
      btnOpenCaptureSettings && btnOpenCaptureSettings.click();
      return;
    case "help":
      btnGalleryHelp && btnGalleryHelp.click();
      return;
    default:
  }
}

function filenameFromUrl(url) {
  try {
    const u = new URL(url);
    const seg = u.pathname.split("/").filter(Boolean).pop() || "media";
    const clean = seg.split("?")[0].replace(/[^\w.\-]+/g, "_") || "media";
    const m = clean.match(/^(.+)-((?:jpe?g|jpg|png|gif|webp|avif|bmp|mp4|webm|mov|m4v|mkv))\.\d+$/i);
    if (m && m[1] && m[2]) {
      const stem = m[1].replace(/[^\w.\-]+/g, "_") || "media";
      const ext = m[2].toLowerCase() === "jpeg" ? "jpg" : m[2].toLowerCase();
      return `${stem}.${ext}`;
    }
    return clean;
  } catch (_) {
    return "media";
  }
}

/** Trim pct% off left, right, top, and bottom (each edge), after any manual crop step. */
function shouldApplyPercentInsetCrop() {
  return !!settings.cropBottomEnabled && Number(settings.cropBottomPercent) > 0;
}

function currentInsetPercent() {
  return Math.max(0, Math.min(49, Number(settings.cropBottomPercent) || 0));
}

function currentInsetMode() {
  const m = String(settings.cropInsetMode || "all").toLowerCase();
  return m === "top" || m === "right" || m === "bottom" || m === "left" ? m : "all";
}

function currentInsetPercents() {
  const p = currentInsetPercent();
  const mode = currentInsetMode();
  if (mode === "top") return { top: p, right: 0, bottom: 0, left: 0 };
  if (mode === "right") return { top: 0, right: p, bottom: 0, left: 0 };
  if (mode === "bottom") return { top: 0, right: 0, bottom: p, left: 0 };
  if (mode === "left") return { top: 0, right: 0, bottom: 0, left: p };
  return { top: p, right: p, bottom: p, left: p };
}

function applyInsetPreviewStyle(imgEl, url) {
  if (!imgEl) return;
  imgEl.style.removeProperty("clip-path");
  imgEl.style.removeProperty("transform");
  imgEl.style.removeProperty("transform-origin");
  if (!shouldApplyImagePipelineForUrl(url)) return;
  const inset = currentInsetPercents();
  const active = inset.top + inset.right + inset.bottom + inset.left;
  if (active <= 0) return;
  const scaleX = 1 / Math.max(0.02, 1 - (inset.left + inset.right) / 100);
  const scaleY = 1 / Math.max(0.02, 1 - (inset.top + inset.bottom) / 100);
  imgEl.style.clipPath = `inset(${inset.top}% ${inset.right}% ${inset.bottom}% ${inset.left}%)`;
  imgEl.style.transform = `scale(${scaleX.toFixed(4)}, ${scaleY.toFixed(4)})`;
  imgEl.style.transformOrigin = "center center";
}

function editsHasWork(e) {
  if (!e || typeof e !== "object") return false;
  if (e.manualCrop && typeof e.manualCrop === "object") {
    const m = e.manualCrop;
    if (Number(m.w) > 0.01 && Number(m.h) > 0.01) return true;
  }
  if (Array.isArray(e.blurs) && e.blurs.length) return true;
  if (Array.isArray(e.texts) && e.texts.length) return true;
  return false;
}

function getImageEdits(url) {
  if (!url) return null;
  return imageEdits[url] || null;
}

function shouldApplyImagePipelineForUrl(url) {
  return shouldApplyPercentInsetCrop() || editsHasWork(getImageEdits(url));
}

function globalImagePipelineActive() {
  if (shouldApplyPercentInsetCrop()) return true;
  for (const k of Object.keys(imageEdits)) {
    if (editsHasWork(imageEdits[k])) return true;
  }
  return false;
}

function syncCropOverflowLabel() {
  if (!btnCropOverflow) return;
  const on = globalImagePipelineActive();
  btnCropOverflow.textContent = "\u2702";
  btnCropOverflow.classList.toggle("tbcc-tool-active", on);
  btnCropOverflow.title = on ? "Crop and watermarks (edits active)" : "Crop and watermarks";
}

function normManualCrop(m) {
  if (!m || typeof m !== "object") return null;
  let x = Number(m.x),
    y = Number(m.y),
    w = Number(m.w),
    h = Number(m.h);
  if (![x, y, w, h].every((n) => Number.isFinite(n))) return null;
  x = Math.max(0, Math.min(1, x));
  y = Math.max(0, Math.min(1, y));
  w = Math.max(0.02, Math.min(1, w));
  h = Math.max(0.02, Math.min(1, h));
  if (x + w > 1) w = 1 - x;
  if (y + h > 1) h = 1 - y;
  return { x, y, w, h };
}

function tbccBlurRect(ctx, cw, ch, bx, by, bw, bh) {
  bx = Math.max(0, Math.floor(bx));
  by = Math.max(0, Math.floor(by));
  bw = Math.max(1, Math.floor(bw));
  bh = Math.max(1, Math.floor(bh));
  bw = Math.min(bw, cw - bx);
  bh = Math.min(bh, ch - by);
  const temp = document.createElement("canvas");
  temp.width = bw;
  temp.height = bh;
  const tctx = temp.getContext("2d");
  tctx.drawImage(ctx.canvas, bx, by, bw, bh, 0, 0, bw, bh);
  const blurCanvas = document.createElement("canvas");
  blurCanvas.width = bw;
  blurCanvas.height = bh;
  const bctx = blurCanvas.getContext("2d");
  bctx.filter = "blur(14px)";
  bctx.drawImage(temp, 0, 0);
  ctx.drawImage(blurCanvas, bx, by);
}

/**
 * Optional same inset % on all four edges, then manual crop / blur / text — send, saved batch, ZIP, download.
 */
async function applyImagePipeline(blob, url) {
  const edits = getImageEdits(url);
  const wantInset = shouldApplyPercentInsetCrop();
  if (!wantInset && !editsHasWork(edits)) return blob;

  try {
    const bmp = await createImageBitmap(blob);
    try {
      const w0 = bmp.width;
      const h0 = bmp.height;
      const mc = edits ? normManualCrop(edits.manualCrop) : null;
      let sx = 0,
        sy = 0,
        sw = w0,
        sh = h0;
      if (mc) {
        sx = Math.floor(mc.x * w0);
        sy = Math.floor(mc.y * h0);
        sw = Math.max(1, Math.floor(mc.w * w0));
        sh = Math.max(1, Math.floor(mc.h * h0));
        sx = Math.min(sx, w0 - 1);
        sy = Math.min(sy, h0 - 1);
        sw = Math.min(sw, w0 - sx);
        sh = Math.min(sh, h0 - sy);
      }

      const c1 = document.createElement("canvas");
      c1.width = sw;
      c1.height = sh;
      const ctx1 = c1.getContext("2d");
      ctx1.drawImage(bmp, sx, sy, sw, sh, 0, 0, sw, sh);

      let offX = 0,
        offY = 0,
        keepW = sw,
        keepH = sh;
      if (wantInset) {
        const inset = currentInsetPercents();
        const offL = Math.floor((sw * inset.left) / 100);
        const offR = Math.floor((sw * inset.right) / 100);
        const offT = Math.floor((sh * inset.top) / 100);
        const offB = Math.floor((sh * inset.bottom) / 100);
        offX = offL;
        offY = offT;
        keepW = Math.max(1, sw - offL - offR);
        keepH = Math.max(1, sh - offT - offB);
      }

      const c2 = document.createElement("canvas");
      c2.width = keepW;
      c2.height = keepH;
      const ctx2 = c2.getContext("2d");
      ctx2.drawImage(c1, offX, offY, keepW, keepH, 0, 0, keepW, keepH);

      const mapOriginalNormRectToOutput = (nx, ny, nw, nh) => {
        let ox1 = nx * w0,
          oy1 = ny * h0,
          ox2 = (nx + nw) * w0,
          oy2 = (ny + nh) * h0;
        ox1 = Math.max(ox1, sx);
        oy1 = Math.max(oy1, sy);
        ox2 = Math.min(ox2, sx + sw);
        oy2 = Math.min(oy2, sy + sh);
        if (ox2 <= ox1 || oy2 <= oy1) return null;
        let c1x1 = ox1 - sx,
          c1y1 = oy1 - sy,
          c1x2 = ox2 - sx,
          c1y2 = oy2 - sy;
        c1x1 = Math.max(c1x1, offX);
        c1y1 = Math.max(c1y1, offY);
        c1x2 = Math.min(c1x2, offX + keepW);
        c1y2 = Math.min(c1y2, offY + keepH);
        if (c1x2 <= c1x1 || c1y2 <= c1y1) return null;
        return { x: c1x1 - offX, y: c1y1 - offY, w: c1x2 - c1x1, h: c1y2 - c1y1 };
      };

      const blurs = edits && Array.isArray(edits.blurs) ? edits.blurs : [];
      for (const br of blurs) {
        const r = mapOriginalNormRectToOutput(Number(br.x), Number(br.y), Number(br.w), Number(br.h));
        if (!r || r.w < 2 || r.h < 2) continue;
        tbccBlurRect(ctx2, keepW, keepH, r.x, r.y, r.w, r.h);
      }

      const texts = edits && Array.isArray(edits.texts) ? edits.texts : [];
      for (const t of texts) {
        const tx = Number(t.x),
          ty = Number(t.y);
        if (!Number.isFinite(tx) || !Number.isFinite(ty)) continue;
        const px = tx * w0 - sx - offX;
        const py = ty * h0 - sy - offY;
        if (px < -8 || py < -8 || px > keepW + 8 || py > keepH + 8) continue;
        const fontPx = Math.max(8, Math.min(160, Number(t.fontPx) || 18));
        ctx2.font = `bold ${fontPx}px sans-serif`;
        ctx2.fillStyle = String(t.color || "#ffffff");
        ctx2.shadowColor = "rgba(0,0,0,0.85)";
        ctx2.shadowBlur = 4;
        ctx2.shadowOffsetX = 1;
        ctx2.shadowOffsetY = 1;
        const txt = String(t.text || "").slice(0, 200);
        ctx2.fillText(txt, px, py);
        ctx2.shadowBlur = 0;
      }

      const out = await new Promise((res) => c2.toBlob((b) => res(b), "image/jpeg", 0.92));
      return out || blob;
    } finally {
      bmp.close();
    }
  } catch (_) {
    return blob;
  }
}

function isImageItem(it) {
  if (!it) return false;
  if (it.mediaType === "video" || String(it.tagName || "").toLowerCase() === "video") return false;
  const u = String(it.url || "");
  if (/\.(mp4|webm|mov|m4v|mkv)(\?|$)/i.test(u)) return false;
  return true;
}

function importResponseOk(data) {
  return (
    (data.status === "imported" || data.status === "skipped" || data.status === "saved_only") && !data.error
  );
}

async function postImportBytes(blob, filename, poolId, savedOnly, source, captionOverride, galleryJobId) {
  const form = new FormData();
  form.append("file", blob, filename);
  form.append("pool_id", String(poolId));
  form.append("saved_only", savedOnly ? "true" : "false");
  form.append("source", source || "extension:upload-cropped");
  if (savedOnly) appendCaptionToSavedForm(form, captionOverride);
  if (typeof tbccPostImportForm === "function") {
    return tbccPostImportForm(form, galleryJobId || null);
  }
  const r = await fetch(API_BASE + "/import/bytes", { method: "POST", body: form });
  return parseImportResponse(r);
}

function filenameForCropUrl(url) {
  const n = filenameFromUrl(url);
  if (/\.(jpe?g)$/i.test(n)) return n;
  return (n.replace(/\.[^.]+$/, "") || "media") + ".jpg";
}

function tbccIsEromeMediaUrl(url) {
  try {
    const h = new URL(String(url || "")).hostname.toLowerCase();
    return h === "erome.com" || h.endsWith(".erome.com");
  } catch (_) {
    return false;
  }
}

function tbccEromeAlbumFromMediaUrl(url) {
  try {
    const u = new URL(url);
    const h = u.hostname.toLowerCase();
    if (h !== "erome.com" && !h.endsWith(".erome.com")) return "";
    const parts = u.pathname.split("/").filter(Boolean);
    if (parts.length < 2) return "";
    const last = parts[parts.length - 1].toLowerCase();
    if (!/\.(mp4|webm|mov|m4v|mkv|jpe?g|png|gif|webp)$/i.test(last)) return "";
    let album = parts[parts.length - 2];
    if (/^\d+$/.test(album) && parts.length >= 3) album = parts[parts.length - 3];
    if (!album) return "";
    return `https://www.erome.com/a/${encodeURIComponent(album)}`;
  } catch (_) {
    return "";
  }
}

async function tbccRefererPageForItem(it) {
  if (!it) return "";
  const mediaUrl = String(it.url || "");
  if (tbccIsEromeMediaUrl(mediaUrl)) {
    if (it.detailPageUrl && /\/a\/[^/]+/i.test(String(it.detailPageUrl))) {
      return String(it.detailPageUrl).split("#")[0];
    }
    const derived = tbccEromeAlbumFromMediaUrl(mediaUrl);
    if (derived) return derived;
    const src = it.tbccSourcePageUrl && String(it.tbccSourcePageUrl);
    if (src && /^https?:\/\//i.test(src)) {
      try {
        const sh = new URL(src).hostname.toLowerCase();
        if (sh === "erome.com" || sh.endsWith(".erome.com")) return src.split("#")[0];
      } catch (_) {}
    }
    return "";
  }
  if (it.tbccSourcePageUrl && /^https?:\/\//i.test(String(it.tbccSourcePageUrl))) {
    return String(it.tbccSourcePageUrl).split("#")[0];
  }
  const tid = it.tabId;
  if (tid != null && tid !== "" && Number.isFinite(Number(tid))) {
    try {
      const tab = await chrome.tabs.get(Number(tid));
      const u = tab && tab.url;
      if (u && /^https?:\/\//i.test(u)) return String(u).split("#")[0];
    } catch (_) {}
  }
  return "";
}

async function fetchUrlBytesToBlob(url, refererPageUrl) {
  url = normalizeTbccMediaUrlForImport(url);
  const ref = typeof refererPageUrl === "string" ? refererPageUrl : "";
  if (url && String(url).startsWith("data:")) {
    try {
      const r = await fetch(url);
      if (r.ok) return await r.blob();
    } catch (_) {}
  }
  try {
    const r = await fetch(url, { credentials: "omit", mode: "cors" });
    if (r.ok) return await r.blob();
  } catch (_) {}
  return new Promise((resolve) => {
    chrome.runtime.sendMessage({ action: "tbcc-content-fetch-bytes", url, refererPageUrl: ref }, (res) => {
      if (chrome.runtime.lastError) {
        resolve(null);
        return;
      }
      if (res && res.ok && res.buffer) {
        resolve(new Blob([res.buffer], { type: "application/octet-stream" }));
      } else resolve(null);
    });
  });
}

/**
 * One gallery item → blob + entry name for ZIP (reuses fetchUrlBytesToBlob for http(s) CORS fallback).
 */
async function getBlobAndNameForZipItem(it, idx, twitterBlobRetry) {
  const n = idx + 1;
  const pad = String(n).padStart(3, "0");
  if (it.file) {
    const raw = (it.name || "file").replace(/[^\w.\-]+/g, "_");
    const safe = raw || "file";
    let blob = it.file;
    if (isImageItem(it) && shouldApplyImagePipelineForUrl(it.url)) {
      try {
        blob = await applyImagePipeline(
          new Blob([await it.file.arrayBuffer()], { type: it.file.type || "application/octet-stream" }),
          it.url
        );
      } catch (_) {}
    }
    const nameOut =
      isImageItem(it) && shouldApplyImagePipelineForUrl(it.url)
        ? /\.(jpe?g)$/i.test(safe)
          ? safe
          : (safe.replace(/\.[^.]+$/, "") || "file") + ".jpg"
        : safe;
    return { filename: pad + "_" + nameOut, blob };
  }
  if (it.url && String(it.url).startsWith("data:image/")) {
    try {
      const r = await fetch(it.url);
      let blob = await r.blob();
      if (isImageItem(it) && shouldApplyImagePipelineForUrl(it.url)) {
        try {
          blob = await applyImagePipeline(blob, it.url);
        } catch (_) {}
      }
      return {
        filename: (pad + "_" + filenameForCropUrl(it.url)).replace(/[^\w.\-]+/g, "_"),
        blob,
      };
    } catch (e) {
      throw new Error("Could not read data URL: " + (e.message || String(e)));
    }
  }
  if (it.url && it.url.startsWith("blob:")) {
    if (!twitterBlobRetry) {
      const tw = await tbccTryResolveBlobVideoViaTwitterNet(it);
      if (tw) {
        it.url = tw;
        it.mediaType = "video";
        it.tagName = "video";
        return getBlobAndNameForZipItem(it, idx, true);
      }
    }
    const r = await fetch(it.url);
    let blob = await r.blob();
    if (isImageItem(it) && shouldApplyImagePipelineForUrl(it.url)) {
      try {
        blob = await applyImagePipeline(blob, it.url);
      } catch (_) {}
    }
    const ext = isImageItem(it) && shouldApplyImagePipelineForUrl(it.url) ? ".jpg" : "";
    return { filename: pad + "_media" + ext, blob };
  }
  if (it.url && (it.url.startsWith("http://") || it.url.startsWith("https://"))) {
    const httpFetchUrl = bestHttpMediaUrlForItem(it) || it.url;
    if (
      typeof tbccIsLikelyHtmlPageUrl === "function" &&
      (it.mediaType === "video" || String(it.tagName || "").toLowerCase() === "video") &&
      tbccIsLikelyHtmlPageUrl(httpFetchUrl)
    ) {
      throw new Error(
        "URL looks like a video page (HTML), not a direct file — use a resolved stream URL or another downloader."
      );
    }
    const url = normalizeTbccMediaUrlForImport(httpFetchUrl);
    const refPage = await tbccRefererPageForItem(it);
    let blob = await fetchUrlBytesToBlob(url, refPage);
    if (!blob) throw new Error("Could not fetch: " + String(httpFetchUrl).slice(0, 96));
    if (isImageItem(it) && shouldApplyImagePipelineForUrl(it.url)) {
      try {
        blob = await applyImagePipeline(blob, it.url);
      } catch (_) {}
      return {
        filename: (pad + "_" + filenameForCropUrl(it.url)).replace(/[^\w.\-]+/g, "_"),
        blob,
      };
    }
    const base = filenameFromUrl(httpFetchUrl);
    const ext = it.mediaType === "video" || String(it.tagName || "").toLowerCase() === "video" ? ".mp4" : "";
    const hasExt = /\.\w{2,5}$/i.test(base);
    const filename = pad + "_" + (hasExt ? base : base + ext);
    return { filename: filename.replace(/[^\w.\-]+/g, "_"), blob };
  }
  throw new Error("Unsupported item for ZIP");
}

function syncCropUiFromSettings() {
  if (cropBottomEnabled) cropBottomEnabled.checked = !!settings.cropBottomEnabled;
  if (cropBottomPercent) {
    const v = Math.max(0, Math.min(49, Number(settings.cropBottomPercent) || 8));
    cropBottomPercent.value = String(v);
  }
  if (cropInsetMode) cropInsetMode.value = currentInsetMode();
}

function persistCropSettings() {
  settings.cropBottomEnabled = !!(cropBottomEnabled && cropBottomEnabled.checked);
  let v = cropBottomPercent ? parseInt(cropBottomPercent.value, 10) : 8;
  if (isNaN(v)) v = 8;
  settings.cropBottomPercent = Math.max(0, Math.min(49, v));
  if (cropInsetMode) settings.cropInsetMode = cropInsetMode.value || "all";
  settings.cropInsetMode = currentInsetMode();
  if (cropBottomPercent) cropBottomPercent.value = String(settings.cropBottomPercent);
  chrome.storage.local.set({ [STORAGE_SETTINGS]: settings });
  syncCropOverflowLabel();
  if (cropStudioActiveUrl && cropPreviewImg) {
    applyInsetPreviewStyle(cropPreviewImg, cropStudioActiveUrl);
  }
  renderGrid();
}

function persistImageEdits() {
  chrome.storage.local.set({ [STORAGE_IMAGE_EDITS]: imageEdits });
  syncCropOverflowLabel();
}

function ensureImageEdit(url) {
  if (!url) return null;
  if (!imageEdits[url]) imageEdits[url] = { blurs: [], texts: [] };
  if (!Array.isArray(imageEdits[url].blurs)) imageEdits[url].blurs = [];
  if (!Array.isArray(imageEdits[url].texts)) imageEdits[url].texts = [];
  return imageEdits[url];
}

function getCropStudioItems() {
  return getFilteredList().filter((i) => selectedUrls.has(i.url) && isImageItem(i));
}

function layoutCropOverlayCanvas() {
  if (!cropPreviewImg || !cropOverlayCanvas || !cropPreviewFrame) return;
  const w = cropPreviewImg.clientWidth;
  const h = cropPreviewImg.clientHeight;
  if (w < 2 || h < 2) return;
  cropOverlayCanvas.style.width = w + "px";
  cropOverlayCanvas.style.height = h + "px";
  cropOverlayCanvas.width = Math.round(w);
  cropOverlayCanvas.height = Math.round(h);
}

function drawCropStudioOverlay() {
  if (!cropOverlayCanvas) return;
  const ctx = cropOverlayCanvas.getContext("2d");
  if (!ctx) return;
  ctx.clearRect(0, 0, cropOverlayCanvas.width, cropOverlayCanvas.height);
  const W = cropOverlayCanvas.width;
  const H = cropOverlayCanvas.height;
  if (W < 2 || H < 2) return;
  const ed = cropStudioActiveUrl ? getImageEdits(cropStudioActiveUrl) : null;
  if (ed && ed.manualCrop) {
    const m = ed.manualCrop;
    ctx.strokeStyle = "#89b4fa";
    ctx.lineWidth = 2;
    ctx.setLineDash([6, 4]);
    ctx.strokeRect(m.x * W, m.y * H, m.w * W, m.h * H);
    ctx.setLineDash([]);
  }
  if (ed && ed.blurs) {
    ctx.strokeStyle = "#fab387";
    ctx.lineWidth = 2;
    for (const b of ed.blurs) {
      ctx.strokeRect(b.x * W, b.y * H, b.w * W, b.h * H);
    }
  }
  if (ed && ed.texts) {
    ctx.fillStyle = "rgba(205, 214, 244, 0.9)";
    ctx.font = "12px sans-serif";
    let i = 0;
    for (const t of ed.texts) {
      const tx = t.x * W;
      const ty = t.y * H;
      ctx.fillText(String(t.text || "").slice(0, 24) + (String(t.text || "").length > 24 ? "…" : ""), tx, ty);
      i++;
    }
  }
  if (cropStudioDrag && cropStudioDrag.cur) {
    const { x0, y0, x1, y1 } = cropStudioDrag.cur;
    const xa = Math.min(x0, x1);
    const ya = Math.min(y0, y1);
    const xb = Math.max(x0, x1);
    const yb = Math.max(y0, y1);
    ctx.strokeStyle = "#cba6f7";
    ctx.setLineDash([4, 4]);
    ctx.strokeRect(xa, ya, xb - xa, yb - ya);
    ctx.setLineDash([]);
  }
}

function refreshCropStudioThumbs() {
  if (!cropStudioThumbs) return;
  cropStudioThumbs.innerHTML = "";
  const items = getCropStudioItems();
  if (cropStudioEmptyHint) cropStudioEmptyHint.hidden = items.length > 0;
  if (!items.length) {
    cropStudioActiveUrl = null;
    if (cropPreviewImg) cropPreviewImg.removeAttribute("src");
    drawCropStudioOverlay();
    return;
  }
  if (!cropStudioActiveUrl || !items.some((i) => i.url === cropStudioActiveUrl)) {
    cropStudioActiveUrl = items[0].url;
  }
  for (const it of items) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "crop-studio-thumb" + (it.url === cropStudioActiveUrl ? " active" : "");
    b.title = (it.name || it.url || "").slice(0, 80);
    const im = document.createElement("img");
    im.alt = "";
    im.src = it.url;
    applyInsetPreviewStyle(im, it.url);
    b.appendChild(im);
    if (editsHasWork(getImageEdits(it.url))) {
      const dot = document.createElement("span");
      dot.className = "crop-studio-thumb-badge";
      b.appendChild(dot);
    }
    b.addEventListener("click", () => {
      cropStudioActiveUrl = it.url;
      refreshCropStudioThumbs();
      loadCropStudioPreview(it.url);
    });
    cropStudioThumbs.appendChild(b);
  }
  loadCropStudioPreview(cropStudioActiveUrl);
}

function loadCropStudioPreview(url) {
  if (!cropPreviewImg || !url) return;
  cropPreviewImg.onload = () => {
    applyInsetPreviewStyle(cropPreviewImg, url);
    layoutCropOverlayCanvas();
    drawCropStudioOverlay();
  };
  cropPreviewImg.src = url;
  applyInsetPreviewStyle(cropPreviewImg, url);
}

function cropCanvasPointer(ev) {
  if (!cropOverlayCanvas) return { x: 0, y: 0 };
  const rect = cropOverlayCanvas.getBoundingClientRect();
  const rw = rect.width || 1;
  const rh = rect.height || 1;
  return {
    x: ((ev.clientX - rect.left) * cropOverlayCanvas.width) / rw,
    y: ((ev.clientY - rect.top) * cropOverlayCanvas.height) / rh,
  };
}

function commitCropStudioRect(tool, x0, y0, x1, y1) {
  if (!cropStudioActiveUrl || !cropOverlayCanvas) return;
  const W = cropOverlayCanvas.width;
  const H = cropOverlayCanvas.height;
  const xa = Math.max(0, Math.min(W, Math.min(x0, x1)));
  const ya = Math.max(0, Math.min(H, Math.min(y0, y1)));
  const xb = Math.max(0, Math.min(W, Math.max(x0, x1)));
  const yb = Math.max(0, Math.min(H, Math.max(y0, y1)));
  let nw = (xb - xa) / W;
  let nh = (yb - ya) / H;
  let nx = xa / W;
  let ny = ya / H;
  if (nw < 0.01 || nh < 0.01) return;
  const ed = ensureImageEdit(cropStudioActiveUrl);
  if (tool === "crop") {
    ed.manualCrop = { x: nx, y: ny, w: nw, h: nh };
  } else if (tool === "blur") {
    ed.blurs.push({ x: nx, y: ny, w: nw, h: nh });
  }
  persistImageEdits();
  drawCropStudioOverlay();
  refreshCropStudioThumbs();
}

function initCropStudioPanel() {
  refreshCropStudioThumbs();
  if (cropTextToolRow && cropToolMode) {
    cropTextToolRow.style.display = cropToolMode.value === "text" ? "flex" : "none";
  }
  syncCropOverflowLabel();
}

function syncFoldToggleLabel() {
  if (!btnToggleFoldVariants) return;
  btnToggleFoldVariants.textContent = "⧉";
  btnToggleFoldVariants.classList.toggle("tbcc-tool-active", !!settings.foldVideoVariants);
  btnToggleFoldVariants.title = settings.foldVideoVariants
    ? "Fold duplicate video resolutions (on)"
    : "Fold duplicate video resolutions (off)";
}

function saveGalleryUiState() {
  const payload = {
    filterType: filterType ? filterType.value : "",
    filterMinW: filterMinW ? filterMinW.value : "",
    filterMinH: filterMinH ? filterMinH.value : "",
    filterUrl: filterUrl ? filterUrl.value : "",
    filterHideUiClutter: filterHideUiClutter ? !!filterHideUiClutter.checked : false,
    activeTab,
  };
  chrome.storage.local.set({ [STORAGE_UI_STATE]: payload });
}

function syncCaptureTabButtons() {
  if (!tabCurrentBtn) return;
  tabCurrentBtn.classList.toggle("active", activeTab === "current");
  if (tabGroupBtn) tabGroupBtn.classList.toggle("active", activeTab === "group");
  if (tabAllBtn) tabAllBtn.classList.toggle("active", activeTab === "all");
}

function applyGalleryUiState(ui) {
  if (!ui || typeof ui !== "object") return;
  if (filterType && ui.filterType != null) filterType.value = String(ui.filterType);
  if (filterMinW && ui.filterMinW != null) filterMinW.value = String(ui.filterMinW);
  if (filterMinH && ui.filterMinH != null) filterMinH.value = String(ui.filterMinH);
  if (filterUrl && ui.filterUrl != null) filterUrl.value = String(ui.filterUrl);
  if (filterHideUiClutter && ui.filterHideUiClutter != null) {
    filterHideUiClutter.checked = !!ui.filterHideUiClutter;
  }
  if (ui.activeTab === "all" || ui.activeTab === "group" || ui.activeTab === "current") {
    activeTab = ui.activeTab;
    syncCaptureTabButtons();
  }
}

function setLightboxVideoMessage(msg) {
  if (!tbccLightboxVideoErr) return;
  const t = (msg || "").trim();
  tbccLightboxVideoErr.textContent = t;
  tbccLightboxVideoErr.hidden = !t;
}

function revokeLightboxVideoObjectUrl() {
  if (!tbccLightboxVideoObjectUrl) return;
  try {
    URL.revokeObjectURL(tbccLightboxVideoObjectUrl);
  } catch (_) {}
  tbccLightboxVideoObjectUrl = "";
}

function closeLightbox() {
  if (!tbccLightbox) return;
  tbccLightbox.classList.remove("visible");
  setLightboxVideoMessage("");
  if (tbccLightboxVideo) {
    revokeLightboxVideoObjectUrl();
    delete tbccLightboxVideo.dataset.tbccBlobTried;
    tbccLightboxVideo.onerror = null;
    tbccLightboxVideo.onloadeddata = null;
    tbccLightboxVideo.pause();
    tbccLightboxVideo.removeAttribute("src");
  }
  if (tbccLightboxImg) tbccLightboxImg.removeAttribute("src");
  currentLightboxItem = null;
}

/**
 * Return the ordered list of items the lightbox can navigate through.
 * Mirrors the current gallery grid order: filtered, sorted, and with folded
 * video groups collapsed to their active variant (so wheel-stepping doesn't
 * re-play every variant of the same MP4 in a row).
 */
function getLightboxNavItems() {
  let rows = [];
  try { rows = getDisplayRows(); } catch (_) { rows = []; }
  const out = [];
  for (const r of rows) {
    let it = null;
    try { it = getItemForDisplayRow(r); } catch (_) {}
    if (it && it.url) out.push(it);
  }
  return out;
}

/**
 * Move the lightbox by `delta` positions (negative = back / left, positive =
 * forward / right). Wraps around at the ends so the user can keep wheeling.
 * No-op when the lightbox is hidden or the current item can't be located.
 */
function stepLightbox(delta) {
  if (!tbccLightbox || !tbccLightbox.classList.contains("visible")) return;
  if (!currentLightboxItem) return;
  const items = getLightboxNavItems();
  if (!items.length) return;
  const curUrl = String(currentLightboxItem.url || "");
  let idx = items.findIndex((i) => String(i.url || "") === curUrl);
  if (idx < 0) {
    /** Current item was filtered/removed; jump to the first item that's still around. */
    idx = 0;
  } else {
    idx = ((idx + delta) % items.length + items.length) % items.length;
  }
  const next = items[idx];
  if (next && next !== currentLightboxItem) openLightboxForItemAfterResolve(next);
}

function openLightboxForItem(item) {
  if (!item || !tbccLightbox) return;
  void (async () => {
    let work = item;
    if (String(item.url || "").startsWith("blob:") && galleryItemMarkedVideo(item)) {
      const tw = await tbccTryResolveBlobVideoViaTwitterNet(item);
      if (tw) work = { ...item, url: tw, mediaType: "video", tagName: "video" };
    }
    openLightboxForItemAfterResolve(work);
  })();
}

function openLightboxForItemAfterResolve(item) {
  if (!item || !tbccLightbox) return;
  currentLightboxItem = item;
  const u = String(bestHttpMediaUrlForItem(item) || item.url || "");
  const uLow = u.toLowerCase();
  const urlLooksLikeVideoFile = /\.(mp4|webm|m3u8|mpd|mov|m4v)(\?|$)/i.test(uLow);
  /** Raster URLs are not decodable as HTML5 video — use the image lightbox (fixes black player on .webp). */
  const urlIsRasterImage = /\.(jpe?g|png|gif|webp|avif|bmp)(\?|$)/i.test(uLow);
  const markedVideo = (item.mediaType || item.tagName || "").toLowerCase() === "video";
  const isVideo =
    !urlIsRasterImage &&
    (urlLooksLikeVideoFile ||
      (markedVideo && !urlPathLooksLikeRasterImage(String(item.url || ""))) ||
      (item.file && item.file.type && item.file.type.startsWith("video/")));
  setLightboxVideoMessage("");
  /**
   * On every navigation: stop the previous video so audio doesn't keep
   * playing after we step to a new tile, and revoke its blob URL.
   */
  if (tbccLightboxVideo) {
    try { tbccLightboxVideo.pause(); } catch (_) {}
    revokeLightboxVideoObjectUrl();
    delete tbccLightboxVideo.dataset.tbccBlobTried;
    tbccLightboxVideo.onerror = null;
    tbccLightboxVideo.onloadeddata = null;
    if (!isVideo) tbccLightboxVideo.removeAttribute("src");
  }
  if (tbccLightboxImg) tbccLightboxImg.style.display = "none";
  if (tbccLightboxVideo) tbccLightboxVideo.style.display = "none";
  if (isVideo && tbccLightboxVideo) {
    if (/\.(m3u8|mpd)(\?|$)/i.test(uLow)) {
      setLightboxVideoMessage(
        "HLS/DASH often will not play in this preview. Use Download or your backend HLS import if the site only offers a manifest."
      );
    }
    const vEl = tbccLightboxVideo;
    revokeLightboxVideoObjectUrl();
    delete vEl.dataset.tbccBlobTried;
    vEl.onerror = null;
    vEl.onloadeddata = null;
    vEl.onerror = async () => {
      const ve = vEl.error;
      const canTryBlobFallback =
        !vEl.dataset.tbccBlobTried &&
        /^https?:\/\//i.test(u) &&
        !/\.(m3u8|mpd)(\?|$)/i.test(uLow);
      if (canTryBlobFallback) {
        vEl.dataset.tbccBlobTried = "1";
        setLightboxVideoMessage("Direct playback failed; trying session-backed fallback...");
        try {
          const refPage = await tbccRefererPageForItem(item);
          const fallbackBlob = await fetchUrlBytesToBlob(u, refPage);
          if (fallbackBlob && fallbackBlob.size > 0) {
            tbccLightboxVideoObjectUrl = URL.createObjectURL(fallbackBlob);
            vEl.src = tbccLightboxVideoObjectUrl;
            return;
          }
        } catch (_) {}
      }
      let hint = "Video failed to load or decode in the sidebar player.";
      if (ve && typeof MediaError !== "undefined") {
        if (ve.code === MediaError.MEDIA_ERR_SRC_NOT_SUPPORTED)
          hint = "This URL format is not supported in the sidebar player (try Download or open in an external app).";
        else if (ve.code === MediaError.MEDIA_ERR_NETWORK) hint = "Network error while loading video (check VPN/proxy and refresh capture).";
        else if (ve.code === MediaError.MEDIA_ERR_DECODE) hint = "Decode error — the file may be DRM/protected or a non-standard variant.";
      }
      setLightboxVideoMessage(hint);
    };
    vEl.onloadeddata = () => {
      if (!/\.(m3u8|mpd)(\?|$)/i.test(uLow)) setLightboxVideoMessage("");
    };
    vEl.src = u;
    vEl.style.display = "block";
  } else if (tbccLightboxImg) {
    tbccLightboxImg.src = u;
    tbccLightboxImg.style.display = "block";
  }
  tbccLightbox.classList.add("visible");
}

function showToast(message, type, clickAction) {
  if (!toastContainer || !message) return;
  const t = type || "info";
  const el = document.createElement("div");
  el.className = "toast " + (t === "success" ? "success" : t === "error" ? "error" : "info");
  el.textContent = message;
  if (clickAction) {
    el.classList.add("toast--clickable");
    el.title = "Click to open";
    el.addEventListener("click", () => {
      chrome.runtime.sendMessage({ action: "tbcc-notification-open", clickAction });
    });
  }
  toastContainer.appendChild(el);
  const ms = t === "error" ? 10000 : clickAction ? 12000 : 4000;
  setTimeout(() => {
    try {
      el.remove();
    } catch (_) {}
  }, ms);
}

function showSystemNotification(title, message, clickAction) {
  try {
    if (!chrome || !chrome.runtime) return;
    chrome.runtime.sendMessage({
      action: "tbcc-notify",
      title: title || "TBCC",
      message: message || "",
      clickAction: clickAction || null,
    });
  } catch (_) {}
}

function notifyCompletion(message, type, settingsKey, title, clickAction) {
  showToast(message, type || "info", clickAction);
  const useSystem = settings && settings.notifyUseSystem !== false;
  const allowed = !settingsKey || settings[settingsKey] !== false;
  if (useSystem && allowed) {
    showSystemNotification(title || "TBCC", message, clickAction);
  }
}

function beginGalleryJob(type, label) {
  const tabId = galleryDockedTab && galleryDockedTab.tabId != null ? galleryDockedTab.tabId : currentTabId;
  return new Promise((resolve) => {
    chrome.runtime.sendMessage(
      { action: "tbcc-gallery-job-begin", type: type || "task", label: label || type, tabId },
      (r) => {
        if (chrome.runtime.lastError) resolve(null);
        else resolve(r && r.id ? r.id : null);
      }
    );
  });
}

function endGalleryJob(id, outcome) {
  if (!id) return;
  chrome.runtime.sendMessage({
    action: "tbcc-gallery-job-end",
    id,
    outcome: outcome || undefined,
  });
}

chrome.runtime.onMessage.addListener((msg) => {
  if (msg && msg.action === "tbcc-gallery-request-close") {
    try {
      window.close();
    } catch (_) {}
    return;
  }
  if (msg && msg.type === "tbcc-progress") {
    const idx = msg.index != null ? Number(msg.index) : 0;
    const total = msg.total != null ? Number(msg.total) : 0;
    if (progressStatus && total > 0) {
      let line = `${idx} / ${total}`;
      if (msg.error) line += ` — ${msg.error}`;
      else if (msg.mediaId) line += " ✓";
      progressStatus.textContent = line;
      if (progressFill) progressFill.style.width = Math.round((100 * idx) / total) + "%";
    }
    if (progressEl) progressEl.classList.add("visible");
  }
});

function updateActionBarVisibility() {
  if (!galleryActionBar) return;
  galleryActionBar.classList.toggle("hidden", selectedCountInFilteredList() === 0);
}

function setTelegramSheetOpen(open) {
  if (!telegramSheet) return;
  if (!open && alwaysIncludePopover) {
    alwaysIncludePopover.hidden = true;
    if (btnAlwaysIncludeToggle) btnAlwaysIncludeToggle.setAttribute("aria-expanded", "false");
  }
  telegramSheet.classList.toggle("open", !!open);
  telegramSheet.setAttribute("aria-hidden", open ? "false" : "true");
  if (open) {
    void (async () => {
      try {
        if (!tbccChannelsCacheLast || !tbccChannelsCacheLast.length) await loadChannelsForForum();
      } catch (_) {}
      renderAlwaysIncludeChannelList();
      renderAlwaysIncludeCustomList();
      syncCaptionFieldFromBase();
    })();
  }
}

function setSavedUrlInboxStatus(text) {
  if (savedUrlInboxStatus) savedUrlInboxStatus.textContent = text || "";
}

function openSavedUrlInboxSheet(open) {
  if (!savedUrlInboxSheet) return;
  if (open) setTelegramSheetOpen(false);
  savedUrlInboxSheet.classList.toggle("open", !!open);
  savedUrlInboxSheet.setAttribute("aria-hidden", open ? "false" : "true");
  if (open) {
    void (async () => {
      await loadPools();
      await renderSavedUrlInboxList();
    })();
  }
}

function syncInboxDefaultDestUi() {
  const isMod = savedUrlInboxDefaultDest && savedUrlInboxDefaultDest.value === "loot_modifier";
  if (savedUrlInboxDefaultPoolWrap) savedUrlInboxDefaultPoolWrap.style.display = isMod ? "none" : "";
}

function buildInboxDestSelect(row) {
  const sel = document.createElement("select");
  sel.className = "pool-select-compact saved-url-inbox-dest";
  sel.title = "Content pool import vs loot modifier URL";
  sel.innerHTML =
    '<option value="pool">Content pool</option><option value="loot_modifier">Loot modifier</option>';
  sel.value = row.destType === "loot_modifier" ? "loot_modifier" : "pool";
  sel.addEventListener("change", async () => {
    const rows = await TbccSavedUrlInbox.getRows();
    const key = TbccSavedUrlInbox.rowKey(row);
    for (const r of rows) {
      if (TbccSavedUrlInbox.rowKey(r) === key) {
        r.destType = sel.value === "loot_modifier" ? "loot_modifier" : "pool";
        if (r.destType === "loot_modifier") r.poolId = null;
        break;
      }
    }
    await TbccSavedUrlInbox.setRows(rows);
    await renderSavedUrlInboxList();
  });
  return sel;
}

function buildInboxPoolSelect(row) {
  const sel = document.createElement("select");
  sel.className = "pool-select-compact saved-url-inbox-pool";
  sel.title = "Content pool for this URL";
  fillPoolSelectElement(sel, cachedPoolsForInbox, row.poolId || "", true);
  if (row.destType === "loot_modifier") sel.disabled = true;
  sel.addEventListener("change", async () => {
    const rows = await TbccSavedUrlInbox.getRows();
    const key = TbccSavedUrlInbox.rowKey(row);
    const pid = sel.value ? parseInt(sel.value, 10) : null;
    for (const r of rows) {
      if (TbccSavedUrlInbox.rowKey(r) === key) {
        r.poolId = Number.isFinite(pid) && pid > 0 ? pid : null;
        break;
      }
    }
    await TbccSavedUrlInbox.setRows(rows);
  });
  return sel;
}

async function importOneLootModifierUrl(url, note, opts) {
  const o = opts || {};
  try {
    const body = {
      url,
      label: note || undefined,
      source_note: "extension:inbox",
    };
    if (o.asZipPack) {
      body.as_zip_pack = true;
      body.random_high_tier = o.randomHighTier !== false;
      if (o.includeZipPromo === true) body.include_zip_promo = true;
      else if (o.includeZipPromo === false) body.include_zip_promo = false;
    }
    const resp = await fetch(API_BASE + "/loot/modifiers/from-url", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const text = await resp.text();
    let data = {};
    try {
      data = text ? JSON.parse(text) : {};
    } catch (_) {}
    if (!resp.ok) {
      const detail = data.detail || data.error || text || "HTTP " + resp.status;
      return { error: String(detail).slice(0, 400) };
    }
    return { status: "imported", modifier_id: data.id, as_zip_pack: !!data.as_zip_pack };
  } catch (e) {
    return { error: String(e.message || e) };
  }
}

function inboxModifierApiBodyFromRow(row) {
  const body = {
    url: row.url,
    label: row.note || undefined,
    source_note: "extension:inbox",
  };
  if (row.lootZipPack === true) {
    body.as_zip_pack = true;
    body.random_high_tier = row.lootRandomHighTier !== false;
    if (row.includeZipPromo === true) body.include_zip_promo = true;
    else if (row.includeZipPromo === false) body.include_zip_promo = false;
  }
  return body;
}

/** One round-trip for many plain loot modifier links (falls back per-row if API unavailable). */
async function importLootModifierUrlsBatch(rows) {
  const list = Array.isArray(rows) ? rows : [];
  if (!list.length) return { results: [], usedBatch: false };
  const items = list.map(inboxModifierApiBodyFromRow);
  try {
    const resp = await fetch(API_BASE + "/loot/modifiers/from-url/batch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ items }),
    });
    const text = await resp.text();
    let data = {};
    try {
      data = text ? JSON.parse(text) : {};
    } catch (_) {}
    if (resp.status === 404 || resp.status === 405) return { results: [], usedBatch: false };
    if (!resp.ok) {
      const detail = data.detail || data.error || text || "HTTP " + resp.status;
      return { results: [], usedBatch: false, error: String(detail).slice(0, 400) };
    }
    const rawResults = Array.isArray(data.results) ? data.results : [];
    const byIndex = new Map(rawResults.map((r) => [Number(r.index), r]));
    const results = list.map((row, i) => {
      const br = byIndex.get(i);
      if (!br) return { row, ok: false, error: "Missing batch result" };
      if (br.ok) {
        return {
          row,
          ok: true,
          data: { status: "imported", modifier_id: br.modifier_id, as_zip_pack: !!br.as_zip_pack },
        };
      }
      return { row, ok: false, error: br.error || "Import failed" };
    });
    return { results, usedBatch: true };
  } catch (e) {
    return { results: [], usedBatch: false, error: String(e.message || e) };
  }
}

/** Background content-pool imports so the inbox sheet stays usable. */
const inboxPoolBackground = {
  running: false,
  jobs: [],
};

function markInboxRowsImporting(all, rowKeys) {
  const keys = new Set(rowKeys);
  for (const r of all) {
    if (keys.has(TbccSavedUrlInbox.rowKey(r))) {
      r.status = "importing";
      r.lastError = "";
    }
  }
}

function applyInboxImportOutcome(row, all, data, isModifier, counters, pendingAutoTag, globalAutoTag) {
  const success = isModifier
    ? data.status === "imported" && !data.error
    : (data.status === "imported" || data.status === "skipped") && !data.error;
  const key = TbccSavedUrlInbox.rowKey(row);
  for (const r of all) {
    if (TbccSavedUrlInbox.rowKey(r) !== key) continue;
    if (success) {
      r.status = "imported";
      if (isModifier) {
        r.lastError = "";
        r.modifierId = data.modifier_id || r.modifierId;
        r.mediaId = null;
        counters.modOk++;
      } else {
        r.lastError = data.status === "skipped" ? "Skipped (duplicate)" : "";
        r.mediaId = data.media_id || r.mediaId;
        r.modifierId = null;
        counters.poolOk++;
        if (r.mediaId) {
          const useRowAutoTag = row.autoTag !== false && globalAutoTag;
          if (useRowAutoTag) {
            pendingAutoTag.push({
              mediaId: r.mediaId,
              url: row.url,
              ref: row.ref || "",
              tagsCsv: row.tagsCsv || "",
              autoTag: true,
            });
          } else if (row.tagsCsv) {
            return { needsTagApply: { mediaId: r.mediaId, tagsCsv: row.tagsCsv, row: r } };
          }
        }
      }
      counters.ok++;
    } else {
      r.status = "queued";
      r.lastError = data.error || "Import failed";
      counters.fail++;
    }
  }
  return null;
}

async function drainInboxPoolBackgroundQueue() {
  if (inboxPoolBackground.running) return;
  inboxPoolBackground.running = true;
  const counters = { ok: 0, fail: 0, poolOk: 0 };
  try {
    while (inboxPoolBackground.jobs.length) {
      const job = inboxPoolBackground.jobs.shift();
      if (!job) continue;
      const { row, all, pendingAutoTag, globalAutoTag, index, total } = job;
      setSavedUrlInboxStatus(`Content pool (background) ${index + 1}/${total}…`);
      const poolId = row.poolId ? parseInt(row.poolId, 10) : 0;
      if (!poolId) {
        counters.fail++;
        const key = TbccSavedUrlInbox.rowKey(row);
        for (const r of all) {
          if (TbccSavedUrlInbox.rowKey(r) === key) {
            r.status = "queued";
            r.lastError = "Pick a content pool";
          }
        }
        await TbccSavedUrlInbox.setRows(all);
        if (savedUrlInboxSheet && savedUrlInboxSheet.classList.contains("open")) void renderSavedUrlInboxList();
        continue;
      }
      const data = await importOneUrl(row.url, poolId, false);
      const tagPending = applyInboxImportOutcome(
        row,
        all,
        data,
        false,
        counters,
        pendingAutoTag,
        globalAutoTag
      );
      if (tagPending && tagPending.needsTagApply) {
        try {
          await applyTagsCsvToMediaIds([tagPending.mediaId], tagPending.tagsCsv);
        } catch (e) {
          tagPending.row.lastError = "Imported; tags failed: " + (e.message || String(e));
        }
      }
      await TbccSavedUrlInbox.setRows(all);
      if (savedUrlInboxSheet && savedUrlInboxSheet.classList.contains("open")) void renderSavedUrlInboxList();
      await new Promise((r) => setTimeout(r, 0));
    }
    if (inboxPoolBackground.pendingAutoTag && inboxPoolBackground.pendingAutoTag.length) {
      setSavedUrlInboxStatus("Auto-tagging imported media (background)…");
      try {
        await applyAutoTaggingForInboxImportedMedia(inboxPoolBackground.pendingAutoTag);
      } catch (e) {
        showToast("Inbox auto-tag failed: " + (e.message || String(e)), "error");
      }
      inboxPoolBackground.pendingAutoTag = [];
    }
    if (counters.poolOk > 0 || counters.fail > 0) {
      const msg = counters.fail
        ? `Background pool import: ${counters.poolOk} done, ${counters.fail} failed.`
        : `Background pool import: ${counters.poolOk} finished.`;
      setSavedUrlInboxStatus(msg);
      showToast(msg, counters.fail ? "info" : "success");
    }
  } finally {
    inboxPoolBackground.running = false;
    if (inboxPoolBackground.jobs.length) void drainInboxPoolBackgroundQueue();
  }
}

function enqueueInboxPoolBackgroundImports(poolRows, all, pendingAutoTag, globalAutoTag) {
  if (!poolRows.length) return 0;
  markInboxRowsImporting(
    all,
    poolRows.map((r) => TbccSavedUrlInbox.rowKey(r))
  );
  const startLen = inboxPoolBackground.jobs.length;
  const total = startLen + poolRows.length;
  poolRows.forEach((row, i) => {
    inboxPoolBackground.jobs.push({
      row,
      all,
      pendingAutoTag,
      globalAutoTag,
      index: startLen + i,
      total,
    });
  });
  void TbccSavedUrlInbox.setRows(all).then(() => {
    if (savedUrlInboxSheet && savedUrlInboxSheet.classList.contains("open")) void renderSavedUrlInboxList();
    void drainInboxPoolBackgroundQueue();
  });
  return poolRows.length;
}

async function renderSavedUrlInboxList() {
  if (!savedUrlInboxList || !window.TbccSavedUrlInbox) return;
  const rows = await TbccSavedUrlInbox.getRows();
  savedUrlInboxList.innerHTML = "";
  if (!rows.length) {
    const empty = document.createElement("p");
    empty.className = "saved-url-inbox-empty";
    empty.textContent = "No URLs queued. Right-click a link → Add URL to TBCC inbox.";
    savedUrlInboxList.appendChild(empty);
    return;
  }
  rows.forEach((row) => {
    const item = document.createElement("div");
    item.className =
      "saved-url-inbox-row" +
      (row.status === "imported"
        ? " saved-url-inbox-row--imported"
        : row.status === "importing"
          ? " saved-url-inbox-row--importing"
          : "");
    item.setAttribute("role", "listitem");

    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.className = "saved-url-inbox-check";
    cb.checked = row.status !== "imported" && row.status !== "importing";
    cb.disabled = row.status === "importing";
    cb.dataset.key = TbccSavedUrlInbox.rowKey(row);

    const body = document.createElement("div");
    body.className = "saved-url-inbox-row__body";

    const link = document.createElement("a");
    link.href = row.url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = row.url;
    link.className = "saved-url-inbox-url";

    const urlEdit = document.createElement("input");
    urlEdit.type = "url";
    urlEdit.className = "tbcc-input saved-url-inbox-url-edit";
    urlEdit.value = row.url;
    urlEdit.title = "Edit URL";

    const meta = document.createElement("div");
    meta.className = "saved-url-inbox-meta";
    if (row.status === "imported") {
      if (row.modifierId)
        meta.textContent = row.lootZipPack
          ? "Loot zip pack #" + row.modifierId
          : "Loot modifier #" + row.modifierId;
      else meta.textContent = row.mediaId ? "Imported · media #" + row.mediaId : "Imported";
    } else if (row.lastError) {
      meta.textContent = "Failed: " + row.lastError;
    } else {
      meta.textContent = row.ref ? "From: " + row.ref : "Queued";
    }

    const tagsIn = document.createElement("input");
    tagsIn.type = "text";
    tagsIn.className = "tbcc-input saved-url-inbox-tags";
    tagsIn.placeholder = "Extra tags (comma-separated)";
    tagsIn.value = row.tagsCsv || "";
    tagsIn.title = "Merged with auto-tags on import when Auto-tag is checked";

    const rowOpts = document.createElement("div");
    rowOpts.className = "saved-url-inbox-row-options";

    const autoTagLbl = document.createElement("label");
    autoTagLbl.title = "Same URL + page-hint auto-tag as Import settings";
    const autoTagCb = document.createElement("input");
    autoTagCb.type = "checkbox";
    autoTagCb.checked = row.autoTag !== false;
    autoTagCb.disabled = row.destType === "loot_modifier";
    autoTagLbl.appendChild(autoTagCb);
    autoTagLbl.appendChild(document.createTextNode("Auto-tag"));

    const zipPromoLbl = document.createElement("label");
    zipPromoLbl.title =
      "Include global promo readme/image when building a zip (gallery export or loot zip pack download)";
    const zipPromoCb = document.createElement("input");
    zipPromoCb.type = "checkbox";
    zipPromoCb.checked = row.includeZipPromo === true;
    zipPromoCb.indeterminate = row.includeZipPromo == null;
    zipPromoLbl.appendChild(zipPromoCb);
    zipPromoLbl.appendChild(document.createTextNode("ZIP promo"));

    const lootZipLbl = document.createElement("label");
    lootZipLbl.title = "Download URL, wrap in zip, inject promo, register as local_zip_pack modifier";
    const lootZipCb = document.createElement("input");
    lootZipCb.type = "checkbox";
    lootZipCb.checked = row.lootZipPack === true;
    lootZipCb.disabled = row.destType !== "loot_modifier";
    lootZipLbl.appendChild(lootZipCb);
    lootZipLbl.appendChild(document.createTextNode("Zip pack"));

    const lootTierLbl = document.createElement("label");
    lootTierLbl.title = "When zipping for loot: random min rarity tier 9 or 10";
    const lootTierCb = document.createElement("input");
    lootTierCb.type = "checkbox";
    lootTierCb.checked = row.lootRandomHighTier !== false;
    lootTierCb.disabled = row.destType !== "loot_modifier" || !lootZipCb.checked;
    lootTierLbl.appendChild(lootTierCb);
    lootTierLbl.appendChild(document.createTextNode("Tier 9–10"));

    lootZipCb.addEventListener("change", () => {
      lootTierCb.disabled = row.destType !== "loot_modifier" || !lootZipCb.checked;
    });

    rowOpts.appendChild(autoTagLbl);
    rowOpts.appendChild(zipPromoLbl);
    if (row.destType === "loot_modifier") {
      rowOpts.appendChild(lootZipLbl);
      rowOpts.appendChild(lootTierLbl);
    }

    zipPromoCb.addEventListener("change", () => {
      zipPromoCb.indeterminate = false;
    });

    const noteIn = document.createElement("input");
    noteIn.type = "text";
    noteIn.className = "tbcc-input saved-url-inbox-note";
    noteIn.placeholder = "Note (optional)";
    noteIn.value = row.note || "";

    const destSel = buildInboxDestSelect(row);
    const poolSel = buildInboxPoolSelect(row);

    const rm = document.createElement("button");
    rm.type = "button";
    rm.className = "tbcc-btn-secondary tbcc-btn--sheet-compact";
    rm.textContent = "Remove";
    rm.addEventListener("click", async () => {
      const latest = await TbccSavedUrlInbox.getRows();
      await TbccSavedUrlInbox.setRows(
        latest.filter((x) => TbccSavedUrlInbox.rowKey(x) !== TbccSavedUrlInbox.rowKey(row))
      );
      await renderSavedUrlInboxList();
    });

    const persistRowEdits = async () => {
      const latest = await TbccSavedUrlInbox.getRows();
      const key = TbccSavedUrlInbox.rowKey(row);
      for (const r of latest) {
        if (TbccSavedUrlInbox.rowKey(r) === key) {
          r.url = urlEdit.value.trim() || r.url;
          r.tagsCsv = tagsIn.value.trim();
          r.note = noteIn.value.trim();
          r.autoTag = autoTagCb.checked;
          r.includeZipPromo = zipPromoCb.indeterminate ? null : zipPromoCb.checked;
          if (r.destType === "loot_modifier") {
            r.lootZipPack = lootZipCb.checked;
            r.lootRandomHighTier = lootTierCb.checked;
          }
          break;
        }
      }
      await TbccSavedUrlInbox.setRows(latest);
    };
    urlEdit.addEventListener("change", () => void persistRowEdits());
    tagsIn.addEventListener("change", () => void persistRowEdits());
    noteIn.addEventListener("change", () => void persistRowEdits());
    autoTagCb.addEventListener("change", () => void persistRowEdits());
    zipPromoCb.addEventListener("change", () => void persistRowEdits());
    if (row.destType === "loot_modifier") {
      lootZipCb.addEventListener("change", () => void persistRowEdits());
      lootTierCb.addEventListener("change", () => void persistRowEdits());
    }

    body.appendChild(link);
    body.appendChild(urlEdit);
    body.appendChild(destSel);
    body.appendChild(poolSel);
    body.appendChild(rowOpts);
    body.appendChild(tagsIn);
    body.appendChild(noteIn);
    body.appendChild(meta);
    body.appendChild(rm);

    item.appendChild(cb);
    item.appendChild(body);
    savedUrlInboxList.appendChild(item);
  });
}

async function applyTagsCsvToMediaIds(mediaIds, csv) {
  const tags = String(csv || "").trim();
  if (!tags || !mediaIds || !mediaIds.length) return;
  const ids = [...new Set(mediaIds.map((x) => parseInt(x, 10)).filter((x) => Number.isFinite(x)))];
  if (!ids.length) return;
  const r = await fetch(`${API_BASE}/media/bulk/tags`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ids, tags, tags_merge: true }),
  });
  const text = await r.text();
  let j = {};
  try {
    j = text ? JSON.parse(text) : {};
  } catch (_) {}
  if (!r.ok || j.error) throw new Error(j.error || j.detail || text || `HTTP ${r.status}`);
}

/** Run async workers over items with a concurrency cap (keeps UI/event loop breathing). */
async function runInboxImportWithConcurrency(items, concurrency, worker) {
  const list = Array.isArray(items) ? items : [];
  if (!list.length) return;
  const n = Math.max(1, Math.min(Number(concurrency) || 1, list.length));
  let next = 0;
  await Promise.all(
    Array.from({ length: n }, async () => {
      while (true) {
        const i = next++;
        if (i >= list.length) break;
        await worker(list[i], i);
        await new Promise((r) => setTimeout(r, 0));
      }
    })
  );
}

const INBOX_MODIFIER_IMPORT_CONCURRENCY = 8;
const INBOX_POOL_IMPORT_CONCURRENCY = 1;
const INBOX_STORAGE_FLUSH_EVERY = 8;

async function importSavedUrlInboxRows(rowsToImport) {
  const counters = { ok: 0, fail: 0, modOk: 0, poolOk: 0 };
  const all = await TbccSavedUrlInbox.getRows();
  const pendingAutoTag = [];
  const globalAutoTag =
    autoTagOnExport && autoTagOnExport.checked !== undefined
      ? !!autoTagOnExport.checked
      : (await chrome.storage.local.get([STORAGE_AUTO_TAG_ON_EXPORT]))[STORAGE_AUTO_TAG_ON_EXPORT] !== false;

  const modifierRows = [];
  const poolRows = [];
  for (const row of rowsToImport) {
    if (row.status === "importing") continue;
    if (row.destType === "loot_modifier") modifierRows.push(row);
    else poolRows.push(row);
  }

  let storageFlushCounter = 0;
  async function maybeFlushInboxStorage(force) {
    storageFlushCounter++;
    if (!force && storageFlushCounter % INBOX_STORAGE_FLUSH_EVERY !== 0) return;
    await TbccSavedUrlInbox.setRows(all);
  }

  // --- Loot modifiers: batch API when possible, else parallel singles ---
  if (modifierRows.length) {
    setSavedUrlInboxStatus(`Loot modifiers 0/${modifierRows.length}…`);
    const zipRows = modifierRows.filter((r) => r.lootZipPack === true);
    const plainRows = modifierRows.filter((r) => r.lootZipPack !== true);

    if (plainRows.length) {
      const batch = await importLootModifierUrlsBatch(plainRows);
      if (batch.usedBatch && batch.results.length) {
        for (let i = 0; i < batch.results.length; i++) {
          const br = batch.results[i];
          setSavedUrlInboxStatus(`Loot modifiers ${Math.min(i + 1, plainRows.length)}/${modifierRows.length}…`);
          if (br.ok) {
            applyInboxImportOutcome(br.row, all, br.data, true, counters, pendingAutoTag, globalAutoTag);
          } else {
            applyInboxImportOutcome(
              br.row,
              all,
              { error: br.error || "Import failed" },
              true,
              counters,
              pendingAutoTag,
              globalAutoTag
            );
          }
        }
      } else {
        const modConcurrency = batch.error ? 2 : INBOX_MODIFIER_IMPORT_CONCURRENCY;
        await runInboxImportWithConcurrency(plainRows, modConcurrency, async (row, i) => {
          setSavedUrlInboxStatus(`Loot modifiers ${i + 1}/${modifierRows.length}…`);
          const data = await importOneLootModifierUrl(row.url, row.note || "", {});
          applyInboxImportOutcome(row, all, data, true, counters, pendingAutoTag, globalAutoTag);
          await maybeFlushInboxStorage(false);
        });
      }
    }

    if (zipRows.length) {
      await runInboxImportWithConcurrency(zipRows, 2, async (row, i) => {
        setSavedUrlInboxStatus(`Loot zip packs ${i + 1}/${zipRows.length}…`);
        const data = await importOneLootModifierUrl(row.url, row.note || "", {
          asZipPack: true,
          randomHighTier: row.lootRandomHighTier !== false,
          includeZipPromo:
            row.includeZipPromo === true ? true : row.includeZipPromo === false ? false : null,
        });
        applyInboxImportOutcome(row, all, data, true, counters, pendingAutoTag, globalAutoTag);
        await maybeFlushInboxStorage(false);
      });
    }
    await maybeFlushInboxStorage(true);
  }

  let poolQueued = 0;
  if (poolRows.length) {
    inboxPoolBackground.pendingAutoTag = [];
    poolQueued = enqueueInboxPoolBackgroundImports(
      poolRows,
      all,
      inboxPoolBackground.pendingAutoTag,
      globalAutoTag
    );
  }

  if (pendingAutoTag.length) {
    setSavedUrlInboxStatus("Auto-tagging imported media…");
    try {
      await applyAutoTaggingForInboxImportedMedia(pendingAutoTag);
    } catch (e) {
      showToast("Inbox auto-tag failed: " + (e.message || String(e)), "error");
    }
  }

  await renderSavedUrlInboxList();
  const parts = [];
  if (counters.modOk) parts.push(`${counters.modOk} loot modifier${counters.modOk === 1 ? "" : "s"}`);
  if (counters.poolOk) parts.push(`${counters.poolOk} content pool`);
  const summary = parts.length ? parts.join(", ") : `${counters.ok} item${counters.ok === 1 ? "" : "s"}`;
  if (poolQueued) {
    setSavedUrlInboxStatus(
      counters.fail
        ? `${summary || "Modifiers done"}; ${poolQueued} pool import(s) running in background…`
        : `${summary ? summary + "; " : ""}${poolQueued} content pool import(s) running in background…`
    );
    showToast(`${poolQueued} pool import(s) started in background`, "info");
  } else {
    setSavedUrlInboxStatus(
      counters.fail ? `Done: ${summary}; ${counters.fail} failed.` : summary ? `Imported ${summary}.` : "Nothing to import."
    );
    if (counters.ok) showToast(`Inbox: ${summary}`, "success");
  }
  return { ...counters, poolQueued };
}

async function getCheckedInboxRows() {
  if (!savedUrlInboxList) return [];
  const keys = new Set(
    [...savedUrlInboxList.querySelectorAll(".saved-url-inbox-check:checked")].map((el) => el.dataset.key)
  );
  const rows = await TbccSavedUrlInbox.getRows();
  return rows.filter((r) => keys.has(TbccSavedUrlInbox.rowKey(r)));
}

function setInboxChecksAll(checked) {
  if (!savedUrlInboxList) return;
  savedUrlInboxList.querySelectorAll(".saved-url-inbox-check").forEach((el) => {
    if (!el.disabled) el.checked = !!checked;
  });
}

async function exportInboxRows(format) {
  const rows = await TbccSavedUrlInbox.getRows();
  if (!rows.length) {
    setSavedUrlInboxStatus("Inbox is empty.");
    return;
  }
  const stamp = new Date().toISOString().slice(0, 10);
  if (format === "json") {
    TbccMasterArchive.downloadText(`tbcc-inbox-${stamp}.json`, JSON.stringify(rows, null, 2), "application/json");
  } else {
    const lines = rows.map((r) => r.url).filter(Boolean);
    TbccMasterArchive.downloadText(`tbcc-inbox-${stamp}.txt`, lines.join("\n"), "text/plain");
  }
  setSavedUrlInboxStatus(`Exported ${rows.length} inbox row(s).`);
}

async function importTextIntoInbox(text) {
  const parsed = TbccMasterArchive.parseImportText(text, "url");
  let added = 0;
  for (const e of parsed) {
    if (e.kind !== "url") continue;
    const r = await TbccSavedUrlInbox.appendUrl(e.value, { ref: e.ref || "", note: e.note || "" });
    if (r.ok && !r.duplicate) added++;
  }
  await renderSavedUrlInboxList();
  setSavedUrlInboxStatus(added ? `Added ${added} URL(s) to inbox.` : "No new URLs (duplicates skipped).");
}

const masterArchiveSheet = document.getElementById("masterArchiveSheet");
const masterArchiveBackdrop = document.getElementById("masterArchiveBackdrop");
const masterArchiveList = document.getElementById("masterArchiveList");
const masterArchiveStatus = document.getElementById("masterArchiveStatus");
const masterArchiveFilter = document.getElementById("masterArchiveFilter");
const masterArchiveKind = document.getElementById("masterArchiveKind");
const masterArchivePager = document.getElementById("masterArchivePager");
const tbccActiveJobsBar = document.getElementById("tbccActiveJobsBar");
const tbccActiveJobsList = document.getElementById("tbccActiveJobsList");
const btnClearStaleJobs = document.getElementById("btnClearStaleJobs");
const btnPauseImportQueue = document.getElementById("btnPauseImportQueue");
const tbccQueueDepthHint = document.getElementById("tbccQueueDepthHint");

const TBCC_IMPORT_TERMINAL_LOCAL = new Set(["done", "failed", "skipped", "cancelled"]);

function tbccIsLocalImportJobTerminal(j) {
  return j && TBCC_IMPORT_TERMINAL_LOCAL.has(String(j.status || "").toLowerCase());
}

function setMasterArchiveStatus(text) {
  if (masterArchiveStatus) masterArchiveStatus.textContent = text || "";
}

async function pullMasterArchiveFromServer() {
  if (!window.TbccMasterArchive || !TbccMasterArchive.syncFromServer) return;
  const r = await TbccMasterArchive.syncFromServer();
  if (r.ok) {
    setMasterArchiveStatus(
      `Synced with server: ${r.total} local entr${r.total === 1 ? "y" : "ies"} (${r.merged} merged, ${r.pulled} pulled).`
    );
    if (masterArchiveUi) masterArchiveUi.resetPage();
    await renderMasterArchiveList();
  } else if (r.error) {
    setMasterArchiveStatus("Server sync skipped: " + r.error);
  }
}

function openMasterArchiveSheet(open) {
  if (!masterArchiveSheet) return;
  if (open) openSavedUrlInboxSheet(false);
  masterArchiveSheet.classList.toggle("open", !!open);
  masterArchiveSheet.setAttribute("aria-hidden", open ? "false" : "true");
  if (open) {
    if (masterArchiveUi) masterArchiveUi.resetPage();
    void pullMasterArchiveFromServer();
    void renderMasterArchiveList();
  }
}

const masterArchiveUi =
  window.TbccArchiveListUi && window.TbccMasterArchive
    ? window.TbccArchiveListUi.createArchiveListController({
        listEl: masterArchiveList,
        statusEl: masterArchiveStatus,
        pagerEl: masterArchivePager,
        mode: "master",
        getEntries: () => TbccMasterArchive.getEntries(),
        getFilters: () => ({
          q: (masterArchiveFilter && masterArchiveFilter.value) || "",
          kind: (masterArchiveKind && masterArchiveKind.value) || "",
          ...(TbccMasterArchive.readSortOptsFromDom ? TbccMasterArchive.readSortOptsFromDom("") : {}),
        }),
        onAddToInbox: async (e) => {
          const r = await TbccSavedUrlInbox.appendUrl(e.value, { ref: "master_archive" });
          setMasterArchiveStatus(
            r.duplicate ? "Already in inbox." : r.ok ? "Added to inbox." : r.error || "Failed."
          );
          if (r.ok && !r.duplicate) await renderSavedUrlInboxList();
        },
      })
    : null;

async function renderMasterArchiveList() {
  if (masterArchiveUi) {
    await masterArchiveUi.refresh();
    return;
  }
  if (!masterArchiveList || !window.TbccMasterArchive) return;
  setMasterArchiveStatus("Archive UI module not loaded.");
}

async function getMasterArchiveFilteredEntries() {
  const all = await TbccMasterArchive.getEntries();
  return TbccMasterArchive.filterEntries(all, {
    q: (masterArchiveFilter && masterArchiveFilter.value) || "",
    kind: (masterArchiveKind && masterArchiveKind.value) || "",
    ...(TbccMasterArchive.readSortOptsFromDom ? TbccMasterArchive.readSortOptsFromDom("") : {}),
  });
}

function onMasterArchiveSortChange() {
  if (masterArchiveUi) masterArchiveUi.resetPage();
  void renderMasterArchiveList();
}
["masterArchiveSort1", "masterArchiveSort1Dir", "masterArchiveSort2", "masterArchiveSort2Dir"].forEach((id) => {
  const el = document.getElementById(id);
  if (el) el.addEventListener("change", onMasterArchiveSortChange);
});

async function copyAllInboxUrls() {
  const rows = await TbccSavedUrlInbox.getRows();
  const lines = rows.map((r) => String(r.url || "").trim()).filter((u) => /^https?:\/\//i.test(u));
  if (!lines.length) {
    setSavedUrlInboxStatus("No URLs in inbox.");
    return;
  }
  const ok = window.TbccArchiveListUi
    ? await window.TbccArchiveListUi.copyTextToClipboard(lines.join("\n"))
    : false;
  if (ok) {
    setSavedUrlInboxStatus(`Copied ${lines.length} inbox URL(s).`);
    const clip = globalThis.TbccClipboard;
    if (clip && clip.showCopied) clip.showCopied();
  } else {
    setSavedUrlInboxStatus("Clipboard failed.");
  }
}

function formatJobAge(ms) {
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m`;
  return `${Math.floor(m / 60)}h ${m % 60}m`;
}

let _tbccLastSystemHealth = null;

async function refreshSystemHealthHint() {
  const el = document.getElementById("tbccSystemHealthHint");
  if (!el) return;
  const data = await new Promise((resolve) => {
    chrome.runtime.sendMessage({ action: "tbcc-health-system" }, (r) => {
      if (chrome.runtime.lastError) resolve(null);
      else resolve(r && r.data ? r.data : null);
    });
  });
  _tbccLastSystemHealth = data;
  if (!data || data.ok) {
    el.hidden = true;
    el.textContent = "";
    return;
  }
  const crit = (data.conflicts || []).filter((c) => c.severity === "critical");
  const msg = crit.length
    ? crit.map((c) => c.message).join(" · ")
    : (data.conflicts || []).map((c) => c.message).join(" · ");
  el.hidden = false;
  el.textContent = msg.slice(0, 280);
  el.title = (data.recommendations || []).join("\n");
}

async function syncPauseImportQueueButton() {
  if (!btnPauseImportQueue) return;
  const paused = await new Promise((resolve) => {
    chrome.runtime.sendMessage({ action: "tbcc-import-queue-pause-get" }, (r) => {
      if (chrome.runtime.lastError) resolve(false);
      else resolve(!!(r && r.paused));
    });
  });
  btnPauseImportQueue.textContent = paused ? "Resume queue" : "Pause queue";
  btnPauseImportQueue.title = paused
    ? "Allow new fast-import uploads to start"
    : "Stop starting new fast-import uploads (in-flight jobs continue)";
  btnPauseImportQueue.classList.toggle("is-active", paused);
}

async function refreshImportQueueDepthHint() {
  if (!tbccQueueDepthHint) return;
  const r = await new Promise((resolve) => {
    chrome.runtime.sendMessage({ action: "tbcc-import-queue-status" }, (resp) => {
      if (chrome.runtime.lastError) resolve(null);
      else resolve(resp);
    });
  });
  const d = r && r.data ? r.data : null;
  if (!d || !r.ok) {
    tbccQueueDepthHint.hidden = true;
    tbccQueueDepthHint.textContent = "";
    return;
  }
  const dbN = d.db_active_import_jobs || 0;
  const act = d.telegram_tasks_active || 0;
  const res = d.telegram_tasks_reserved || 0;
  if (dbN === 0 && act === 0 && res === 0) {
    tbccQueueDepthHint.hidden = true;
    tbccQueueDepthHint.textContent = "";
    return;
  }
  tbccQueueDepthHint.hidden = false;
  const parts = [];
  if (dbN > 0) parts.push(`${dbN} import job${dbN === 1 ? "" : "s"}`);
  if (act > 0 || res > 0) {
    parts.push(`telegram ${act} active${res > 0 ? `, ${res} queued` : ""}`);
  }
  tbccQueueDepthHint.textContent = parts.join(" · ");
}

async function cancelGalleryJob(j) {
  if (!j || !j.id) return;
  if (j.backendJobId) {
    await new Promise((resolve) => {
      chrome.runtime.sendMessage(
        {
          action: "tbcc-import-cancel",
          galleryJobId: j.id,
          backendJobId: j.backendJobId,
        },
        () => resolve()
      );
    });
  } else {
    chrome.runtime.sendMessage({ action: "tbcc-gallery-job-end", id: j.id });
  }
  void refreshActiveJobsBar();
}

async function reconcileImportJobsOnOpen() {
  await new Promise((resolve) => {
    chrome.runtime.sendMessage({ action: "tbcc-import-reconcile" }, () => resolve());
  });
}

async function refreshActiveJobsBar() {
  if (!tbccActiveJobsBar || !tbccActiveJobsList) return;
  void syncPauseImportQueueButton();
  void refreshImportQueueDepthHint();
  const localJobs = [];
  if (inboxPoolBackground.running || inboxPoolBackground.jobs.length) {
    localJobs.push({
      label: `Inbox pool import (${inboxPoolBackground.jobs.length} queued)`,
      type: "inbox-import",
      startedAt: Date.now(),
    });
  }
  const remote = await new Promise((resolve) => {
    chrome.runtime.sendMessage({ action: "tbcc-gallery-job-list" }, (r) => {
      if (chrome.runtime.lastError) resolve([]);
      else resolve((r && r.jobs) || []);
    });
  });
  const jobs = [...remote, ...localJobs];
  if (!jobs.length) {
    tbccActiveJobsBar.hidden = true;
    tbccActiveJobsList.innerHTML = "";
    return;
  }
  tbccActiveJobsBar.hidden = false;
  const now = Date.now();
  tbccActiveJobsList.innerHTML = "";
  for (const j of jobs) {
    const li = document.createElement("li");
    const age = formatJobAge(now - (j.startedAt || now));
    const stage = j.stage ? ` — ${j.stage}` : "";
    const err = j.error ? ` ⚠ ${j.error}` : "";
    const label = document.createElement("span");
    label.className = "tbcc-active-jobs-list__label";
    label.textContent = `${j.label || j.type || "Task"}${stage} (${age})${err}`;
    li.appendChild(label);
    const canCancel =
      j.id &&
      !tbccIsLocalImportJobTerminal(j) &&
      (j.backendJobId || j.type === "send-batch" || j.type === "crawl-tab");
    if (canCancel) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "tbcc-active-jobs-list__cancel";
      btn.textContent = "Cancel";
      btn.title = j.backendJobId ? "Cancel server import job" : "Remove task from list";
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        void cancelGalleryJob(j);
      });
      li.appendChild(btn);
    }
    if (j.status === "failed" || j.status === "cancelled" || j.error) li.style.color = "rgb(248 113 113)";
    else if (tbccIsLocalImportJobTerminal(j)) li.style.color = "rgb(134 239 172)";
    else if (now - (j.startedAt || now) > 15 * 60 * 1000) li.style.color = "rgb(251 191 36)";
    tbccActiveJobsList.appendChild(li);
  }
}

function setFilterOverlayOpen(open) {
  if (!filterOverlay) return;
  if (!open && filterOverlay.contains(document.activeElement)) {
    try {
      if (btnFilterToggle) btnFilterToggle.focus();
      else document.activeElement?.blur?.();
    } catch (_) {}
  }
  filterOverlay.classList.toggle("visible", !!open);
  filterOverlay.setAttribute("aria-hidden", open ? "false" : "true");
  if (open && filterMinW) {
    requestAnimationFrame(() => {
      try {
        filterMinW.focus();
      } catch (_) {}
    });
  }
}

function resetFilterFields() {
  if (filterType) filterType.value = "";
  if (filterMinW) filterMinW.value = "";
  if (filterMinH) filterMinH.value = "";
  if (filterUrl) filterUrl.value = "";
  if (filterHideUiClutter) filterHideUiClutter.checked = false;
  saveGalleryUiState();
  renderGrid();
}

function setCropPopoverOpen(open) {
  if (!cropPopover) return;
  cropPopover.classList.toggle("visible", !!open);
  cropPopover.setAttribute("aria-hidden", open ? "false" : "true");
  if (open) initCropStudioPanel();
}

function updateActionBarSubtitle() {}

async function importSavedUrlJson(urls, poolId, captionOverride) {
  const normalized = (urls || []).map((u) => normalizeTbccMediaUrlForImport(u));
  const payload = { urls: normalized, pool_id: poolId, saved_only: true };
  const c =
    captionOverride != null && String(captionOverride).trim()
      ? String(captionOverride).trim()
      : getAlbumCaptionForSend();
  if (c) payload.caption = c;
  const r = await fetch(API_BASE + "/import/url", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseImportResponse(r);
}

let zipPromoPayloadCache = null;

async function fetchZipPromoPayload() {
  if (zipPromoPayloadCache) return zipPromoPayloadCache;
  try {
    const r = await fetch(API_BASE + "/zip-bundle-settings/extension-payload");
    if (!r.ok) return { enabled: false };
    zipPromoPayloadCache = await r.json();
    return zipPromoPayloadCache;
  } catch (_) {
    return { enabled: false };
  }
}

/** Resolve whether to add global ZIP promo for a gallery selection. */
async function resolveZipPromoForSelection(selected) {
  const items = Array.isArray(selected) ? selected : [];
  if (items.some((i) => i && i.tbccIncludeZipPromo === true)) return true;
  if (items.some((i) => i && i.tbccIncludeZipPromo === false)) return false;
  try {
    const local = await chrome.storage.local.get(["tbccZipPromoInGallery"]);
    return local.tbccZipPromoInGallery !== false;
  } catch (_) {
    return true;
  }
}

/** Add global promo readme + image from TBCC settings (Misc → ZIP promo inserts). */
async function appendZipPromoFiles(zip, opts) {
  const force = opts && opts.force;
  const skip = opts && opts.skip;
  if (skip) return 0;
  if (!force) {
    try {
      const local = await chrome.storage.local.get(["tbccZipPromoInGallery"]);
      if (local.tbccZipPromoInGallery === false) return 0;
    } catch (_) {}
  }
  const p = await fetchZipPromoPayload();
  if (!p || !p.enabled) return 0;
  let n = 0;
  if (p.include_text_file && p.text_body) {
    zip.file(p.text_filename || "TBCC_README.txt", p.text_body);
    n++;
  }
  if (p.include_image && p.image_url) {
    try {
      const ir = await fetch(p.image_url);
      if (ir.ok) {
        const blob = await ir.blob();
        zip.file(p.image_filename || "TBCC_PROMO.jpg", blob);
        n++;
      }
    } catch (_) {}
  }
  return n;
}

async function downloadSelectedAsZip() {
  const list = getFilteredList();
  const selected = list.filter((i) => selectedUrls.has(i.url));
  if (selected.length === 0 || !chrome.downloads) return;
  const jobId = await beginGalleryJob("zip-export", "ZIP export");
  try {
  if (typeof JSZip === "undefined") {
    if (progressEl) progressEl.classList.add("visible");
    if (progressTitle) progressTitle.textContent = "ZIP bundle";
    if (progressStatus) progressStatus.textContent = "JSZip library missing — reload the side panel.";
    if (btnDownloadZip) btnDownloadZip.disabled = selectedCountInFilteredList() === 0;
    if (btnDownload) btnDownload.disabled = selectedCountInFilteredList() === 0;
    if (btnCopyJd) btnCopyJd.disabled = selectedCountInFilteredList() === 0;
    return;
  }
  btnDownloadZip.disabled = true;
  if (btnDownload) btnDownload.disabled = true;
  if (btnCopyJd) btnCopyJd.disabled = true;
  if (progressError) progressError.textContent = "";
  if (progressEl) progressEl.classList.add("visible");
  if (progressTitle) progressTitle.textContent = "ZIP bundle";
  if (progressFill) progressFill.style.width = "0%";

  const zip = new JSZip();
  let ok = 0;
  const total = selected.length;
  for (let i = 0; i < total; i++) {
    try {
      const { filename, blob } = await getBlobAndNameForZipItem(selected[i], i);
      zip.file(filename, blob);
      ok++;
    } catch (e) {
      if (progressError)
        progressError.textContent = (progressError.textContent || "") + (e.message || "error") + "; ";
    }
    if (progressStatus) progressStatus.textContent = "Packing " + (i + 1) + " / " + total;
    if (progressFill) progressFill.style.width = Math.round(((i + 1) / total) * 100) + "%";
  }

  if (ok === 0) {
    if (progressStatus) progressStatus.textContent = "No files added to ZIP.";
    btnDownloadZip.disabled = false;
    if (btnDownload) btnDownload.disabled = selectedCountInFilteredList() === 0;
    if (btnCopyJd) btnCopyJd.disabled = selectedCountInFilteredList() === 0;
    return;
  }

  try {
    const includePromo = await resolveZipPromoForSelection(selected);
    const promoAdded = await appendZipPromoFiles(zip, { force: includePromo, skip: !includePromo });
    if (promoAdded > 0 && progressStatus) {
      progressStatus.textContent = "Added " + promoAdded + " promo file(s) to ZIP…";
    }
    if (progressStatus) progressStatus.textContent = "Compressing…";
    const out = await zip.generateAsync(
      { type: "blob", compression: "DEFLATE", compressionOptions: { level: 6 } },
      (meta) => {
        if (progressFill && meta && meta.percent != null) progressFill.style.width = meta.percent + "%";
        if (progressStatus) progressStatus.textContent = "Compressing… " + Math.round(meta.percent || 0) + "%";
      }
    );
    const blobUrl = URL.createObjectURL(out);
    const stamp = new Date().toISOString().slice(0, 19).replace(/[-:T]/g, "");
    await new Promise((resolve) => {
      chrome.downloads.download({ url: blobUrl, filename: "tbcc/tbcc_bundle_" + stamp + ".zip", saveAs: false }, () => {
        URL.revokeObjectURL(blobUrl);
        resolve();
      });
    });
    const msg = "Saved ZIP with " + ok + " file(s) to Downloads/tbcc/ (use for digital bundle upload).";
    if (progressStatus) progressStatus.textContent = msg;
    notifyCompletion(msg, "success", "notifyOnZipComplete", "TBCC ZIP complete", {
      type: "url",
      url: "http://localhost:5173/",
    });
  } catch (e) {
    if (progressError) progressError.textContent = (progressError.textContent || "") + (e.message || "ZIP failed") + "; ";
  }
  btnDownloadZip.disabled = false;
  if (btnDownload) btnDownload.disabled = selectedCountInFilteredList() === 0;
  if (btnCopyJd) btnCopyJd.disabled = selectedCountInFilteredList() === 0;
  } finally {
    endGalleryJob(jobId);
  }
}

async function sendSelectedToJDownloader() {
  const list = getFilteredList();
  const selected = list.filter((i) => selectedUrls.has(i.url));
  const lines = selected
    .map((i) => {
      const page = i.tbccSourcePageUrl || "";
      if (page && /^https?:\/\//i.test(page)) return page;
      return bestHttpMediaUrlForItem(i) || i.url;
    })
    .filter((u) => typeof u === "string" && (u.startsWith("http://") || u.startsWith("https://")));
  const uniq = [...new Set(lines)];
  if (!uniq.length) return;
  if (progressEl) progressEl.classList.add("visible");
  if (progressStatus) progressStatus.textContent = "Sending " + uniq.length + " link(s) to JDownloader…";
  try {
    const r = await fetch(API_BASE + "/jd/add-links", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        links: uniq.join("\n"),
        package_name: "TBCC gallery " + new Date().toISOString().slice(0, 16).replace("T", " "),
        autostart: false,
      }),
    });
    const text = await r.text();
    let data = {};
    try {
      data = text ? JSON.parse(text) : {};
    } catch (_) {}
    if (!r.ok) throw new Error((data && data.detail) || text || r.statusText);
    if (progressStatus)
      progressStatus.textContent = "Added " + uniq.length + " link(s) to JDownloader LinkGrabber.";
    showToast("Sent to JDownloader. Check LinkCollector in JD or My.JDownloader.", "success");
  } catch (e) {
    try {
      const clip = globalThis.TbccClipboard;
      if (clip && clip.copyText) {
        await clip.copyText(uniq.join("\n"), { anchor: btnCopyJd || undefined });
      } else {
        await navigator.clipboard.writeText(uniq.join("\n"));
        showToast("Copied!", "success");
      }
      if (progressStatus)
        progressStatus.textContent =
          "MyJD unavailable — copied " + uniq.length + " URL(s) for manual paste.";
      showToast((e && e.message ? e.message : "MyJD failed") + " — URLs copied to clipboard.", "info");
    } catch (clipErr) {
      if (progressError)
        progressError.textContent =
          (progressError.textContent || "") + (clipErr.message || e.message || "send failed") + "; ";
    }
  }
}

async function downloadSelected() {
  const list = getFilteredList();
  const selected = list.filter((i) => selectedUrls.has(i.url));
  if (selected.length === 0 || !chrome.downloads) return;
  const jobId = await beginGalleryJob("download", "Gallery download");
  try {
  btnDownload.disabled = true;
  if (btnDownloadZip) btnDownloadZip.disabled = true;
  if (btnCopyJd) btnCopyJd.disabled = true;
  let n = 0;
  for (let i = 0; i < selected.length; i++) {
    const it = selected[i];
    const idx = String(i + 1).padStart(2, "0");
    try {
      if (it.file) {
        let dlBlob = it.file;
        let name = (it.name || "file").replace(/[^\w.\-]+/g, "_");
        if (isImageItem(it) && shouldApplyImagePipelineForUrl(it.url)) {
          try {
            dlBlob = await applyImagePipeline(
              new Blob([await it.file.arrayBuffer()], { type: it.file.type || "application/octet-stream" }),
              it.url
            );
            name = /\.(jpe?g)$/i.test(name) ? name : (name.replace(/\.[^.]+$/, "") || "file") + ".jpg";
          } catch (_) {}
        }
        const blobUrl = URL.createObjectURL(dlBlob);
        await new Promise((resolve) => {
          chrome.downloads.download({ url: blobUrl, filename: "tbcc/" + name, saveAs: false }, () => {
            URL.revokeObjectURL(blobUrl);
            resolve();
          });
        });
      } else if (it.url && (it.url.startsWith("http://") || it.url.startsWith("https://"))) {
        const httpFetchUrl = bestHttpMediaUrlForItem(it) || it.url;
        if (
          typeof tbccIsLikelyHtmlPageUrl === "function" &&
          (it.mediaType === "video" || String(it.tagName || "").toLowerCase() === "video") &&
          tbccIsLikelyHtmlPageUrl(httpFetchUrl)
        ) {
          throw new Error(
            "That URL is a page (HTML), not a video file. The extension needs a direct .mp4 (or similar) link — or use JDownloader / your backend to resolve the stream."
          );
        }
        if (isImageItem(it) && shouldApplyImagePipelineForUrl(it.url)) {
          const raw = await fetchUrlBytesToBlob(it.url, await tbccRefererPageForItem(it));
          if (!raw || !raw.size) throw new Error("Could not fetch image for processing");
          const out = await applyImagePipeline(raw, it.url);
          const filename = "tbcc/" + idx + "_" + filenameForCropUrl(it.url);
          const blobUrl = URL.createObjectURL(out);
          await new Promise((resolve, reject) => {
            chrome.downloads.download({ url: blobUrl, filename, saveAs: false }, () => {
              URL.revokeObjectURL(blobUrl);
              if (chrome.runtime.lastError) reject(new Error(chrome.runtime.lastError.message));
              else resolve();
            });
          });
        } else if (hostNeedsSessionFetch(httpFetchUrl)) {
          const raw = await fetchUrlBytesToBlob(httpFetchUrl, await tbccRefererPageForItem(it));
          if (!raw || !raw.size) throw new Error("Could not fetch media for download (session)");
          const base = filenameFromUrl(httpFetchUrl);
          const ext =
            it.mediaType === "video" || String(it.tagName || "").toLowerCase() === "video"
              ? /\.(mp4|webm|m4v|mov|mkv|m3u8|mpd)(\?|$)/i.test(base)
                ? ""
                : ".mp4"
              : "";
          const hasExt = /\.\w{2,5}$/i.test(base);
          const filename = ("tbcc/" + idx + "_" + (hasExt ? base : base + ext)).replace(/[^\w.\-]+/g, "_");
          const blobUrl = URL.createObjectURL(raw);
          await new Promise((resolve, reject) => {
            chrome.downloads.download({ url: blobUrl, filename, saveAs: false }, () => {
              URL.revokeObjectURL(blobUrl);
              if (chrome.runtime.lastError) reject(new Error(chrome.runtime.lastError.message));
              else resolve();
            });
          });
        } else {
          const base = filenameFromUrl(httpFetchUrl);
          const ext = it.mediaType === "video" || (it.tagName || "").toLowerCase() === "video" ? ".mp4" : "";
          const hasExt = /\.\w{2,5}$/i.test(base);
          const filename = "tbcc/" + idx + "_" + (hasExt ? base : base + ext);
          await new Promise((resolve, reject) => {
            chrome.downloads.download({ url: httpFetchUrl, filename, saveAs: false }, () => {
              if (chrome.runtime.lastError) reject(new Error(chrome.runtime.lastError.message));
              else resolve();
            });
          });
        }
      } else if (it.url && String(it.url).startsWith("data:image/")) {
        try {
          const r = await fetch(it.url);
          let b = await r.blob();
          if (isImageItem(it) && shouldApplyImagePipelineForUrl(it.url)) {
            b = await applyImagePipeline(b, it.url);
          }
          const blobUrl = URL.createObjectURL(b);
          await new Promise((resolve, reject) => {
            chrome.downloads.download(
              { url: blobUrl, filename: "tbcc/" + idx + "_" + filenameForCropUrl(it.url), saveAs: false },
              () => {
                URL.revokeObjectURL(blobUrl);
                if (chrome.runtime.lastError) reject(new Error(chrome.runtime.lastError.message));
                else resolve();
              }
            );
          });
        } catch (e) {
          throw new Error("Could not download data URL image");
        }
      } else if (it.url && it.url.startsWith("blob:")) {
        if (isImageItem(it) && shouldApplyImagePipelineForUrl(it.url)) {
          const r = await fetch(it.url);
          let b = await r.blob();
          b = await applyImagePipeline(b, it.url);
          const blobUrl = URL.createObjectURL(b);
          await new Promise((resolve) => {
            chrome.downloads.download({ url: blobUrl, filename: "tbcc/" + idx + "_media.jpg", saveAs: false }, () => {
              URL.revokeObjectURL(blobUrl);
              resolve();
            });
          });
        } else {
          try {
            const tw = await tbccTryResolveBlobVideoViaTwitterNet(it);
            if (tw) {
              it.url = tw;
              it.mediaType = "video";
              it.tagName = "video";
              i--;
              continue;
            }
            const r = await fetch(it.url);
            const b = await r.blob();
            const ext =
              it.mediaType === "video" || String(it.tagName || "").toLowerCase() === "video" ? ".mp4" : "";
            const blobUrl = URL.createObjectURL(b);
            await new Promise((resolve, reject) => {
              chrome.downloads.download(
                { url: blobUrl, filename: "tbcc/" + idx + "_media" + ext, saveAs: false },
                () => {
                  URL.revokeObjectURL(blobUrl);
                  if (chrome.runtime.lastError) reject(new Error(chrome.runtime.lastError.message));
                  else resolve();
                }
              );
            });
          } catch (_) {
            throw new Error(
              "Page-only blob: video — play clips on X so video.twimg.com URLs appear, then tap Refresh in TBCC and try again."
            );
          }
        }
      }
      n++;
    } catch (e) {
      if (progressError) progressError.textContent = (progressError.textContent || "") + (e.message || "download failed") + "; ";
    }
  }
  if (progressEl && n > 0) {
    progressEl.classList.add("visible");
    progressStatus.textContent = "Downloaded " + n + " file(s) to your Downloads/tbcc folder (or browser default).";
  }
  btnDownload.disabled = false;
  if (btnDownloadZip) btnDownloadZip.disabled = selectedCountInFilteredList() === 0;
  if (btnCopyJd) btnCopyJd.disabled = selectedCountInFilteredList() === 0;
  } finally {
    endGalleryJob(jobId);
  }
}

btnDownload && btnDownload.addEventListener("click", () => downloadSelected());
btnDownloadZip && btnDownloadZip.addEventListener("click", () => downloadSelectedAsZip());
btnCopyJd && btnCopyJd.addEventListener("click", () => void sendSelectedToJDownloader());
btnCrawlTab && btnCrawlTab.addEventListener("click", () => void crawlActiveTab());
void refreshCrawlerTabUrlLabel();

selectAllCb && selectAllCb.addEventListener("change", () => {
  const list = getFilteredList();
  if (selectAllCb.checked) list.forEach((i) => selectedUrls.add(i.url));
  else list.forEach((i) => selectedUrls.delete(i.url));
  renderGrid();
});

chrome.storage.onChanged.addListener((changes, area) => {
  if (area !== "local") return;
  if (changes[STORAGE_SETTINGS]) {
    const nv = changes[STORAGE_SETTINGS].newValue;
    if (nv && typeof nv === "object") {
      settings = { ...settings, ...nv };
      syncCropUiFromSettings();
      syncCropOverflowLabel();
    }
  }
  if (changes[STORAGE_IMAGE_EDITS]) {
    const nv = changes[STORAGE_IMAGE_EDITS].newValue;
    if (nv && typeof nv === "object" && !Array.isArray(nv)) imageEdits = nv;
    else imageEdits = {};
    syncCropOverflowLabel();
  }
  if (changes[STORAGE_SELECTION]) {
    const gen = changes.tbccSelectionGen && changes.tbccSelectionGen.newValue;
    if (gen != null && gen === gallerySelectionPersistGen) return;

    const newVal = Array.isArray(changes[STORAGE_SELECTION].newValue) ? changes[STORAGE_SELECTION].newValue : [];
    const merged = new Set(selectedUrls);
    for (const r of newVal) {
      if (!r || typeof r !== "string") continue;
      if (/^(slot:|seq:|hash:)/.test(r)) {
        const u = resolveSelectionRefToUrl(r);
        if (u) merged.add(u);
      } else if (
        r.startsWith("http://") ||
        r.startsWith("https://") ||
        r.startsWith("data:") ||
        r.startsWith("blob:")
      ) {
        merged.add(r);
      }
    }
    if (merged.size === 0 && newVal.length > 0 && selectedUrls.size > 0) return;
    if (setsEqual(merged, selectedUrls)) return;
    selectedUrls = merged;
    mergeUrlsIntoImageListFromSelection();
    renderGrid();
  }
  if (changes.tbccOverlayMode) void syncOverlayToggleButton();
});

btnToggleOverlay &&
  btnToggleOverlay.addEventListener("click", async () => {
    const { tbccOverlayMode } = await chrome.storage.local.get("tbccOverlayMode");
    await chrome.storage.local.set({ tbccOverlayMode: !tbccOverlayMode });
    await syncOverlayToggleButton();
    const tid = await resolveTargetTabId();
    if (!tid) return;
    const ok = await ensureOverlayScriptReady(tid);
    if (!ok) {
      alert("Could not enable on-screen buttons on this tab. Open a normal http(s) page and reload that tab once.");
    }
  });

btnSelectAllOnPage &&
  btnSelectAllOnPage.addEventListener("click", async () => {
    const tid = await resolveTargetTabId();
    if (!tid) return;
    try {
      await chrome.tabs.sendMessage(tid, { action: "tbcc-overlay-select-all" });
    } catch (_) {
      alert("Could not reach this page — reload the tab or open a normal https page.");
    }
  });

[filterType, filterMinW, filterMinH, filterUrl, filterHideUiClutter].forEach((el) => {
  if (!el) return;
  el.addEventListener("change", () => {
    saveGalleryUiState();
    renderGrid();
  });
});
[filterMinW, filterMinH, filterUrl].forEach((el) => {
  if (!el) return;
  el.addEventListener("input", () => {
    saveGalleryUiState();
    if (el === filterUrl) renderGrid();
  });
});

tabCurrentBtn &&
  tabCurrentBtn.addEventListener("click", async () => {
    activeTab = "current";
    syncCaptureTabButtons();
    saveGalleryUiState();
    await clearSelectionForNewCapture();
    doRefresh();
  });
tabGroupBtn &&
  tabGroupBtn.addEventListener("click", async () => {
    activeTab = "group";
    syncCaptureTabButtons();
    saveGalleryUiState();
    await clearSelectionForNewCapture();
    doRefresh();
  });
tabAllBtn &&
  tabAllBtn.addEventListener("click", async () => {
    activeTab = "all";
    syncCaptureTabButtons();
    saveGalleryUiState();
    await clearSelectionForNewCapture();
    doRefresh();
  });

btnGalleryDock &&
  btnGalleryDock.addEventListener("click", async () => {
    const docked = !!(galleryDockedTab && galleryDockedTab.tabId != null);
    await setGalleryTabDock(!docked);
  });

chrome.storage.onChanged.addListener((changes, area) => {
  if (area !== "local" || !changes.tbccGalleryDockedTab) return;
  const next = changes.tbccGalleryDockedTab.newValue;
  if (next && next.tabId != null) {
    galleryDockedTab = next;
    currentTabId = next.tabId;
  } else {
    galleryDockedTab = null;
  }
  syncGalleryDockUi();
  void refreshCrawlerTabUrlLabel();
});

btnGalleryPopOut &&
  btnGalleryPopOut.addEventListener("click", () => {
    try {
      chrome.windows.create(
        {
          url: chrome.runtime.getURL("gallery.html"),
          type: "popup",
          width: 560,
          height: 920,
          focused: true,
        },
        () => {
          const err = chrome.runtime.lastError;
          if (err) showToast(err.message || "Could not open pop-out window", "error");
        }
      );
    } catch (e) {
      showToast((e && e.message) || "Could not open pop-out window", "error");
    }
  });

btnRefresh && btnRefresh.addEventListener("click", () => refreshPanelOrHardScan());

const btnTbccLaunchApiFromGallery = document.getElementById("btnTbccLaunchApiFromGallery");
const btnTbccRetryApiFromGallery = document.getElementById("btnTbccRetryApiFromGallery");
if (btnTbccLaunchApiFromGallery && typeof globalThis.tbccLaunchFullStack === "function") {
  btnTbccLaunchApiFromGallery.addEventListener("click", () => {
    globalThis.tbccLaunchFullStack();
    showToast("Launching TBCC stack…", "info");
  });
}
if (btnTbccRetryApiFromGallery) {
  btnTbccRetryApiFromGallery.addEventListener("click", () => {
    invalidateTbccApiReachableCache();
    void refreshTbccApiOfflineBanner().then((ok) => {
      if (ok) {
        void Promise.all([loadTagCatalog(), loadPools(), loadChannelsForForum()]).then(() =>
          showToast("API connected.", "info")
        );
      } else {
        showToast("API still offline — start backend or use Launch full stack.", "info");
      }
    });
  });
}

viewMainEl &&
  viewMainEl.addEventListener("contextmenu", (e) => {
    if (viewMainEl.hidden) return;
    if (e.target.closest && e.target.closest("#tbccGalleryCtxMenu")) {
      e.preventDefault();
      return;
    }
    if (galleryCtxMenuIgnoresTarget(e.target)) return;
    e.preventDefault();
    openGalleryContextMenu(e.clientX, e.clientY);
  });

galleryCtxMenu &&
  galleryCtxMenu.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-ctx]");
    if (!btn || btn.disabled) return;
    e.stopPropagation();
    onGalleryContextMenuAction(btn.getAttribute("data-ctx"));
  });

document.addEventListener(
  "click",
  (e) => {
    if (!galleryCtxMenu || galleryCtxMenu.hidden) return;
    if (e.target.closest && e.target.closest("#tbccGalleryCtxMenu")) return;
    closeGalleryContextMenu();
  },
  true
);

document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape" || !galleryCtxMenu || galleryCtxMenu.hidden) return;
  closeGalleryContextMenu();
});

gridEl &&
  gridEl.addEventListener(
    "scroll",
    () => {
      closeGalleryContextMenu();
    },
    { passive: true }
  );

btnSelectToggle &&
  btnSelectToggle.addEventListener("click", runSelectToggle);

btnSelectAnchorToggle && btnSelectAnchorToggle.addEventListener("click", runSelectAnchorToggle);

if (tagCatalogComboboxMount && typeof createTagCatalogCombobox === "function") {
  tagCatalogCombobox = createTagCatalogCombobox(tagCatalogComboboxMount, {
    placeholder: "Search catalog…",
    onPick: onCatalogTagPicked,
  });
}
btnTagSuggest && btnTagSuggest.addEventListener("click", () => void suggestTagsFromPage());
btnTagsCatalogReload && btnTagsCatalogReload.addEventListener("click", () => void loadTagCatalog());
btnTagCreate && btnTagCreate.addEventListener("click", () => void createTagOnServer());
btnTagsClear && btnTagsClear.addEventListener("click", () => clearGallerySendTags());

fileInput && fileInput.addEventListener("change", () => {
  if (fileInput.files && fileInput.files.length) addLocalFiles(fileInput.files);
  fileInput.value = "";
});

poolSelect &&
  poolSelect.addEventListener("change", () => {
    syncPoolSelectTooltip();
    if (poolSelect.value) chrome.storage.local.set({ tbccPoolId: parseInt(poolSelect.value, 10) });
  });

sendSilent &&
  sendSilent.addEventListener("change", async () => {
    await chrome.storage.local.set({ [STORAGE_SEND_SILENT]: !!sendSilent.checked });
  });

forumPostEnabled &&
  forumPostEnabled.addEventListener("change", async () => {
    await chrome.storage.local.set({ tbccForumPostEnabled: !!forumPostEnabled.checked });
    updateTelegramPostControls();
    if (
      forumPostEnabled.checked &&
      forumChannelSelect &&
      forumChannelSelect.value &&
      postDestMode &&
      postDestMode.value === "forum"
    )
      await loadForumTopics(parseInt(forumChannelSelect.value, 10));
  });
autoTagOnExport &&
  autoTagOnExport.addEventListener("change", async () => {
    await chrome.storage.local.set({ [STORAGE_AUTO_TAG_ON_EXPORT]: !!autoTagOnExport.checked });
    updateTelegramPostControls();
  });
btnDestMacroPool &&
  btnDestMacroPool.addEventListener("click", () => void applyDestMacro("pool"));
btnDestMacroSaved &&
  btnDestMacroSaved.addEventListener("click", () => void applyDestMacro("saved"));
btnDestMacroForum &&
  btnDestMacroForum.addEventListener("click", () => void applyDestMacro("forum"));
btnDestMacroChannel &&
  btnDestMacroChannel.addEventListener("click", () => void applyDestMacro("channel"));
forumChannelSelect &&
  forumChannelSelect.addEventListener("change", async () => {
    const v = forumChannelSelect.value ? parseInt(forumChannelSelect.value, 10) : null;
    await chrome.storage.local.set({ tbccForumChannelId: v });
    updateTelegramPostControls();
    if (v && postDestMode && postDestMode.value === "forum") await loadForumTopics(v);
    else setForumTopicOptions([], null);
  });
forumTopicSelect &&
  forumTopicSelect.addEventListener("change", async () => {
    const v = forumTopicSelect.value ? parseInt(forumTopicSelect.value, 10) : null;
    await chrome.storage.local.set({ tbccForumTopicId: v });
  });
forumAlbumCaption &&
  forumAlbumCaption.addEventListener("input", () => {
    const lines = buildAlwaysIncludeLinksLines();
    captionBaseText = stripTrailingLinkBlock(forumAlbumCaption.value || "", lines);
    void persistCaptionSlicesToStorage();
  });
btnAutoCap && btnAutoCap.addEventListener("click", () => void autoCapFromPage());
btnAlwaysIncludeToggle &&
  btnAlwaysIncludeToggle.addEventListener("click", (e) => {
    e.stopPropagation();
    if (!alwaysIncludePopover) return;
    alwaysIncludePopover.hidden = !alwaysIncludePopover.hidden;
    btnAlwaysIncludeToggle.setAttribute("aria-expanded", alwaysIncludePopover.hidden ? "false" : "true");
    if (!alwaysIncludePopover.hidden) {
      renderAlwaysIncludeChannelList();
      renderAlwaysIncludeCustomList();
    }
  });
btnAlwaysIncludeCustomAdd &&
  btnAlwaysIncludeCustomAdd.addEventListener("click", async () => {
    const label = alwaysIncludeCustomLabel ? alwaysIncludeCustomLabel.value.trim() : "";
    const url = alwaysIncludeCustomUrl ? alwaysIncludeCustomUrl.value.trim() : "";
    if (!url || !/^https?:\/\//i.test(url)) {
      showToast("Enter a URL starting with http(s)://", "info");
      return;
    }
    const id =
      typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
        ? crypto.randomUUID()
        : "c_" + Date.now();
    const nextCustom = [...(alwaysIncludeCaptionState.custom || []), { id, label: label || "Link", url, enabled: true }];
    await saveAlwaysIncludeCaptionState({ ...alwaysIncludeCaptionState, custom: nextCustom });
    if (alwaysIncludeCustomUrl) alwaysIncludeCustomUrl.value = "";
    if (alwaysIncludeCustomLabel) alwaysIncludeCustomLabel.value = "";
    renderAlwaysIncludeCustomList();
    showToast("Custom link added — toggle checkboxes to include in sends.", "success");
  });
  btnCaptionLibraryOpen.addEventListener("click", async () => {
    if (captionLibTitle) captionLibTitle.value = "";
    if (captionLibBody) captionLibBody.value = "";
    await renderCaptionLibraryModalList();
    setCaptionLibraryModalOpen(true);
  });
captionLibraryClose &&
  captionLibraryClose.addEventListener("click", () => setCaptionLibraryModalOpen(false));
captionLibraryBackdrop &&
  captionLibraryBackdrop.addEventListener("click", () => setCaptionLibraryModalOpen(false));
btnCaptionLibSave &&
  btnCaptionLibSave.addEventListener("click", async () => {
    const title = captionLibTitle ? captionLibTitle.value.trim() : "";
    const body = captionLibBody ? captionLibBody.value.trim() : "";
    if (!body) {
      showToast("Enter caption text to save.", "info");
      return;
    }
    try {
      const r = await fetch(API_BASE + "/caption-snippets/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: title || null, body }),
      });
      const text = await r.text();
      if (!r.ok) throw new Error(text || `HTTP ${r.status}`);
      if (captionLibTitle) captionLibTitle.value = "";
      if (captionLibBody) captionLibBody.value = "";
      await renderCaptionLibraryModalList();
      showToast("Saved to caption library.", "success");
    } catch (e) {
      showToast("Save failed: " + (e.message || String(e)), "error");
    }
  });
btnForumTopicsRefresh &&
  btnForumTopicsRefresh.addEventListener("click", async () => {
    const v = forumChannelSelect && parseInt(forumChannelSelect.value, 10);
    if (v) await loadForumTopics(v);
  });
function hostNeedsSessionFetch(url) {
  try {
    const h = new URL(url).hostname.toLowerCase();
    return (
      h === "onlyfans.com" ||
      h.endsWith(".onlyfans.com") ||
      h === "erome.com" ||
      h.endsWith(".erome.com") ||
      h === "motherless.com" ||
      h.endsWith(".motherless.com") ||
      h.includes("motherlessmedia.com") ||
      h.includes("coomer.st") ||
      h.includes("coomer.party") ||
      h.includes("kemono.party") ||
      h.includes("kemono.su") ||
      h.includes("kemono.si") ||
      h === "fapello.com" ||
      h.endsWith(".fapello.com") ||
      h === "fetlife.com" ||
      h.endsWith(".fetlife.com") ||
      h === "nudostar.com" ||
      h.endsWith(".nudostar.com") ||
      h === "video.twimg.com"
    );
  } catch (_) {
    return false;
  }
}

function shouldRetryImportViaSession(url, err) {
  const msg = String(err || "").toLowerCase();
  const u = String(url || "").toLowerCase();
  if (hostNeedsSessionFetch(url)) return true;
  if (u.includes("/attachments/") || u.includes("/data/attachments/")) return true;
  return (
    msg.includes("403") ||
    msg.includes("forbidden") ||
    msg.includes("could not download") ||
    msg.includes("access denied") ||
    msg.includes("cloudflare") ||
    msg.includes("captcha") ||
    msg.includes("referer")
  );
}

/** Fetch image bytes using Chrome cookie jar + Referer (same idea as a logged-in tab). */
async function importUrlViaExtensionSession(url, poolId, savedOnly, refererPageUrl, captionOverride) {
  url = normalizeTbccMediaUrlForImport(url);
  const cap =
    captionOverride != null && String(captionOverride).trim() !== ""
      ? String(captionOverride).trim()
      : savedOnly
        ? getAlbumCaptionForSend()
        : "";
  return new Promise((resolve) => {
    chrome.runtime.sendMessage(
      {
        action: "tbcc-import-bytes-session",
        url,
        poolId,
        savedOnly: !!savedOnly,
        source: "extension:gallery-session",
        refererPageUrl: typeof refererPageUrl === "string" ? refererPageUrl : "",
        caption: cap || undefined,
      },
      (data) => {
        if (chrome.runtime.lastError) resolve({ error: chrome.runtime.lastError.message });
        else resolve(data && typeof data === "object" ? data : { error: "No response" });
      }
    );
  });
}

/** Same as context menu: backend fetches URL (fast; works for public hotlinks). */
async function importOneUrl(url, poolId, savedOnly, captionOverride) {
  try {
    url = normalizeTbccMediaUrlForImport(url);
    const payload = { url, pool_id: poolId };
    if (savedOnly) {
      payload.saved_only = true;
      const c =
        captionOverride != null && String(captionOverride).trim() !== ""
          ? String(captionOverride).trim()
          : getAlbumCaptionForSend();
      if (c) payload.caption = c;
    }
    const resp = await fetch(API_BASE + "/import/url", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const text = await resp.text();
    let data = {};
    try {
      data = text ? JSON.parse(text) : {};
    } catch (_) {}
    if (!resp.ok && !data.error) data.error = (text && text.slice(0, 240)) || "HTTP " + resp.status;
    return data;
  } catch (e) {
    return { error: String(e.message || e) };
  }
}

/** Per-URL in-tab cap (large batches no longer one 2-minute race). */
const IN_TAB_PER_URL_MS = 90000;
/** Telegram media group max size; backend groups Saved Messages sends into albums of up to this many. */
const SAVED_ALBUM_CHUNK = 10;
/** Must match backend `SavedBatchUrlsBody` / `SAVED_BATCH_MAX_FILES` (import_.py) for POST /import/url with urls[]. */
const SAVED_URL_BATCH_MAX = 100;

async function parseImportResponse(r) {
  const text = await r.text();
  let data = {};
  try {
    data = text ? JSON.parse(text) : {};
  } catch (_) {}
  if (!r.ok && !data.error) data.error = (text && text.slice(0, 240)) || "HTTP " + r.status;
  return data;
}

function isPerchanceHttpUrl(url) {
  try {
    return new URL(String(url || "")).hostname.toLowerCase().endsWith("perchance.org");
  } catch (_) {
    return false;
  }
}

function kindForSavedItem(it) {
  if (it.file) return "file";
  /** data: / blob: must be read in-page (often generator iframe) then POST /import/saved-batch from the extension. */
  if (it.url && String(it.url).startsWith("data:")) return "datapage";
  if (it.url && String(it.url).startsWith("blob:") && it.tabId) return "intab:" + it.tabId;
  if (it.url && /^https?:\/\//i.test(it.url)) {
    if (typeof tbccIsPerchanceBadHttpUrl === "function" && tbccIsPerchanceBadHttpUrl(it.url)) {
      if (it.tabId) return "intab:" + it.tabId;
      return "other";
    }
    if (it.tabId && isPerchanceHttpUrl(it.url)) return "intab:" + it.tabId;
    return hostNeedsSessionFetch(it.url) ? "session" : "plain";
  }
  if (it.url && it.tabId) return "intab:" + it.tabId;
  return "other";
}

function groupConsecutiveSavedKinds(selected) {
  const groups = [];
  let cur = null;
  for (const it of selected) {
    const k = kindForSavedItem(it);
    if (!cur || cur.kind !== k) {
      if (cur) groups.push(cur);
      cur = { kind: k, items: [] };
    }
    cur.items.push(it);
  }
  if (cur) groups.push(cur);
  return groups;
}

/** capture.js uses `skipped` for successful Saved Messages batch units; backend uses count. */
function tbccSavedUnitsFromBatch(batch) {
  if (!batch || batch.error) return 0;
  if (typeof batch.saved === "number" && batch.saved > 0) return batch.saved;
  return (batch.imported || 0) + (batch.skipped || 0);
}

function tbccPickBestFrameBatchResults(results, expectLen) {
  let best = null;
  let bestOk = -1;
  for (const fr of results || []) {
    const p = fr && fr.result;
    if (!p || !Array.isArray(p)) continue;
    const ok = p.filter((x) => x && x.length).length;
    if (expectLen > 0 && ok !== expectLen) continue;
    if (ok > bestOk) {
      bestOk = ok;
      best = p;
    }
  }
  return best;
}

/** Fetch blob:/data: URLs inside the page (correct iframe) and return byte arrays to the gallery. */
async function readPageUrlsAsByteArrays(tabId, urls, frameId) {
  const target = tbccScriptTargetForTabFrame(tabId, frameId, urls);
  const results = await chrome.scripting.executeScript({
    target,
    func: async (urlList) => {
      const out = [];
      for (const u of urlList) {
        try {
          const r = await fetch(u);
          if (!r.ok) {
            out.push(null);
            continue;
          }
          const ab = await r.arrayBuffer();
          out.push(Array.from(new Uint8Array(ab)));
        } catch (_) {
          out.push(null);
        }
      }
      return out;
    },
    args: [urls],
  });
  if (target.allFrames && Array.isArray(results) && results.length > 1) {
    return tbccPickBestFrameBatchResults(results, urls.length);
  }
  const p = results && results[0] && results[0].result;
  if (!p || !Array.isArray(p)) return null;
  return p;
}

async function postSavedBatchFilesFromPageItems(items, bump, appendErr, savedCaption) {
  for (let i = 0; i < items.length; i += SAVED_ALBUM_CHUNK) {
    const chunk = items.slice(i, i + SAVED_ALBUM_CHUNK);
    const form = new FormData();
    const sent = [];
    for (let j = 0; j < chunk.length; j++) {
      const it = chunk[j];
      const arr = it._tbccBytes;
      if (!arr || !arr.length) continue;
      let blob = new Blob([new Uint8Array(arr)], { type: "application/octet-stream" });
      if (shouldApplyImagePipelineForUrl(it.url) && isImageItem(it)) {
        try {
          blob = await applyImagePipeline(blob, it.url);
        } catch (_) {}
      }
      const name =
        isImageItem(it) && shouldApplyImagePipelineForUrl(it.url)
          ? filenameForCropUrl(it.url)
          : `media_${j}.jpg`;
      form.append("files", blob, name);
      sent.push(it);
    }
    if (!sent.length) {
      appendErr("Could not read image bytes from the page (tab closed or wrong frame?)");
      continue;
    }
    appendCaptionToSavedForm(form, savedCaption);
    try {
      const r = await fetch(API_BASE + "/import/saved-batch", { method: "POST", body: form });
      const data = await parseImportResponse(r);
      if (data.status === "saved_only" && !data.error) {
        for (const it of sent) {
          await addToCollected({ url: it.url, type: it.type || "image", addedAt: Date.now(), to_saved: true });
          bump();
        }
      } else {
        appendErr(data.error || "Saved batch failed");
      }
    } catch (e) {
      appendErr(e.message || String(e));
    }
  }
}

function importViaExtensionBytesSavedBatch(urls, captionOverride) {
  const cap =
    captionOverride != null && String(captionOverride).trim() !== ""
      ? String(captionOverride).trim()
      : getAlbumCaptionForSend();
  return new Promise((resolve) => {
    chrome.runtime.sendMessage(
      { action: "tbcc-import-bytes-session-saved-batch", urls, caption: cap },
      (data) => {
        if (chrome.runtime.lastError) resolve({ error: chrome.runtime.lastError.message });
        else resolve(data && typeof data === "object" ? data : { error: "No response" });
      }
    );
  });
}

async function runSendSavedBatchAlbums(selected, poolId, bump, appendErr, savedCaption) {
  const cap =
    savedCaption != null && String(savedCaption).trim() !== ""
      ? String(savedCaption).trim()
      : await ensureSavedMessagesCaption(selected);
  const groups = groupConsecutiveSavedKinds(selected);
  for (const g of groups) {
    if (g.kind === "file") {
      for (let i = 0; i < g.items.length; i += SAVED_ALBUM_CHUNK) {
        const chunk = g.items.slice(i, i + SAVED_ALBUM_CHUNK);
        const form = new FormData();
        for (const it of chunk) {
          let fileToSend = it.file;
          let name = it.name || "media";
          if (shouldApplyImagePipelineForUrl(it.url) && isImageItem(it)) {
            try {
              const raw = new Blob([await it.file.arrayBuffer()], {
                type: it.file.type || "application/octet-stream",
              });
              const cropped = await applyImagePipeline(raw, it.url);
              fileToSend = cropped;
              name = /\.(jpe?g)$/i.test(name) ? name : (name.replace(/\.[^.]+$/, "") || "media") + ".jpg";
            } catch (_) {}
          }
          form.append("files", fileToSend, name);
        }
        appendCaptionToSavedForm(form, cap);
        try {
          const r = await fetch(API_BASE + "/import/saved-batch", { method: "POST", body: form });
          const data = await parseImportResponse(r);
          if (data.status === "saved_only" && !data.error) {
            for (const it of chunk) {
              await addToCollected({ url: it.url, type: it.type || "image", addedAt: Date.now(), to_saved: true });
              bump();
            }
          } else {
            appendErr(data.error || "Saved batch failed");
          }
        } catch (e) {
          appendErr(e.message);
        }
      }
    } else if (g.kind === "datapage") {
      for (let i = 0; i < g.items.length; i += SAVED_ALBUM_CHUNK) {
        const chunk = g.items.slice(i, i + SAVED_ALBUM_CHUNK);
        const prepared = [];
        for (const it of chunk) {
          try {
            const raw = await fetchUrlBytesToBlob(it.url, await tbccRefererPageForItem(it));
            if (!raw || !raw.size) {
              appendErr("Could not read image data from gallery tile");
              continue;
            }
            prepared.push({ ...it, _tbccBytes: Array.from(new Uint8Array(await raw.arrayBuffer())) });
          } catch (e) {
            appendErr((e.message || String(e)).slice(0, 160));
          }
        }
        if (prepared.length) await postSavedBatchFilesFromPageItems(prepared, bump, appendErr, cap);
      }
    } else if (g.kind.startsWith("intab:")) {
      const tabId = parseInt(g.kind.slice("intab:".length), 10);
      if (!tabId || isNaN(tabId)) {
        appendErr("Invalid tab for page media");
        continue;
      }
      const byFrame = new Map();
      for (const it of g.items) {
        const fid =
          it.tbccCaptureFrameId != null && Number.isFinite(Number(it.tbccCaptureFrameId))
            ? Number(it.tbccCaptureFrameId)
            : 0;
        if (!byFrame.has(fid)) byFrame.set(fid, []);
        byFrame.get(fid).push(it);
      }
      for (const [frameId, frameItems] of byFrame) {
        for (let i = 0; i < frameItems.length; i += SAVED_ALBUM_CHUNK) {
          const chunk = frameItems.slice(i, i + SAVED_ALBUM_CHUNK);
          const urls = chunk.map((it) => it.url);
          try {
            const payload = await readPageUrlsAsByteArrays(
              tabId,
              urls,
              frameId === 0 ? null : frameId
            );
            if (!payload || payload.length !== chunk.length) {
              appendErr("Could not read images from the page (wrong tab/frame or tab closed)");
              continue;
            }
            const prepared = [];
            for (let j = 0; j < chunk.length; j++) {
              if (payload[j] && payload[j].length) prepared.push({ ...chunk[j], _tbccBytes: payload[j] });
            }
            if (!prepared.length) {
              appendErr("Could not read image bytes from Perchance (blob expired — refresh and resend)");
              continue;
            }
            if (prepared.length < chunk.length) {
              appendErr(
                `${chunk.length - prepared.length} of ${chunk.length} image(s) could not be read from the page`
              );
            }
            await postSavedBatchFilesFromPageItems(prepared, bump, appendErr, cap);
          } catch (e) {
            appendErr(e.message || String(e));
          }
        }
      }
    } else if (g.kind === "plain") {
      /** Backend rejects >100 URLs per JSON body; each chunk still becomes Telegram albums (≤10) server-side. */
      for (let start = 0; start < g.items.length; start += SAVED_URL_BATCH_MAX) {
        const slice = g.items.slice(start, start + SAVED_URL_BATCH_MAX);
        const sliceNeedsBytes = slice.some((it) => isImageItem(it) && shouldApplyImagePipelineForUrl(it.url));
        if (!sliceNeedsBytes) {
          const urls = slice.map((it) => normalizeTbccMediaUrlForImport(it.url));
          try {
            const payload = { urls, pool_id: poolId, saved_only: true };
            if (cap) payload.caption = cap;
            const r = await fetch(API_BASE + "/import/url", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(payload),
            });
            const data = await parseImportResponse(r);
            if (data.status === "saved_only" && !data.error) {
              const okSet =
                Array.isArray(data.ok_urls) && data.ok_urls.length
                  ? new Set(data.ok_urls.map((u) => normalizeTbccMediaUrlForImport(u)))
                  : null;
              for (const it of slice) {
                const u = normalizeTbccMediaUrlForImport(it.url);
                if (okSet && !okSet.has(u)) continue;
                await addToCollected({ url: it.url, type: "image", addedAt: Date.now(), to_saved: true });
                bump();
              }
              if (Array.isArray(data.errors) && data.errors.length) {
                const first = data.errors[0] && data.errors[0].error;
                appendErr(
                  data.errors.length === 1
                    ? first || "One URL failed"
                    : `${data.errors.length} URL(s) failed; others were sent. ${first ? String(first).slice(0, 120) : ""}`
                );
              }
            } else {
              appendErr(data.error || "Saved batch (URLs) failed");
            }
          } catch (e) {
            appendErr(e.message);
          }
        } else {
          let pendingCrops = [];
          const flushCrops = async () => {
            if (!pendingCrops.length) return;
            const form = new FormData();
            pendingCrops.forEach((p, j) => form.append("files", p.blob, p.name || `media_${j}.jpg`));
            appendCaptionToSavedForm(form, cap);
            try {
              const r = await fetch(API_BASE + "/import/saved-batch", { method: "POST", body: form });
              const data = await parseImportResponse(r);
              if (data.status === "saved_only" && !data.error) {
                for (const p of pendingCrops) {
                  await addToCollected({ url: p.url, type: "image", addedAt: Date.now(), to_saved: true });
                  bump();
                }
              } else {
                appendErr(data.error || "Saved batch (cropped) failed");
              }
            } catch (e) {
              appendErr(e.message);
            }
            pendingCrops = [];
          };
          for (const it of slice) {
            if (isImageItem(it) && !shouldApplyImagePipelineForUrl(it.url)) {
              await flushCrops();
              try {
                const data = await importSavedUrlJson([it.url], poolId, cap);
                if (data.status === "saved_only" && !data.error) {
                  await addToCollected({ url: it.url, type: "image", addedAt: Date.now(), to_saved: true });
                  bump();
                } else {
                  appendErr(data.error || "Saved URL import failed");
                }
              } catch (e) {
                appendErr(e.message);
              }
              continue;
            }
            if (isImageItem(it)) {
              try {
                const raw = await fetchUrlBytesToBlob(it.url, await tbccRefererPageForItem(it));
                if (raw && raw.size > 0) {
                  const cropped = await applyImagePipeline(raw, it.url);
                  pendingCrops.push({
                    blob: cropped,
                    name: filenameForCropUrl(it.url),
                    url: it.url,
                  });
                  if (pendingCrops.length >= SAVED_ALBUM_CHUNK) await flushCrops();
                } else {
                  await flushCrops();
                  try {
                    const data = await importSavedUrlJson([it.url], poolId, cap);
                    if (data.status === "saved_only" && !data.error) {
                      await addToCollected({ url: it.url, type: "image", addedAt: Date.now(), to_saved: true });
                      bump();
                    } else {
                      appendErr(data.error || "Saved URL import failed");
                    }
                  } catch (e) {
                    appendErr(e.message);
                  }
                }
              } catch (e) {
                appendErr(e.message);
                await flushCrops();
                try {
                  const data = await importSavedUrlJson([it.url], poolId, cap);
                  if (data.status === "saved_only" && !data.error) {
                    await addToCollected({ url: it.url, type: "image", addedAt: Date.now(), to_saved: true });
                    bump();
                  } else {
                    appendErr(data.error || "Saved URL import failed");
                  }
                } catch (e2) {
                  appendErr(e2.message);
                }
              }
            } else {
              await flushCrops();
              try {
                const data = await importSavedUrlJson([it.url], poolId, cap);
                if (data.status === "saved_only" && !data.error) {
                  await addToCollected({ url: it.url, type: "image", addedAt: Date.now(), to_saved: true });
                  bump();
                } else {
                  appendErr(data.error || "Saved URL import failed");
                }
              } catch (e) {
                appendErr(e.message);
              }
            }
          }
          await flushCrops();
        }
      }
    } else if (g.kind === "session") {
      if (!g.items.some((it) => isImageItem(it) && shouldApplyImagePipelineForUrl(it.url))) {
        const urls = g.items.map((it) => it.url);
        try {
          const data = await importViaExtensionBytesSavedBatch(urls, cap);
          if (data.ok && !data.error) {
            for (const it of g.items) {
              await addToCollected({ url: it.url, type: "image", addedAt: Date.now(), to_saved: true });
              bump();
            }
          } else {
            appendErr(data.error || "Session saved batch failed");
          }
        } catch (e) {
          appendErr(e.message);
        }
      } else {
        for (let i = 0; i < g.items.length; i += SAVED_ALBUM_CHUNK) {
          const chunk = g.items.slice(i, i + SAVED_ALBUM_CHUNK);
          const allImg = chunk.every(isImageItem);
          if (!allImg) {
            try {
              const data = await importViaExtensionBytesSavedBatch(chunk.map((x) => x.url), cap);
              if (data.ok && !data.error) {
                for (const it of chunk) {
                  await addToCollected({ url: it.url, type: "image", addedAt: Date.now(), to_saved: true });
                  bump();
                }
              } else {
                appendErr(data.error || "Session saved batch failed");
              }
            } catch (e) {
              appendErr(e.message);
            }
            continue;
          }
          try {
            const form = new FormData();
            for (const it of chunk) {
              const raw = await fetchUrlBytesToBlob(it.url, await tbccRefererPageForItem(it));
              if (!raw || !raw.size) throw new Error("fetch bytes");
              const cropped = await applyImagePipeline(raw, it.url);
              form.append("files", cropped, filenameForCropUrl(it.url));
            }
            appendCaptionToSavedForm(form, cap);
            const r = await fetch(API_BASE + "/import/saved-batch", { method: "POST", body: form });
            const data = await parseImportResponse(r);
            if (data.status === "saved_only" && !data.error) {
              for (const it of chunk) {
                await addToCollected({ url: it.url, type: "image", addedAt: Date.now(), to_saved: true });
                bump();
              }
            } else {
              appendErr(data.error || "Saved batch (session crop) failed");
            }
          } catch (e) {
            try {
              const data = await importViaExtensionBytesSavedBatch(chunk.map((x) => x.url), cap);
              if (data.ok && !data.error) {
                for (const it of chunk) {
                  await addToCollected({ url: it.url, type: "image", addedAt: Date.now(), to_saved: true });
                  bump();
                }
              } else {
                appendErr(data.error || "Session saved batch failed");
              }
            } catch (e2) {
              appendErr(e2.message || String(e));
            }
          }
        }
      }
    } else {
      const byTab = new Map();
      for (const it of g.items) {
        if (!it || !it.url) continue;
        const tid = it.tabId;
        if (tid == null) {
          appendErr("Unsupported item for Saved Messages (no tab)");
          continue;
        }
        if (!byTab.has(tid)) byTab.set(tid, []);
        byTab.get(tid).push(it);
      }
      for (const [tabId, tabItems] of byTab) {
        for (let i = 0; i < tabItems.length; i += SAVED_ALBUM_CHUNK) {
          const chunk = tabItems.slice(i, i + SAVED_ALBUM_CHUNK);
          const frameId =
            chunk[0] && chunk[0].tbccCaptureFrameId != null ? chunk[0].tbccCaptureFrameId : null;
          const urls = chunk.map((it) => it.url);
          try {
            const batch = await fetchAndUploadViaTab(Number(tabId), urls, poolId, true, frameId, cap);
            (batch.errors || []).forEach((e) => appendErr(e.error || String(e)));
            const units = tbccSavedUnitsFromBatch(batch);
            if (units > 0) {
              for (const it of chunk) {
                await addToCollected({ url: it.url, type: "image", addedAt: Date.now(), to_saved: true });
                bump();
              }
            } else if (!(batch.errors || []).length) {
              appendErr("Saved Messages batch returned no uploaded files");
            }
          } catch (e) {
            appendErr(e.message || String(e));
          }
        }
      }
    }
  }
  if (typeof TbccSendPromo !== "undefined" && TbccSendPromo.sendSavedTail) {
    await TbccSendPromo.sendSavedTail(poolId, appendCaptionToSavedForm, appendErr, bump);
  }
}

function tbccScriptTargetForTabFrame(tabId, frameId, urls) {
  const needsFrame =
    frameId != null &&
    frameId !== "" &&
    Number.isFinite(Number(frameId)) &&
    Number(frameId) !== 0;
  const hasBlob = (urls || []).some((u) => String(u).startsWith("blob:"));
  if (needsFrame) return { tabId, frameIds: [Number(frameId)] };
  if (hasBlob) return { tabId, allFrames: true };
  return { tabId };
}

function mergeFetchUploadResults(merged, batch) {
  if (!batch) return;
  if (batch.error) merged.errors.push({ error: batch.error, url: "(batch)" });
  merged.imported += batch.imported || 0;
  merged.skipped += batch.skipped || 0;
  if (typeof batch.saved === "number") merged.saved = (merged.saved || 0) + batch.saved;
  (batch.media_ids || []).forEach((id) => merged.media_ids.push(id));
  (batch.errors || []).forEach((e) => merged.errors.push(e));
}

async function fetchAndUploadViaTab(tabId, urls, poolId, savedOnly, frameId, savedCaptionOverride) {
  const merged = { imported: 0, skipped: 0, errors: [], media_ids: [] };
  const so = !!savedOnly;
  const urlList = urls || [];
  const savedCaption = so
    ? savedCaptionOverride != null && String(savedCaptionOverride).trim() !== ""
      ? String(savedCaptionOverride).trim()
      : getAlbumCaptionForSend()
    : "";
  const target = tbccScriptTargetForTabFrame(tabId, frameId, urlList);
  /** Saved Msgs: one injection with all URLs so capture.js can batch /import/saved-batch (albums). */
  if (so && urlList.length > 0) {
    await chrome.scripting.executeScript({ target, files: ["media-url-guards.js", "auto-tag-utils.js", "capture.js"] });
    const exec = chrome.scripting.executeScript({
      target,
      func: (allUrls, pid, savedOnlyFlag, src, captionStr) =>
        typeof window.__tbccFetchAndUpload === "function"
          ? window.__tbccFetchAndUpload(allUrls, pid, !!savedOnlyFlag, src, captionStr || "")
          : Promise.resolve({ error: "TBCC capture not ready", imported: 0, skipped: 0, errors: [], media_ids: [] }),
      args: [urlList, poolId, so, "extension:gallery:fallback", savedCaption],
    });
    const timeout = new Promise((_, rej) =>
      setTimeout(
        () => rej(new Error("In-tab fetch timed out — page may block scripts or CDN blocked fetch.")),
        IN_TAB_PER_URL_MS * Math.max(1, Math.ceil(urlList.length / 5))
      )
    );
    try {
      const results = await Promise.race([exec, timeout]);
      if (target.allFrames && Array.isArray(results) && results.length > 1) {
        let picked = null;
        let bestUnits = 0;
        for (const fr of results) {
          const batch = fr && fr.result;
          const units = tbccSavedUnitsFromBatch(batch);
          if (batch && !batch.error && units > bestUnits) {
            bestUnits = units;
            picked = batch;
          }
        }
        mergeFetchUploadResults(merged, picked || (results[0] && results[0].result) || {});
      } else {
        mergeFetchUploadResults(merged, (results && results[0] && results[0].result) || {});
      }
    } catch (e) {
      merged.errors.push({ error: e.message || String(e), url: "(batch)" });
    }
    return merged;
  }
  for (let u = 0; u < urlList.length; u++) {
    const oneUrl = urlList[u];
    const oneTarget = tbccScriptTargetForTabFrame(tabId, frameId, [oneUrl]);
    await chrome.scripting.executeScript({ target: oneTarget, files: ["media-url-guards.js", "auto-tag-utils.js", "capture.js"] });
    const exec = chrome.scripting.executeScript({
      target: oneTarget,
      func: (singleUrl, pid, savedOnlyFlag, src, captionStr) =>
        typeof window.__tbccFetchAndUpload === "function"
          ? window.__tbccFetchAndUpload([singleUrl], pid, !!savedOnlyFlag, src, captionStr || "")
          : Promise.resolve({ error: "TBCC capture not ready", imported: 0, skipped: 0, errors: [], media_ids: [] }),
      args: [oneUrl, poolId, so, "extension:gallery:fallback", savedCaption],
    });
    const timeout = new Promise((_, rej) =>
      setTimeout(
        () => rej(new Error("In-tab fetch timed out — page may block scripts or CDN blocked fetch.")),
        IN_TAB_PER_URL_MS
      )
    );
    try {
      const results = await Promise.race([exec, timeout]);
      let batch = (results && results[0] && results[0].result) || {};
      if (oneTarget.allFrames && Array.isArray(results)) {
        let bestUnits = 0;
        for (const fr of results) {
          const b = fr && fr.result;
          const units = tbccSavedUnitsFromBatch(b);
          if (b && !b.error && units > bestUnits) {
            bestUnits = units;
            batch = b;
          }
        }
      }
      if (batch.error) merged.errors.push({ error: batch.error, url: String(oneUrl).slice(0, 80) });
      merged.imported += batch.imported || 0;
      merged.skipped += batch.skipped || 0;
      (batch.media_ids || []).forEach((id) => merged.media_ids.push(id));
      (batch.errors || []).forEach((e) => merged.errors.push(e));
    } catch (e) {
      merged.errors.push({ error: e.message || String(e), url: String(oneUrl).slice(0, 80) });
    }
  }
  return merged;
}

async function fetchAndUploadViaTabForItem(tabId, it, poolId, savedOnly) {
  const frameId = it && it.tbccCaptureFrameId != null ? it.tbccCaptureFrameId : null;
  return fetchAndUploadViaTab(tabId, [it.url], poolId, savedOnly, frameId);
}

function trackImportedMediaRecord(target, mediaId, item, tabIdHint, urlHint) {
  const id = parseInt(mediaId, 10);
  if (!Number.isFinite(id)) return;
  target.push({
    mediaId: id,
    tabId: Number.isFinite(Number((item && item.tabId) || tabIdHint)) ? Number((item && item.tabId) || tabIdHint) : null,
    item: item
      ? item
      : {
          url: urlHint || "",
          pageUrl: "",
          pageHost: "",
        },
  });
}

async function runSendBatch(savedOnly) {
  const list = getFilteredList();
  const rawSelected = list.filter((i) => selectedUrls.has(i.url));
  const selected = savedOnly ? prepareSelectedForSavedSend(rawSelected) : rawSelected;
  if (selected.length === 0) return;
  const jobLabel = savedOnly ? "Saved Messages send" : "TBCC import/send";
  const jobId = await beginGalleryJob("send-batch", jobLabel);
  try {
  const { tbccLiteMode } = await chrome.storage.local.get("tbccLiteMode");
  if (tbccLiteMode && selected.length > TBCC_LITE_BATCH_CAP) {
    alert(
      `TBCC Lite: select at most ${TBCC_LITE_BATCH_CAP} items per batch. Turn off Lite mode in the extension popup (toolbar).`
    );
    return;
  }
  const poolId = await getPoolId();
  const importedMediaIds = [];
  const importedMediaRecords = [];
  let telegramPostAttempted = false;
  let telegramPostHadError = false;
  if (btnSend) btnSend.disabled = true;
  progressEl.classList.add("visible");
  if (progressTitle)
    progressTitle.textContent = savedOnly ? "Sending to Saved Messages…" : "Sending to TBCC…";
  progressFill.style.width = "0%";
  progressStatus.textContent = "0 / " + selected.length;
  progressError.textContent = "";

  let done = 0;
  const total = selected.length;
  if (importQueueEl) {
    importQueueEl.innerHTML = "";
    importQueueEl.classList.add("visible");
    const head = document.createElement("div");
    head.className = "row";
    head.textContent = (savedOnly ? "Saved Messages — " : "TBCC pool — ") + total + " item(s)";
    importQueueEl.appendChild(head);
  }
  const bump = () => {
    done++;
    progressFill.style.width = Math.round((100 * done) / total) + "%";
    progressStatus.textContent = done + " / " + total;
  };
  const appendErr = (msg) => {
    if (msg) progressError.textContent = (progressError.textContent ? progressError.textContent + "; " : "") + msg;
    if (importQueueEl && msg) {
      importQueueEl.classList.add("visible");
      const row = document.createElement("div");
      row.className = "row";
      row.style.color = "#f38ba8";
      row.textContent = msg.length > 160 ? msg.slice(0, 160) + "…" : msg;
      importQueueEl.appendChild(row);
    }
  };
  if (savedOnly && rawSelected.length > selected.length) {
    appendErr(
      `${rawSelected.length - selected.length} tile(s) skipped (embed link or duplicate slot — refresh gallery and resend)`
    );
  }

  if (savedOnly) {
    if (progressTitle) progressTitle.textContent = "Preparing caption…";
    const savedCaption = await ensureSavedMessagesCaption(selected);
    if (progressTitle) progressTitle.textContent = "Sending to Saved Messages…";
    if (!savedCaption.trim()) {
      showToast(
        "No caption or tags to attach — open Send settings, add message text or tags, or use Auto cap.",
        "info"
      );
    }
    await runSendSavedBatchAlbums(selected, poolId, bump, appendErr, savedCaption);
    progressStatus.textContent = "Done: " + done + " / " + total;
    if (progressTitle)
      progressTitle.textContent =
        progressError && progressError.textContent && progressError.textContent.trim()
          ? "Finished with errors"
          : "Done";
    if (btnSend) btnSend.disabled = false;
    updateCountAndSend();
    const hadErrSaved = progressError && progressError.textContent && progressError.textContent.trim();
    if (!hadErrSaved) persistCaptionClear();
    clearGallerySendTags();
    if (hadErrSaved) {
      notifyCompletion(
        "Saved Messages finished with errors (" + done + " / " + total + ").",
        "error",
        "notifyOnSendSavedComplete",
        "TBCC Saved Messages",
        { type: "telegram_saved" }
      );
    } else {
      notifyCompletion(
        "Completed " + done + " / " + total + " (Saved Messages).",
        "success",
        "notifyOnSendSavedComplete",
        "TBCC Saved Messages",
        { type: "telegram_saved" }
      );
    }
    return;
  }

  const withFile = selected.filter((i) => i.file);
  const fromPage = selected.filter((i) => !i.file && i.tabId);

  for (const it of withFile) {
    let uploadBlob = it.file;
    let uploadName = it.name || "media";
    if (shouldApplyImagePipelineForUrl(it.url) && isImageItem(it)) {
      try {
        const raw = new Blob([await it.file.arrayBuffer()], { type: it.file.type || "application/octet-stream" });
        const cropped = await applyImagePipeline(raw, it.url);
        uploadBlob = cropped;
        uploadName = /\.(jpe?g)$/i.test(uploadName) ? uploadName : (uploadName.replace(/\.[^.]+$/, "") || "media") + ".jpg";
      } catch (_) {}
    }
    const form = new FormData();
    form.append("file", uploadBlob, uploadName);
    form.append("pool_id", String(poolId));
    form.append("saved_only", savedOnly ? "true" : "false");
    form.append("source", savedOnly ? "extension:upload-saved" : "extension:upload");
    try {
      const r = await fetch(API_BASE + "/import/bytes", { method: "POST", body: form });
      const text = await r.text();
      let data = {};
      try {
        data = text ? JSON.parse(text) : {};
      } catch (_) {}
      if (savedOnly && data.status === "saved_only" && !data.error) {
        await addToCollected({ url: it.url, type: it.type || "image", addedAt: Date.now(), to_saved: true });
      } else if (!savedOnly && data.status === "imported" && data.media_id) {
        importedMediaIds.push(data.media_id);
        trackImportedMediaRecord(importedMediaRecords, data.media_id, it, it.tabId, it.url);
        await addToCollected({ url: it.url, type: it.type || "image", addedAt: Date.now(), media_id: data.media_id });
      } else if (data.error) appendErr(data.error);
    } catch (e) {
      appendErr(e.message);
    }
    bump();
  }

  const httpPage = fromPage.filter((i) => i.url && /^https?:\/\//i.test(i.url));
  const needBytesByTab = {};
  for (const it of httpPage) {
    if (shouldApplyImagePipelineForUrl(it.url) && isImageItem(it)) {
      try {
        const raw = await fetchUrlBytesToBlob(it.url, await tbccRefererPageForItem(it));
        if (raw && raw.size > 0) {
          const cropped = await applyImagePipeline(raw, it.url);
          const data = await postImportBytes(
            cropped,
            filenameForCropUrl(it.url),
            poolId,
            savedOnly,
            "extension:gallery-crop",
            null,
            jobId
          );
          if (importResponseOk(data)) {
            if (savedOnly && data.status === "saved_only")
              await addToCollected({ url: it.url, type: "image", addedAt: Date.now(), to_saved: true });
            else if (!savedOnly && data.media_id) {
              importedMediaIds.push(data.media_id);
              trackImportedMediaRecord(importedMediaRecords, data.media_id, it, it.tabId, it.url);
              await addToCollected({ url: it.url, type: "image", addedAt: Date.now(), media_id: data.media_id });
            }
            bump();
            continue;
          }
          if (data.error) appendErr(String(data.error).length > 220 ? String(data.error).slice(0, 220) + "…" : data.error);
        }
      } catch (e) {
        appendErr((e.message || String(e)).slice(0, 200));
      }
    }
    if (hostNeedsSessionFetch(it.url)) {
      try {
        const data = await importUrlViaExtensionSession(
          it.url,
          poolId,
          savedOnly,
          await tbccRefererPageForItem(it)
        );
        const ok =
          (data.status === "imported" || data.status === "skipped" || data.status === "saved_only") && !data.error;
        if (ok) {
          if (savedOnly && data.status === "saved_only")
            await addToCollected({ url: it.url, type: "image", addedAt: Date.now(), to_saved: true });
          else if (!savedOnly && data.media_id)
            await addToCollected({ url: it.url, type: "image", addedAt: Date.now(), media_id: data.media_id });
          if (!savedOnly && data.media_id) {
            importedMediaIds.push(data.media_id);
            trackImportedMediaRecord(importedMediaRecords, data.media_id, it, it.tabId, it.url);
          }
          bump();
          continue;
        }
        if (data.error) appendErr(String(data.error).length > 220 ? String(data.error).slice(0, 220) + "…" : data.error);
      } catch (e) {
        appendErr((e.message || String(e)).slice(0, 200));
      }
      needBytesByTab[it.tabId] = needBytesByTab[it.tabId] || [];
      needBytesByTab[it.tabId].push(it);
      continue;
    }
    let data = await importOneUrl(it.url, poolId, savedOnly);
    let ok =
      (data.status === "imported" || data.status === "skipped" || data.status === "saved_only") && !data.error;
    if (!ok && data.error && shouldRetryImportViaSession(it.url, data.error)) {
      try {
        data = await importUrlViaExtensionSession(it.url, poolId, savedOnly, await tbccRefererPageForItem(it));
        ok =
          (data.status === "imported" || data.status === "skipped" || data.status === "saved_only") && !data.error;
      } catch (_) {}
    }
    if (ok) {
      if (savedOnly && data.status === "saved_only")
        await addToCollected({ url: it.url, type: "image", addedAt: Date.now(), to_saved: true });
      else if (!savedOnly && data.media_id) {
        importedMediaIds.push(data.media_id);
        trackImportedMediaRecord(importedMediaRecords, data.media_id, it, it.tabId, it.url);
        await addToCollected({ url: it.url, type: "image", addedAt: Date.now(), media_id: data.media_id });
      }
      bump();
    } else {
      const shortErr = data.error
        ? String(data.error).length > 220
          ? String(data.error).slice(0, 220) + "…"
          : data.error
        : "URL import failed — in-tab fetch";
      appendErr(shortErr);
      needBytesByTab[it.tabId] = needBytesByTab[it.tabId] || [];
      needBytesByTab[it.tabId].push(it);
    }
  }
  fromPage.forEach((it) => {
    if (it.url && !/^https?:\/\//i.test(it.url) && it.tabId) {
      needBytesByTab[it.tabId] = needBytesByTab[it.tabId] || [];
      needBytesByTab[it.tabId].push(it);
    }
  });

  const urlToItem = new Map(selected.map((i) => [i.url, i]));
  for (const tabIdStr of Object.keys(needBytesByTab)) {
    const tabId = parseInt(tabIdStr, 10);
    const pendingItems = needBytesByTab[tabIdStr].slice();
    if (!pendingItems.length) continue;
    const byFrame = new Map();
    for (const raw of pendingItems) {
      const it = raw && raw.url ? raw : urlToItem.get(raw) || { url: raw, tabId };
      const url = it.url || "";
      if (!url) continue;
      const fid = it.tbccCaptureFrameId != null && Number.isFinite(Number(it.tbccCaptureFrameId)) ? Number(it.tbccCaptureFrameId) : 0;
      if (!byFrame.has(fid)) byFrame.set(fid, []);
      byFrame.get(fid).push(it);
    }
    for (const [frameId, frameItems] of byFrame) {
    const forTab = [];
    for (const it of frameItems) {
      const url = it.url || "";
      if (shouldApplyImagePipelineForUrl(url) && it && isImageItem(it)) {
        try {
          const raw = await fetchUrlBytesToBlob(url, await tbccRefererPageForItem(it || { tabId, url }));
          if (raw && raw.size > 0) {
            const cropped = await applyImagePipeline(raw, url);
            const data = await postImportBytes(
              cropped,
              filenameForCropUrl(url),
              poolId,
              savedOnly,
              "extension:gallery-crop-fallback",
              null,
              jobId
            );
            if (importResponseOk(data)) {
              if (savedOnly && data.status === "saved_only")
                await addToCollected({ url, type: "image", addedAt: Date.now(), to_saved: true });
              else if (!savedOnly && data.media_id) {
                importedMediaIds.push(data.media_id);
                trackImportedMediaRecord(importedMediaRecords, data.media_id, it, tabId, url);
                await addToCollected({ url, type: "image", addedAt: Date.now(), media_id: data.media_id });
              }
              bump();
              continue;
            }
            if (data.error)
              appendErr(String(data.error).length > 180 ? String(data.error).slice(0, 180) + "…" : data.error);
          }
        } catch (e) {
          appendErr((e.message || String(e)).slice(0, 160));
        }
      }
      if (!hostNeedsSessionFetch(url)) {
        try {
          const data = await importUrlViaExtensionSession(
            url,
            poolId,
            savedOnly,
            await tbccRefererPageForItem(it || { tabId, url })
          );
          const ok =
            (data.status === "imported" || data.status === "skipped" || data.status === "saved_only") &&
            !data.error;
          if (ok) {
            if (savedOnly && data.status === "saved_only")
              await addToCollected({ url, type: "image", addedAt: Date.now(), to_saved: true });
            else if (!savedOnly && data.media_id) {
              importedMediaIds.push(data.media_id);
              trackImportedMediaRecord(importedMediaRecords, data.media_id, it, tabId, url);
              await addToCollected({ url, type: "image", addedAt: Date.now(), media_id: data.media_id });
            }
            bump();
            continue;
          }
          if (data.error)
            appendErr(String(data.error).length > 180 ? String(data.error).slice(0, 180) + "…" : data.error);
        } catch (e) {
          appendErr((e.message || String(e)).slice(0, 160));
        }
      }
      forTab.push(url);
    }
    if (!forTab.length) continue;
    try {
      const batch = await fetchAndUploadViaTab(
        tabId,
        forTab,
        poolId,
        savedOnly,
        frameId === 0 ? null : frameId
      );
      if (batch.error) appendErr(batch.error);
      if (!savedOnly)
        (batch.media_ids || []).forEach((id, idx) => {
          importedMediaIds.push(id);
          const url = forTab[idx] || forTab[0] || "";
          const itRow = urlToItem.get(url) || frameItems[idx] || null;
          trackImportedMediaRecord(importedMediaRecords, id, itRow, tabId, url);
        });
      (batch.errors || []).forEach((e) => appendErr(e.error || String(e)));
      if (savedOnly) {
        forTab.forEach((url) => addToCollected({ url, type: "image", addedAt: Date.now(), to_saved: true }));
      } else {
        forTab.forEach((url) => addToCollected({ url, type: "image", addedAt: Date.now() }));
      }
    } catch (e) {
      appendErr(e.message || String(e));
    }
    for (let i = 0; i < forTab.length; i++) bump();
    }
  }

  if (!savedOnly && importedMediaIds.length) {
    const useAutoTag = !!(autoTagOnExport && autoTagOnExport.checked);
    const hasManualTags = gallerySendTags.length > 0;
    if (progressTitle) progressTitle.textContent = useAutoTag ? "Auto-tagging…" : "Applying tags…";
    try {
      if (!tagCatalog.length) {
        try {
          await loadTagCatalog();
        } catch (_) {}
      }
      if (useAutoTag) {
        await applyAutoTaggingForImportedMedia(importedMediaRecords);
        syncEnrichImportedMedia(importedMediaIds).catch((e) => {
          appendErr("API enrich (background): " + (e.message || String(e)));
        });
      } else if (hasManualTags) await applySendTagsToImportedMedia(importedMediaIds);
    } catch (e) {
      appendErr("Tags: " + (e.message || String(e)));
    }
  } else if (!savedOnly && !importedMediaIds.length && gallerySendTags.length) {
    appendErr("No library rows imported — tags were not applied (check errors above).");
  }

  if (!savedOnly && forumPostEnabled && forumPostEnabled.checked && forumChannelSelect) {
    const fc = parseInt(forumChannelSelect.value, 10);
    const uniqueIds = [...new Set(importedMediaIds)];
    if (typeof TbccSendPromo !== "undefined" && TbccSendPromo.importMediaId) {
      const promoMediaId = await TbccSendPromo.importMediaId(poolId);
      if (promoMediaId) uniqueIds.push(promoMediaId);
    }
    const mode = (postDestMode && postDestMode.value) || "channel";
    if (fc && uniqueIds.length) {
      telegramPostAttempted = true;
      let threadId = null;
      if (mode === "forum") {
        const ft = forumTopicSelect && forumTopicSelect.value ? parseInt(forumTopicSelect.value, 10) : 0;
        if (!ft) {
          appendErr("Select a group topic, or set destination to Channel or group.");
          telegramPostHadError = true;
        } else {
          threadId = ft;
        }
      }
      if (!(mode === "forum" && !threadId)) {
        if (progressTitle) {
          progressTitle.textContent =
            mode === "forum" ? "Posting to group topic…" : "Posting to Telegram channel…";
        }
        try {
          const payload = {
            channel_id: fc,
            media_ids: uniqueIds,
            caption: getAlbumCaptionForSend(),
            mark_posted: true,
            message_thread_id: mode === "forum" && threadId ? threadId : null,
            send_silent: !!(sendSilent && sendSilent.checked),
          };
          const r = await fetch(API_BASE + "/forum/post-album", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          });
          const text = await r.text();
          let j = {};
          try {
            j = text ? JSON.parse(text) : {};
          } catch (_) {}
          if (j.error) appendErr(String(j.error));
          if (j.error) telegramPostHadError = true;
          else if (j.errors && j.errors.length) {
            appendErr(j.errors.join("; "));
            telegramPostHadError = true;
          } else if (j.ok === false && j.sent_chunks === 0) {
            appendErr("Telegram post returned no chunks sent");
            telegramPostHadError = true;
          }
        } catch (e) {
          appendErr(e.message || String(e));
          telegramPostHadError = true;
        }
      }
    }
  }

  progressStatus.textContent = "Done: " + done + " / " + total;
  if (progressTitle)
    progressTitle.textContent = progressError && progressError.textContent && progressError.textContent.trim()
      ? "Finished with errors"
      : "Done";
  if (btnSend) btnSend.disabled = false;
  updateCountAndSend();
  const hadErr = progressError && progressError.textContent && progressError.textContent.trim();
  if (!hadErr) persistCaptionClear();
  clearGallerySendTags();
  if (hadErr) {
    notifyCompletion(
      "TBCC send finished with errors (" + done + " / " + total + ").",
      "error",
      "notifyOnSendTbccComplete",
      "TBCC send status"
    );
  } else {
    notifyCompletion(
      "Completed " + done + " / " + total + " item(s).",
      "success",
      "notifyOnSendTbccComplete",
      "TBCC import complete",
      { type: "url", url: "http://localhost:5173/" }
    );
  }
  if (telegramPostAttempted && !telegramPostHadError) {
    const mode = (postDestMode && postDestMode.value) || "channel";
    const ch = forumChannelSelect && forumChannelSelect.selectedOptions && forumChannelSelect.selectedOptions[0];
    const channelName = ch ? (ch.textContent || "").trim() : "selected destination";
    const label = mode === "forum" ? "forum topic" : "channel/group";
    const chId = ch && ch.value ? parseInt(ch.value, 10) : NaN;
    const chRow = Number.isFinite(chId) ? (tbccChannelsCacheLast || []).find((c) => parseInt(c.id, 10) === chId) : null;
    const channelUrl = chRow ? captionLinkForChannelRow(chRow) : "";
    notifyCompletion(
      "Telegram post sent to " + label + ": " + channelName,
      "success",
      "notifyOnSendChannelComplete",
      "TBCC Telegram post",
      channelUrl ? { type: "url", url: channelUrl } : null
    );
  }
  } finally {
    endGalleryJob(jobId);
  }
}

/**
 * Destination Saved → Telegram Saved Messages (albums ≤10) with caption + #hashtags from Send settings.
 * Library → TBCC pool (+ tags on media rows); Topic/Channel → pool then Telegram post.
 */
function sendToTBCC() {
  const destSaved = postDestMode && postDestMode.value === "saved";
  if (destSaved) {
    if (forumPostEnabled && !forumPostEnabled.checked) {
      forumPostEnabled.checked = true;
      void chrome.storage.local.set({ tbccForumPostEnabled: true });
      updateTelegramPostControls();
      updateImportSheetLayout();
      syncDestMacroButtons();
    }
    return runSendBatch(true);
  }
  return runSendBatch(false);
}

btnSend && btnSend.addEventListener("click", sendToTBCC);

async function addToCollected(item) {
  const key = STORAGE_COLLECTED;
  const raw = await new Promise((r) => chrome.storage.local.get(key, (o) => r(o[key])));
  const arr = Array.isArray(raw) ? raw : [];
  arr.push(item);
  await tbccStorageLocalSet({ [key]: arr.slice(-120) });
}

btnOpenCaptureSettings &&
  btnOpenCaptureSettings.addEventListener("click", () => {
    if (typeof window.tbccSetPanelView === "function") window.tbccSetPanelView("options");
  });
btnGalleryHelp &&
  btnGalleryHelp.addEventListener("click", () => {
    window.alert(
      "TBCC Gallery shortcuts:\n\nR — Refresh (pools/channels/embeds + rescan when “Full refresh” is on in ⚙ Options)\nO — Preview first selected\nCtrl+S — Send\nEsc — Close preview / quick menu\n\nCapture scope: Current tab, Group (Chrome tab group only), or All tabs in this window.\n\nLightbox: mouse wheel or trackpad (vertical or horizontal) steps between items; arrow keys also work.\n\n⎘ in the top bar opens the gallery in a separate window (useful while closing the side panel).\n\nRight-click in the gallery (below the top nav) for a quick menu: refresh, on-page boxes, select, download, filter, and more.\n\nDouble-click a tile for full-size preview.\n\nImport settings (Dest): content pool, tags, optional Telegram. URL inbox queues links for server-side import.\n\nCapture settings (format, auto-scan, …) are under ⚙ Options."
    );
  });
btnFilterToggle &&
  btnFilterToggle.addEventListener("click", () => {
    setFilterOverlayOpen(!filterOverlay || !filterOverlay.classList.contains("visible"));
  });
btnFilterReset &&
  btnFilterReset.addEventListener("click", (e) => {
    e.stopPropagation();
    resetFilterFields();
  });
btnFilterDone &&
  btnFilterDone.addEventListener("click", () => {
    setFilterOverlayOpen(false);
    saveGalleryUiState();
    renderGrid();
  });
filterOverlay &&
  filterOverlay.addEventListener("click", (e) => {
    if (e.target === filterOverlay) {
      setFilterOverlayOpen(false);
      saveGalleryUiState();
    }
  });
btnTelegramSheetOpen &&
  btnTelegramSheetOpen.addEventListener("click", () => {
    setTelegramSheetOpen(true);
  });
btnTelegramSheetDone &&
  btnTelegramSheetDone.addEventListener("click", () => {
    setTelegramSheetOpen(false);
  });
telegramSheetBackdrop &&
  telegramSheetBackdrop.addEventListener("click", () => {
    if (alwaysIncludePopover && !alwaysIncludePopover.hidden) {
      alwaysIncludePopover.hidden = true;
      if (btnAlwaysIncludeToggle) btnAlwaysIncludeToggle.setAttribute("aria-expanded", "false");
    }
    setTelegramSheetOpen(false);
  });
btnSavedUrlInboxOpen &&
  btnSavedUrlInboxOpen.addEventListener("click", () => openSavedUrlInboxSheet(true));
const btnSavedUrlInboxOpenToolbar = document.getElementById("btnSavedUrlInboxOpenToolbar");
btnSavedUrlInboxOpenToolbar &&
  btnSavedUrlInboxOpenToolbar.addEventListener("click", () => openSavedUrlInboxSheet(true));
btnSavedUrlInboxDone &&
  btnSavedUrlInboxDone.addEventListener("click", () => openSavedUrlInboxSheet(false));
savedUrlInboxBackdrop &&
  savedUrlInboxBackdrop.addEventListener("click", () => openSavedUrlInboxSheet(false));
savedUrlInboxDefaultDest &&
  savedUrlInboxDefaultDest.addEventListener("change", () => {
    syncInboxDefaultDestUi();
    chrome.storage.local.set({
      [STORAGE_INBOX_DEFAULT_DEST]: savedUrlInboxDefaultDest.value === "loot_modifier" ? "loot_modifier" : "pool",
    });
  });
btnSavedUrlInboxAdd &&
  btnSavedUrlInboxAdd.addEventListener("click", async () => {
    const url = savedUrlInboxManualUrl && savedUrlInboxManualUrl.value.trim();
    if (!url) return showToast("Enter a URL.", "info");
    const defDest =
      savedUrlInboxDefaultDest && savedUrlInboxDefaultDest.value === "loot_modifier"
        ? "loot_modifier"
        : "pool";
    const defPool =
      savedUrlInboxDefaultPool && savedUrlInboxDefaultPool.value
        ? parseInt(savedUrlInboxDefaultPool.value, 10)
        : null;
    const r = await TbccSavedUrlInbox.appendUrl(url, {
      destType: defDest,
      poolId: defDest === "pool" && Number.isFinite(defPool) && defPool > 0 ? defPool : null,
    });
    if (r.error) return showToast(r.error, "error");
    if (savedUrlInboxManualUrl) savedUrlInboxManualUrl.value = "";
    await renderSavedUrlInboxList();
    showToast(r.duplicate ? "Already in inbox." : "Added to inbox.", r.duplicate ? "info" : "success");
  });
savedUrlInboxDefaultPool &&
  savedUrlInboxDefaultPool.addEventListener("change", () => {
    const v = savedUrlInboxDefaultPool.value;
    if (v) chrome.storage.local.set({ tbccPoolId: parseInt(v, 10) });
    if (poolSelect) poolSelect.value = v;
    syncPoolSelectTooltip();
  });
btnSavedUrlInboxImportSel &&
  btnSavedUrlInboxImportSel.addEventListener("click", async () => {
    const picked = await getCheckedInboxRows();
    const active = picked.filter((r) => r.status !== "importing");
    if (!active.length) {
      return showToast(
        picked.length ? "Selected URLs are already importing in the background." : "Check one or more URLs.",
        "info"
      );
    }
    btnSavedUrlInboxImportSel.disabled = true;
    try {
      await importSavedUrlInboxRows(active);
    } finally {
      btnSavedUrlInboxImportSel.disabled = false;
    }
  });
btnSavedUrlInboxRemoveSel &&
  btnSavedUrlInboxRemoveSel.addEventListener("click", async () => {
    const picked = await getCheckedInboxRows();
    if (!picked.length) return showToast("Check URLs to remove.", "info");
    const drop = new Set(picked.map((r) => TbccSavedUrlInbox.rowKey(r)));
    const rows = (await TbccSavedUrlInbox.getRows()).filter((r) => !drop.has(TbccSavedUrlInbox.rowKey(r)));
    await TbccSavedUrlInbox.setRows(rows);
    await renderSavedUrlInboxList();
  });
btnSavedUrlInboxClearImported &&
  btnSavedUrlInboxClearImported.addEventListener("click", async () => {
    const rows = (await TbccSavedUrlInbox.getRows()).filter((r) => r.status !== "imported");
    await TbccSavedUrlInbox.setRows(rows);
    await renderSavedUrlInboxList();
  });
const btnSavedUrlInboxSelectAll = document.getElementById("btnSavedUrlInboxSelectAll");
const btnSavedUrlInboxDeselectAll = document.getElementById("btnSavedUrlInboxDeselectAll");
const btnSavedUrlInboxExport = document.getElementById("btnSavedUrlInboxExport");
const btnSavedUrlInboxImport = document.getElementById("btnSavedUrlInboxImport");
const btnSavedUrlInboxMaster = document.getElementById("btnSavedUrlInboxMaster");
const savedUrlInboxImportFile = document.getElementById("savedUrlInboxImportFile");
btnSavedUrlInboxSelectAll &&
  btnSavedUrlInboxSelectAll.addEventListener("click", () => setInboxChecksAll(true));
btnSavedUrlInboxDeselectAll &&
  btnSavedUrlInboxDeselectAll.addEventListener("click", () => setInboxChecksAll(false));
btnSavedUrlInboxExport &&
  btnSavedUrlInboxExport.addEventListener("click", () => void exportInboxRows("json"));
btnSavedUrlInboxImport &&
  btnSavedUrlInboxImport.addEventListener("click", () => {
    if (savedUrlInboxImportFile) savedUrlInboxImportFile.click();
  });
savedUrlInboxImportFile &&
  savedUrlInboxImportFile.addEventListener("change", async () => {
    const file = savedUrlInboxImportFile.files && savedUrlInboxImportFile.files[0];
    savedUrlInboxImportFile.value = "";
    if (!file) return;
    try {
      await importTextIntoInbox(await file.text());
    } catch (e) {
      setSavedUrlInboxStatus(String(e.message || e));
    }
  });
const btnSavedUrlInboxCopyAll = document.getElementById("btnSavedUrlInboxCopyAll");
btnSavedUrlInboxCopyAll &&
  btnSavedUrlInboxCopyAll.addEventListener("click", () => void copyAllInboxUrls());
btnSavedUrlInboxMaster &&
  btnSavedUrlInboxMaster.addEventListener("click", () => openMasterArchiveSheet(true));
const btnMasterArchiveDone = document.getElementById("btnMasterArchiveDone");
masterArchiveBackdrop &&
  masterArchiveBackdrop.addEventListener("click", () => openMasterArchiveSheet(false));
btnMasterArchiveDone &&
  btnMasterArchiveDone.addEventListener("click", () => openMasterArchiveSheet(false));
masterArchiveFilter &&
  masterArchiveFilter.addEventListener("input", () => {
    if (masterArchiveUi) masterArchiveUi.resetPage();
    void renderMasterArchiveList();
  });
masterArchiveKind &&
  masterArchiveKind.addEventListener("change", () => {
    if (masterArchiveUi) masterArchiveUi.resetPage();
    void renderMasterArchiveList();
  });
const btnMasterSelectAll = document.getElementById("btnMasterSelectAll");
const btnMasterDeselectAll = document.getElementById("btnMasterDeselectAll");
const btnMasterCopyUrls = document.getElementById("btnMasterCopyUrls");
btnMasterSelectAll &&
  btnMasterSelectAll.addEventListener("click", () => masterArchiveUi && masterArchiveUi.selectAllOnPage());
btnMasterDeselectAll &&
  btnMasterDeselectAll.addEventListener("click", () => masterArchiveUi && masterArchiveUi.deselectAllOnPage());
btnMasterCopyUrls &&
  btnMasterCopyUrls.addEventListener("click", async () => {
    if (!masterArchiveUi) return;
    const r = await masterArchiveUi.copyCheckedUrlsOnPage();
    if (r.ok) {
      setMasterArchiveStatus(`Copied ${r.count} URL(s) from this page.`);
      const clip = globalThis.TbccClipboard;
      if (clip && clip.showCopied) clip.showCopied();
    } else {
      setMasterArchiveStatus(r.error || "Copy failed.");
    }
  });
const btnMasterExportJson = document.getElementById("btnMasterExportJson");
const btnMasterExportCsv = document.getElementById("btnMasterExportCsv");
const btnMasterExportTxt = document.getElementById("btnMasterExportTxt");
const btnMasterImport = document.getElementById("btnMasterImport");
const btnMasterAddToInbox = document.getElementById("btnMasterAddToInbox");
const btnMasterClear = document.getElementById("btnMasterClear");
const masterArchiveImportFile = document.getElementById("masterArchiveImportFile");
btnMasterExportJson &&
  btnMasterExportJson.addEventListener("click", async () => {
    const entries = await getMasterArchiveFilteredEntries();
    TbccMasterArchive.downloadText(
      `tbcc-master-${new Date().toISOString().slice(0, 10)}.json`,
      TbccMasterArchive.exportJson(entries),
      "application/json"
    );
    setMasterArchiveStatus(`Exported ${entries.length} entr${entries.length === 1 ? "y" : "ies"} (JSON).`);
  });
btnMasterExportCsv &&
  btnMasterExportCsv.addEventListener("click", async () => {
    const entries = await getMasterArchiveFilteredEntries();
    TbccMasterArchive.downloadText(
      `tbcc-master-${new Date().toISOString().slice(0, 10)}.csv`,
      TbccMasterArchive.exportCsv(entries),
      "text/csv"
    );
    setMasterArchiveStatus(`Exported ${entries.length} entr${entries.length === 1 ? "y" : "ies"} (CSV).`);
  });
btnMasterExportTxt &&
  btnMasterExportTxt.addEventListener("click", async () => {
    const entries = await getMasterArchiveFilteredEntries();
    TbccMasterArchive.downloadText(
      `tbcc-master-${new Date().toISOString().slice(0, 10)}.txt`,
      TbccMasterArchive.exportText(entries),
      "text/plain"
    );
    setMasterArchiveStatus(`Exported ${entries.length} entr${entries.length === 1 ? "y" : "ies"} (text).`);
  });
btnMasterImport &&
  btnMasterImport.addEventListener("click", () => {
    if (masterArchiveImportFile) masterArchiveImportFile.click();
  });
masterArchiveImportFile &&
  masterArchiveImportFile.addEventListener("change", async () => {
    const file = masterArchiveImportFile.files && masterArchiveImportFile.files[0];
    masterArchiveImportFile.value = "";
    if (!file) return;
    const parsed = TbccMasterArchive.parseImportText(await file.text());
    const r = await TbccMasterArchive.importEntries(parsed, true);
    setMasterArchiveStatus(r.ok ? `Imported ${r.added} new entr${r.added === 1 ? "y" : "ies"}.` : r.error || "Import failed.");
    await renderMasterArchiveList();
  });
btnMasterAddToInbox &&
  btnMasterAddToInbox.addEventListener("click", async () => {
    if (!masterArchiveUi) return;
    const keys = masterArchiveUi.getSelectedKeys();
    if (!keys.size) {
      setMasterArchiveStatus("Check URL rows on this page.");
      return;
    }
    const filtered = await getMasterArchiveFilteredEntries();
    let added = 0;
    for (const e of filtered) {
      if (e.kind !== "url" || !keys.has(TbccMasterArchive.entryKey(e))) continue;
      const r = await TbccSavedUrlInbox.appendUrl(e.value, { ref: "master_archive" });
      if (r.ok && !r.duplicate) added++;
    }
    setMasterArchiveStatus(`Added ${added} URL(s) to inbox.`);
    if (added) await renderSavedUrlInboxList();
  });
const btnMasterSyncServer = document.getElementById("btnMasterSyncServer");
const masterArchivePaste = document.getElementById("masterArchivePaste");
const btnMasterPasteImport = document.getElementById("btnMasterPasteImport");
btnMasterSyncServer &&
  btnMasterSyncServer.addEventListener("click", () => void pullMasterArchiveFromServer());
btnMasterPasteImport &&
  btnMasterPasteImport.addEventListener("click", async () => {
    const text = masterArchivePaste && masterArchivePaste.value.trim();
    if (!text) return setMasterArchiveStatus("Paste URLs first.");
    const parsed = TbccMasterArchive.parseImportText(text, "url");
    const r = await TbccMasterArchive.importEntries(parsed, true);
    if (masterArchivePaste) masterArchivePaste.value = "";
    setMasterArchiveStatus(
      r.ok ? `Added ${r.added} entr${r.added === 1 ? "y" : "ies"} to local + server.` : r.error || "Import failed."
    );
    await renderMasterArchiveList();
  });
btnMasterClear &&
  btnMasterClear.addEventListener("click", async () => {
    if (
      !confirm(
        "Clear LOCAL master archive only? Server dashboard archive is unchanged. Export first if unsure."
      )
    )
      return;
    await TbccMasterArchive.clearArchive();
    await renderMasterArchiveList();
    setMasterArchiveStatus("Local archive cleared.");
  });
btnClearStaleJobs &&
  btnClearStaleJobs.addEventListener("click", () => {
    chrome.runtime.sendMessage({ action: "tbcc-gallery-job-clear-stale" }, () => void refreshActiveJobsBar());
  });
btnPauseImportQueue &&
  btnPauseImportQueue.addEventListener("click", async () => {
    const paused = await new Promise((resolve) => {
      chrome.runtime.sendMessage({ action: "tbcc-import-queue-pause-get" }, (r) => {
        if (chrome.runtime.lastError) resolve(false);
        else resolve(!!(r && r.paused));
      });
    });
    chrome.runtime.sendMessage({ action: "tbcc-import-queue-pause-set", paused: !paused }, () => {
      void syncPauseImportQueueButton();
      showToast(!paused ? "New imports paused" : "Import queue resumed", "info");
    });
  });
chrome.storage.onChanged.addListener((changes, area) => {
  if (area !== "local") return;
  if (changes[TbccSavedUrlInbox.STORAGE_SAVED_VIDEO_URLS]) {
    if (savedUrlInboxSheet && savedUrlInboxSheet.classList.contains("open")) void renderSavedUrlInboxList();
  }
  if (
    window.TbccMasterArchive &&
    changes[TbccMasterArchive.STORAGE_MASTER] &&
    masterArchiveSheet &&
    masterArchiveSheet.classList.contains("open")
  ) {
    void renderMasterArchiveList();
  }
});
btnCropOverflow &&
  btnCropOverflow.addEventListener("click", (e) => {
    e.stopPropagation();
    syncCropUiFromSettings();
    setCropPopoverOpen(true);
  });
cropToolMode &&
  cropToolMode.addEventListener("change", () => {
    if (cropTextToolRow) cropTextToolRow.style.display = cropToolMode.value === "text" ? "flex" : "none";
  });
btnCropClearImage &&
  btnCropClearImage.addEventListener("click", () => {
    if (!cropStudioActiveUrl) return;
    delete imageEdits[cropStudioActiveUrl];
    persistImageEdits();
    refreshCropStudioThumbs();
    drawCropStudioOverlay();
  });
btnCropClearSelected &&
  btnCropClearSelected.addEventListener("click", () => {
    for (const it of getCropStudioItems()) {
      delete imageEdits[it.url];
    }
    persistImageEdits();
    refreshCropStudioThumbs();
    drawCropStudioOverlay();
  });
if (cropOverlayCanvas) {
  cropOverlayCanvas.addEventListener("pointerdown", (e) => {
    if (!cropStudioActiveUrl || !cropToolMode) return;
    const tool = cropToolMode.value;
    const { x, y } = cropCanvasPointer(e);
    if (tool === "text") {
      const txt = cropTextInput && cropTextInput.value.trim();
      if (!txt) return;
      const W = cropOverlayCanvas.width;
      const H = cropOverlayCanvas.height;
      const ed = ensureImageEdit(cropStudioActiveUrl);
      const fontPx = cropTextFont ? parseInt(cropTextFont.value, 10) || 20 : 20;
      const color = cropTextColor && cropTextColor.value ? cropTextColor.value : "#ffffff";
      ed.texts.push({ x: x / W, y: y / H, text: txt, fontPx, color });
      persistImageEdits();
      drawCropStudioOverlay();
      refreshCropStudioThumbs();
      return;
    }
    cropStudioDrag = { tool, startX: x, startY: y, cur: { x0: x, y0: y, x1: x, y1: y } };
    cropOverlayCanvas.setPointerCapture(e.pointerId);
  });
  cropOverlayCanvas.addEventListener("pointermove", (e) => {
    if (!cropStudioDrag) return;
    const { x, y } = cropCanvasPointer(e);
    cropStudioDrag.cur = { x0: cropStudioDrag.startX, y0: cropStudioDrag.startY, x1: x, y1: y };
    drawCropStudioOverlay();
  });
  cropOverlayCanvas.addEventListener("pointerup", (e) => {
    if (!cropStudioDrag) return;
    const { tool, startX, startY, cur } = cropStudioDrag;
    cropStudioDrag = null;
    try {
      cropOverlayCanvas.releasePointerCapture(e.pointerId);
    } catch (_) {}
    if (cur && (tool === "crop" || tool === "blur")) {
      commitCropStudioRect(tool, startX, startY, cur.x1, cur.y1);
    }
    drawCropStudioOverlay();
  });
  cropOverlayCanvas.addEventListener("pointercancel", () => {
    cropStudioDrag = null;
    drawCropStudioOverlay();
  });
}
if (cropPreviewImg && typeof ResizeObserver !== "undefined") {
  const ro = new ResizeObserver(() => {
    layoutCropOverlayCanvas();
    drawCropStudioOverlay();
  });
  ro.observe(cropPreviewImg);
}
btnCropDone &&
  btnCropDone.addEventListener("click", () => {
    persistCropSettings();
    setCropPopoverOpen(false);
  });
cropPopover &&
  cropPopover.addEventListener("click", (e) => {
    if (e.target === cropPopover) setCropPopoverOpen(false);
  });
btnAddFilesOverflow &&
  btnAddFilesOverflow.addEventListener("click", (e) => {
    e.stopPropagation();
    if (fileInput) fileInput.click();
  });
btnToggleFoldVariants &&
  btnToggleFoldVariants.addEventListener("click", (e) => {
    e.stopPropagation();
    settings.foldVideoVariants = !settings.foldVideoVariants;
    chrome.storage.local.set({ [STORAGE_SETTINGS]: settings });
    syncFoldToggleLabel();
    renderGrid();
  });
cropBottomEnabled && cropBottomEnabled.addEventListener("change", () => persistCropSettings());
cropBottomPercent && cropBottomPercent.addEventListener("change", () => persistCropSettings());
cropBottomPercent && cropBottomPercent.addEventListener("input", () => persistCropSettings());
cropInsetMode && cropInsetMode.addEventListener("change", () => persistCropSettings());

(async function init() {
  const initStarted = Date.now();
  if (window.TbccMasterArchive) {
    void TbccMasterArchive.restoreFromBackupIfEmpty();
    void TbccMasterArchive.restoreInboxFromMirrorIfEmpty(
      () => TbccSavedUrlInbox.getRows(),
      (rows) => TbccSavedUrlInbox.setRows(rows)
    );
  }
  setInterval(() => {
    void refreshActiveJobsBar();
    void refreshSystemHealthHint();
  }, 2500);
  void reconcileImportJobsOnOpen().then(() => refreshActiveJobsBar());
  void refreshSystemHealthHint();
  try {
    window.__tbccGallerySidepanelPort = chrome.runtime.connect({ name: "tbcc-gallery-sidepanel" });
  } catch (_) {}
  window.addEventListener("pagehide", (ev) => {
    if (ev && ev.persisted) return;
    void chrome.storage.local.set({ tbccOverlayMode: false });
  });
  const s = await new Promise((r) => chrome.storage.local.get(STORAGE_SETTINGS, (o) => r(o[STORAGE_SETTINGS])));
  if (s) {
    settings = { ...settings, ...s };
    if (settings.cropBottomPercent != null && typeof settings.cropBottomPercent !== "number") {
      const n = parseInt(String(settings.cropBottomPercent), 10);
      settings.cropBottomPercent = isNaN(n) ? 8 : Math.max(0, Math.min(49, n));
    }
    if (typeof settings.cropBottomEnabled !== "boolean") settings.cropBottomEnabled = !!settings.cropBottomEnabled;
    settings.cropInsetMode = currentInsetMode();
    if (typeof settings.foldVideoVariants !== "boolean") settings.foldVideoVariants = true;
    if (typeof settings.clearSelectionOnOpen !== "boolean") settings.clearSelectionOnOpen = false;
    if (typeof settings.preserveOrphanSelections !== "boolean") settings.preserveOrphanSelections = false;
    if (typeof settings.debugTileRender !== "boolean") settings.debugTileRender = false;
    if (typeof settings.subtabEnabled !== "boolean") settings.subtabEnabled = true;
    if (typeof settings.subtabAutoCapture !== "boolean") settings.subtabAutoCapture = true;
    settings.subtabCap = Math.max(1, Math.min(5, parseInt(String(settings.subtabCap || 3), 10) || 3));
    if (typeof settings.gridSortMode !== "string") settings.gridSortMode = "default";
    if (settings.gridViewMode !== "details") settings.gridViewMode = "grid";
  }
  if (settings.clearSelectionOnOpen === true) {
    await clearSelectionForNewCapture();
  }
  syncCropUiFromSettings();
  syncFoldToggleLabel();
  if (tbccSortSelect) {
    tbccSortSelect.value = settings.gridSortMode || "default";
    tbccSortSelect.addEventListener("change", () => {
      settings.gridSortMode = tbccSortSelect.value || "default";
      persistSettingsNow();
      renderGrid();
    });
  }
  if (tbccSortDetailsToggle) {
    tbccSortDetailsToggle.classList.toggle("is-active", settings.gridViewMode === "details");
    tbccSortDetailsToggle.addEventListener("click", () => {
      settings.gridViewMode = settings.gridViewMode === "details" ? "grid" : "details";
      tbccSortDetailsToggle.classList.toggle("is-active", settings.gridViewMode === "details");
      if (gridEl) gridEl.classList.toggle("grid--details", settings.gridViewMode === "details");
      persistSettingsNow();
      renderGrid();
    });
    if (gridEl) gridEl.classList.toggle("grid--details", settings.gridViewMode === "details");
  }
  await loadGalleryDockState();
  currentTabId = await resolveTargetTabId();
  void refreshCrawlerTabUrlLabel();
  await restoreSubtabsForCurrentTab();
  subtabRestoredForTabId = currentTabId;
  await wireSubtabUi();
  renderSubtabBar();
  const rawImgEd = await new Promise((r) =>
    chrome.storage.local.get(STORAGE_IMAGE_EDITS, (o) => r(o[STORAGE_IMAGE_EDITS]))
  );
  if (rawImgEd && typeof rawImgEd === "object" && !Array.isArray(rawImgEd)) imageEdits = rawImgEd;
  syncCropOverflowLabel();
  const uiStored = await new Promise((r) => chrome.storage.local.get(STORAGE_UI_STATE, (o) => r(o[STORAGE_UI_STATE])));
  applyGalleryUiState(uiStored);
  const tagSt = await new Promise((r) => chrome.storage.local.get(STORAGE_SEND_TAGS, (o) => r(o)));
  const arrTags = tagSt[STORAGE_SEND_TAGS];
  gallerySendTags = Array.isArray(arrTags)
    ? arrTags.map((x) => String(x).trim()).filter(Boolean).slice(0, 32)
    : [];
  renderTagChipRow();
  await loadAlwaysIncludeCaptionState();
  const apiOk = await refreshTbccApiOfflineBanner();
  if (typeof TbccSendPromo !== "undefined" && TbccSendPromo.refresh) {
    void TbccSendPromo.refresh(apiOk);
    chrome.storage.local.get(["tbccShowSendPromoStrip"], (local) => {
      const btn = document.getElementById("btnToggleSendPromoStrip");
      if (btn) btn.classList.toggle("is-active", local.tbccShowSendPromoStrip === true);
    });
  }
  if (apiOk && typeof TbccMasterArchive !== "undefined" && TbccMasterArchive.syncFromServer) {
    void TbccMasterArchive.syncFromServer().then((r) => {
      if (r.ok && r.merged > 0) console.info("TBCC master archive: synced", r.merged, "entries from server");
    });
  }
  if (apiOk) {
    await Promise.all([loadTagCatalog(), loadPools(), loadChannelsForForum()]);
  } else {
    await Promise.all([loadPools(), loadChannelsForForum()]);
  }
  const forumStored = await new Promise((r) =>
    chrome.storage.local.get(
      [
        "tbccForumPostEnabled",
        "tbccForumChannelId",
        "tbccForumTopicId",
        "tbccForumAlbumCaption",
        "tbccPostDestMode",
        "tbccTelegramPostSectionOpen",
        STORAGE_AUTO_TAG_ON_EXPORT,
        STORAGE_SEND_SILENT,
      ],
      (o) => r(o)
    )
  );
  if (forumPostEnabled) forumPostEnabled.checked = !!forumStored.tbccForumPostEnabled;
  const capHydrate = await new Promise((r) =>
    chrome.storage.local.get([STORAGE_CAPTION_BASE, "tbccForumAlbumCaption"], (o) => r(o))
  );
  const linesHydrate = buildAlwaysIncludeLinksLines();
  if (Object.prototype.hasOwnProperty.call(capHydrate, STORAGE_CAPTION_BASE)) {
    captionBaseText = typeof capHydrate[STORAGE_CAPTION_BASE] === "string" ? capHydrate[STORAGE_CAPTION_BASE] : "";
  } else if (typeof capHydrate.tbccForumAlbumCaption === "string") {
    captionBaseText = stripTrailingLinkBlock(capHydrate.tbccForumAlbumCaption, linesHydrate);
  } else {
    captionBaseText = "";
  }
  syncCaptionFieldFromBase();
  if (autoTagOnExport) autoTagOnExport.checked = forumStored[STORAGE_AUTO_TAG_ON_EXPORT] !== false;
  if (sendSilent) sendSilent.checked = !!forumStored[STORAGE_SEND_SILENT];
  let destMode = forumStored.tbccPostDestMode;
  if (!destMode) destMode = forumStored.tbccForumTopicId != null ? "forum" : "channel";
  if (postDestMode) postDestMode.value = destMode;
  setTelegramSheetOpen(false);
  updateTelegramPostControls();
  if (forumPostEnabled && forumPostEnabled.checked && forumStored.tbccForumChannelId != null && destMode === "forum")
    await loadForumTopics(forumStored.tbccForumChannelId);
  if (settings.autoRefresh !== false) await doRefresh();
  else {
    showLoading(false);
    currentTabId = await resolveTargetTabId();
    const { [STORAGE_SELECTION]: storedArr = [] } = await chrome.storage.local.get(STORAGE_SELECTION);
    selectedUrls = new Set(Array.isArray(storedArr) ? storedArr : []);
    mergeUrlsIntoImageListFromSelection();
    renderGrid();
    await notifyOverlayRefresh();
  }
  await syncOverlayToggleButton();
  tbccLightboxClose && tbccLightboxClose.addEventListener("click", closeLightbox);
  tbccLightbox &&
    tbccLightbox.addEventListener("click", (e) => {
      if (e.target === tbccLightbox) closeLightbox();
    });

  /**
   * Wheel-driven navigation in the lightbox (vertical or horizontal):
   *   wheel UP / left-trackpad swipe (dominant axis negative)  → next item
   *   wheel DOWN / right (dominant axis positive)               → previous item
   *
   * passive:false so we can preventDefault and stop the side-panel from
   * scrolling underneath the lightbox while it's open. Throttled to
   * TBCC_LIGHTBOX_WHEEL_MIN_MS so a single trackpad swipe doesn't fling
   * past many images.
   */
  if (tbccLightbox) {
    tbccLightbox.addEventListener(
      "wheel",
      (e) => {
        if (!tbccLightbox.classList.contains("visible")) return;
        if (!e) return;
        const dy = typeof e.deltaY === "number" ? e.deltaY : 0;
        const dx = typeof e.deltaX === "number" ? e.deltaX : 0;
        if (dy === 0 && dx === 0) return;
        e.preventDefault();
        const now = Date.now();
        if (now - _tbccLightboxWheelLastMs < TBCC_LIGHTBOX_WHEEL_MIN_MS) return;
        _tbccLightboxWheelLastMs = now;
        const useX = Math.abs(dx) > Math.abs(dy);
        const primary = useX ? dx : dy;
        stepLightbox(primary < 0 ? 1 : -1);
      },
      { passive: false }
    );
  }
  if (galleryDropZone) {
    ["dragenter", "dragover"].forEach((ev) => {
      galleryDropZone.addEventListener(ev, (e) => {
        e.preventDefault();
        e.stopPropagation();
        galleryDropZone.classList.add("tbcc-drop-target");
      });
    });
    galleryDropZone.addEventListener("dragleave", (e) => {
      e.preventDefault();
      if (e.target === galleryDropZone) galleryDropZone.classList.remove("tbcc-drop-target");
    });
    galleryDropZone.addEventListener("drop", (e) => {
      e.preventDefault();
      e.stopPropagation();
      galleryDropZone.classList.remove("tbcc-drop-target");
      if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length) addLocalFiles(e.dataTransfer.files);
    });
  }
  document.querySelector("#filterOverlay .filter-panel")?.addEventListener("click", (e) => e.stopPropagation());
  document.querySelector("#cropPopover .filter-panel")?.addEventListener("click", (e) => e.stopPropagation());

  document.addEventListener("keydown", (e) => {
    const t = e.target;
    if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT")) return;
    if (filterOverlay && filterOverlay.classList.contains("visible") && e.key === "Escape") {
      e.preventDefault();
      setFilterOverlayOpen(false);
      return;
    }
    if (cropPopover && cropPopover.classList.contains("visible") && e.key === "Escape") {
      e.preventDefault();
      setCropPopoverOpen(false);
      return;
    }
    if (savedUrlInboxSheet && savedUrlInboxSheet.classList.contains("open") && e.key === "Escape") {
      e.preventDefault();
      openSavedUrlInboxSheet(false);
      return;
    }
    if (telegramSheet && telegramSheet.classList.contains("open") && e.key === "Escape") {
      e.preventDefault();
      setTelegramSheetOpen(false);
      return;
    }
    if (e.key === "?" || (e.shiftKey && e.key === "/")) {
      e.preventDefault();
      window.alert(
        "TBCC Gallery shortcuts:\n\nR — Refresh (full reload when enabled in ⚙ Options)\nO — Preview\nCtrl+S — Send\nEsc — Close overlays / preview\n\nCurrent / Group / All tabs: Group only scans tabs in the same Chrome tab group as the active tab.\n\nLightbox: wheel or trackpad (vertical or horizontal) steps between items.\n\n⎘ opens a pop-out gallery window.\n\nDouble-click a tile for full-size preview.\n\nImport settings / URL inbox: content pool + tags; inbox imports on the server (not sidebar bytes)."
      );
      return;
    }
    if (e.key === "Escape" && tbccLightbox && tbccLightbox.classList.contains("visible")) {
      e.preventDefault();
      closeLightbox();
      return;
    }
    /**
     * Keyboard navigation while the lightbox is open: arrows + PageUp/PageDown
     * + Home/End. ArrowDown is intentionally treated as "forward" to match the
     * wheel direction the user requested (wheel UP = forward), but ArrowRight
     * is the more conventional binding so we keep both.
     */
    if (tbccLightbox && tbccLightbox.classList.contains("visible")) {
      if (e.key === "ArrowRight" || e.key === "PageDown") {
        e.preventDefault();
        stepLightbox(1);
        return;
      }
      if (e.key === "ArrowLeft" || e.key === "PageUp") {
        e.preventDefault();
        stepLightbox(-1);
        return;
      }
      if (e.key === "Home") {
        e.preventDefault();
        const items = getLightboxNavItems();
        if (items[0]) openLightboxForItemAfterResolve(items[0]);
        return;
      }
      if (e.key === "End") {
        e.preventDefault();
        const items = getLightboxNavItems();
        if (items.length) openLightboxForItemAfterResolve(items[items.length - 1]);
        return;
      }
    }
    if (e.key === "r" || e.key === "R") {
      e.preventDefault();
      refreshPanelOrHardScan();
    }
    if (e.key === "o" || e.key === "O") {
      const first = getFilteredList().find((i) => selectedUrls.has(i.url));
      if (first) openLightboxForItem(first);
    }
    if (e.ctrlKey && (e.key === "s" || e.key === "S")) {
      e.preventDefault();
      if (btnSend && !btnSend.disabled) sendToTBCC();
    }
  });
  window.addEventListener("resize", () => {
    if (imageList.length) renderGrid();
  });
  gridEl && gridEl.addEventListener("mousedown", onGridCtrlMarqueeMouseDown);
  window.addEventListener("blur", () => {
    if (!marqueeDrag) return;
    if (marqueeDrag.box) marqueeDrag.box.remove();
    finishMarqueeDragListeners();
    marqueeDrag = null;
  });

  let visTimer;
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState !== "visible") return;
    if (settings.autoRefresh === false) return;
    if (Date.now() - initStarted < 900) return;
    clearTimeout(visTimer);
    visTimer = setTimeout(() => doRefresh(), 300);
  });
})();

