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
const STORAGE_COLLECTED = "tbcc_collected";
const STORAGE_SETTINGS = "tbcc_gallery_settings";
const STORAGE_SELECTION = "tbccSelectionUrls";
const STORAGE_UI_STATE = "tbcc_gallery_ui_state";
/** Comma-free list of tag display names to merge onto media after pool Send */
const STORAGE_SEND_TAGS = "tbccGallerySendTags";
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
  /** Capture: include resource-timing images on non–OnlyFans pages (more URLs). */
  resourceTimingAllImages: false,
  /** Delay before running capture (ms) so lazy images can load; 0 = off. */
  captureLazyDelayMs: 0,
  /** Fold multiple MP4 URLs that look like the same asset (different resolutions) into one tile. */
  foldVideoVariants: true,
  /**
   * When true (default), ↻ / R also reloads pools, channels, forum topics, and embedded iframes
   * (Collected / Tools / Options) before rescanning — same work as closing and reopening the side panel.
   * When false, ↻ only runs a tab rescan (legacy behavior).
   */
  refreshHard: true,
};

const tabCurrentBtn = document.getElementById("tabCurrent");
const tabAllBtn = document.getElementById("tabAll");
const btnRefresh = document.getElementById("btnRefresh");
const btnFilterToggle = document.getElementById("btnFilterToggle");
const filterOverlay = document.getElementById("filterOverlay");
const btnFilterReset = document.getElementById("btnFilterReset");
const btnFilterDone = document.getElementById("btnFilterDone");
const filterType = document.getElementById("filterType");
const filterMinW = document.getElementById("filterMinW");
const filterMinH = document.getElementById("filterMinH");
const filterUrl = document.getElementById("filterUrl");
const selectAllCb = document.getElementById("selectAll");
const selectionChip = document.getElementById("selectionChip");
const btnGalleryHelp = document.getElementById("btnGalleryHelp");
const btnOpenCaptureSettings = document.getElementById("btnOpenCaptureSettings");
const galleryActionBar = document.getElementById("galleryActionBar");
const btnOverflow = document.getElementById("btnOverflow");
const overflowMenu = document.getElementById("overflowMenu");
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
const postDestMode = document.getElementById("postDestMode");
const forumChannelSelect = document.getElementById("forumChannelSelect");
const forumTopicSelect = document.getElementById("forumTopicSelect");
const forumTopicRow = document.getElementById("forumTopicRow");
const forumAlbumCaption = document.getElementById("forumAlbumCaption");
const btnAutoCap = document.getElementById("btnAutoCap");
const forumPostEnabledLabel = document.getElementById("forumPostEnabledLabel");
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
const galleryScanStrip = document.getElementById("galleryScanStrip");
const galleryScanFill = document.getElementById("galleryScanFill");
const galleryScanLabel = document.getElementById("galleryScanLabel");
const btnToggleFoldVariants = document.getElementById("btnToggleFoldVariants");
const btnSelectAll = document.getElementById("btnSelectAll");
const btnDeselect = document.getElementById("btnDeselect");
const tagChipRow = document.getElementById("tagChipRow");
const tagPickInput = document.getElementById("tagPickInput");
const tbccTagDatalist = document.getElementById("tbccTagDatalist");
const btnTagSuggest = document.getElementById("btnTagSuggest");
const btnTagsCatalogReload = document.getElementById("btnTagsCatalogReload");
const tagNewName = document.getElementById("tagNewName");
const tagNewCategory = document.getElementById("tagNewCategory");
const btnTagCreate = document.getElementById("btnTagCreate");
const btnTagsClear = document.getElementById("btnTagsClear");

let tagCatalog = [];
/** Ordered display names for tags applied on next pool Send */
let gallerySendTags = [];

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
  const list = getFilteredList();
  let n = 0;
  for (const i of list) {
    if (selectedUrls.has(i.url)) n++;
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
  if (tagPickInput) tagPickInput.value = "";
  if (tagNewName) tagNewName.value = "";
  if (tagNewCategory) tagNewCategory.value = "";
}

function looksLikeBareDomain(s) {
  return /^[\w.-]+\.[a-z]{2,}$/i.test(String(s).trim()) && !String(s).includes(" ");
}

async function loadTagCatalog() {
  try {
    const r = await fetch(`${API_BASE}/tags`);
    if (!r.ok) throw new Error(await r.text());
    tagCatalog = await r.json();
    if (tbccTagDatalist) {
      tbccTagDatalist.innerHTML = "";
      for (const t of tagCatalog) {
        const o = document.createElement("option");
        o.value = t.name;
        tbccTagDatalist.appendChild(o);
      }
    }
  } catch (e) {
    console.warn("TBCC loadTagCatalog:", e);
  }
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

function addPickedCatalogTag() {
  const v = tagPickInput && tagPickInput.value.trim();
  if (!v) return;
  const low = v.toLowerCase();
  const row = tagCatalog.find((t) => {
    const n = (t.name && String(t.name).toLowerCase()) || "";
    const s = (t.slug && String(t.slug).toLowerCase()) || "";
    return n === low || (s && s === low);
  });
  addGallerySendTag(row ? row.name : v);
  tagPickInput.value = "";
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

async function notifyOverlayRefresh() {
  const tid = await resolveTargetTabId();
  if (!tid) return;
  chrome.tabs.sendMessage(tid, { action: "tbcc-overlay-refresh" }).catch(() => {});
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
  if (Number.isNaN(minW) && Number.isNaN(minH)) return;
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
  return list;
}

/**
 * Extra capture passes so late resource-timing / webRequest URLs appear without manual refresh.
 * Shorter gaps feel much snappier; stagnant passes still exit early when two runs add nothing.
 */
const SCAN_MERGE_DELAYS_MS = [0, 400, 1000];

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
  return { tabId, list: deduped.map((i) => ({ ...i, tabId })) };
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

function applySelectionFromStorage(storedSel) {
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
  if (activeTab === "current") {
    for (const u of storedSel) {
      if (urlsInList.has(u) || !/^https?:\/\//i.test(u)) continue;
      const mt = guessMediaType(u);
      imageList.push({
        url: u,
        mediaType: mt,
        tagName: mt === "video" ? "video" : "img",
        tabId: currentTabId,
      });
      urlsInList.add(u);
      selectedUrls.add(u);
    }
  }
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
  const { [STORAGE_SELECTION]: storedArr = [] } = await chrome.storage.local.get(STORAGE_SELECTION);
  const storedSel = new Set(Array.isArray(storedArr) ? storedArr : []);
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
    applySelectionFromStorage(storedSel);
    await persistSelection();

    if (activeTab === "current" && currentTabId != null) {
      setScanStripVisible(true);
      setScanProgress(0.28, "Scanning…");
      showLoading(false);
      renderGrid();
      await notifyOverlayRefresh();
      let stagnantPass = 0;
      for (let p = 0; p < SCAN_MERGE_DELAYS_MS.length; p++) {
        setScanProgress(0.28 + ((p + 1) / SCAN_MERGE_DELAYS_MS.length) * 0.68, "Scanning…");
        await new Promise((r) => setTimeout(r, SCAN_MERGE_DELAYS_MS[p]));
        const before = imageList.length;
        const merged = await appendMergedCapture(currentTabId);
        if (merged > 0) {
          applySelectionFromStorage(storedSel);
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
      return;
    }
  } finally {
    showLoading(false);
    if (!scanStripHandled) setScanStripVisible(false);
  }
  renderGrid();
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
  if (/\.mp4(\?|$)/i.test(ulow)) return "MP4";
  if (/\.webm(\?|$)/i.test(ulow)) return "WEBM";
  if (/\.webp(\?|$)/i.test(ulow)) return "WEBP";
  if (/\.png(\?|$)/i.test(ulow)) return "PNG";
  if (/\.(jpe?g)(\?|$)/i.test(ulow)) return "JPG";
  if (/\.gif(\?|$)/i.test(ulow)) return "GIF";
  if (isVideo) return "VIDEO";
  return "Media";
}

/** Poster + seek first frame so tiles are not a blank grey gradient when the player starts at t=0 black. */
function appendVideoMediaToCell(div, item, dimsEl) {
  const wrap = document.createElement("div");
  wrap.className = "cell-media-wrap";
  let posterEl = null;
  if (item.posterUrl && /^https?:\/\//i.test(item.posterUrl)) {
    posterEl = document.createElement("img");
    posterEl.className = "cell-video-poster";
    posterEl.alt = "";
    posterEl.loading = "lazy";
    posterEl.decoding = "async";
    posterEl.src = item.posterUrl;
    posterEl.onerror = () => {
      try {
        posterEl.remove();
      } catch (_) {}
      posterEl = null;
    };
    wrap.appendChild(posterEl);
  }
  const v = document.createElement("video");
  v.className = "cell-media cell-video";
  v.src = item.url;
  v.muted = true;
  v.playsInline = true;
  v.preload = "metadata";
  v.setAttribute("playsinline", "");
  v.onerror = () => {
    if (!wrap.querySelector(".placeholder")) {
      const ph = document.createElement("div");
      ph.className = "placeholder";
      ph.textContent = "Video";
      wrap.appendChild(ph);
    }
    try {
      v.remove();
    } catch (_) {}
  };
  const markReady = () => {
    v.classList.add("tbcc-thumb-ready");
    dimsEl.textContent = formatVideoCellLabel(item, v);
    try {
      if (v.videoWidth > 0 && v.videoHeight > 0) {
        item.naturalWidth = v.videoWidth;
        item.naturalHeight = v.videoHeight;
        item.width = item.width || v.videoWidth;
        item.height = item.height || v.videoHeight;
      }
    } catch (_) {}
    scheduleFilterRerenderFromLazyDims();
  };
  v.addEventListener(
    "loadedmetadata",
    () => {
      try {
        const dur = v.duration;
        if (typeof dur === "number" && isFinite(dur) && dur > 0.08) v.currentTime = Math.min(0.08, dur * 0.02);
        else v.currentTime = 0.02;
      } catch (_) {
        markReady();
      }
    },
    { once: true }
  );
  v.addEventListener("seeked", markReady, { once: true });
  v.addEventListener("loadeddata", () => {
    if (!v.classList.contains("tbcc-thumb-ready")) {
      try {
        v.currentTime = 0.06;
      } catch (_) {
        markReady();
      }
    }
  });
  wrap.appendChild(v);
  div.appendChild(wrap);
}

function renderGrid() {
  if (!gridEl) return;
  cancelPendingFilterDimRerender();
  pruneVideoGroupPick();
  const list = getFilteredList();
  const displayRows = getDisplayRows();
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
      const play = document.createElement("div");
      play.className = "cell-play";
      play.textContent = "▶";
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
      img.referrerPolicy = "no-referrer";
      img.src = item.url;
      img.onload = () => {
        if (img.naturalWidth && img.naturalHeight) {
          dimsEl.textContent = `${img.naturalWidth}×${img.naturalHeight}`;
          item.naturalWidth = img.naturalWidth;
          item.naturalHeight = img.naturalHeight;
          item.width = item.width || img.naturalWidth;
          item.height = item.height || img.naturalHeight;
          scheduleFilterRerenderFromLazyDims();
        }
      };
      img.onerror = () => {
        const ph = document.createElement("div");
        ph.className = "placeholder";
        ph.textContent = "—";
        div.appendChild(ph);
        img.remove();
      };
      div.appendChild(img);
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
    div.appendChild(dimsEl);
    div.addEventListener("click", (e) => {
      if (e.target === cb || (cb && cb.contains && cb.contains(e.target))) return;
      if (e.target.closest && e.target.closest(".cell-variant-row")) return;
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
  const list = getFilteredList();
  const selInView = selectedCountInFilteredList();
  if (selectionChip) selectionChip.textContent = selInView + " / " + list.length + " selected";
  if (btnSend) btnSend.disabled = selInView === 0;
  if (btnDownload) btnDownload.disabled = selInView === 0;
  if (btnDownloadZip) btnDownloadZip.disabled = selInView === 0;
  if (btnCopyJd) btnCopyJd.disabled = selInView === 0;
  if (btnSelectAll) btnSelectAll.disabled = list.length === 0 || selInView === list.length;
  if (btnDeselect) btnDeselect.disabled = selInView === 0;
  updateSendButtonLabel();
  updateForumCheckboxLabel();
  updateActionBarVisibility();
  updateActionBarSubtitle();
  persistSelection();
}

function filenameFromUrl(url) {
  try {
    const u = new URL(url);
    const seg = u.pathname.split("/").filter(Boolean).pop() || "media";
    return seg.split("?")[0].replace(/[^\w.\-]+/g, "_") || "media";
  } catch (_) {
    return "media";
  }
}

function shouldApplyBottomCrop() {
  return !!settings.cropBottomEnabled && Number(settings.cropBottomPercent) > 0;
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

async function fetchUrlBytesToBlob(url) {
  url = normalizeTbccMediaUrlForImport(url);
  try {
    const r = await fetch(url, { credentials: "omit", mode: "cors" });
    if (r.ok) return await r.blob();
  } catch (_) {}
  return new Promise((resolve) => {
    chrome.runtime.sendMessage({ action: "tbcc-content-fetch-bytes", url }, (res) => {
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
async function getBlobAndNameForZipItem(it, idx) {
  const n = idx + 1;
  const pad = String(n).padStart(3, "0");
  if (it.file) {
    const raw = (it.name || "file").replace(/[^\w.\-]+/g, "_");
    const safe = raw || "file";
    return { filename: pad + "_" + safe, blob: it.file };
  }
  if (it.url && it.url.startsWith("blob:")) {
    const r = await fetch(it.url);
    const blob = await r.blob();
    return { filename: pad + "_media", blob };
  }
  if (it.url && (it.url.startsWith("http://") || it.url.startsWith("https://"))) {
    if (
      typeof tbccIsLikelyHtmlPageUrl === "function" &&
      (it.mediaType === "video" || String(it.tagName || "").toLowerCase() === "video") &&
      tbccIsLikelyHtmlPageUrl(it.url)
    ) {
      throw new Error(
        "URL looks like a video page (HTML), not a direct file — use a resolved stream URL or another downloader."
      );
    }
    const url = normalizeTbccMediaUrlForImport(it.url);
    const blob = await fetchUrlBytesToBlob(url);
    if (!blob) throw new Error("Could not fetch: " + String(it.url).slice(0, 96));
    const base = filenameFromUrl(it.url);
    const ext = it.mediaType === "video" || String(it.tagName || "").toLowerCase() === "video" ? ".mp4" : "";
    const hasExt = /\.\w{2,5}$/i.test(base);
    const filename = pad + "_" + (hasExt ? base : base + ext);
    return { filename: filename.replace(/[^\w.\-]+/g, "_"), blob };
  }
  throw new Error("Unsupported item for ZIP");
}

async function cropBottomStripFromBlob(blob) {
  if (!shouldApplyBottomCrop()) return blob;
  const pct = Math.min(50, Math.max(0, Number(settings.cropBottomPercent) || 0));
  if (pct <= 0) return blob;
  const frac = pct / 100;
  try {
    const bmp = await createImageBitmap(blob);
    try {
      const w = bmp.width;
      const h = bmp.height;
      const keepH = Math.max(1, Math.floor(h * (1 - frac)));
      const canvas = document.createElement("canvas");
      canvas.width = w;
      canvas.height = keepH;
      const ctx = canvas.getContext("2d");
      ctx.drawImage(bmp, 0, 0, w, keepH, 0, 0, w, keepH);
      const out = await new Promise((res) => canvas.toBlob((b) => res(b), "image/jpeg", 0.92));
      return out || blob;
    } finally {
      bmp.close();
    }
  } catch (_) {
    return blob;
  }
}

function syncCropUiFromSettings() {
  if (cropBottomEnabled) cropBottomEnabled.checked = !!settings.cropBottomEnabled;
  if (cropBottomPercent) {
    const v = Math.max(0, Math.min(50, Number(settings.cropBottomPercent) || 8));
    cropBottomPercent.value = String(v);
  }
}

function persistCropSettings() {
  settings.cropBottomEnabled = !!(cropBottomEnabled && cropBottomEnabled.checked);
  let v = cropBottomPercent ? parseInt(cropBottomPercent.value, 10) : 8;
  if (isNaN(v)) v = 8;
  settings.cropBottomPercent = Math.max(0, Math.min(50, v));
  if (cropBottomPercent) cropBottomPercent.value = String(settings.cropBottomPercent);
  chrome.storage.local.set({ [STORAGE_SETTINGS]: settings });
}

function syncFoldToggleLabel() {
  if (!btnToggleFoldVariants) return;
  btnToggleFoldVariants.textContent = settings.foldVideoVariants ? "Fold video variants ✓" : "Fold video variants";
}

function saveGalleryUiState() {
  const payload = {
    filterType: filterType ? filterType.value : "",
    filterMinW: filterMinW ? filterMinW.value : "",
    filterMinH: filterMinH ? filterMinH.value : "",
    filterUrl: filterUrl ? filterUrl.value : "",
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

function closeLightbox() {
  if (!tbccLightbox) return;
  tbccLightbox.classList.remove("visible");
  if (tbccLightboxVideo) {
    tbccLightboxVideo.pause();
    tbccLightboxVideo.removeAttribute("src");
  }
  if (tbccLightboxImg) tbccLightboxImg.removeAttribute("src");
}

function openLightboxForItem(item) {
  if (!item || !tbccLightbox) return;
  const u = String(item.url || "");
  const isVideo =
    (item.mediaType || item.tagName || "").toLowerCase() === "video" ||
    /\.(mp4|webm|m3u8|mpd)(\?|$)/i.test(u) ||
    (item.file && item.file.type && item.file.type.startsWith("video/"));
  if (tbccLightboxImg) tbccLightboxImg.style.display = "none";
  if (tbccLightboxVideo) tbccLightboxVideo.style.display = "none";
  if (isVideo && tbccLightboxVideo) {
    tbccLightboxVideo.src = u;
    tbccLightboxVideo.style.display = "block";
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
  filterOverlay.classList.toggle("visible", !!open);
  filterOverlay.setAttribute("aria-hidden", open ? "false" : "true");
}

function resetFilterFields() {
  if (filterType) filterType.value = "";
  if (filterMinW) filterMinW.value = "";
  if (filterMinH) filterMinH.value = "";
  if (filterUrl) filterUrl.value = "";
  saveGalleryUiState();
  renderGrid();
}

function setCropPopoverOpen(open) {
  if (!cropPopover) return;
  cropPopover.classList.toggle("visible", !!open);
  cropPopover.setAttribute("aria-hidden", open ? "false" : "true");
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
    if (progressStatus)
      progressStatus.textContent = "Saved ZIP with " + ok + " file(s) to Downloads/tbcc/ (use for digital bundle upload).";
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
    .map((i) => i.url)
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
        const blobUrl = URL.createObjectURL(it.file);
        const name = (it.name || "file").replace(/[^\w.\-]+/g, "_");
        await new Promise((resolve) => {
          chrome.downloads.download({ url: blobUrl, filename: "tbcc/" + name, saveAs: false }, () => {
            URL.revokeObjectURL(blobUrl);
            resolve();
          });
        });
      } else if (it.url && (it.url.startsWith("http://") || it.url.startsWith("https://"))) {
        if (
          typeof tbccIsLikelyHtmlPageUrl === "function" &&
          (it.mediaType === "video" || String(it.tagName || "").toLowerCase() === "video") &&
          tbccIsLikelyHtmlPageUrl(it.url)
        ) {
          throw new Error(
            "That URL is a page (HTML), not a video file. The extension needs a direct .mp4 (or similar) link — or use JDownloader / your backend to resolve the stream."
          );
        }
        const base = filenameFromUrl(it.url);
        const ext = it.mediaType === "video" || (it.tagName || "").toLowerCase() === "video" ? ".mp4" : "";
        const hasExt = /\.\w{2,5}$/i.test(base);
        const filename = "tbcc/" + idx + "_" + (hasExt ? base : base + ext);
        await new Promise((resolve, reject) => {
          chrome.downloads.download({ url: it.url, filename, saveAs: false }, () => {
            if (chrome.runtime.lastError) reject(new Error(chrome.runtime.lastError.message));
            else resolve();
          });
        });
      } else if (it.url && it.url.startsWith("blob:")) {
        await new Promise((resolve) => {
          chrome.downloads.download({ url: it.url, filename: "tbcc/" + idx + "_media", saveAs: false }, resolve);
        });
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
    }
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

[filterType, filterMinW, filterMinH, filterUrl].forEach((el) => {
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
  tabCurrentBtn.addEventListener("click", () => {
    activeTab = "current";
    tabCurrentBtn.classList.add("active");
    tabAllBtn && tabAllBtn.classList.remove("active");
    saveGalleryUiState();
    doRefresh();
  });
tabAllBtn &&
  tabAllBtn.addEventListener("click", () => {
    activeTab = "all";
    tabAllBtn.classList.add("active");
    tabCurrentBtn && tabCurrentBtn.classList.remove("active");
    saveGalleryUiState();
    doRefresh();
  });

btnRefresh && btnRefresh.addEventListener("click", () => refreshPanelOrHardScan());

btnSelectAll &&
  btnSelectAll.addEventListener("click", () => {
    const list = getFilteredList();
    list.forEach((i) => selectedUrls.add(i.url));
    renderGrid();
    updateCountAndSend();
  });

btnDeselect &&
  btnDeselect.addEventListener("click", () => {
    selectedUrls.clear();
    lastSelectionAnchorIndex = 0;
    renderGrid();
    updateCountAndSend();
  });

tagPickInput &&
  tagPickInput.addEventListener("change", () => {
    addPickedCatalogTag();
  });
tagPickInput &&
  tagPickInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      addPickedCatalogTag();
    }
  });
btnTagSuggest && btnTagSuggest.addEventListener("click", () => void suggestTagsFromPage());
btnTagsCatalogReload && btnTagsCatalogReload.addEventListener("click", () => void loadTagCatalog());
btnTagCreate && btnTagCreate.addEventListener("click", () => void createTagOnServer());
btnTagsClear && btnTagsClear.addEventListener("click", () => clearGallerySendTags());

fileInput && fileInput.addEventListener("change", () => {
  if (fileInput.files && fileInput.files.length) addLocalFiles(fileInput.files);
  fileInput.value = "";
});

poolSelect && poolSelect.addEventListener("change", () => { if (poolSelect.value) chrome.storage.local.set({ tbccPoolId: parseInt(poolSelect.value, 10) }); });

forumPostEnabled &&
  forumPostEnabled.addEventListener("change", async () => {
    await chrome.storage.local.set({ tbccForumPostEnabled: !!forumPostEnabled.checked });
    updateTelegramPostControls();
    if (forumPostEnabled.checked && forumChannelSelect && forumChannelSelect.value && postDestMode && postDestMode.value === "forum")
      await loadForumTopics(parseInt(forumChannelSelect.value, 10));
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
      h.endsWith(".fapello.com")
    );
  } catch (_) {
    return false;
  }
}

/** Fetch image bytes using Chrome cookie jar + Referer (same idea as a logged-in tab). */
async function importUrlViaExtensionSession(url, poolId, savedOnly) {
  url = normalizeTbccMediaUrlForImport(url);
  return new Promise((resolve) => {
    chrome.runtime.sendMessage(
      {
        action: "tbcc-import-bytes-session",
        url,
        poolId,
        savedOnly: !!savedOnly,
        source: "extension:gallery-session",
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
          if (shouldApplyBottomCrop() && isImageItem(it)) {
            try {
              const raw = new Blob([await it.file.arrayBuffer()], {
                type: it.file.type || "application/octet-stream",
              });
              const cropped = await cropBottomStripFromBlob(raw);
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
      if (!shouldApplyBottomCrop()) {
        for (let start = 0; start < g.items.length; start += SAVED_URL_BATCH_MAX) {
          const slice = g.items.slice(start, start + SAVED_URL_BATCH_MAX);
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
              for (const it of slice) {
                await addToCollected({ url: it.url, type: "image", addedAt: Date.now(), to_saved: true });
                bump();
              }
            } else {
              appendErr(data.error || "Saved batch (URLs) failed");
              slice.forEach(() => bump());
            }
          } catch (e) {
            appendErr(e.message);
            slice.forEach(() => bump());
          }
        }
      } else {
        for (let start = 0; start < g.items.length; start += SAVED_URL_BATCH_MAX) {
          const slice = g.items.slice(start, start + SAVED_URL_BATCH_MAX);
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
            if (isImageItem(it)) {
              try {
                const raw = await fetchUrlBytesToBlob(it.url);
                if (raw && raw.size > 0) {
                  const cropped = await cropBottomStripFromBlob(raw);
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
      if (!shouldApplyBottomCrop()) {
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
              const raw = await fetchUrlBytesToBlob(it.url);
              if (!raw || !raw.size) throw new Error("fetch bytes");
              const cropped = await cropBottomStripFromBlob(raw);
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
            if (shouldApplyBottomCrop() && isImageItem(it)) {
              try {
                blob = await cropBottomStripFromBlob(blob);
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
    if (hadErrSaved) showToast("Some items failed — see progress details.", "error");
    else showToast("Completed " + done + " / " + total + " (Saved Messages).", "success");
    return;
  }

  const withFile = selected.filter((i) => i.file);
  const fromPage = selected.filter((i) => !i.file && i.tabId);

  for (const it of withFile) {
    let uploadBlob = it.file;
    let uploadName = it.name || "media";
    if (shouldApplyBottomCrop() && isImageItem(it)) {
      try {
        const raw = new Blob([await it.file.arrayBuffer()], { type: it.file.type || "application/octet-stream" });
        const cropped = await cropBottomStripFromBlob(raw);
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
    if (shouldApplyBottomCrop() && isImageItem(it)) {
      try {
        const raw = await fetchUrlBytesToBlob(it.url);
        if (raw && raw.size > 0) {
          const cropped = await cropBottomStripFromBlob(raw);
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
        const data = await importUrlViaExtensionSession(it.url, poolId, savedOnly);
        const ok =
          (data.status === "imported" || data.status === "skipped" || data.status === "saved_only") && !data.error;
        if (ok) {
          if (savedOnly && data.status === "saved_only")
            await addToCollected({ url: it.url, type: "image", addedAt: Date.now(), to_saved: true });
          else if (!savedOnly && data.media_id)
            await addToCollected({ url: it.url, type: "image", addedAt: Date.now(), media_id: data.media_id });
          if (!savedOnly && data.media_id) importedMediaIds.push(data.media_id);
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
    const data = await importOneUrl(it.url, poolId, savedOnly);
    const ok =
      (data.status === "imported" || data.status === "skipped" || data.status === "saved_only") && !data.error;
    if (ok) {
      if (savedOnly && data.status === "saved_only")
        await addToCollected({ url: it.url, type: "image", addedAt: Date.now(), to_saved: true });
      else if (!savedOnly && data.media_id) {
        importedMediaIds.push(data.media_id);
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
      if (shouldApplyBottomCrop() && it && isImageItem(it)) {
        try {
          const raw = await fetchUrlBytesToBlob(url);
          if (raw && raw.size > 0) {
            const cropped = await cropBottomStripFromBlob(raw);
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
          const data = await importUrlViaExtensionSession(url, poolId, savedOnly);
          const ok =
            (data.status === "imported" || data.status === "skipped" || data.status === "saved_only") &&
            !data.error;
          if (ok) {
            if (savedOnly && data.status === "saved_only")
              await addToCollected({ url, type: "image", addedAt: Date.now(), to_saved: true });
            else if (!savedOnly && data.media_id) {
              importedMediaIds.push(data.media_id);
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
      if (!savedOnly) (batch.media_ids || []).forEach((id) => importedMediaIds.push(id));
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
    const csv = getSendTagsCsv().trim();
    if (csv) {
      if (progressTitle) progressTitle.textContent = "Applying tags…";
      try {
        await applySendTagsToImportedMedia(importedMediaIds);
      } catch (e) {
        appendErr("Tags: " + (e.message || String(e)));
      }
    }
  }

  if (!savedOnly && forumPostEnabled && forumPostEnabled.checked && forumChannelSelect) {
    const fc = parseInt(forumChannelSelect.value, 10);
    const uniqueIds = [...new Set(importedMediaIds)];
    const mode = (postDestMode && postDestMode.value) || "channel";
    if (fc && uniqueIds.length) {
      let threadId = null;
      if (mode === "forum") {
        const ft = forumTopicSelect && forumTopicSelect.value ? parseInt(forumTopicSelect.value, 10) : 0;
        if (!ft) {
          appendErr("Select a forum topic, or set destination to “Channel or group”.");
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
          else if (j.errors && j.errors.length) appendErr(j.errors.join("; "));
          else if (j.ok === false && j.sent_chunks === 0) appendErr("Telegram post returned no chunks sent");
        } catch (e) {
          appendErr(e.message || String(e));
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
  if (hadErr) showToast("Some items failed — see progress details.", "error");
  else showToast("Completed " + done + " / " + total + " item(s).", "success");
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
      "TBCC Gallery shortcuts:\n\nR — Refresh (pools/channels/embeds + rescan when “Full refresh” is on in ⚙ Options)\nO — Preview first selected\nCtrl+S — Send\nEsc — Close preview\n\nDouble-click a tile for full-size preview.\n\nTags: open Destination before Send — catalog, create, or Suggest from page; after a pool import they merge as manual tags (saved-only skips tagging).\n\nCapture settings (format, auto-scan, …) are under ⚙ Options."
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
const overflowWrapEl = document.querySelector(".overflow-wrap");
overflowWrapEl &&
  overflowWrapEl.addEventListener("click", (e) => {
    e.stopPropagation();
  });
btnOverflow &&
  btnOverflow.addEventListener("click", (e) => {
    e.stopPropagation();
    if (overflowMenu) overflowMenu.classList.toggle("visible");
  });
document.addEventListener("click", () => {
  if (overflowMenu) overflowMenu.classList.remove("visible");
});
btnCropOverflow &&
  btnCropOverflow.addEventListener("click", (e) => {
    e.stopPropagation();
    if (overflowMenu) overflowMenu.classList.remove("visible");
    syncCropUiFromSettings();
    setCropPopoverOpen(true);
  });
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
    if (overflowMenu) overflowMenu.classList.remove("visible");
    if (fileInput) fileInput.click();
  });
btnToggleFoldVariants &&
  btnToggleFoldVariants.addEventListener("click", (e) => {
    e.stopPropagation();
    if (overflowMenu) overflowMenu.classList.remove("visible");
    settings.foldVideoVariants = !settings.foldVideoVariants;
    chrome.storage.local.set({ [STORAGE_SETTINGS]: settings });
    syncFoldToggleLabel();
    renderGrid();
  });
cropBottomEnabled && cropBottomEnabled.addEventListener("change", () => persistCropSettings());
cropBottomPercent && cropBottomPercent.addEventListener("change", () => persistCropSettings());

(async function init() {
  const initStarted = Date.now();
  const s = await new Promise((r) => chrome.storage.local.get(STORAGE_SETTINGS, (o) => r(o[STORAGE_SETTINGS])));
  if (s) {
    settings = { ...settings, ...s };
    if (settings.cropBottomPercent != null && typeof settings.cropBottomPercent !== "number") {
      const n = parseInt(String(settings.cropBottomPercent), 10);
      settings.cropBottomPercent = isNaN(n) ? 8 : Math.max(0, Math.min(50, n));
    }
    if (typeof settings.cropBottomEnabled !== "boolean") settings.cropBottomEnabled = !!settings.cropBottomEnabled;
    if (typeof settings.foldVideoVariants !== "boolean") settings.foldVideoVariants = true;
  }
  syncCropUiFromSettings();
  syncFoldToggleLabel();
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
      ],
      (o) => r(o)
    )
  );
  if (forumPostEnabled) forumPostEnabled.checked = !!forumStored.tbccForumPostEnabled;
  if (forumAlbumCaption && typeof forumStored.tbccForumAlbumCaption === "string")
    forumAlbumCaption.value = forumStored.tbccForumAlbumCaption;
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
  overflowMenu && overflowMenu.addEventListener("click", (e) => e.stopPropagation());
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
  window.addEventListener("resize", () => { if (imageList.length) renderGrid(); });
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
