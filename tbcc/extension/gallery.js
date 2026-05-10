const API_BASE = "http://localhost:8000";

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
      h.endsWith(".erome.com")
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
const tabAllBtn = document.getElementById("tabAll");
const btnRefresh = document.getElementById("btnRefresh");
const crawlerUrlInput = document.getElementById("crawlerUrl");
const btnCrawlerUseCurrent = document.getElementById("btnCrawlerUseCurrent");
const btnCrawlerDeploy = document.getElementById("btnCrawlerDeploy");
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
const actionBarSubtitle = document.getElementById("actionBarSubtitle");
const btnTelegramSheetOpen = document.getElementById("btnTelegramSheetOpen");
const btnTelegramSheetDone = document.getElementById("btnTelegramSheetDone");
const telegramSheet = document.getElementById("telegramSheet");
const telegramSheetBackdrop = document.getElementById("telegramSheetBackdrop");
const cropPopover = document.getElementById("cropPopover");
const btnCropOverflow = document.getElementById("btnCropOverflow");
const btnCropDone = document.getElementById("btnCropDone");
const btnAddFilesOverflow = document.getElementById("btnAddFilesOverflow");
const toastContainer = document.getElementById("toastContainer");
const poolSelect = document.getElementById("poolSelect");
const forumPostEnabled = document.getElementById("forumPostEnabled");
const autoTagOnExport = document.getElementById("autoTagOnExport");
const postDestMode = document.getElementById("postDestMode");
const forumChannelSelect = document.getElementById("forumChannelSelect");
const forumTopicSelect = document.getElementById("forumTopicSelect");
const forumTopicRow = document.getElementById("forumTopicRow");
const forumAlbumCaption = document.getElementById("forumAlbumCaption");
const btnAutoCap = document.getElementById("btnAutoCap");
const forumPostEnabledLabel = document.getElementById("forumPostEnabledLabel");
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
const tagCatalogSelect = document.getElementById("tagCatalogSelect");
const btnTagSuggest = document.getElementById("btnTagSuggest");
const btnTagsCatalogReload = document.getElementById("btnTagsCatalogReload");
const tagNewName = document.getElementById("tagNewName");
const tagNewCategory = document.getElementById("tagNewCategory");
const btnTagCreate = document.getElementById("btnTagCreate");
const btnTagsClear = document.getElementById("btnTagsClear");
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

/** Same caption box as Telegram post — also attached to each album sent to Saved Messages. */
function getAlbumCaptionForSend() {
  return forumAlbumCaption && forumAlbumCaption.value ? forumAlbumCaption.value.trim() : "";
}
function appendCaptionToSavedForm(form) {
  const c = getAlbumCaptionForSend();
  if (c) form.append("caption", c);
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
    updateCountAndSend();
    return;
  }
  if (e.ctrlKey || e.metaKey) {
    e.preventDefault();
    e.stopPropagation();
    if (selectedUrls.has(url)) selectedUrls.delete(url);
    else selectedUrls.add(url);
    renderGrid();
    updateCountAndSend();
    return;
  }
  lastSelectionAnchorIndex = displayIdx;
  if (selectedUrls.has(url)) selectedUrls.delete(url);
  else selectedUrls.add(url);
  renderGrid();
  updateCountAndSend();
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
    updateCountAndSend();
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
      updateCountAndSend();
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

function persistSelection() {
  return chrome.storage.local.set({ tbccSelectionUrls: [...selectedUrls] });
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
  void chrome.storage.local.set({ [STORAGE_SEND_TAGS]: gallerySendTags });
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
  if (tagCatalogSelect) tagCatalogSelect.value = "";
  if (tagNewName) tagNewName.value = "";
  if (tagNewCategory) tagNewCategory.value = "";
}

function looksLikeBareDomain(s) {
  return /^[\w.-]+\.[a-z]{2,}$/i.test(String(s).trim()) && !String(s).includes(" ");
}

async function loadTagCatalog() {
  const endpoints = [
    `${API_BASE}/tags/`,
    `${API_BASE}/tags`,
    "http://127.0.0.1:8000/tags/",
    "http://127.0.0.1:8000/tags",
  ];
  let lastErr = null;
  for (let pass = 0; pass < 2; pass++) {
    for (const url of endpoints) {
      try {
        const r = await fetch(url, { cache: "no-store" });
        if (!r.ok) throw new Error(await r.text());
        tagCatalog = await r.json();
        if (tagCatalogSelect) {
          const prev = tagCatalogSelect.value;
          tagCatalogSelect.innerHTML = "";
          const ph = document.createElement("option");
          ph.value = "";
          ph.textContent = "Pick from catalog…";
          tagCatalogSelect.appendChild(ph);
          for (const t of tagCatalog) {
            const label =
              (t.name != null && String(t.name).trim()) || (t.slug != null && String(t.slug).trim()) || "";
            if (!label) continue;
            const o = document.createElement("option");
            o.value = label;
            o.textContent = label;
            tagCatalogSelect.appendChild(o);
          }
          if (prev && [...tagCatalogSelect.options].some((opt) => opt.value === prev)) {
            tagCatalogSelect.value = prev;
          }
        }
        return;
      } catch (e) {
        lastErr = e;
      }
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  console.warn("TBCC loadTagCatalog:", lastErr);
}

async function createTagOnServer() {
  const name = tagNewName && tagNewName.value.trim();
  const category = tagNewCategory && tagNewCategory.value.trim();
  if (!name) {
    showToast("Enter a tag name.", "info");
    return;
  }
  try {
    const r = await fetch(`${API_BASE}/tags`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, category: category || undefined }),
    });
    const text = await r.text();
    let data = {};
    try {
      data = text ? JSON.parse(text) : {};
    } catch (_) {}
    if (!r.ok) throw new Error(typeof data.detail === "string" ? data.detail : text || r.statusText);
    addGallerySendTag(data.name || name);
    tagNewName.value = "";
    await loadTagCatalog();
    showToast("Tag created and added to Send list.", "success");
  } catch (e) {
    showToast(e.message || String(e), "error");
  }
}

function onCatalogTagSelected() {
  if (!tagCatalogSelect) return;
  const v = tagCatalogSelect.value.trim();
  if (!v) return;
  const low = v.toLowerCase();
  const row = tagCatalog.find((t) => {
    const n = (t.name && String(t.name).toLowerCase()) || "";
    const s = (t.slug && String(t.slug).toLowerCase()) || "";
    return n === low || (s && s === low);
  });
  addGallerySendTag(row ? (row.name && String(row.name).trim()) || row.slug || v : v);
  tagCatalogSelect.value = "";
}

async function suggestTagsFromPage() {
  const tid = await resolveTargetTabId();
  if (!tid) {
    showToast("Open a normal https page tab to scan.", "info");
    return;
  }
  let hints = [];
  try {
    await chrome.scripting.executeScript({ target: { tabId: tid }, files: ["media-url-guards.js", "capture.js"] });
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
  "thumbnail",
  "gallery",
  "post",
  "posts",
]);

function normalizeAutoTagCandidate(raw) {
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
  set.add(lookup.get(low) || normalized);
}

/** Always tag imported media with the capture / page hostname (not CDN-only hosts). */
function addMandatorySiteTag(set, lookup, hostname) {
  const raw = String(hostname || "")
    .trim()
    .replace(/^www\./i, "");
  if (!raw || !raw.includes(".")) return;
  const normalized = normalizeAutoTagCandidate(raw);
  if (!normalized) return;
  const low = normalized.toLowerCase();
  set.add(lookup.get(low) || normalized);
}

function normTabId(x) {
  const n = Number(x);
  return Number.isFinite(n) ? n : null;
}

async function fetchTagHintsInTab(tabId) {
  const tid = normTabId(tabId);
  if (tid == null) return [];
  try {
    await chrome.scripting.executeScript({ target: { tabId: tid }, files: ["media-url-guards.js", "capture.js"] });
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

function extractAutoTagsFromUrl(rawUrl, lookup, set) {
  try {
    const u = new URL(String(rawUrl || ""));
    const host = String(u.hostname || "").replace(/^www\./i, "");
    addAutoTagToSet(set, lookup, host, true);
    host
      .split(".")
      .filter(Boolean)
      .forEach((part) => addAutoTagToSet(set, lookup, part, false));
    const pathParts = String(u.pathname || "")
      .split("/")
      .map((part) => decodeURIComponent(part || "").trim())
      .filter(Boolean);
    pathParts.forEach((part) => {
      part
        .split(/[^a-zA-Z0-9]+/g)
        .filter(Boolean)
        .forEach((bit) => addAutoTagToSet(set, lookup, bit, false));
    });
  } catch (_) {}
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
    extractAutoTagsFromUrl(pageFromCapture, lookup, out);
    extractAutoTagsFromUrl(item.url, lookup, out);
  } else if (pageFromCapture) {
    extractAutoTagsFromUrl(pageFromCapture, lookup, out);
  }
  return out;
}

async function collectPageHintsByTabId(tabIds) {
  const out = new Map();
  const list = [...new Set((tabIds || []).map(normTabId).filter((x) => x != null))];
  for (const tabId of list) {
    out.set(tabId, await fetchTagHintsInTab(tabId));
  }
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
  for (const sp of uniq) {
    const key = normalizeSourcePageKey(sp);
    if (out.has(key)) continue;
    const tabId = await findTabIdForSourcePageUrl(sp);
    if (tabId == null) {
      out.set(key, []);
      continue;
    }
    out.set(key, await fetchTagHintsInTab(tabId));
  }
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
    pageHints.forEach((h) => addAutoTagToSet(tags, lookup, h, true));
    const perItem = collectPerItemAutoTags(rec.item || null, lookup, rec.sourcePage);
    perItem.forEach((t) => tags.add(t));
    if (rec.sourcePage) {
      try {
        const host = new URL(rec.sourcePage).hostname.replace(/^www\./i, "");
        addMandatorySiteTag(tags, lookup, host);
      } catch (_) {}
    }
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
}

const TBCC_TELEGRAM_CAPTION_MAX = 1024;

/** Turn a TBCC tag or hint string into a single Telegram-style #hashtag token. */
function displayTagToHashtag(tag) {
  const raw = String(tag || "")
    .trim()
    .replace(/^#+/u, "");
  if (!raw) return "";
  const compact = raw.replace(/\s+/gu, "");
  if (!compact) return "";
  const capped = compact.length > 42 ? compact.slice(0, 42) : compact;
  return "#" + capped;
}

/** Chosen send tags first, then extra page hints (deduped, domain-like hints skipped). */
function buildHashtagLineFromTagsAndHints(sendTags, pageHints) {
  const seen = new Set();
  const out = [];
  for (const t of sendTags || []) {
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
    if (looksLikeBareDomain(hint)) continue;
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
    await chrome.scripting.executeScript({ target: { tabId: tid }, files: ["media-url-guards.js", "capture.js"] });
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
      hints = Array.isArray(res.hints) ? res.hints : [];
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
  if (forumAlbumCaption) {
    forumAlbumCaption.value = cap;
    forumAlbumCaption.dispatchEvent(new Event("input", { bubbles: true }));
  }
  await chrome.storage.local.set({ tbccForumAlbumCaption: cap });
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

async function loadPools() {
  try {
    const r = await fetch(API_BASE + "/pools");
    const pools = await r.json();
    if (poolSelect) {
      poolSelect.innerHTML = "";
      (pools || []).forEach((p) => {
        const o = document.createElement("option");
        o.value = String(p.id);
        o.textContent = p.name || "Pool " + p.id;
        poolSelect.appendChild(o);
      });
      const { tbccPoolId } = await chrome.storage.local.get("tbccPoolId");
      if (tbccPoolId != null) poolSelect.value = String(tbccPoolId);
      syncPoolSelectTooltip();
    }
  } catch (_) {}
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
    await Promise.all([loadPools(), loadChannelsForForum()]);
    await reloadForumTopicsIfNeeded();
    reloadEmbeddedPanelIframes();
  }
  await doRefresh();
}

async function loadChannelsForForum() {
  if (!forumChannelSelect) return;
  try {
    const r = await fetch(API_BASE + "/channels");
    const channels = await r.json();
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
  } catch (_) {
    forumChannelSelect.innerHTML = '<option value="">(API offline)</option>';
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

function applyTelegramPostSectionCollapsed(collapsed) {
  /* Sheet UI: collapsed=true means sheet closed */
  setTelegramSheetOpen(!collapsed);
}

function updateForumCheckboxLabel() {
  if (!forumPostEnabledLabel) return;
  const savedMode = postDestMode && postDestMode.value === "saved";
  forumPostEnabledLabel.textContent = savedMode
    ? "Send to Telegram Saved Messages only (skips TBCC pool — no import)"
    : "After import to the pool above, also post to Telegram (see destination)";
}

function updateAutoTagCheckboxLabel() {
  if (!autoTagOnExportLabel) return;
  const savedMode = postDestMode && postDestMode.value === "saved";
  autoTagOnExportLabel.textContent = savedMode
    ? "Auto-tag on export (disabled for Saved-only sends)"
    : "Auto-tag on export (page + per-item hints)";
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
  if (postDestMode) postDestMode.disabled = !on;
  const savedMode = postDestMode && postDestMode.value === "saved";
  const forumMode = postDestMode && postDestMode.value === "forum";
  if (forumChannelSelect) {
    forumChannelSelect.disabled = !on || savedMode;
    forumChannelSelect.style.display = savedMode ? "none" : "";
  }
  if (forumTopicRow) forumTopicRow.style.display = forumMode ? "flex" : "none";
  const ch = forumChannelSelect && forumChannelSelect.value;
  if (forumTopicSelect) forumTopicSelect.disabled = !on || !ch || !forumMode;
  if (btnForumTopicsRefresh) btnForumTopicsRefresh.disabled = !on || !ch || !forumMode;
  updateForumCheckboxLabel();
  updateAutoTagCheckboxLabel();
  updateSendButtonLabel();
  updateActionBarSubtitle();
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
  const rtAll = capSettings.resourceTimingAllImages === true;
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
      files: ["media-url-guards.js", "capture.js"],
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
    if (payload.list && payload.list.length) mergedList.push(...payload.list);
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

async function resolveTargetTabId() {
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
      await chrome.storage.local.set({ tbccSelectionUrls: kept, tbccSelectionMeta: keptMeta });
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
  selectedUrls = new Set();
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
const SUBTAB_MAX_IMAGES_PER_SNAPSHOT = 600;
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
  t.imageListSnapshot = trimmed.map((i) => ({
    url: i.url,
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
    tbccStreamManifest: i.tbccStreamManifest,
    tbccSourcePageUrl: i.tbccSourcePageUrl,
    tabId: i.tabId,
  }));
  t.selectionUrls = Array.from(selectedUrls);
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
      await chrome.storage.local.set({ [key]: payload });
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
  selectedUrls = new Set(target.selectionUrls || []);
  try {
    await chrome.storage.local.set({ [STORAGE_SELECTION]: Array.from(selectedUrls) });
  } catch (_) {}
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
      selectedUrls = new Set(target.selectionUrls || []);
      try {
        await chrome.storage.local.set({ [STORAGE_SELECTION]: Array.from(selectedUrls) });
      } catch (_) {}
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

async function appendMergedCapture(tabId) {
  const { list } = await runCaptureInTab(tabId);
  if (!list || !list.length) return 0;
  const seen = new Set(imageList.map((i) => i.url));
  let n = 0;
  for (const it of list) {
    if (!it || !it.url || seen.has(it.url)) continue;
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
      try {
        const tab = await chrome.tabs.get(currentTabId);
        const u = (tab && tab.url) || "";
        if (/onlyfans\.com/i.test(u)) scanDelays = SCAN_MERGE_DELAYS_MS_ONLYFANS;
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
      if (settings.subtabEnabled) snapshotCurrentStateIntoActiveSubtab();
      return;
    }
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

async function fillCrawlerUrlFromCurrentTab() {
  if (!crawlerUrlInput) return "";
  const u = await getCurrentTabUrl();
  if (u) crawlerUrlInput.value = u;
  return u;
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

async function deployCrawlerFromSidebar() {
  if (!crawlerUrlInput || !btnCrawlerDeploy) return;
  let url = crawlerUrlInput.value.trim();
  if (!url) url = await fillCrawlerUrlFromCurrentTab();
  if (!url || !/^https?:\/\//i.test(url)) {
    setCrawlerStatus("Enter a URL", "error");
    showToast("Enter a crawler URL or open a normal https page tab.", "info");
    return;
  }
  btnCrawlerDeploy.disabled = true;
  setCrawlerStatus("Crawling...", "info");
  try {
    const r = await fetch(API_BASE + "/crawler/resolve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, adapter: "auto", limit: 500 }),
    });
    const text = await r.text();
    let data = {};
    try {
      data = text ? JSON.parse(text) : {};
    } catch (_) {}
    if (!r.ok) throw new Error((data && data.detail) || text || r.statusText);
    const items = Array.isArray(data.items) ? data.items : [];
    if (!items.length) {
      const warning = Array.isArray(data.warnings) && data.warnings.length ? data.warnings[0] : "No media found.";
      throw new Error(warning);
    }
    const sourceUrl = data.source_url || url;
    const have = new Set(imageList.map((i) => i && i.url).filter(Boolean));
    const added = [];
    for (const item of items) {
      if (!item || !item.url || have.has(item.url)) continue;
      const row = crawlerItemToGalleryItem(item, sourceUrl, data.adapter);
      imageList.push(row);
      selectedUrls.add(row.url);
      have.add(row.url);
      added.push(row);
    }
    await persistSelection();
    if (settings.subtabEnabled && activeGalleryTabId != null) snapshotCurrentStateIntoActiveSubtab();
    renderGrid();
    setCrawlerStatus(added.length + " added", "success");
    showToast(`Crawler added ${added.length} media item(s). Use Dest, Send, ZIP, or Download next.`, "success");
  } catch (e) {
    const msg = e && e.message ? e.message : String(e);
    setCrawlerStatus("Failed", "error");
    showToast("Crawler failed: " + msg, "error");
  } finally {
    btnCrawlerDeploy.disabled = false;
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

  const markDimsFromImg = (img) => {
    try {
      if (img && img.naturalWidth > 0 && img.naturalHeight > 0) {
        item.naturalWidth = img.naturalWidth;
        item.naturalHeight = img.naturalHeight;
        if (!item.width || item.width < img.naturalWidth) item.width = img.naturalWidth;
        if (!item.height || item.height < img.naturalHeight) item.height = img.naturalHeight;
      }
    } catch (_) {}
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
          updateCountAndSend();
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
          updateCountAndSend();
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

function updateCountAndSend() {
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
  updateForumCheckboxLabel();
  updateActionBarVisibility();
  updateActionBarSubtitle();
  syncCropOverflowLabel();
  if (cropPopover && cropPopover.classList.contains("visible")) initCropStudioPanel();
  persistSelection();
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
  updateCountAndSend();
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
  updateCountAndSend();
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

async function postImportBytes(blob, filename, poolId, savedOnly, source) {
  const form = new FormData();
  form.append("file", blob, filename);
  form.append("pool_id", String(poolId));
  form.append("saved_only", savedOnly ? "true" : "false");
  form.append("source", source || "extension:upload-cropped");
  if (savedOnly) appendCaptionToSavedForm(form);
  const r = await fetch(API_BASE + "/import/bytes", { method: "POST", body: form });
  return parseImportResponse(r);
}

function filenameForCropUrl(url) {
  const n = filenameFromUrl(url);
  if (/\.(jpe?g)$/i.test(n)) return n;
  return (n.replace(/\.[^.]+$/, "") || "media") + ".jpg";
}

async function tbccRefererPageForItem(it) {
  if (!it) return "";
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

function applyGalleryUiState(ui) {
  if (!ui || typeof ui !== "object") return;
  if (filterType && ui.filterType != null) filterType.value = String(ui.filterType);
  if (filterMinW && ui.filterMinW != null) filterMinW.value = String(ui.filterMinW);
  if (filterMinH && ui.filterMinH != null) filterMinH.value = String(ui.filterMinH);
  if (filterUrl && ui.filterUrl != null) filterUrl.value = String(ui.filterUrl);
  if (filterHideUiClutter && ui.filterHideUiClutter != null) {
    filterHideUiClutter.checked = !!ui.filterHideUiClutter;
  }
  if (ui.activeTab === "all" && tabAllBtn && tabCurrentBtn) {
    activeTab = "all";
    tabAllBtn.classList.add("active");
    tabCurrentBtn.classList.remove("active");
  } else if (ui.activeTab === "current" && tabAllBtn && tabCurrentBtn) {
    activeTab = "current";
    tabCurrentBtn.classList.add("active");
    tabAllBtn.classList.remove("active");
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

function showToast(message, type) {
  if (!toastContainer || !message) return;
  const t = type || "info";
  const el = document.createElement("div");
  el.className = "toast " + (t === "success" ? "success" : t === "error" ? "error" : "info");
  el.textContent = message;
  toastContainer.appendChild(el);
  const ms = t === "error" ? 10000 : 4000;
  setTimeout(() => {
    try {
      el.remove();
    } catch (_) {}
  }, ms);
}

function showSystemNotification(title, message) {
  try {
    if (!chrome || !chrome.notifications) return;
    const iconUrl = chrome.runtime.getURL("icons/icon16.png");
    chrome.notifications.create("tbcc-sidepanel-" + Date.now(), {
      type: "basic",
      iconUrl,
      title: title || "TBCC",
      message: message || "",
    });
  } catch (_) {}
}

function notifyCompletion(message, type, settingsKey, title) {
  showToast(message, type || "info");
  if (!settings || settings.notifyUseSystem === false) return;
  if (settingsKey && settings[settingsKey] === false) return;
  showSystemNotification(title || "TBCC", message);
}

function updateActionBarVisibility() {
  if (!galleryActionBar) return;
  galleryActionBar.classList.toggle("hidden", selectedCountInFilteredList() === 0);
}

function setTelegramSheetOpen(open) {
  if (!telegramSheet) return;
  telegramSheet.classList.toggle("open", !!open);
  telegramSheet.setAttribute("aria-hidden", open ? "false" : "true");
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

function updateActionBarSubtitle() {
  if (!actionBarSubtitle) return;
  const on = forumPostEnabled && forumPostEnabled.checked;
  const mode = postDestMode && postDestMode.value;
  if (!on) {
    actionBarSubtitle.textContent = "";
    return;
  }
  if (mode === "saved") {
    actionBarSubtitle.textContent = "→ Saved Messages";
    return;
  }
  const ch = forumChannelSelect && forumChannelSelect.selectedOptions[0];
  const chLabel = ch ? ch.textContent.trim() : "";
  if (mode === "forum") {
    const tp = forumTopicSelect && forumTopicSelect.selectedOptions[0];
    const tLabel = tp ? tp.textContent.trim() : "";
    actionBarSubtitle.textContent = chLabel
      ? tLabel
        ? "→ " + chLabel + " · " + tLabel
        : "→ " + chLabel + " (forum)"
      : "→ Forum…";
  } else {
    actionBarSubtitle.textContent = chLabel ? "→ " + chLabel : "→ Channel…";
  }
}

async function importSavedUrlJson(urls, poolId) {
  const normalized = (urls || []).map((u) => normalizeTbccMediaUrlForImport(u));
  const payload = { urls: normalized, pool_id: poolId, saved_only: true };
  const c = getAlbumCaptionForSend();
  if (c) payload.caption = c;
  const r = await fetch(API_BASE + "/import/url", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseImportResponse(r);
}

async function downloadSelectedAsZip() {
  const list = getFilteredList();
  const selected = list.filter((i) => selectedUrls.has(i.url));
  if (selected.length === 0 || !chrome.downloads) return;
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
    notifyCompletion(msg, "success", "notifyOnZipComplete", "TBCC ZIP complete");
  } catch (e) {
    if (progressError) progressError.textContent = (progressError.textContent || "") + (e.message || "ZIP failed") + "; ";
  }
  btnDownloadZip.disabled = false;
  if (btnDownload) btnDownload.disabled = selectedCountInFilteredList() === 0;
  if (btnCopyJd) btnCopyJd.disabled = selectedCountInFilteredList() === 0;
}

async function copySelectedUrlsForJDownloader() {
  const list = getFilteredList();
  const selected = list.filter((i) => selectedUrls.has(i.url));
  const lines = selected
    .map((i) => bestHttpMediaUrlForItem(i) || i.url)
    .filter((u) => typeof u === "string" && (u.startsWith("http://") || u.startsWith("https://")));
  if (!lines.length) return;
  try {
    await navigator.clipboard.writeText(lines.join("\n"));
    if (progressEl) progressEl.classList.add("visible");
    if (progressStatus)
      progressStatus.textContent =
        "Copied " + lines.length + " URL(s). Paste into JDownloader LinkGrabber or MyJDownloader.";
  } catch (e) {
    if (progressEl) progressEl.classList.add("visible");
    if (progressError) progressError.textContent = (progressError.textContent || "") + (e.message || "clipboard failed") + "; ";
  }
}

async function downloadSelected() {
  const list = getFilteredList();
  const selected = list.filter((i) => selectedUrls.has(i.url));
  if (selected.length === 0 || !chrome.downloads) return;
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
}

btnDownload && btnDownload.addEventListener("click", () => downloadSelected());
btnDownloadZip && btnDownloadZip.addEventListener("click", () => downloadSelectedAsZip());
btnCopyJd && btnCopyJd.addEventListener("click", () => copySelectedUrlsForJDownloader());
btnCrawlerUseCurrent && btnCrawlerUseCurrent.addEventListener("click", () => void fillCrawlerUrlFromCurrentTab());
btnCrawlerDeploy && btnCrawlerDeploy.addEventListener("click", () => void deployCrawlerFromSidebar());
crawlerUrlInput &&
  crawlerUrlInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      void deployCrawlerFromSidebar();
    }
  });

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
    const newVal = changes[STORAGE_SELECTION].newValue || [];
    const next = new Set(Array.isArray(newVal) ? newVal : []);
    if (setsEqual(next, selectedUrls)) return;
    selectedUrls = next;
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
    tabCurrentBtn.classList.add("active");
    tabAllBtn && tabAllBtn.classList.remove("active");
    saveGalleryUiState();
    await clearSelectionForNewCapture();
    doRefresh();
  });
tabAllBtn &&
  tabAllBtn.addEventListener("click", async () => {
    activeTab = "all";
    tabAllBtn.classList.add("active");
    tabCurrentBtn && tabCurrentBtn.classList.remove("active");
    saveGalleryUiState();
    await clearSelectionForNewCapture();
    doRefresh();
  });

btnRefresh && btnRefresh.addEventListener("click", () => refreshPanelOrHardScan());

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

tagCatalogSelect &&
  tagCatalogSelect.addEventListener("change", () => {
    onCatalogTagSelected();
  });
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

forumPostEnabled &&
  forumPostEnabled.addEventListener("change", async () => {
    await chrome.storage.local.set({ tbccForumPostEnabled: !!forumPostEnabled.checked });
    updateTelegramPostControls();
    if (forumPostEnabled.checked && forumChannelSelect && forumChannelSelect.value && postDestMode && postDestMode.value === "forum")
      await loadForumTopics(parseInt(forumChannelSelect.value, 10));
  });
autoTagOnExport &&
  autoTagOnExport.addEventListener("change", async () => {
    await chrome.storage.local.set({ [STORAGE_AUTO_TAG_ON_EXPORT]: !!autoTagOnExport.checked });
    updateTelegramPostControls();
  });
postDestMode &&
  postDestMode.addEventListener("change", async () => {
    await chrome.storage.local.set({ tbccPostDestMode: postDestMode.value || "channel" });
    updateTelegramPostControls();
    if (postDestMode.value === "forum" && forumChannelSelect && forumChannelSelect.value)
      await loadForumTopics(parseInt(forumChannelSelect.value, 10));
  });
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
    chrome.storage.local.set({ tbccForumAlbumCaption: forumAlbumCaption.value || "" });
  });
btnAutoCap && btnAutoCap.addEventListener("click", () => void autoCapFromPage());
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
async function importUrlViaExtensionSession(url, poolId, savedOnly, refererPageUrl) {
  url = normalizeTbccMediaUrlForImport(url);
  return new Promise((resolve) => {
    chrome.runtime.sendMessage(
      {
        action: "tbcc-import-bytes-session",
        url,
        poolId,
        savedOnly: !!savedOnly,
        source: "extension:gallery-session",
        refererPageUrl: typeof refererPageUrl === "string" ? refererPageUrl : "",
      },
      (data) => {
        if (chrome.runtime.lastError) resolve({ error: chrome.runtime.lastError.message });
        else resolve(data && typeof data === "object" ? data : { error: "No response" });
      }
    );
  });
}

/** Same as context menu: backend fetches URL (fast; works for public hotlinks). */
async function importOneUrl(url, poolId, savedOnly) {
  try {
    url = normalizeTbccMediaUrlForImport(url);
    const payload = { url, pool_id: poolId };
    if (savedOnly) payload.saved_only = true;
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

function kindForSavedItem(it) {
  if (it.file) return "file";
  /** Page-captured media is often a blob: URL — was misclassified as "other" and sent one-by-one via /import/bytes (no albums). */
  if (it.url && String(it.url).startsWith("blob:") && it.tabId) return "blob:" + it.tabId;
  if (it.url && /^https?:\/\//i.test(it.url)) return hostNeedsSessionFetch(it.url) ? "session" : "plain";
  return "other";
}

function groupConsecutiveSavedKinds(selected) {
  const groups = [];
  let cur = null;
  for (const it of selected) {
    const k = kindForSavedItem(it);
    if (k === "other") {
      if (cur) {
        groups.push(cur);
        cur = null;
      }
      groups.push({ kind: "other", items: [it] });
      continue;
    }
    if (!cur || cur.kind !== k) {
      if (cur) groups.push(cur);
      cur = { kind: k, items: [] };
    }
    cur.items.push(it);
  }
  if (cur) groups.push(cur);
  return groups;
}

function importViaExtensionBytesSavedBatch(urls) {
  return new Promise((resolve) => {
    chrome.runtime.sendMessage(
      { action: "tbcc-import-bytes-session-saved-batch", urls, caption: getAlbumCaptionForSend() },
      (data) => {
        if (chrome.runtime.lastError) resolve({ error: chrome.runtime.lastError.message });
        else resolve(data && typeof data === "object" ? data : { error: "No response" });
      }
    );
  });
}

async function runSendSavedBatchAlbums(selected, poolId, bump, appendErr) {
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
        appendCaptionToSavedForm(form);
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
            chunk.forEach(() => bump());
          }
        } catch (e) {
          appendErr(e.message);
          chunk.forEach(() => bump());
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
            const cap = getAlbumCaptionForSend();
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
                if (okSet && !okSet.has(u)) {
                  bump();
                  continue;
                }
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
              slice.forEach(() => bump());
            }
          } catch (e) {
            appendErr(e.message);
            slice.forEach(() => bump());
          }
        } else {
          let pendingCrops = [];
          const flushCrops = async () => {
            if (!pendingCrops.length) return;
            const form = new FormData();
            pendingCrops.forEach((p, j) => form.append("files", p.blob, p.name || `media_${j}.jpg`));
            appendCaptionToSavedForm(form);
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
                pendingCrops.forEach(() => bump());
              }
            } catch (e) {
              appendErr(e.message);
              pendingCrops.forEach(() => bump());
            }
            pendingCrops = [];
          };
          for (const it of slice) {
            if (isImageItem(it) && !shouldApplyImagePipelineForUrl(it.url)) {
              await flushCrops();
              try {
                const data = await importSavedUrlJson([it.url], poolId);
                if (data.status === "saved_only" && !data.error) {
                  await addToCollected({ url: it.url, type: "image", addedAt: Date.now(), to_saved: true });
                  bump();
                } else {
                  appendErr(data.error || "Saved URL import failed");
                  bump();
                }
              } catch (e) {
                appendErr(e.message);
                bump();
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
                    const data = await importSavedUrlJson([it.url], poolId);
                    if (data.status === "saved_only" && !data.error) {
                      await addToCollected({ url: it.url, type: "image", addedAt: Date.now(), to_saved: true });
                      bump();
                    } else {
                      appendErr(data.error || "Saved URL import failed");
                      bump();
                    }
                  } catch (e) {
                    appendErr(e.message);
                    bump();
                  }
                }
              } catch (e) {
                appendErr(e.message);
                await flushCrops();
                try {
                  const data = await importSavedUrlJson([it.url], poolId);
                  if (data.status === "saved_only" && !data.error) {
                    await addToCollected({ url: it.url, type: "image", addedAt: Date.now(), to_saved: true });
                    bump();
                  } else {
                    appendErr(data.error || "Saved URL import failed");
                    bump();
                  }
                } catch (e2) {
                  appendErr(e2.message);
                  bump();
                }
              }
            } else {
              await flushCrops();
              try {
                const data = await importSavedUrlJson([it.url], poolId);
                if (data.status === "saved_only" && !data.error) {
                  await addToCollected({ url: it.url, type: "image", addedAt: Date.now(), to_saved: true });
                  bump();
                } else {
                  appendErr(data.error || "Saved URL import failed");
                  bump();
                }
              } catch (e) {
                appendErr(e.message);
                bump();
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
          const data = await importViaExtensionBytesSavedBatch(urls);
          if (data.ok && !data.error) {
            for (const it of g.items) {
              await addToCollected({ url: it.url, type: "image", addedAt: Date.now(), to_saved: true });
              bump();
            }
          } else {
            appendErr(data.error || "Session saved batch failed");
            g.items.forEach(() => bump());
          }
        } catch (e) {
          appendErr(e.message);
          g.items.forEach(() => bump());
        }
      } else {
        for (let i = 0; i < g.items.length; i += SAVED_ALBUM_CHUNK) {
          const chunk = g.items.slice(i, i + SAVED_ALBUM_CHUNK);
          const allImg = chunk.every(isImageItem);
          if (!allImg) {
            try {
              const data = await importViaExtensionBytesSavedBatch(chunk.map((x) => x.url));
              if (data.ok && !data.error) {
                for (const it of chunk) {
                  await addToCollected({ url: it.url, type: "image", addedAt: Date.now(), to_saved: true });
                  bump();
                }
              } else {
                appendErr(data.error || "Session saved batch failed");
                chunk.forEach(() => bump());
              }
            } catch (e) {
              appendErr(e.message);
              chunk.forEach(() => bump());
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
            appendCaptionToSavedForm(form);
            const r = await fetch(API_BASE + "/import/saved-batch", { method: "POST", body: form });
            const data = await parseImportResponse(r);
            if (data.status === "saved_only" && !data.error) {
              for (const it of chunk) {
                await addToCollected({ url: it.url, type: "image", addedAt: Date.now(), to_saved: true });
                bump();
              }
            } else {
              appendErr(data.error || "Saved batch (session crop) failed");
              chunk.forEach(() => bump());
            }
          } catch (e) {
            try {
              const data = await importViaExtensionBytesSavedBatch(chunk.map((x) => x.url));
              if (data.ok && !data.error) {
                for (const it of chunk) {
                  await addToCollected({ url: it.url, type: "image", addedAt: Date.now(), to_saved: true });
                  bump();
                }
              } else {
                appendErr(data.error || "Session saved batch failed");
                chunk.forEach(() => bump());
              }
            } catch (e2) {
              appendErr(e2.message || String(e));
              chunk.forEach(() => bump());
            }
          }
        }
      }
    } else if (g.kind.startsWith("blob:")) {
      const tabId = parseInt(g.kind.slice("blob:".length), 10);
      if (!tabId || isNaN(tabId)) {
        appendErr("Invalid tab for blob media");
        g.items.forEach(() => bump());
        continue;
      }
      for (let i = 0; i < g.items.length; i += SAVED_ALBUM_CHUNK) {
        const chunk = g.items.slice(i, i + SAVED_ALBUM_CHUNK);
        const blobUrls = chunk.map((it) => it.url);
        try {
          const results = await chrome.scripting.executeScript({
            target: { tabId },
            func: async (urls) => {
              const out = [];
              for (const u of urls) {
                const r = await fetch(u);
                const ab = await r.arrayBuffer();
                out.push(Array.from(new Uint8Array(ab)));
              }
              return out;
            },
            args: [blobUrls],
          });
          const payload = results && results[0] && results[0].result;
          if (!payload || !Array.isArray(payload) || payload.length !== chunk.length) {
            appendErr("Could not read blob URLs from the page (tab closed?)");
            chunk.forEach(() => bump());
            continue;
          }
          const form = new FormData();
          for (let j = 0; j < payload.length; j++) {
            const arr = payload[j];
            const it = chunk[j];
            const u8 = new Uint8Array(arr);
            let blob = new Blob([u8], { type: "application/octet-stream" });
            if (shouldApplyImagePipelineForUrl(it.url) && isImageItem(it)) {
              try {
                blob = await applyImagePipeline(blob, it.url);
              } catch (_) {}
            }
            form.append("files", blob, `media_${j}.jpg`);
          }
          appendCaptionToSavedForm(form);
          const r = await fetch(API_BASE + "/import/saved-batch", { method: "POST", body: form });
          const data = await parseImportResponse(r);
          if (data.status === "saved_only" && !data.error) {
            for (const it of chunk) {
              await addToCollected({ url: it.url, type: it.type || "image", addedAt: Date.now(), to_saved: true });
              bump();
            }
          } else {
            appendErr(data.error || "Saved batch (blobs) failed");
            chunk.forEach(() => bump());
          }
        } catch (e) {
          appendErr(e.message || String(e));
          chunk.forEach(() => bump());
        }
      }
    } else {
      for (const it of g.items) {
        try {
          if (it.tabId && it.url) {
            const batch = await fetchAndUploadViaTab(it.tabId, [it.url], poolId, true);
            (batch.errors || []).forEach((e) => appendErr(e.error || String(e)));
            if ((batch.imported || 0) + (batch.skipped || 0) > 0) {
              await addToCollected({ url: it.url, type: "image", addedAt: Date.now(), to_saved: true });
            }
          } else {
            appendErr("Unsupported item for Saved Messages");
          }
        } catch (e) {
          appendErr(e.message);
        }
        bump();
      }
    }
  }
}

async function fetchAndUploadViaTab(tabId, urls, poolId, savedOnly) {
  const merged = { imported: 0, skipped: 0, errors: [], media_ids: [] };
  const so = !!savedOnly;
  const urlList = urls || [];
  const savedCaption = so ? getAlbumCaptionForSend() : "";
  /** Saved Msgs: one injection with all URLs so capture.js can batch /import/saved-batch (albums). */
  if (so && urlList.length > 0) {
    await chrome.scripting.executeScript({ target: { tabId }, files: ["media-url-guards.js", "capture.js"] });
    const exec = chrome.scripting.executeScript({
      target: { tabId },
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
      const batch = (results && results[0] && results[0].result) || {};
      if (batch.error) merged.errors.push({ error: batch.error, url: "(batch)" });
      merged.imported += batch.imported || 0;
      merged.skipped += batch.skipped || 0;
      (batch.media_ids || []).forEach((id) => merged.media_ids.push(id));
      (batch.errors || []).forEach((e) => merged.errors.push(e));
    } catch (e) {
      merged.errors.push({ error: e.message || String(e), url: "(batch)" });
    }
    return merged;
  }
  for (let u = 0; u < urlList.length; u++) {
    const oneUrl = urlList[u];
    await chrome.scripting.executeScript({ target: { tabId }, files: ["media-url-guards.js", "capture.js"] });
    const exec = chrome.scripting.executeScript({
      target: { tabId },
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
      const batch = (results && results[0] && results[0].result) || {};
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
  const selected = list.filter((i) => selectedUrls.has(i.url));
  if (selected.length === 0) return;
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

  if (savedOnly) {
    await runSendSavedBatchAlbums(selected, poolId, bump, appendErr);
    progressStatus.textContent = "Done: " + done + " / " + total;
    if (progressTitle)
      progressTitle.textContent =
        progressError && progressError.textContent && progressError.textContent.trim()
          ? "Finished with errors"
          : "Done";
    if (btnSend) btnSend.disabled = false;
    updateCountAndSend();
    clearGallerySendTags();
    const hadErrSaved = progressError && progressError.textContent && progressError.textContent.trim();
    if (hadErrSaved) {
      notifyCompletion(
        "Saved Messages finished with errors (" + done + " / " + total + ").",
        "error",
        "notifyOnSendSavedComplete",
        "TBCC Saved Messages"
      );
    } else {
      notifyCompletion(
        "Completed " + done + " / " + total + " (Saved Messages).",
        "success",
        "notifyOnSendSavedComplete",
        "TBCC Saved Messages"
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
            "extension:gallery-crop"
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
      needBytesByTab[it.tabId].push(it.url);
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
      needBytesByTab[it.tabId].push(it.url);
    }
  }
  fromPage.forEach((it) => {
    if (it.url && !/^https?:\/\//i.test(it.url) && it.tabId) {
      needBytesByTab[it.tabId] = needBytesByTab[it.tabId] || [];
      needBytesByTab[it.tabId].push(it.url);
    }
  });

  const urlToItem = new Map(selected.map((i) => [i.url, i]));
  for (const tabIdStr of Object.keys(needBytesByTab)) {
    const tabId = parseInt(tabIdStr, 10);
    let urls = needBytesByTab[tabIdStr].slice();
    if (!urls.length) continue;
    const forTab = [];
    for (const url of urls) {
      const it = urlToItem.get(url);
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
              "extension:gallery-crop-fallback"
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
      const batch = await fetchAndUploadViaTab(tabId, forTab, poolId, savedOnly);
      if (batch.error) appendErr(batch.error);
      if (!savedOnly)
        (batch.media_ids || []).forEach((id, idx) => {
          importedMediaIds.push(id);
          const url = forTab[idx] || forTab[0] || "";
          const it = urlToItem.get(url) || null;
          trackImportedMediaRecord(importedMediaRecords, id, it, tabId, url);
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

  if (!savedOnly && importedMediaIds.length) {
    const useAutoTag = !!(autoTagOnExport && autoTagOnExport.checked);
    if (progressTitle) progressTitle.textContent = useAutoTag ? "Auto-tagging…" : "Applying tags…";
    try {
      if (useAutoTag) await applyAutoTaggingForImportedMedia(importedMediaRecords);
      else await applySendTagsToImportedMedia(importedMediaIds);
    } catch (e) {
      appendErr("Tags: " + (e.message || String(e)));
    }
  }

  if (!savedOnly && forumPostEnabled && forumPostEnabled.checked && forumChannelSelect) {
    const fc = parseInt(forumChannelSelect.value, 10);
    const uniqueIds = [...new Set(importedMediaIds)];
    const mode = (postDestMode && postDestMode.value) || "channel";
    if (fc && uniqueIds.length) {
      telegramPostAttempted = true;
      let threadId = null;
      if (mode === "forum") {
        const ft = forumTopicSelect && forumTopicSelect.value ? parseInt(forumTopicSelect.value, 10) : 0;
        if (!ft) {
          appendErr("Select a forum topic, or set destination to “Channel or group”.");
          telegramPostHadError = true;
        } else {
          threadId = ft;
        }
      }
      if (!(mode === "forum" && !threadId)) {
        if (progressTitle) {
          progressTitle.textContent =
            mode === "forum" ? "Posting to forum topic…" : "Posting to Telegram channel…";
        }
        try {
          const payload = {
            channel_id: fc,
            media_ids: uniqueIds,
            caption: forumAlbumCaption && forumAlbumCaption.value ? forumAlbumCaption.value : "",
            mark_posted: true,
            message_thread_id: mode === "forum" && threadId ? threadId : null,
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
  clearGallerySendTags();
  const hadErr = progressError && progressError.textContent && progressError.textContent.trim();
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
      "TBCC import complete"
    );
  }
  if (telegramPostAttempted && !telegramPostHadError) {
    const mode = (postDestMode && postDestMode.value) || "channel";
    const ch = forumChannelSelect && forumChannelSelect.selectedOptions && forumChannelSelect.selectedOptions[0];
    const channelName = ch ? (ch.textContent || "").trim() : "selected destination";
    const label = mode === "forum" ? "forum topic" : "channel/group";
    notifyCompletion(
      "Telegram post sent to " + label + ": " + channelName,
      "success",
      "notifyOnSendChannelComplete",
      "TBCC Telegram post"
    );
  }
}

/**
 * Destination "Saved Messages only" + section enabled → upload to Telegram Saved Messages only (no pool).
 * Otherwise → import to TBCC pool and optionally post to channel/forum per settings.
 */
function sendToTBCC() {
  const destSaved = postDestMode && postDestMode.value === "saved";
  const postOn = forumPostEnabled && forumPostEnabled.checked;
  if (destSaved && postOn) {
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
  await new Promise((r) => chrome.storage.local.set({ [key]: arr.slice(-500) }, r));
}

btnOpenCaptureSettings &&
  btnOpenCaptureSettings.addEventListener("click", () => {
    if (typeof window.tbccSetPanelView === "function") window.tbccSetPanelView("options");
  });
btnGalleryHelp &&
  btnGalleryHelp.addEventListener("click", () => {
    window.alert(
      "TBCC Gallery shortcuts:\n\nR — Refresh (pools/channels/embeds + rescan when “Full refresh” is on in ⚙ Options)\nO — Preview first selected\nCtrl+S — Send\nEsc — Close preview / quick menu\n\nRight-click in the gallery (below the top nav) for a quick menu: refresh, on-page boxes, select, download, filter, and more.\n\nDouble-click a tile for full-size preview.\n\nTags: open Destination before Send — catalog, create, or Suggest from page; after a pool import they merge as manual tags (saved-only skips tagging).\n\nCapture settings (format, auto-scan, …) are under ⚙ Options."
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
    setTelegramSheetOpen(false);
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
  currentTabId = await resolveTargetTabId();
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
  await Promise.all([loadTagCatalog(), loadPools(), loadChannelsForForum()]);
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
      ],
      (o) => r(o)
    )
  );
  if (forumPostEnabled) forumPostEnabled.checked = !!forumStored.tbccForumPostEnabled;
  if (forumAlbumCaption && typeof forumStored.tbccForumAlbumCaption === "string")
    forumAlbumCaption.value = forumStored.tbccForumAlbumCaption;
  if (autoTagOnExport) autoTagOnExport.checked = forumStored[STORAGE_AUTO_TAG_ON_EXPORT] !== false;
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
    if (telegramSheet && telegramSheet.classList.contains("open") && e.key === "Escape") {
      e.preventDefault();
      setTelegramSheetOpen(false);
      return;
    }
    if (e.key === "?" || (e.shiftKey && e.key === "/")) {
      e.preventDefault();
      window.alert(
        "TBCC Gallery shortcuts:\n\nR — Refresh (full reload when enabled in ⚙ Options)\nO — Preview\nCtrl+S — Send\nEsc — Close overlays / preview\n\nDouble-click a tile for full-size preview.\n\nTags: open Destination — catalog, create, Suggest from page; merges after pool import (not saved-only)."
      );
      return;
    }
    if (e.key === "Escape" && tbccLightbox && tbccLightbox.classList.contains("visible")) {
      e.preventDefault();
      closeLightbox();
      return;
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

