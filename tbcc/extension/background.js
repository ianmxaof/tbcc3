importScripts(
  "tbcc-api-client.js",
  "tbcc-username-filter.js",
  "model-search-shared.js",
  "username-search-history-shared.js",
  "auto-tag-utils.js",
  "media-url-guards.js",
  "tbcc-master-archive.js",
  "tbcc-import-pipeline.js",
  "tbcc-webp-convert.js",
  "tbcc-extension-modules.js",
  "launch-full-stack.js",
  "severity-toast-colors.js",
  "tbcc-zip-naming.js",
  "tbcc-promo-watermark.js",
  "tbcc-download-router.js"
);

const SAVED_ALBUM_CHUNK = 10;
/** Match capture.js: overlap session fetches before sequential /import/saved-batch POSTs. */
const TBCC_FETCH_CONCURRENCY = 3;

/**
 * Run fetchFn(url, idx) for each URL with at most TBCC_FETCH_CONCURRENCY in flight; results match urls order.
 */
async function fetchUrlsWithConcurrency(urls, fetchFn, maxConcurrency) {
  const n = urls.length;
  if (n === 0) return [];
  const results = new Array(n);
  let nextIndex = 0;
  async function worker() {
    while (true) {
      const idx = nextIndex++;
      if (idx >= n) return;
      results[idx] = await fetchFn(urls[idx], idx);
    }
  }
  const cap =
    maxConcurrency != null && Number.isFinite(Number(maxConcurrency))
      ? Number(maxConcurrency)
      : fetchConcurrencyForUrls(urls);
  const w = Math.min(Math.max(1, cap), n);
  await Promise.all(Array.from({ length: w }, () => worker()));
  return results;
}
const STORAGE_LAST_TAB = "tbccLastActiveTabId";
/** Gallery pinned to a tab — side panel keeps sourcing that tab while you browse elsewhere. */
const STORAGE_GALLERY_DOCKED_TAB = "tbccGalleryDockedTab";
/** Active long-running gallery work (survives panel close only when backed by service worker / API). */
const STORAGE_GALLERY_JOBS = "tbccGalleryActiveJobs";
/** Set when user leaves the docked tab while jobs run — blocks opening side panel until jobs finish. */
const STORAGE_GALLERY_DOCK_LOCK = "tbccGalleryDockPanelLock";
const TBCC_GALLERY_JOB_MAX_AGE_MS = 2 * 60 * 60 * 1000;
const STORAGE_IMPORT_QUEUE_PAUSED = "tbccImportQueuePaused";
const TBCC_IMPORT_POLL_ALARM_PREFIX = "tbcc-ipoll:";
const TBCC_IMPORT_POLL_DELAY_MIN = 0.12;
const STORAGE_COLLECTED = "tbcc_collected";
const STORAGE_MODEL_SEARCH_ENABLED = "tbccModelSearchEnabledSites";
const STORAGE_MODEL_SEARCH_MODE = "tbccModelSearchOpenMode";
const STORAGE_LAST_COPIED_USERNAME = "tbccLastCopiedUsername";
const STORAGE_PAGE_MENU_ITEMS = "tbccPageMenuItems";
const TBCC_CTX_MENU_SYNC_ALARM = "tbcc-ctx-menu-sync";
const STORAGE_AOF_POOLS = "tbccAofPoolsCache";
const STORAGE_STORAGE_HUB_TOPICS = "tbccStorageHubTopicsCache";
/** Offline fallback — keep in sync with aof_storage_hub_map.AOF_STORAGE_TOPIC_MAP */
const TBCC_STORAGE_HUB_TOPICS_FALLBACK = [
  { network_key: "abg", message_thread_id: 3387, short_label: "ABG/LBFM", menu_label: "🥡 ABG/LBFM" },
  { network_key: "ai", message_thread_id: 5978, short_label: "AI", menu_label: "🤖 AI" },
  { network_key: "ass", message_thread_id: 3779, short_label: "ASS", menu_label: "🍑 ASS" },
  { network_key: "big_tits", message_thread_id: 5752, short_label: "BIG TITS", menu_label: "🍒 BIG TITS" },
  { network_key: "blowjob", message_thread_id: 9505, short_label: "BLOWJOB", menu_label: "💋 BLOWJOB" },
  { network_key: "bop", message_thread_id: 9501, short_label: "BOP", menu_label: "🤠 BOP" },
  { network_key: "full_length", message_thread_id: 11281, short_label: "FULL LENGTH", menu_label: "🎬 FULL LENGTH" },
  { network_key: "goon", message_thread_id: 2934, short_label: "GOON", menu_label: "🤡 GOON" },
  { network_key: "milf", message_thread_id: 5972, short_label: "MILF/GILF", menu_label: "🧜‍♀️ MILF/GILF" },
  { network_key: "packs", message_thread_id: 5980, short_label: "PACKS", menu_label: "📦 PACKS" },
  { network_key: "taboo", message_thread_id: 2919, short_label: "TABOO 18+", menu_label: "🔞 TABOO 18+" },
  { network_key: "voyeur", message_thread_id: 3058, short_label: "PUBLIC / VOYEUR", menu_label: "👀 PUBLIC / VOYEUR" },
];
const STORAGE_MODEL_SEARCH_HISTORY = "tbccModelSearchHistory";
/** Per-source hit/miss tallies from macro probes. */
const STORAGE_MODEL_SEARCH_SITE_STATS = "tbccModelSearchSiteStats";
/** Session: tbccLazyTabUrl_<tabId> → URL loaded on first focus. */
const LAZY_TAB_URL_PREFIX = "tbccLazyTabUrl_";
const STORAGE_PAYMENT_BOT_USERNAME = "tbccPaymentBotUsername";
const STORAGE_MACRO_SEARCH_BOT_USERNAME = "tbccMacroSearchBotUsername";
const STORAGE_REVERSE_IMAGE_ENABLED = "tbccReverseImageEnabledSites";
const STORAGE_REVERSE_IMAGE_MODE = "tbccReverseImageOpenMode";
const STORAGE_MODEL_SEARCH_LAST_SUMMARY = "tbccModelSearchLastSummary";
const STORAGE_AUTO_TAG_ON_EXPORT = "tbccAutoTagOnExport";
/** Saved from context menu — watch pages or direct media URLs (extension Options). */
const STORAGE_SAVED_VIDEO_URLS = "tbccSavedVideoUrls";
const STORAGE_DOWNLOAD_ROUTES = "tbccDownloadRoutes";
const STORAGE_DOWNLOAD_ROUTING_SETTINGS = "tbccDownloadRoutingSettings";
const TBCC_SAVED_VIDEO_URLS_CAP = 600;
let tbccRedgifsTempToken = "";
let tbccRedgifsTempTokenExpiresAt = 0;

const TBCC_AUTOTAG_STOPWORDS = new Set([
  "www",
  "com",
  "net",
  "org",
  "image",
  "images",
  "video",
  "videos",
  "media",
  "thumb",
  "thumbnail",
  "photo",
  "post",
  "posts",
]);

/**
 * Fan out username search across enabled sites (config JSON + options).
 * Modes: foreground (first tab active), background (all inactive). Legacy "dashboard" is treated as foreground.
 */
async function loadReverseImageConfig() {
  const r = await fetch(chrome.runtime.getURL("reverse-image-sites.json"));
  if (!r.ok) throw new Error("reverse-image-sites.json");
  return r.json();
}

function buildReverseEngineUrl(template, imageUrl) {
  return template.split("{imageUrl}").join(encodeURIComponent(imageUrl));
}

/**
 * Public http(s) image URL → multi-engine reverse search (config + options).
 * Fan-out opens one tab per engine (foreground or background).
 */
async function launchReverseImageSearch(imageUrl) {
  imageUrl = normalizeTbccMediaUrlForImport((imageUrl || "").trim()) || (imageUrl || "").trim();
  if (!imageUrl) {
    notify("TBCC", "No image URL for reverse search.");
    return;
  }
  if (!/^https?:\/\//i.test(imageUrl)) {
    notify("TBCC", "Reverse image search needs an http(s) URL.");
    return;
  }
  if (imageUrl.startsWith("blob:") || imageUrl.startsWith("data:")) {
    notify(
      "TBCC",
      "Blob/data URLs cannot be sent to search engines. Save or open a hosted image URL first."
    );
    return;
  }
  let cfg;
  try {
    cfg = await loadReverseImageConfig();
  } catch (_) {
    notify("TBCC", "Reverse image: missing or invalid reverse-image-sites.json.");
    return;
  }
  const data = await chrome.storage.local.get([STORAGE_REVERSE_IMAGE_ENABLED, STORAGE_REVERSE_IMAGE_MODE]);
  const enabled = data[STORAGE_REVERSE_IMAGE_ENABLED] || {};
  const sites = (cfg.sites || []).filter((s) => enabled[s.id] !== false);
  if (!sites.length) {
    notify("TBCC", "No reverse-image sources enabled — open extension Options.");
    return;
  }
  let mode = data[STORAGE_REVERSE_IMAGE_MODE] || "foreground";
  if (mode === "dashboard") mode = "foreground";
  const wantActive = mode === "foreground";
  let first = true;
  for (const s of sites) {
    const u = buildReverseEngineUrl(s.url, imageUrl);
    await chrome.tabs.create({ url: u, active: wantActive && first });
    first = false;
  }
}

function tbccMenuIdForSite(siteId) {
  const b64 = btoa(unescape(encodeURIComponent(String(siteId))))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
  return "tbccmsi_" + b64;
}

function tbccSiteIdFromMenuId(menuId) {
  if (!menuId || !String(menuId).startsWith("tbccmsi_")) return null;
  let b64 = String(menuId).slice(8).replace(/-/g, "+").replace(/_/g, "/");
  while (b64.length % 4) b64 += "=";
  try {
    return decodeURIComponent(escape(atob(b64)));
  } catch (_) {
    return null;
  }
}

function normalizeUsernameCandidate(raw) {
  if (typeof TbccUsernameFilter !== "undefined" && TbccUsernameFilter.normalizeUsernameCandidate) {
    return TbccUsernameFilter.normalizeUsernameCandidate(raw);
  }
  if (!raw) return "";
  let s = String(raw).trim();
  s = s.replace(/^@+/, "");
  s = s.replace(/^[^\w]+|[^\w.:-]+$/g, "");
  if (!s) return "";
  if (!/^[a-zA-Z0-9._-]{2,64}$/.test(s)) return "";
  return s;
}

function usernameFromText(text) {
  if (!text) return "";
  const s = String(text);
  const tagged = s.match(/@([a-zA-Z0-9._-]{2,64})/);
  if (tagged && tagged[1]) return normalizeUsernameCandidate(tagged[1]);
  return normalizeUsernameCandidate(s);
}

function usernameFromUrl(rawUrl) {
  if (!rawUrl) return "";
  const str = String(rawUrl).trim();
  const tagged = str.match(/@([a-zA-Z0-9._-]{2,64})/);
  if (tagged && tagged[1]) return normalizeUsernameCandidate(tagged[1]);
  try {
    const u = new URL(str);
    for (const key of ["username", "user", "u", "model", "handle", "nick", "q"]) {
      const n = normalizeUsernameCandidate(u.searchParams.get(key) || "");
      if (n) return n;
    }
    const skip = new Set(["search", "models", "model", "profile", "profiles", "user", "users", "www", "en"]);
    const segs = u.pathname
      .split("/")
      .map((x) => decodeURIComponent(x || "").trim())
      .filter(Boolean);
    for (let i = segs.length - 1; i >= 0; i--) {
      const seg = segs[i];
      if (skip.has(seg.toLowerCase())) continue;
      const n = normalizeUsernameCandidate(seg);
      if (n) return n;
    }
  } catch (_) {}
  return "";
}

async function resolveModelSearchUsernameFromContext(info, tab) {
  const sel = usernameFromText((info.selectionText || "").trim());
  if (sel) return sel;
  const fromLink =
    usernameFromText(String(info.linkText || "").trim()) ||
    usernameFromUrl((info.linkUrl || "").trim()) ||
    usernameFromUrl((info.srcUrl || "").trim());
  if (fromLink) return fromLink;
  if (tab && tab.id != null) {
    try {
      const resp = await chrome.tabs.sendMessage(tab.id, { action: "tbcc-get-context-username" });
      const fromPage = usernameFromText(resp && resp.username ? resp.username : "");
      if (fromPage) return fromPage;
    } catch (_) {}
  }
  try {
    const data = await chrome.storage.local.get(STORAGE_LAST_COPIED_USERNAME);
    const fromCopied = usernameFromText(data && data[STORAGE_LAST_COPIED_USERNAME] ? data[STORAGE_LAST_COPIED_USERNAME] : "");
    if (fromCopied) return fromCopied;
  } catch (_) {}
  return "";
}

async function recordModelSearchSummary(username, sites, onlySiteId) {
  const rows = sites.map((s) => ({
    siteId: s.id,
    name: s.name || s.id,
    url: buildModelSearchUrl(s.url, username),
    countHint: null,
    fetchStatus: "pending",
  }));
  const summary = {
    query: String(username).trim(),
    ts: Date.now(),
    mode: onlySiteId ? "single" : "all",
    rows,
  };
  await chrome.storage.local.set({ [STORAGE_MODEL_SEARCH_LAST_SUMMARY]: summary });
}

function resolveUsernameSearchSource(meta) {
  const h = typeof TbccUsernameSearchHistory !== "undefined" ? TbccUsernameSearchHistory : null;
  if (!h) return "unknown";
  const m = meta && typeof meta === "object" ? meta : {};
  if (m.source) return h.normalizeUsernameSearchSource(m.source);
  if (m.pageUrl) return h.inferUsernameSearchSourceFromUrl(m.pageUrl);
  return "unknown";
}

async function recordModelSearchSiteStats(rows) {
  if (!Array.isArray(rows) || !rows.length) return;
  let stats = {};
  try {
    const data = await chrome.storage.local.get(STORAGE_MODEL_SEARCH_SITE_STATS);
    stats =
      data[STORAGE_MODEL_SEARCH_SITE_STATS] && typeof data[STORAGE_MODEL_SEARCH_SITE_STATS] === "object"
        ? { ...data[STORAGE_MODEL_SEARCH_SITE_STATS] }
        : {};
  } catch (_) {}
  const now = Date.now();
  for (const row of rows) {
    const id = String((row && row.siteId) || "").trim();
    if (!id) continue;
    const prev = stats[id] && typeof stats[id] === "object" ? stats[id] : { hits: 0, misses: 0, name: "", lastAt: 0 };
    const hit = !!(row && row.hasResults && Number(row.count) > 0);
    stats[id] = {
      hits: Number(prev.hits || 0) + (hit ? 1 : 0),
      misses: Number(prev.misses || 0) + (hit ? 0 : 1),
      name: String((row && row.name) || prev.name || id),
      lastAt: now,
    };
  }
  await chrome.storage.local.set({ [STORAGE_MODEL_SEARCH_SITE_STATS]: stats });
}

function siteStatsRankScore(entry) {
  if (!entry || typeof entry !== "object") return -1;
  const hits = Number(entry.hits || 0);
  const misses = Number(entry.misses || 0);
  const total = hits + misses;
  if (total <= 0) return -1;
  return hits / total + Math.min(hits, 50) / 1000;
}

async function openModelSearchUrlLazy(url, opts) {
  const u = String(url || "").trim();
  if (!/^https?:\/\//i.test(u)) return { ok: false, error: "invalid_url" };
  const active = !!(opts && opts.active);
  const lazy = !opts || opts.lazy !== false;
  if (!lazy) {
    const tab = await chrome.tabs.create({ url: u, active });
    return { ok: true, tabId: tab && tab.id, lazy: false };
  }
  const tab = await chrome.tabs.create({ url: "about:blank", active: false });
  const tabId = tab && tab.id;
  if (tabId == null) return { ok: false, error: "no_tab" };
  try {
    await chrome.storage.session.set({ [LAZY_TAB_URL_PREFIX + tabId]: u });
  } catch (_) {
    await chrome.tabs.update(tabId, { url: u, active });
    return { ok: true, tabId, lazy: false };
  }
  if (active) {
    await chrome.tabs.update(tabId, { active: true });
    await hydrateLazyModelSearchTab(tabId);
  }
  return { ok: true, tabId, lazy: true };
}

async function hydrateLazyModelSearchTab(tabId) {
  if (tabId == null) return false;
  const key = LAZY_TAB_URL_PREFIX + tabId;
  let pending = "";
  try {
    const data = await chrome.storage.session.get(key);
    pending = String(data[key] || "").trim();
  } catch (_) {
    return false;
  }
  if (!pending || !/^https?:\/\//i.test(pending)) return false;
  try {
    await chrome.storage.session.remove(key);
  } catch (_) {}
  try {
    await chrome.tabs.update(tabId, { url: pending });
    return true;
  } catch (_) {
    return false;
  }
}

async function listMacroSourcesWithStats() {
  let cfg;
  try {
    cfg = await getMergedModelSearchSites();
  } catch (_) {
    return { ok: false, error: "config", sites: [] };
  }
  const data = await chrome.storage.local.get([STORAGE_MODEL_SEARCH_ENABLED, STORAGE_MODEL_SEARCH_SITE_STATS]);
  const enabled = data[STORAGE_MODEL_SEARCH_ENABLED] || {};
  const stats =
    data[STORAGE_MODEL_SEARCH_SITE_STATS] && typeof data[STORAGE_MODEL_SEARCH_SITE_STATS] === "object"
      ? data[STORAGE_MODEL_SEARCH_SITE_STATS]
      : {};
  const sites = (cfg.sites || [])
    .filter((s) => enabled[s.id] !== false && normalizeModelSearchCategory(s.category) === MODEL_SEARCH_CATEGORY_MACRO)
    .map((s) => {
      const st = stats[s.id] && typeof stats[s.id] === "object" ? stats[s.id] : null;
      const hits = Number((st && st.hits) || 0);
      const misses = Number((st && st.misses) || 0);
      const total = hits + misses;
      return {
        id: s.id,
        name: s.name || s.id,
        url: s.url,
        category: normalizeModelSearchCategory(s.category),
        hits,
        misses,
        total,
        hitRate: total ? hits / total : null,
        rankScore: siteStatsRankScore(st),
        lastAt: Number((st && st.lastAt) || 0),
      };
    });
  sites.sort(
    (a, b) =>
      b.rankScore - a.rankScore ||
      b.hits - a.hits ||
      String(a.name).localeCompare(String(b.name))
  );
  return { ok: true, sites };
}

async function recordModelSearchHistory(username, meta) {
  const clean = normalizeUsernameCandidate(username);
  if (!clean) return;
  let arr = [];
  try {
    const data = await chrome.storage.local.get(STORAGE_MODEL_SEARCH_HISTORY);
    arr = Array.isArray(data[STORAGE_MODEL_SEARCH_HISTORY]) ? data[STORAGE_MODEL_SEARCH_HISTORY] : [];
  } catch (_) {}
  const now = Date.now();
  const source = resolveUsernameSearchSource(meta) || "model_search";
  const deduped = arr.filter((x) => x && x.username && String(x.username).toLowerCase() !== clean.toLowerCase());
  const next = [{ username: clean, ts: now, source }, ...deduped].slice(0, 200);
  await chrome.storage.local.set({ [STORAGE_MODEL_SEARCH_HISTORY]: next });
  if (typeof TbccMasterArchive !== "undefined") {
    const archived =
      typeof TbccUsernameFilter !== "undefined" && TbccUsernameFilter.acceptUsernameForArchive
        ? TbccUsernameFilter.acceptUsernameForArchive(clean, { source: source || "model_search" })
        : clean;
    if (archived) void TbccMasterArchive.recordUsername(archived, { source: source || "model_search" });
  }
}

const MACRO_SEARCH_CONCURRENCY = 8;

async function probeModelSearchSite(site, username) {
  const url = buildModelSearchUrl(site.url, username);
  let fetchStatus = "ok";
  let analysis = { hasResults: false, count: 0, reason: "none" };
  try {
    const r = await fetch(url, {
      credentials: "omit",
      redirect: "follow",
      headers: { Accept: "text/html,application/json,*/*;q=0.8" },
    });
    const text = await r.text();
    if (!r.ok) fetchStatus = "http_" + r.status;
    analysis = analyzeModelSearchHtml(text, r.url || url, username);
    if (!r.ok && analysis.reason === "none") analysis = { ...analysis, reason: "http_" + r.status };
  } catch (_) {
    fetchStatus = "err";
    analysis = { hasResults: false, count: 0, reason: "err" };
  }
  return {
    siteId: site.id,
    name: site.name || site.id,
    url,
    count: analysis.count || 0,
    hasResults: !!analysis.hasResults,
    fetchStatus,
    reason: analysis.reason || "none",
    confidence: analysis.confidence || "none",
    signal: analysis.signal || "none",
    resultLinks: analysis.resultLinks || 0,
  };
}

async function fetchUrlsWithConcurrencyItems(items, workerFn, maxConcurrency) {
  const n = items.length;
  if (n === 0) return [];
  const results = new Array(n);
  let nextIndex = 0;
  async function worker() {
    while (true) {
      const idx = nextIndex++;
      if (idx >= n) return;
      results[idx] = await workerFn(items[idx], idx);
    }
  }
  const cap = Math.min(Math.max(1, maxConcurrency || MACRO_SEARCH_CONCURRENCY), n);
  await Promise.all(Array.from({ length: cap }, () => worker()));
  return results;
}

/**
 * Native macro search: probe all enabled macro-category sources; store hits-only report.
 * Does not open browser tabs (use launchModelSearch for tab fan-out).
 */
async function launchMacroModelSearch(username, meta) {
  const cleanUsername = normalizeUsernameCandidate(username);
  if (!cleanUsername) {
    notify("TBCC", "Macro search expects a username.");
    return { ok: false, error: "invalid_username" };
  }
  const historyMeta = Object.assign({}, meta && typeof meta === "object" ? meta : {});
  if (!historyMeta.source && !historyMeta.pageUrl) historyMeta.source = "macro";
  let cfg;
  try {
    cfg = await getMergedModelSearchSites();
  } catch (_) {
    notify("TBCC", "Macro search: missing or invalid model-search-sites.json.");
    return { ok: false, error: "config" };
  }
  const data = await chrome.storage.local.get(STORAGE_MODEL_SEARCH_ENABLED);
  const enabled = data[STORAGE_MODEL_SEARCH_ENABLED] || {};
  const sourceHint = resolveUsernameSearchSource(historyMeta);
  const preferredFamilies = preferredFamiliesForUsernameSource(sourceHint);

  let sites = (cfg.sites || []).filter((s) => enabled[s.id] !== false);
  // Default macro engine: macro-category sites. Source-aware: also allow matching family from other cats.
  if (preferredFamilies && preferredFamilies.length) {
    sites = sites.filter((s) => {
      const fam = modelSearchSiteFamily(s);
      const cat = normalizeModelSearchCategory(s.category);
      if (preferredFamilies.includes(fam)) return true;
      // Keep explicit livecams/videos category rows when those families are preferred
      if (preferredFamilies.includes("livecams") && cat === MODEL_SEARCH_CATEGORY_LIVECAMS) return true;
      if (preferredFamilies.includes("videos") && cat === MODEL_SEARCH_CATEGORY_VIDEOS) return true;
      return false;
    });
  } else {
    sites = sites.filter((s) => normalizeModelSearchCategory(s.category) === MODEL_SEARCH_CATEGORY_MACRO);
  }

  const badSites = [];
  sites = sites.filter((s) => {
    try {
      const u = buildModelSearchUrl(s.url, cleanUsername);
      new URL(u.split("{username}").join("x"));
      if (!/^https?:\/\//i.test(u)) throw new Error("bad");
      return true;
    } catch (_) {
      badSites.push(s.name || s.id);
      return false;
    }
  });
  if (!sites.length) {
    const srcLabel = sourceHint && sourceHint !== "unknown" ? ` for ${sourceHint}` : "";
    notify(
      "TBCC",
      badSites.length
        ? "No valid sources — fix URLs in Lookup tab → Manage sources."
        : preferredFamilies
          ? `No matching sources enabled${srcLabel} (webcam/archive sites). Enable livecams/macro cam sources in Options.`
          : "No macro sources enabled — enable sites under Macro search in extension options."
    );
    return { ok: false, error: "no_sites", source: sourceHint, families: preferredFamilies };
  }

  const pendingSummary = {
    query: cleanUsername,
    ts: Date.now(),
    mode: "macro",
    status: "running",
    scanned: 0,
    totalSites: sites.length,
    hits: [],
    totalCount: 0,
    rows: [],
  };
  await chrome.storage.local.set({ [STORAGE_MODEL_SEARCH_LAST_SUMMARY]: pendingSummary });

  const rows = await fetchUrlsWithConcurrencyItems(
    sites,
    (site) => probeModelSearchSite(site, cleanUsername),
    MACRO_SEARCH_CONCURRENCY
  );

  let scanned = 0;
  const hits = [];
  let totalCount = 0;
  for (const row of rows) {
    scanned++;
    // Drop low-confidence / template false positives (search box echo, sidebar cards).
    const conf = String(row.confidence || "").toLowerCase();
    const okHit =
      row.hasResults &&
      row.count > 0 &&
      (conf === "high" || conf === "medium" || row.signal === "result_links" || row.signal === "json" || row.signal === "json_total");
    if (okHit) {
      hits.push({
        siteId: row.siteId,
        name: row.name,
        url: row.url,
        count: row.count,
        confidence: row.confidence || "medium",
        signal: row.signal || "",
        family: modelSearchSiteFamily({ id: row.siteId, name: row.name, url: row.url }),
      });
      totalCount += row.count;
    }
  }
  hits.sort((a, b) => b.count - a.count || String(a.name).localeCompare(String(b.name)));

  const summary = {
    query: cleanUsername,
    ts: Date.now(),
    mode: "macro",
    status: "done",
    scanned,
    totalSites: sites.length,
    hits,
    totalCount,
    rows,
    source: sourceHint,
    families: preferredFamilies,
  };
  await chrome.storage.local.set({ [STORAGE_MODEL_SEARCH_LAST_SUMMARY]: summary });
  await recordModelSearchHistory(cleanUsername, historyMeta);
  await recordModelSearchSiteStats(rows);

  const hitN = hits.length;
  const srcNote = sourceHint && sourceHint !== "unknown" && sourceHint !== "macro" ? ` [${sourceHint}]` : "";
  notify(
    "TBCC",
    hitN
      ? `Macro search${srcNote}: ${hitN} site(s), ~${totalCount} result(s) for ${cleanUsername}`
      : preferredFamilies
        ? `Macro search${srcNote}: no real hits on ${scanned} webcam/archive source(s) for ${cleanUsername}`
        : `Macro search: no hits on ${scanned} site(s) for ${cleanUsername}`
  );
  if (badSites.length) {
    notifyThrottled(
      "macro-search-bad",
      "TBCC",
      `Skipped ${badSites.length} macro source(s) with invalid URLs.`,
      12000
    );
  }
  return { ok: true, summary };
}

async function fetchCountsForSites(username, sites) {
  const rows = await fetchUrlsWithConcurrencyItems(
    sites,
    (site) => probeModelSearchSite(site, username),
    MACRO_SEARCH_CONCURRENCY
  );
  const data = await chrome.storage.local.get(STORAGE_MODEL_SEARCH_LAST_SUMMARY);
  const sum = data[STORAGE_MODEL_SEARCH_LAST_SUMMARY];
  if (!sum || !Array.isArray(sum.rows)) return;
  for (const row of rows) {
    const target = sum.rows.find((x) => x.siteId === row.siteId);
    if (target) {
      target.countHint = row.hasResults ? row.count : null;
      target.fetchStatus = row.fetchStatus;
    }
  }
  await chrome.storage.local.set({ [STORAGE_MODEL_SEARCH_LAST_SUMMARY]: sum });
}

async function launchModelSearch(username, onlySiteId = null, onlyCategory = null, meta = null) {
  const cleanUsername = normalizeUsernameCandidate(username);
  if (!cleanUsername) {
    notify("TBCC", "Model search expects a username.");
    return;
  }
  const historyMeta = Object.assign({}, meta && typeof meta === "object" ? meta : {});
  if (!historyMeta.source && !historyMeta.pageUrl) historyMeta.source = "model_search";
  let cfg;
  try {
    cfg = await getMergedModelSearchSites();
  } catch (_) {
    notify("TBCC", "Model search: missing or invalid model-search-sites.json.");
    return;
  }
  const data = await chrome.storage.local.get([STORAGE_MODEL_SEARCH_ENABLED, STORAGE_MODEL_SEARCH_MODE]);
  const enabled = data[STORAGE_MODEL_SEARCH_ENABLED] || {};
  let sites = (cfg.sites || []).filter((s) => enabled[s.id] !== false);
  if (onlyCategory) {
    const cat = normalizeModelSearchCategory(onlyCategory);
    sites = sites.filter((s) => normalizeModelSearchCategory(s.category) === cat);
  }
  if (onlySiteId) {
    sites = sites.filter((s) => s.id === onlySiteId);
  }
  if (!sites.length) {
    notify("TBCC", "No model search sources enabled — open Extension options (Model search).");
    return;
  }
  let mode = data[STORAGE_MODEL_SEARCH_MODE] || "foreground";
  if (mode === "dashboard") mode = "foreground";
  const wantActive = mode === "foreground";
  const badSites = [];
  let first = true;
  let opened = 0;
  for (const s of sites) {
    let u;
    try {
      u = buildModelSearchUrl(s.url, cleanUsername);
      new URL(u.split("{username}").join("x"));
    } catch (_) {
      badSites.push(s.name || s.id);
      continue;
    }
    if (!/^https?:\/\//i.test(u)) {
      badSites.push(s.name || s.id);
      continue;
    }
    try {
      // Lazy tabs: about:blank until focused — avoids loading dozens of sites at once.
      const r = await openModelSearchUrlLazy(u, { lazy: true, active: wantActive && first });
      if (r && r.ok) opened++;
    } catch (e) {
      notify("TBCC", `Could not open ${s.name || s.id}: ${String(e.message || e).slice(0, 120)}`);
      badSites.push(s.name || s.id);
    }
    first = false;
  }
  if (badSites.length && badSites.length === sites.length) {
    notify(
      "TBCC",
      "Model search failed — check custom source URLs in Options (need {username}, valid https URL)."
    );
    return;
  }
  if (badSites.length) {
    notifyThrottled(
      "model-search-bad",
      "TBCC",
      `Skipped ${badSites.length} source(s) with invalid URLs: ${badSites.slice(0, 4).join(", ")}${badSites.length > 4 ? "…" : ""}`,
      15000
    );
  }
  if (opened > 1) {
    notifyThrottled(
      "model-search-lazy",
      "TBCC",
      `Opened ${opened} unloaded tab(s) for ${cleanUsername} — pages load only when you switch to them.`,
      10000
    );
  }
  await recordModelSearchSummary(cleanUsername, sites, onlySiteId);
  await recordModelSearchHistory(cleanUsername, historyMeta);
  void fetchCountsForSites(cleanUsername, sites);
}

/**
 * Hosts where backend /import/url is wrong choice: no browser cookies, wrong Referer, or IP-bound CDN.
 * Erome: CDN requires Referer from album page https://www.erome.com/a/{id} (derived from path).
 */
function hostNeedsSessionFetch(url) {
  try {
    const h = new URL(url).hostname.toLowerCase();
    return (
      h === "onlyfans.com" ||
      h.endsWith(".onlyfans.com") ||
      h === "erome.com" ||
      h.endsWith(".erome.com") ||
      h.includes("coomer.st") ||
      h.includes("coomer.party") ||
      h.includes("kemono.party") ||
      h.includes("kemono.su") ||
      h.includes("kemono.si") ||
      h === "fetlife.com" ||
      h.endsWith(".fetlife.com") ||
      h.includes("fetlife") ||
      h === "fapello.com" ||
      h.endsWith(".fapello.com") ||
      h === "nudostar.com" ||
      h.endsWith(".nudostar.com") ||
      h === "video.twimg.com" ||
      h.includes("bunkr") ||
      h.includes("bunkrr") ||
      h.endsWith("scdn.st") ||
      h.endsWith(".scdn.st")
    );
  } catch (_) {
    return false;
  }
}

/** Same as gallery.js: avoid Vite :5173 /api/media URLs when fetching TBCC thumbnails for import. */
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

function isEromeHost(hostname) {
  const h = String(hostname || "").toLowerCase();
  return h === "erome.com" || h.endsWith(".erome.com");
}

function isEromeMediaUrl(url) {
  try {
    return isEromeHost(new URL(url).hostname);
  } catch (_) {
    return false;
  }
}

/** CDN path …/content/m/r/{slug}/… → https://fapello.com/{slug}/ */
function fapelloProfileRefererFromMediaUrl(url) {
  try {
    const u = new URL(url);
    const h = (u.hostname || "").toLowerCase();
    if (h !== "fapello.com" && !h.endsWith(".fapello.com")) return "";
    const m = (u.pathname || "").match(/\/content\/m\/r\/([^/]+)/i);
    if (!m || !m[1]) return "";
    return `${u.protocol}//${u.hostname}/${encodeURIComponent(m[1])}/`;
  } catch (_) {
    return "";
  }
}

function isFapelloHost(hostname) {
  const h = String(hostname || "").toLowerCase();
  return h === "fapello.com" || h.endsWith(".fapello.com");
}

/** CDN path …/albumId/file.mp4 → https://www.erome.com/a/albumId */
function eromeAlbumPageFromMediaUrl(url) {
  try {
    const u = new URL(url);
    if (!isEromeHost(u.hostname)) return "";
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

function isEromeAlbumPageUrl(pageUrl) {
  try {
    const u = new URL(String(pageUrl || "").split("#")[0]);
    return isEromeHost(u.hostname) && /^\/a\/[^/]+/i.test(u.pathname || "");
  } catch (_) {
    return false;
  }
}

/** CDN path …/albumId/file.mp4 → album https://www.erome.com/a/albumId */
function eromeReferrerChain(url, refererPageUrl) {
  try {
    const u = new URL(url);
    const host = u.hostname.toLowerCase();
    if (!isEromeHost(host)) return null;
    const chain = [];
    const pushRef = (s) => {
      const t = String(s || "").trim().split("#")[0];
      if (!t || !/^https?:\/\//i.test(t)) return;
      if (!chain.includes(t)) chain.push(t);
    };
    const albumFromCdn = eromeAlbumPageFromMediaUrl(url);
    if (albumFromCdn) pushRef(albumFromCdn);
    if (refererPageUrl && isEromeAlbumPageUrl(refererPageUrl)) pushRef(refererPageUrl);
    else if (refererPageUrl && isEromeHost(new URL(refererPageUrl).hostname)) pushRef(refererPageUrl);
    pushRef("https://www.erome.com/");
    return chain.length ? chain : ["https://www.erome.com/"];
  } catch (_) {
    return ["https://www.erome.com/"];
  }
}

const _eromeWarmAt = new Map();
let _eromeFetchQueue = Promise.resolve();

function enqueueEromeFetch(task) {
  const run = _eromeFetchQueue.then(task, task);
  _eromeFetchQueue = run.catch(() => {});
  return run;
}

const _cachedBrowserUa = { at: 0, ua: "" };

async function getBrowserUserAgent(tabId) {
  if (Date.now() - _cachedBrowserUa.at < 120000 && _cachedBrowserUa.ua) return _cachedBrowserUa.ua;
  let ua = "";
  const tryTab = async (id) => {
    if (id == null || id < 0) return "";
    try {
      const inj = await chrome.scripting.executeScript({
        target: { tabId: id },
        func: () => navigator.userAgent,
      });
      return inj && inj[0] && inj[0].result ? String(inj[0].result) : "";
    } catch (_) {
      return "";
    }
  };
  ua = await tryTab(tabId);
  if (!ua) {
    try {
      const [active] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
      if (active && active.id != null) ua = await tryTab(active.id);
    } catch (_) {}
  }
  if (!ua) {
    ua =
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36";
  }
  _cachedBrowserUa.ua = ua;
  _cachedBrowserUa.at = Date.now();
  return ua;
}

function eromeMediaStemFromUrl(url) {
  try {
    const base = (new URL(url).pathname.split("/").pop() || "").split("?")[0];
    return base.replace(/\.[^.]+$/, "").replace(/_(\d+p|full|hq|hd|sd)$/i, "");
  } catch (_) {
    return "";
  }
}

function eromeExtractMediaUrlsFromHtml(html) {
  if (!html || typeof html !== "string") return [];
  const flat = html.replace(/\\\//g, "/");
  const out = [];
  const seen = new Set();
  const re = /https?:\/\/[^\s"'<>]+?\.(?:mp4|webm|m4v|mkv|mov)(?:\?[^\s"'<>]*)?/gi;
  let m;
  while ((m = re.exec(flat)) !== null) {
    const u = String(m[0] || "").replace(/&amp;/g, "&");
    if (!/^https?:\/\//i.test(u) || !isEromeMediaUrl(u)) continue;
    if (seen.has(u)) continue;
    seen.add(u);
    out.push(u);
  }
  return out;
}

function eromeScoreMediaUrl(u, stem) {
  const s = String(u || "").toLowerCase();
  const st = String(stem || "").toLowerCase();
  let sc = 0;
  if (st && s.includes(st)) sc += 50;
  else if (st && st.split("_")[0] && s.includes(st.split("_")[0])) sc += 28;
  if (s.includes("1080") || s.includes("2160") || s.includes("4k")) sc += 18;
  if (s.includes("720")) sc += 10;
  if (s.includes("full")) sc += 12;
  if (s.includes("?")) sc += 6;
  if (s.includes("thumb") || s.includes("preview")) sc -= 40;
  return sc;
}

async function fetchWithTimeout(url, init, timeoutMs) {
  const ms = Math.max(5000, timeoutMs || 60000);
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), ms);
  try {
    return await fetch(url, { ...init, signal: ctrl.signal });
  } catch (e) {
    if (e && e.name === "AbortError") {
      throw new Error(`Fetch timed out after ${Math.round(ms / 1000)}s`);
    }
    throw e;
  } finally {
    clearTimeout(timer);
  }
}

function tbccFetchTimeoutMs(url) {
  try {
    const path = new URL(url).pathname.toLowerCase();
    if (/\.(mp4|webm|m4v|mov|mkv)(\?|$)/i.test(path)) return 180000;
  } catch (_) {}
  return 45000;
}

/** Stall timeout — abort if no bytes arrive for stallMs (resets per chunk). */
async function readResponseArrayBufferWithStall(res, stallMs) {
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  if (!res.body || typeof res.body.getReader !== "function") return await res.arrayBuffer();
  const reader = res.body.getReader();
  const chunks = [];
  let total = 0;
  let stallTimer;
  const bump = () => {
    clearTimeout(stallTimer);
    stallTimer = setTimeout(() => {
      try {
        reader.cancel("stall");
      } catch (_) {}
    }, stallMs);
  };
  bump();
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      bump();
      chunks.push(value);
      total += value.byteLength;
    }
  } finally {
    clearTimeout(stallTimer);
  }
  const out = new Uint8Array(total);
  let off = 0;
  for (const c of chunks) {
    out.set(c, off);
    off += c.byteLength;
  }
  return out.buffer;
}

async function mergeCookiesForUrls(urlList) {
  const seen = new Set();
  const pairs = [];
  for (const pageUrl of urlList) {
    try {
      const cookies = await chrome.cookies.getAll({ url: pageUrl });
      for (const c of cookies) {
        if (!seen.has(c.name)) {
          seen.add(c.name);
          pairs.push(`${c.name}=${c.value}`);
        }
      }
    } catch (_) {}
  }
  return pairs.join("; ");
}

/** Erome: merge per-URL cookies + all *.erome.com domain cookies + CDN origin. */
async function mergeEromeCookieHeader(eromeChain, mediaUrl) {
  const urls = [...(eromeChain || [])];
  if (mediaUrl) {
    try {
      const mu = new URL(mediaUrl);
      urls.push(mediaUrl, `${mu.protocol}//${mu.hostname}/`);
    } catch (_) {}
  }
  let header = await mergeCookiesForUrls(urls);
  try {
    const domainCookies = await chrome.cookies.getAll({ domain: "erome.com" });
    const seen = new Set();
    if (header) {
      for (const part of header.split("; ")) {
        const n = part.split("=")[0];
        if (n) seen.add(n);
      }
    }
    const extra = [];
    for (const c of domainCookies) {
      if (!seen.has(c.name)) {
        seen.add(c.name);
        extra.push(`${c.name}=${c.value}`);
      }
    }
    if (extra.length) header = header ? `${header}; ${extra.join("; ")}` : extra.join("; ");
  } catch (_) {}
  return header;
}

function sessionFetchHeaders(referer, targetUrl, userAgent, opts) {
  const h = {
    Accept: "*/*",
    "Accept-Language": "en-US,en;q=0.9",
  };
  if (userAgent) h["User-Agent"] = userAgent;
  if (referer) h.Referer = referer;
  if (opts && opts.origin) h.Origin = opts.origin;
  try {
    const tu = targetUrl ? new URL(targetUrl) : null;
    const ru = referer ? new URL(referer) : null;
    h["Sec-Fetch-Dest"] = tu && /\.(mp4|webm|m4v|mov|mkv)(\?|$)/i.test(tu.pathname) ? "video" : "empty";
    h["Sec-Fetch-Mode"] = "cors";
    h["Sec-Fetch-Site"] =
      tu && ru && tu.hostname !== ru.hostname ? "cross-site" : tu && ru ? "same-origin" : "cross-site";
  } catch (_) {}
  return h;
}

const TBCC_TAB_FETCH_MAX_BYTES = 48 * 1024 * 1024;

/** Resolve blob:/data: context-menu URLs to the https URL the page actually loaded. */
async function resolveMediaUrlFromTab(tabId, url) {
  const u = String(url || "").trim();
  if (!/^blob:|^data:/i.test(u)) return u;
  if (tabId == null || tabId < 0) return u;
  try {
    const inj = await chrome.scripting.executeScript({
      target: { tabId },
      func: () => {
        try {
          var vids = document.querySelectorAll("video");
          for (var i = 0; i < vids.length; i++) {
            var cs = vids[i].currentSrc || vids[i].src || "";
            if (cs.indexOf("http") === 0) return cs;
          }
        } catch (_) {}
        try {
          var entries = performance.getEntriesByType("resource");
          for (var j = entries.length - 1; j >= 0; j--) {
            var n = entries[j] && entries[j].name;
            if (n && /\.(mp4|webm|m4v|mov|mkv)(\?|$)/i.test(n.split("?")[0])) return n;
          }
        } catch (_) {}
        return "";
      },
    });
    const resolved = inj && inj[0] && inj[0].result ? String(inj[0].result).trim() : "";
    if (resolved && /^https?:\/\//i.test(resolved)) return resolved;
  } catch (_) {}
  return u;
}

/** Prefer HLS/MP4 from network log when DOM only exposes poster/page URLs (e.g. cam sites). */
async function tbccResolveBestCopyableMediaUrl(tabId, hintUrl) {
  let hint = String(hintUrl || "").trim();
  if (/^blob:|^data:/i.test(hint)) {
    hint = await resolveMediaUrlFromTab(tabId, hint);
  }
  const candidates = new Set();
  if (hint && tbccIsStorableHttpUrl(hint)) candidates.add(hint);
  if (tabId != null && tabId >= 0) {
    try {
      const got = await chrome.storage.session.get([
        `tbcc_net_media_${tabId}`,
        `tbcc_net_manifest_${tabId}`,
      ]);
      const net = got[`tbcc_net_media_${tabId}`];
      if (Array.isArray(net)) {
        for (const u of net) {
          if (tbccInboxWorthyNetVideoUrl(u)) candidates.add(String(u).trim());
        }
      }
      const mans = got[`tbcc_net_manifest_${tabId}`];
      if (Array.isArray(mans)) {
        for (const u of mans) {
          if (tbccIsStorableHttpUrl(u)) candidates.add(String(u).trim());
        }
      }
    } catch (_) {}
  }
  if (!candidates.size) return hint || "";
  const scoreFn = typeof tbccScoreVideoUrl === "function" ? tbccScoreVideoUrl : () => 0;
  let best = "";
  let bestScore = -9999;
  let hintHost = "";
  try {
    hintHost = hint ? new URL(hint).hostname.toLowerCase() : "";
  } catch (_) {}
  for (const u of candidates) {
    let sc = scoreFn(u);
    try {
      const h = new URL(u).hostname.toLowerCase();
      if (hintHost && h === hintHost) sc += 12;
    } catch (_) {}
    if (/\.(m3u8|mpd)(\?|$)/i.test(u)) sc += 8;
    if (sc > bestScore) {
      bestScore = sc;
      best = u;
    }
  }
  if (bestScore < 20 && hint && tbccIsStorableHttpUrl(hint)) return hint;
  return best || hint || "";
}

async function tbccAfterInboxSave(arr, urlList) {
  if (typeof TbccMasterArchive === "undefined") return;
  await TbccMasterArchive.mirrorInboxRows(arr);
  for (const u of urlList || []) {
    if (tbccIsStorableHttpUrl(u)) void TbccMasterArchive.recordUrl(u, { source: "inbox" });
  }
}

/** Download in the page context (page cookies + referrer) — works on Erome and many CDNs. */
async function fetchMediaBytesFromTab(tabId, mediaUrl, refererPageUrl) {
  if (tabId == null || tabId < 0 || !mediaUrl || !/^https?:\/\//i.test(mediaUrl)) return null;
  const ref = String(refererPageUrl || "").trim().split("#")[0];
  if (!ref || !/^https?:\/\//i.test(ref)) return null;
  try {
    const tab = await chrome.tabs.get(tabId);
    if (!tab || !tab.url || !tbccIsInjectableHttpUrl(tab.url)) return null;
    const inj = await chrome.scripting.executeScript({
      target: { tabId },
      func: async (u, pageRef, maxBytes) => {
        try {
          let len = 0;
          try {
            const head = await fetch(u, {
              method: "HEAD",
              credentials: "include",
              referrer: pageRef,
              referrerPolicy: "strict-origin-when-cross-origin",
            });
            len = parseInt(head.headers.get("content-length") || "0", 10) || 0;
            if (len > maxBytes) return { skip: true, reason: "too_large", len };
          } catch (_) {}
          const r = await fetch(u, {
            credentials: "include",
            referrer: pageRef,
            referrerPolicy: "strict-origin-when-cross-origin",
          });
          if (!r.ok) return { ok: false, status: r.status };
          const buf = await r.arrayBuffer();
          if (buf.byteLength > maxBytes) return { skip: true, reason: "too_large", len: buf.byteLength };
          const arr = new Uint8Array(buf);
          const bytes = new Array(arr.length);
          for (let i = 0; i < arr.length; i++) bytes[i] = arr[i];
          return { ok: true, bytes, len: arr.length };
        } catch (e) {
          return { ok: false, error: String(e.message || e) };
        }
      },
      args: [mediaUrl, ref, TBCC_TAB_FETCH_MAX_BYTES],
    });
    const r = inj && inj[0] && inj[0].result;
    if (!r || r.skip || !r.ok || !Array.isArray(r.bytes)) return null;
    return new Uint8Array(r.bytes).buffer;
  } catch (_) {
    return null;
  }
}

function fetchEromeBytesFromTab(tabId, mediaUrl, albumUrl) {
  return fetchMediaBytesFromTab(tabId, mediaUrl, albumUrl);
}

async function tbccOpenEromeAlbumTab(albumUrl) {
  const album = String(albumUrl || "").trim().split("#")[0];
  if (!album || !/^https?:\/\//i.test(album)) return;
  try {
    const tabs = await chrome.tabs.query({});
    for (const t of tabs) {
      if (!t.url) continue;
      try {
        if (t.url.split("#")[0] === album) {
          if (t.id != null) await chrome.tabs.update(t.id, { active: true });
          if (t.windowId != null) await chrome.windows.update(t.windowId, { focused: true });
          return;
        }
      } catch (_) {}
    }
    await chrome.tabs.create({ url: album, active: true });
  } catch (_) {}
}

/** Same-tab fetch refreshes the browser cookie jar before chrome.cookies reads. */
async function tbccPrewarmEromeTab(tabId, eromeChain) {
  if (tabId == null || tabId < 0) return;
  const album = (eromeChain || []).find((u) => /\/a\/[^/]+/i.test(u));
  if (!album) return;
  try {
    const tab = await chrome.tabs.get(tabId);
    if (!tab || !tab.url) return;
    if (!isEromeHost(new URL(tab.url).hostname)) return;
    await chrome.scripting.executeScript({
      target: { tabId },
      func: async (albumUrl) => {
        try {
          await fetch(albumUrl, { credentials: "include", cache: "no-store" });
        } catch (_) {}
      },
      args: [album],
    });
    await new Promise((r) => setTimeout(r, 120));
  } catch (_) {}
}

/** Prefer the URL the page actually loaded (query tokens, resource timing) over bare context-menu srcUrl. */
async function eromeResolveUrlFromActiveTab(tabId, requestedUrl) {
  const stem = eromeMediaStemFromUrl(requestedUrl);
  if (tabId == null || tabId < 0 || !stem) return requestedUrl;
  try {
    const tab = await chrome.tabs.get(tabId);
    if (!tab || !tab.url || !isEromeHost(new URL(tab.url).hostname)) return requestedUrl;
    const inj = await chrome.scripting.executeScript({
      target: { tabId },
      func: (mediaStem, requested) => {
        var out = [];
        var seen = {};
        function add(u) {
          if (!u || seen[u]) return;
          if (u.indexOf("http") !== 0) return;
          seen[u] = 1;
          out.push(u);
        }
        try {
          var vids = document.querySelectorAll("video");
          for (var i = 0; i < vids.length; i++) {
            if (vids[i].currentSrc) add(vids[i].currentSrc);
            if (vids[i].src && vids[i].src.indexOf("http") === 0) add(vids[i].src);
          }
        } catch (_) {}
        try {
          var entries = performance.getEntriesByType("resource");
          for (var j = 0; j < entries.length; j++) {
            var n = entries[j] && entries[j].name;
            if (n && /\.(mp4|webm|m4v|mov)(\?|$)/i.test(n.split("?")[0])) add(n);
          }
        } catch (_) {}
        var stemLo = (mediaStem || "").toLowerCase();
        var reqLo = (requested || "").toLowerCase();
        var matches = out.filter(function (u) {
          var ul = u.toLowerCase();
          return ul.indexOf(stemLo) >= 0 || (reqLo && ul.split("?")[0] === reqLo.split("?")[0]);
        });
        if (!matches.length && stemLo) {
          var prefix = stemLo.split("_")[0];
          if (prefix.length >= 4) {
            matches = out.filter(function (u) {
              return u.toLowerCase().indexOf(prefix) >= 0;
            });
          }
        }
        if (!matches.length) return requested;
        matches.sort(function (a, b) {
          function score(s) {
            var x = s.toLowerCase();
            var sc = 0;
            if (x.indexOf(stemLo) >= 0) sc += 40;
            if (x.indexOf("1080") >= 0 || x.indexOf("2160") >= 0) sc += 16;
            if (x.indexOf("720") >= 0) sc += 8;
            if (x.indexOf("?") >= 0) sc += 5;
            return sc;
          }
          return score(b) - score(a);
        });
        return matches[0];
      },
      args: [stem, requestedUrl],
    });
    const picked = inj && inj[0] && inj[0].result ? String(inj[0].result).trim() : "";
    if (picked && /^https?:\/\//i.test(picked) && isEromeMediaUrl(picked)) return picked;
  } catch (_) {}
  return requestedUrl;
}

async function eromeResolveAlternateMediaUrls(primaryUrl, eromeChain, cookieHeader, tabId) {
  const stem = eromeMediaStemFromUrl(primaryUrl);
  const out = [];
  const seen = new Set([primaryUrl]);
  const push = (u) => {
    const t = String(u || "").trim();
    if (!t || !/^https?:\/\//i.test(t) || !isEromeMediaUrl(t) || seen.has(t)) return;
    seen.add(t);
    out.push(t);
  };
  if (tabId != null) {
    const fromTab = await eromeResolveUrlFromActiveTab(tabId, primaryUrl);
    push(fromTab);
  }
  const album = (eromeChain || []).find((u) => /\/a\/[^/]+/i.test(u));
  if (album) {
    try {
      const ua = await getBrowserUserAgent(tabId);
      const base = cookieHeader ? { Cookie: cookieHeader } : {};
      const res = await fetch(album, {
        method: "GET",
        credentials: "omit",
        headers: {
          ...base,
          ...sessionFetchHeaders("https://www.erome.com/", album, ua, {}),
          Accept: "text/html,application/xhtml+xml,*/*;q=0.8",
        },
      });
      if (res.ok) {
        const html = await res.text();
        const urls = eromeExtractMediaUrlsFromHtml(html);
        urls.sort((a, b) => eromeScoreMediaUrl(b, stem) - eromeScoreMediaUrl(a, stem));
        for (const u of urls) push(u);
        const parsed = parseEromeMediaFromHtml(html);
        if (parsed) push(parsed);
      }
    } catch (_) {}
  }
  return out;
}

/** Refresh album-page cookies before CDN GET (helps after rapid back-to-back imports). */
async function warmEromeAlbumCookies(chain, cookieHeader, mediaUrl, userAgent) {
  const album = chain.find((u) => /\/a\/[^/]+/i.test(u));
  if (!album) return;
  const now = Date.now();
  const prev = _eromeWarmAt.get(album);
  if (prev != null && now - prev < 45000) return;
  _eromeWarmAt.set(album, now);
  const base = cookieHeader ? { Cookie: cookieHeader } : {};
  const warmHeaders = {
    ...base,
    ...sessionFetchHeaders("https://www.erome.com/", album, userAgent, {}),
    Accept: "text/html,application/xhtml+xml,*/*;q=0.8",
  };
  try {
    await fetchWithTimeout(album, { method: "GET", credentials: "omit", headers: warmHeaders }, 45000);
  } catch (_) {}
}

function fetchConcurrencyForUrls(urls) {
  if (Array.isArray(urls) && urls.some((u) => isEromeMediaUrl(u))) return 1;
  return TBCC_FETCH_CONCURRENCY;
}

async function fetchEromeCdnOnce(targetUrl, eromeChain, cookieHeader, userAgent) {
  await warmEromeAlbumCookies(eromeChain, cookieHeader, targetUrl, userAgent);
  const base = cookieHeader ? { Cookie: cookieHeader } : {};
  const timeoutMs = tbccFetchTimeoutMs(targetUrl);
  const backoffMs = [0, 800, 2000];
  let lastStatus = 403;
  for (let attempt = 0; attempt < backoffMs.length; attempt++) {
    if (backoffMs[attempt] > 0) await new Promise((r) => setTimeout(r, backoffMs[attempt]));
    for (const ref of eromeChain) {
      const hdr = {
        ...base,
        ...sessionFetchHeaders(ref, targetUrl, userAgent, {}),
      };
      let res = await fetchWithTimeout(
        targetUrl,
        { method: "GET", credentials: "omit", headers: hdr },
        timeoutMs
      );
      if (res.ok) return await res.arrayBuffer();
      lastStatus = res.status;
      res = await fetchWithTimeout(
        targetUrl,
        {
          method: "GET",
          credentials: "omit",
          headers: {
            ...base,
            ...sessionFetchHeaders(ref, targetUrl, userAgent, { origin: "https://www.erome.com" }),
          },
        },
        timeoutMs
      );
      if (res.ok) return await res.arrayBuffer();
      lastStatus = res.status;
    }
  }
  return { failed: true, status: lastStatus };
}

async function fetchEromeCdnWithRetries(url, eromeChain, cookieHeader, refererPageUrl, tabId) {
  const ua = await getBrowserUserAgent(tabId);
  await tbccPrewarmEromeTab(tabId, eromeChain);
  cookieHeader = await mergeEromeCookieHeader(eromeChain, url);

  const album = eromeChain.find((u) => /\/a\/[^/]+/i.test(u));
  const candidates = [url];
  let lastStatus = 403;

  for (let pass = 0; pass < 2; pass++) {
    for (const targetUrl of candidates) {
      const chain = eromeReferrerChain(targetUrl, refererPageUrl) || eromeChain;
      const albumForTab = chain.find((u) => /\/a\/[^/]+/i.test(u)) || album;
      const pageRef = refererPageUrl || albumForTab || "";
      if (tabId != null && pageRef) {
        const fromTab = await fetchMediaBytesFromTab(tabId, targetUrl, pageRef);
        if (fromTab instanceof ArrayBuffer && fromTab.byteLength > 0) return fromTab;
      }
      if (tabId != null && albumForTab) {
        const fromTab = await fetchEromeBytesFromTab(tabId, targetUrl, albumForTab);
        if (fromTab instanceof ArrayBuffer && fromTab.byteLength > 0) return fromTab;
      }
      const cookies = await mergeEromeCookieHeader(chain, targetUrl);
      const result = await fetchEromeCdnOnce(targetUrl, chain, cookies, ua);
      if (result instanceof ArrayBuffer) return result;
      if (result && result.failed && result.status) lastStatus = result.status;
    }
    if (pass > 0) break;
    const alternates = await eromeResolveAlternateMediaUrls(url, eromeChain, cookieHeader, tabId);
    for (const alt of alternates) {
      if (!candidates.includes(alt)) candidates.push(alt);
    }
    if (candidates.length <= 1) break;
  }

  if (lastStatus === 403 && album) {
    await tbccOpenEromeAlbumTab(album);
  }

  let rateHint =
    lastStatus === 403
      ? " Do NOT clear Erome cookies — that removes the 18+ session. Open the album tab, click Enter/18+, play the video, then right-click the video again."
      : "";
  if (lastStatus === 403) {
    rateHint += " If the first video worked and the second failed, wait a few seconds and retry.";
  }
  try {
    const badRef = String(refererPageUrl || "").split("#")[0];
    if (badRef && /^https?:\/\//i.test(badRef) && !isEromeHost(new URL(badRef).hostname)) {
      rateHint +=
        " Your active tab is not Erome — use the album tab TBCC just opened (or already had open).";
    }
  } catch (_) {}
  const albumHint = album ? ` Album: ${album}` : "";
  throw new Error(
    "Erome CDN " +
      lastStatus +
      " — blocked download." +
      rateHint +
      albumHint
  );
}

async function fetchUrlWithBrowserSession(url, refererPageUrl, tabId, opts) {
  const stallMs = opts && opts.stallTimeoutMs ? Math.max(2000, Number(opts.stallTimeoutMs)) : 0;
  const readBody = async (res) =>
    stallMs > 0 ? readResponseArrayBufferWithStall(res, stallMs) : await res.arrayBuffer();
  const eromeChain = eromeReferrerChain(url, refererPageUrl);
  let cookieHeader = "";
  if (eromeChain) {
    await tbccPrewarmEromeTab(tabId, eromeChain);
    cookieHeader = await mergeEromeCookieHeader(eromeChain, url);
  } else {
    try {
      const u0 = new URL(url);
      const h0 = (u0.hostname || "").toLowerCase();
      if (h0.includes("fetlife")) {
        cookieHeader = await mergeCookiesForUrls([url, "https://fetlife.com/"]);
      } else if (h0 === "nudostar.com" || h0.endsWith(".nudostar.com")) {
        cookieHeader = await mergeCookiesForUrls([url, "https://nudostar.com/forum/", "https://nudostar.com/"]);
      } else if (h0 === "video.twimg.com") {
        const twUrls = [url, "https://x.com/", "https://twitter.com/"];
        const ref = String(refererPageUrl || "").trim().split("#")[0];
        if (ref && /^https?:\/\//i.test(ref)) twUrls.push(ref);
        cookieHeader = await mergeCookiesForUrls(twUrls);
      } else {
        cookieHeader = (await chrome.cookies.getAll({ url })).map((c) => `${c.name}=${c.value}`).join("; ");
      }
    } catch (_) {}
  }
  const base = {};
  if (cookieHeader) base.Cookie = cookieHeader;

  if (eromeChain) {
    return enqueueEromeFetch(() =>
      fetchEromeCdnWithRetries(url, eromeChain, cookieHeader, refererPageUrl, tabId)
    );
  }

  try {
    const u = new URL(url);
    const h = u.hostname.toLowerCase();
    if (h === "nudostar.com" || h.endsWith(".nudostar.com")) {
      const refs = [];
      const addRef = (s) => {
        const t = String(s || "").trim();
        if (!t || refs.includes(t)) return;
        refs.push(t);
      };
      if (refererPageUrl) {
        try {
          const rp = new URL(String(refererPageUrl).split("#")[0]);
          const rh = rp.hostname.toLowerCase();
          if (rh === "nudostar.com" || rh.endsWith(".nudostar.com")) addRef(rp.toString());
        } catch (_) {}
      }
      addRef(`${u.protocol}//${u.hostname}/forum/`);
      addRef(`${u.protocol}//${u.hostname}/`);
      addRef("https://nudostar.com/forum/");
      addRef("https://nudostar.com/");
      for (const ref of refs) {
        try {
          let res = await fetch(url, { method: "GET", credentials: "omit", headers: { ...base, Referer: ref } });
          if (res.ok) return await readBody(res);
          res = await fetch(url, {
            method: "GET",
            credentials: "omit",
            headers: { ...base, Referer: ref, Origin: `${u.protocol}//${u.hostname}` },
          });
          if (res.ok) return await readBody(res);
        } catch (_) {}
      }
    }
    if (isFapelloHost(h)) {
      const refs = [];
      const addRef = (s) => {
        const t = String(s || "").trim().split("#")[0];
        if (t && /^https?:\/\//i.test(t) && !refs.includes(t)) refs.push(t);
      };
      addRef(refererPageUrl);
      addRef(fapelloProfileRefererFromMediaUrl(url));
      addRef(`${u.protocol}//${u.hostname}/`);
      if (tabId != null) {
        for (const ref of refs) {
          if (!ref) continue;
          const fromTab = await fetchMediaBytesFromTab(tabId, url, ref);
          if (fromTab instanceof ArrayBuffer && fromTab.byteLength > 256) return fromTab;
        }
      }
      for (const ref of refs) {
        try {
          let res = await fetch(url, { method: "GET", credentials: "omit", headers: { ...base, Referer: ref } });
          if (res.ok) return await readBody(res);
          res = await fetch(url, {
            method: "GET",
            credentials: "omit",
            headers: { ...base, Referer: ref, Origin: new URL(ref).origin },
          });
          if (res.ok) return await readBody(res);
        } catch (_) {}
      }
      throw new Error(
        "Fapello CDN blocked fetch — keep the profile tab open in Chrome, then retry ZIP download."
      );
    }
    /** Twitter / X: CDN rejects Referer https://video.twimg.com/ — must look like navigation from x.com.
     * Prefer no Cookie (signed amplify URLs); reject tiny bodies (CDN error stubs ~15 B). */
    if (h === "video.twimg.com" || h === "pbs.twimg.com") {
      const refs = [];
      const pushRef = (s) => {
        const t = String(s || "").trim().split("#")[0];
        if (t && /^https?:\/\//i.test(t) && !refs.includes(t)) refs.push(t);
      };
      pushRef(refererPageUrl);
      pushRef("https://x.com/");
      pushRef("https://twitter.com/");
      const expectVideo = h === "video.twimg.com" || /\.mp4(\?|#|$)/i.test(u.pathname);
      const minBytes = expectVideo ? 48 * 1024 : 256;
      const tryOnce = async (headers) => {
        const res = await fetch(url, {
          method: "GET",
          credentials: "omit",
          headers,
        });
        if (!res.ok) return null;
        const ab = await readBody(res);
        if (!ab || ab.byteLength < minBytes) return null;
        return ab;
      };
      for (const ref of refs) {
        try {
          const origin = new URL(ref).origin;
          // No Cookie first — matches chrome.downloads / XEnhancer path.
          let ab = await tryOnce({ Referer: ref, Origin: origin });
          if (ab) return ab;
          if (cookieHeader) {
            ab = await tryOnce({ ...base, Referer: ref, Origin: origin });
            if (ab) return ab;
          }
        } catch (_) {}
      }
      throw new Error(
        "Twitter / X video CDN blocked fetch — play the clip on X, tap Refresh in TBCC, then download the video.twimg.com tile (not a blob: entry)."
      );
    }
    if (h.includes("onlyfans.com")) base.Referer = "https://onlyfans.com/";
    else if (/(^|\.)fetlife\.com$/i.test(h) || h.includes("fetlife")) base.Referer = "https://fetlife.com/";
    else if (h.includes("motherless") || h.endsWith("motherlessmedia.com"))
      base.Referer = h.includes(".xxx") ? "https://motherless.xxx/" : "https://motherless.com/";
    else if (/(^|\.)coomer\.(st|party)$/.test(h) || /^n\d+\.coomer\.(st|party)$/i.test(h))
      base.Referer = "https://coomer.st/";
    else if (/(^|\.)kemono\.(party|su|si)$/.test(h) || /^n\d+\.kemono\.(party|su|si)$/i.test(h))
      base.Referer = "https://kemono.party/";
    else base.Referer = `${u.protocol}//${u.hostname}/`;
  } catch (_) {
    base.Referer = "https://www.erome.com/";
  }
  const res = await fetch(url, { method: "GET", credentials: "omit", headers: base });
  return await readBody(res);
}

function decodeHtmlAttr(s) {
  if (!s) return "";
  return String(s)
    .replace(/&amp;/g, "&")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">");
}

/**
 * Extract main image URL from a detail-page HTML (og/twitter + JSON-LD hints + main <img> fallbacks).
 * Used for motherless ?full pages and generic same-origin gallery detail URLs.
 */
function parseDetailPagePrimaryImageFromHtml(html) {
  if (!html || typeof html !== "string") return "";
  const tryMatch = (re) => {
    const m = html.match(re);
    return m && m[1] ? decodeHtmlAttr(m[1].trim()) : "";
  };
  let u =
    tryMatch(/property=["']og:image["'][^>]*content=["']([^"']+)["']/i) ||
    tryMatch(/content=["']([^"']+)["'][^>]*property=["']og:image["']/i) ||
    tryMatch(/property=["']og:image:url["'][^>]*content=["']([^"']+)["']/i) ||
    tryMatch(/name=["']twitter:image["'][^>]*content=["']([^"']+)["']/i) ||
    tryMatch(/name=["']twitter:image:src["'][^>]*content=["']([^"']+)["']/i) ||
    tryMatch(/link[^>]+rel=["']image_src["'][^>]*href=["']([^"']+)["']/i) ||
    tryMatch(/href=["']([^"']+)["'][^>]*rel=["']image_src["']/i);
  if (u && /^https?:\/\//i.test(u)) return u;
  if (u && u.startsWith("//")) return "https:" + u;
  const mJson = tryMatch(/"image"\s*:\s*"([^"]+\.(?:jpe?g|png|gif|webp)[^"]*)"/i);
  if (mJson && /^https?:\/\//i.test(mJson)) return mJson;
  const m2 = html.match(
    /<img[^>]+(?:class|id)=["'][^"']*(?:static|media|full|main|photo|large|content|picture|wp-image|attachment|original|size-full)[^"']*["'][^>]*src=["']([^"']+\.(?:jpe?g|png|gif|webp)[^"']*)["']/i
  );
  if (m2 && m2[1]) {
    const u2 = decodeHtmlAttr(m2[1].trim());
    if (/^https?:\/\//i.test(u2)) return u2;
    if (u2.startsWith("//")) return "https:" + u2;
  }
  const m3 = html.match(
    /<img[^>]+src=["']([^"']+\.(?:jpe?g|png|gif|webp)[^"']*)["'][^>]*(?:class|id)=["'][^"']*(?:static|media|full|main|photo|large|content)[^"']*["']/i
  );
  if (m3 && m3[1]) {
    const u2 = decodeHtmlAttr(m3[1].trim());
    if (/^https?:\/\//i.test(u2)) return u2;
    if (u2.startsWith("//")) return "https:" + u2;
  }
  const m4 = html.match(
    /<img[^>]+(?:class|id)=["'][^"']*(?:static|media|full|main)[^"']*["'][^>]*src=["']([^"']+\.(?:jpe?g|png|gif|webp)[^"']*)["']/i
  );
  if (m4 && m4[1]) {
    const u2 = decodeHtmlAttr(m4[1].trim());
    if (/motherless|motherlessmedia|cdn/i.test(u2)) return u2.startsWith("//") ? "https:" + u2 : u2;
  }
  return "";
}

function redgifsIdFromDetailUrl(detailUrl) {
  try {
    const u = new URL(detailUrl);
    if (!/(^|\.)redgifs\.com$/i.test(u.hostname)) return "";
    const m = (u.pathname || "").match(/^\/(?:watch|ifr|gifs)\/([^/?#]+)/i);
    return m && m[1] ? String(m[1]).trim() : "";
  } catch (_) {
    return "";
  }
}

function redgifsIdFromAnyUrl(rawUrl) {
  try {
    const s = String(rawUrl || "");
    const m = s.match(/(?:\/(?:watch|ifr|gifs)\/)([a-z0-9]+)/i);
    if (m && m[1]) return String(m[1]).trim();
    try {
      const u = new URL(s);
      const base = (u.pathname.split("/").pop() || "").trim();
      if (base) {
        const b = base.split("?")[0].split("#")[0];
        const p1 = b.match(/^([a-z0-9]+)-(?:mobile|poster|thumb|thumbnail|small|large)\.(?:jpe?g|png|webp|avif)$/i);
        if (p1 && p1[1]) return String(p1[1]).trim();
        const p2 = b.match(/^([a-z0-9]+)\.(?:jpe?g|png|webp|avif|gif|mp4|webm)$/i);
        if (p2 && p2[1]) return String(p2[1]).trim();
      }
    } catch (_) {}
  } catch (_) {}
  return "";
}

/**
 * RedGIF pages often include stream URLs in escaped JSON blobs.
 * Prefer direct MP4 over posters (.webp/.jpg), and prefer HD when available.
 */
function parseRedgifsMediaFromHtml(html) {
  if (!html || typeof html !== "string") return "";
  const flat = html.replace(/\\\//g, "/").replace(/&amp;/g, "&");
  const candidates = [];
  const re = /https?:\/\/[^\s"'<>]+?\.(?:mp4|webm|m4v|m3u8|mpd)(?:\?[^\s"'<>]*)?/gi;
  let m;
  while ((m = re.exec(flat)) !== null) {
    const u = String(m[0] || "").trim();
    if (!/^https?:\/\//i.test(u)) continue;
    candidates.push(u);
  }
  const uniq = [...new Set(candidates)];
  const score = (u) => {
    const s = String(u || "").toLowerCase();
    let sc = 0;
    if (s.includes("redgifs")) sc += 50;
    if (s.includes(".mp4")) sc += 52;
    if (s.includes(".webm")) sc += 30;
    if (s.includes(".m3u8")) sc += 22;
    if (s.includes("/hd.") || s.includes("-hd.") || s.includes("hd.mp4")) sc += 30;
    if (s.includes("/sd.") || s.includes("-sd.") || s.includes("sd.mp4")) sc += 18;
    if (s.includes("1080") || s.includes("2160") || s.includes("4k")) sc += 14;
    if (s.includes("poster") || s.includes("thumb") || s.includes("preview") || s.includes("sprite")) sc -= 80;
    if (s.includes(".webp") || s.includes(".jpg") || s.includes(".jpeg") || s.includes(".png")) sc -= 120;
    return sc;
  };
  uniq.sort((a, b) => score(b) - score(a));
  const best = uniq[0] || "";
  if (best && score(best) >= 16) return best;
  return "";
}

async function fetchRedgifsTemporaryToken() {
  const now = Date.now();
  if (tbccRedgifsTempToken && tbccRedgifsTempTokenExpiresAt > now + 15000) return tbccRedgifsTempToken;
  const res = await fetch("https://api.redgifs.com/v2/auth/temporary", {
    method: "GET",
    credentials: "omit",
    headers: { Accept: "application/json" },
  });
  if (!res.ok) throw new Error(`RedGIF token HTTP ${res.status}`);
  const data = await res.json();
  const token = data && data.token ? String(data.token) : "";
  if (!token) throw new Error("RedGIF token missing");
  tbccRedgifsTempToken = token;
  tbccRedgifsTempTokenExpiresAt = now + 5 * 60 * 1000;
  return token;
}

async function fetchRedgifsMediaViaApi(detailUrl) {
  const gifId = redgifsIdFromDetailUrl(detailUrl) || redgifsIdFromAnyUrl(detailUrl);
  if (!gifId) return "";
  try {
    const token = await fetchRedgifsTemporaryToken();
    const res = await fetch(`https://api.redgifs.com/v2/gifs/${encodeURIComponent(gifId)}`, {
      method: "GET",
      credentials: "omit",
      headers: { Accept: "application/json", Authorization: `Bearer ${token}` },
    });
    if (!res.ok) return "";
    const data = await res.json();
    const gif = data && data.gif ? data.gif : {};
    const urls = gif && gif.urls ? gif.urls : {};
    const picks = [urls.hd, urls.sd, urls.gif, urls.vthumbnail, urls.thumbnail]
      .map((u) => (typeof u === "string" ? u.trim() : ""))
      .filter(Boolean);
    for (const u of picks) {
      if (/\.(mp4|webm|m4v|m3u8|mpd)(\?|$)/i.test(u)) return u;
    }
    return "";
  } catch (_) {
    return "";
  }
}

/**
 * FetLife video pages embed escaped MP4/M3U8 URLs in JSON; og:video is often empty.
 * Prefer CDN URLs; ignore obvious preview/thumb paths.
 */
function parseFetlifeStreamFromHtml(html) {
  if (!html || typeof html !== "string") return "";
  const flat = html.replace(/\\\//g, "/");
  const candidates = [];
  const re = /https?:\/\/[^\s"'<>]+?\.(?:mp4|webm|m4v|m3u8)(?:\?[^\s"'<>]*)?/gi;
  let m;
  while ((m = re.exec(flat)) !== null) {
    let u = m[0].replace(/&amp;/g, "&");
    if (!/^https?:\/\//i.test(u)) continue;
    candidates.push(u);
  }
  const uniq = [...new Set(candidates)];
  const score = (u) => {
    const s = u.toLowerCase();
    let sc = 0;
    if (s.includes("fetlife") || s.includes("cloudfront") || s.includes("fetlifecdn")) sc += 55;
    if (s.includes(".mp4")) sc += 42;
    if (s.includes(".webm")) sc += 38;
    if (s.includes(".m3u8")) sc += 22;
    if (s.includes("1080") || s.includes("2160") || s.includes("4k")) sc += 20;
    if (s.includes("720")) sc += 10;
    if (s.includes("thumb") || s.includes("preview") || s.includes("sprite") || s.includes("poster")) sc -= 55;
    return sc;
  };
  uniq.sort((a, b) => score(b) - score(a));
  const best = uniq[0];
  if (!best || score(best) < 12) return "";
  return best;
}

/**
 * Erome album pages can expose direct media via script JSON/escaped URLs while <video src> may be blob: at runtime.
 * Parse HTML for likely CDN stream URLs and prefer highest-quality candidates.
 */
function parseEromeMediaFromHtml(html) {
  if (!html || typeof html !== "string") return "";
  const flat = html.replace(/\\\//g, "/");
  const candidates = [];
  const re = /https?:\/\/[^\s"'<>]+?\.(?:mp4|webm|m4v|m3u8|mpd)(?:\?[^\s"'<>]*)?/gi;
  let m;
  while ((m = re.exec(flat)) !== null) {
    const u = String(m[0] || "").replace(/&amp;/g, "&");
    if (!/^https?:\/\//i.test(u)) continue;
    candidates.push(u);
  }
  const uniq = [...new Set(candidates)];
  const score = (u) => {
    const s = String(u || "").toLowerCase();
    let sc = 0;
    if (s.includes("erome")) sc += 38;
    if (s.includes(".m3u8")) sc += 55;
    if (s.includes(".mpd")) sc += 52;
    if (s.includes(".mp4")) sc += 42;
    if (s.includes("full")) sc += 18;
    if (s.includes("1080") || s.includes("2160") || s.includes("4k")) sc += 16;
    if (s.includes("720")) sc += 8;
    if (s.includes("thumb") || s.includes("poster") || s.includes("preview") || s.includes("sprite")) sc -= 60;
    return sc;
  };
  uniq.sort((a, b) => score(b) - score(a));
  const best = uniq[0] || "";
  if (!best || score(best) < 10) return "";
  return best;
}

/** Prefer direct video URL on ?full pages, then full-size image. */
function parseMotherlessMediaFromHtml(html) {
  if (!html || typeof html !== "string") return "";
  const tryMatch = (re) => {
    const m = html.match(re);
    return m && m[1] ? decodeHtmlAttr(m[1].trim()) : "";
  };
  let v =
    tryMatch(/property=["']og:video:url["'][^>]*content=["']([^"']+)["']/i) ||
    tryMatch(/property=["']og:video:secure_url["'][^>]*content=["']([^"']+)["']/i) ||
    tryMatch(/property=["']og:video["'][^>]*content=["']([^"']+)["']/i) ||
    tryMatch(/<video[^>]+src=["']([^"']+\.(?:mp4|webm|m4v)[^"']*)["']/i) ||
    tryMatch(/<source[^>]+src=["']([^"']+\.(?:mp4|webm|m4v)[^"']*)["']/i);
  if (v) {
    if (/^https?:\/\//i.test(v)) return v;
    if (v.startsWith("//")) return "https:" + v;
  }
  return parseDetailPagePrimaryImageFromHtml(html);
}

function coomerApiUrlFromPostPageUrl(postPageUrl) {
  try {
    const u = new URL(postPageUrl);
    const m = u.pathname.match(/^\/([^/]+)\/user\/([^/]+)\/post\/(\d+)\/?$/);
    if (!m) return "";
    return `${u.origin}/api/v1/${m[1]}/user/${encodeURIComponent(m[2])}/post/${m[3]}`;
  } catch (_) {
    return "";
  }
}

function coomerFullUrlsFromPostJson(data) {
  if (!data || typeof data !== "object") return [];
  const post = data.post;
  if (!post || typeof post !== "object") return [];
  const previews = Array.isArray(data.previews) ? data.previews : [];
  const pathToServer = new Map();
  for (const p of previews) {
    if (p && p.path && p.server) pathToServer.set(p.path, String(p.server).replace(/\/$/, ""));
  }
  function dataUrlForFile(f) {
    if (!f || !f.path) return "";
    const path = f.path.startsWith("/") ? f.path : "/" + f.path;
    let srv = pathToServer.get(f.path) || pathToServer.get(path);
    if (!srv && previews[0] && previews[0].server) srv = String(previews[0].server).replace(/\/$/, "");
    if (!srv) return "";
    return srv + "/data" + path;
  }
  const urls = [];
  if (post.file) {
    const u = dataUrlForFile(post.file);
    if (u) urls.push(u);
  }
  const att = post.attachments;
  if (Array.isArray(att)) {
    for (const a of att) {
      const u = dataUrlForFile(a);
      if (u) urls.push(u);
    }
  }
  const vids = data.videos;
  if (Array.isArray(vids)) {
    for (const v of vids) {
      if (typeof v === "string" && /^https?:\/\//i.test(v)) urls.push(v);
      else if (v && typeof v === "object" && v.path) {
        const u = dataUrlForFile(v);
        if (u) urls.push(u);
      }
    }
  }
  return [...new Set(urls)];
}

async function fetchCoomerPostJson(postPageUrl) {
  const apiUrl = coomerApiUrlFromPostPageUrl(postPageUrl);
  if (!apiUrl) throw new Error("Invalid coomer post URL");
  const origin = (() => {
    try {
      return new URL(postPageUrl).origin;
    } catch (_) {
      return "https://coomer.st";
    }
  })();
  const cookieHeader = await mergeCookiesForUrls([postPageUrl, `${origin}/`]);
  const headers = {
    Accept: "text/css",
    "User-Agent":
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    Referer: String(postPageUrl).split("#")[0],
  };
  if (cookieHeader) headers.Cookie = cookieHeader;
  const res = await fetch(apiUrl, { method: "GET", credentials: "omit", headers });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return await res.json();
}


function tbccIsMotherlessHostName(hostname) {
  return /(^|\.)motherless\.(com|xxx)$/i.test(String(hostname || ""));
}

function tbccIsMotherlessGalleryPageUrl(raw) {
  try {
    const u = new URL(String(raw || "").trim());
    if (!tbccIsMotherlessHostName(u.hostname)) return false;
    const path = u.pathname.replace(/\/+$/, "") || "/";
    // /G2949A47, /G2949A47/ITEM, /gallery/…
    if (/^\/G[A-Za-z0-9]{4,}(\/|$)/i.test(path)) return true;
    if (/^\/gallery\//i.test(path)) return true;
    return false;
  } catch (_) {
    return false;
  }
}

/**
 * Collect Motherless gallery media ids from the open tab (nested /Gxxx/MEDIA or /MEDIA links).
 */
async function tbccCollectMotherlessGalleryMediaFromTab(tabId) {
  if (tabId == null) return { ok: false, error: "No tab", items: [] };
  try {
    await chrome.scripting.executeScript({
      target: { tabId },
      files: ["capture.js"],
    });
  } catch (_) {}
  const inj = await chrome.scripting.executeScript({
    target: { tabId },
    func: () => {
      const reserved = {
        g: 1,
        images: 1,
        groups: 1,
        videos: 1,
        search: 1,
        members: 1,
        login: 1,
        register: 1,
        upload: 1,
        rules: 1,
        privacy: 1,
        dmca: 1,
        help: 1,
        faq: 1,
        about: 1,
        contact: 1,
        categories: 1,
        tags: 1,
        boards: 1,
        store: 1,
        chat: 1,
        galleries: 1,
        shouts: 1,
        girls: 1,
        porn: 1,
      };
      const path = (location.pathname || "").replace(/\/+$/, "");
      const galleryMatch = path.match(/^\/(G[A-Za-z0-9]{4,})/i);
      const galleryId = galleryMatch ? galleryMatch[1].toUpperCase() : "";
      const out = [];
      const seen = new Set();
      const pushId = (mediaId, href, thumb) => {
        const id = String(mediaId || "").trim();
        if (!id || id.length < 4) return;
        if (reserved[id.toLowerCase()]) return;
        // Skip bare gallery root id (G…) when it matches this gallery
        if (galleryId && id.toUpperCase() === galleryId) return;
        if (/^G[A-Za-z0-9]{4,}$/i.test(id) && !href.includes("/" + id + "/") && href.replace(/\/+$/, "").endsWith("/" + id)) {
          // likely another gallery card — skip
          if (/^G/i.test(id)) return;
        }
        const key = id.toUpperCase();
        if (seen.has(key)) return;
        seen.add(key);
        const detailUrl = location.origin + "/" + id + "?full";
        out.push({
          mediaId: id,
          motherlessDetailUrl: detailUrl,
          url: thumb || detailUrl,
          mediaType: "image",
          source: "motherless:gallery",
        });
      };
      document.querySelectorAll("a[href]").forEach((a) => {
        let href = a.getAttribute("href") || "";
        try {
          href = new URL(href, location.href).pathname;
        } catch (_) {
          return;
        }
        // /Gxxx/MEDIAID or /MEDIAID
        let m = href.match(/^\/(G[A-Za-z0-9]{4,})\/([A-Za-z0-9]{4,})\/?$/i);
        if (m) {
          pushId(m[2], href, (a.querySelector("img") && a.querySelector("img").src) || "");
          return;
        }
        m = href.match(/^\/([A-Za-z0-9]{6,})\/?$/i);
        if (m) {
          const id = m[1];
          if (/^G/i.test(id)) return; // gallery hub cards
          pushId(id, href, (a.querySelector("img") && a.querySelector("img").src) || "");
        }
      });
      // thumbnail containers with data-codename
      document.querySelectorAll("[data-image-view-modal-codename], [data-codename]").forEach((el) => {
        const id = el.getAttribute("data-image-view-modal-codename") || el.getAttribute("data-codename") || "";
        if (/^[A-Za-z0-9]{4,}$/.test(id) && !/^G/i.test(id)) {
          const img = el.querySelector && el.querySelector("img");
          pushId(id, "/" + id, (img && img.src) || "");
        }
      });
      return {
        ok: true,
        galleryId,
        pageUrl: location.href.split("#")[0],
        items: out,
      };
    },
  });
  const res = inj && inj[0] && inj[0].result;
  if (!res || !res.ok) return { ok: false, error: "Collect failed", items: [] };
  return res;
}

async function tbccResolveMotherlessDetailUrls(detailUrls) {
  const unique = [...new Set((detailUrls || []).filter(Boolean))];
  const map = {};
  const CONC = 4;
  for (let i = 0; i < unique.length; i += CONC) {
    const chunk = unique.slice(i, i + CONC);
    await Promise.all(
      chunk.map(async (du) => {
        try {
          const html = await fetchMotherlessHtml(du);
          const media = parseMotherlessMediaFromHtml(html);
          if (media) map[du] = media;
        } catch (e) {
          console.warn("tbccResolveMotherlessDetailUrls", du, e);
        }
      })
    );
  }
  return map;
}

/**
 * mode: "zip" | "download"
 */
async function tbccMotherlessGalleryBulkFromTab(tab, mode) {
  if (!tab || tab.id == null) throw new Error("No tab");
  const pageUrl = String(tab.url || "").trim();
  if (!tbccIsMotherlessGalleryPageUrl(pageUrl)) {
    throw new Error("Open a Motherless gallery page (/G… ) first.");
  }
  notify("TBCC Motherless", mode === "zip" ? "Collecting gallery for ZIP…" : "Collecting gallery for download…");
  const collected = await tbccCollectMotherlessGalleryMediaFromTab(tab.id);
  const rawItems = (collected && collected.items) || [];
  if (!rawItems.length) throw new Error("No media found on this gallery page.");

  const detailUrls = rawItems.map((it) => it.motherlessDetailUrl).filter(Boolean);
  notify("TBCC Motherless", `Resolving ${detailUrls.length} media URL(s)…`);
  const map = await tbccResolveMotherlessDetailUrls(detailUrls);

  const items = [];
  const seen = new Set();
  for (const it of rawItems) {
    const resolved = map[it.motherlessDetailUrl];
    if (!resolved || seen.has(resolved)) continue;
    seen.add(resolved);
    const isVideo = /\.(mp4|webm|mov|m4v)(\?|$)/i.test(resolved);
    items.push({
      url: resolved,
      thumbUrl: it.url && it.url !== it.motherlessDetailUrl ? it.url : undefined,
      mediaType: isVideo ? "video" : "image",
      tagName: isVideo ? "video" : "img",
      source: "motherless:gallery",
      width: 0,
      height: 0,
      naturalWidth: 0,
      naturalHeight: 0,
      tbccZipProfileName: collected.galleryId || "motherless",
    });
  }
  if (!items.length) throw new Error("Could not resolve any full media URLs (login/CDN?).");

  const mergePayload = {
    action: "tbcc-gallery-merge-harvest",
    items,
    sourceUrl: collected.pageUrl || pageUrl,
    adapter: "motherless-gallery",
    autoZip: mode === "zip",
    autoDownload: mode === "download",
    mergeId: "mlg-" + Date.now() + "-" + Math.random().toString(36).slice(2, 8),
    selectAll: true,
    sourceTabId: tab.id,
  };

  tbccTryOpenGallerySidePanelSync(tab);
  try {
    await chrome.storage.session.set({ tbccPendingGalleryMerge: mergePayload });
  } catch (_) {}
  tbccPostGalleryPanelMessage(mergePayload);

  notify(
    "TBCC Motherless",
    mode === "zip"
      ? `ZIP packing ${items.length} file(s) — check gallery panel.`
      : `Downloading ${items.length} file(s) — check gallery panel.`
  );
  return { ok: true, count: items.length, galleryId: collected.galleryId || "" };
}

async function fetchMotherlessHtml(detailUrl) {
  let u = detailUrl.trim();
  if (u.indexOf("?") < 0) u = `${u}?full`;
  else if (u.toLowerCase().indexOf("full") < 0) u = `${u}${u.includes("?") ? "&" : "?"}full`;
  const cookieHeader = await mergeCookiesForUrls([
    u,
    "https://motherless.com/",
    "https://www.motherless.com/",
    "https://motherless.xxx/",
    "https://www.motherless.xxx/",
  ]);
  let referer = "https://motherless.com/";
  try {
    if (/\.xxx$/i.test(new URL(u).hostname || "")) referer = "https://motherless.xxx/";
  } catch (_) {}
  const headers = {
    Accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    Referer: referer,
    "User-Agent":
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
  };
  if (cookieHeader) headers.Cookie = cookieHeader;
  const res = await fetch(u, { method: "GET", credentials: "omit", headers });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return await res.text();
}

/** Generic same-origin gallery detail page (no ?full — used for nudogram-style /photo/… links). */
async function fetchDetailPageHtml(detailUrl) {
  try {
    const u = detailUrl.trim();
    const cookieHeader = await mergeCookiesForUrls([u]);
    const headers = {
      Accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
      "User-Agent":
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    };
    try {
      const uo = new URL(u);
      headers.Referer = `${uo.protocol}//${uo.hostname}/`;
    } catch (_) {}
    if (cookieHeader) headers.Cookie = cookieHeader;
    const res = await fetch(u, { method: "GET", credentials: "omit", headers });
    if (!res.ok) return null;
    return await res.text();
  } catch (_) {
    return null;
  }
}

function blobNameAndTypeForUrl(url) {
  try {
    const path = new URL(url).pathname.toLowerCase();
    const att = path.match(/-(jpe?g|jpg|png|gif|webp|avif|bmp|mp4|webm|mov|m4v|mkv)\.\d+\/?$/i);
    if (att && att[1]) {
      const ext = att[1].toLowerCase() === "jpeg" ? "jpg" : att[1].toLowerCase();
      if (ext === "jpg") return { name: "media.jpg", type: "image/jpeg" };
      if (ext === "png") return { name: "media.png", type: "image/png" };
      if (ext === "gif") return { name: "media.gif", type: "image/gif" };
      if (ext === "webp") return { name: "media.webp", type: "image/webp" };
      if (ext === "avif") return { name: "media.avif", type: "image/avif" };
      if (ext === "bmp") return { name: "media.bmp", type: "image/bmp" };
      if (ext === "mp4") return { name: "media.mp4", type: "video/mp4" };
      if (ext === "webm") return { name: "media.webm", type: "video/webm" };
      if (ext === "mov") return { name: "media.mov", type: "video/quicktime" };
      if (ext === "m4v") return { name: "media.m4v", type: "video/x-m4v" };
      if (ext === "mkv") return { name: "media.mkv", type: "video/x-matroska" };
    }
    if (path.endsWith(".mp4") || path.endsWith(".m4v")) return { name: "media.mp4", type: "video/mp4" };
    if (path.endsWith(".webm")) return { name: "media.webm", type: "video/webm" };
    if (path.endsWith(".mov")) return { name: "media.mov", type: "video/quicktime" };
    if (path.endsWith(".m3u8")) return { name: "playlist.m3u8", type: "application/vnd.apple.mpegurl" };
    if (path.endsWith(".mpd")) return { name: "manifest.mpd", type: "application/dash+xml" };
    if (path.endsWith(".gif")) return { name: "media.gif", type: "image/gif" };
    if (path.endsWith(".png")) return { name: "media.png", type: "image/png" };
    if (path.endsWith(".webp")) return { name: "media.webp", type: "image/webp" };
    if (path.endsWith(".jpg") || path.endsWith(".jpeg")) return { name: "media.jpg", type: "image/jpeg" };
  } catch (_) {}
  return { name: "media.jpg", type: "application/octet-stream" };
}

async function tbccPrepareImportArrayBuffer(arrayBuffer, url) {
  const { name, type } = blobNameAndTypeForUrl(url);
  if (typeof TbccWebp === "undefined" || !TbccWebp.tbccEnsureJpegArrayBuffer) {
    return { buffer: arrayBuffer, name, type };
  }
  const r = await TbccWebp.tbccEnsureJpegArrayBuffer(arrayBuffer, url, name);
  return {
    buffer: r.buffer,
    name: r.name,
    type: r.converted ? "image/jpeg" : type,
  };
}

async function postBytesToTbcc(arrayBuffer, url, poolId, savedOnly, source, caption, galleryJobId) {
  const prep = await tbccPrepareImportArrayBuffer(arrayBuffer, url);
  const form = new FormData();
  form.append("file", new Blob([prep.buffer], { type: prep.type }), prep.name);
  form.append("pool_id", String(poolId));
  form.append("saved_only", savedOnly ? "true" : "false");
  form.append("source", source || "extension:session-fetch");
  if (savedOnly && caption && String(caption).trim()) {
    form.append("caption", String(caption).trim());
  }
  return tbccPostImportForm(form, galleryJobId || null);
}

function shouldFallbackToSessionFetch(errorMsg) {
  return /403|forbidden|could not download|cookies|blocked|timeout|timed out|erome cdn/i.test(
    String(errorMsg || "")
  );
}

async function tryBackendSavedImport(body) {
  try {
    const resp = await tbccFetchApi("/import/url", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const text = await resp.text();
    let data = {};
    try {
      data = text ? JSON.parse(text) : {};
    } catch (_) {
      return { ok: false, fallback: true, error: resp.ok ? "Invalid server response." : `Server error ${resp.status}` };
    }
    if (data.status === "saved_only" && !data.error) {
      return { ok: true, data, fallback: false };
    }
    if (data.error) {
      return {
        ok: false,
        fallback: shouldFallbackToSessionFetch(data.error),
        error: String(data.error),
        data,
      };
    }
    return { ok: false, fallback: true, error: "Unexpected backend response", data };
  } catch (e) {
    return { ok: false, fallback: true, error: String(e && e.message ? e.message : e) };
  }
}

async function importViaExtensionBytes(
  url,
  poolId,
  savedOnly,
  source,
  caption,
  refererPageUrl,
  tabId,
  galleryJobId
) {
  url = normalizeTbccMediaUrlForImport(url);
  const ab = await fetchUrlWithBrowserSession(url, refererPageUrl, tabId);
  return postBytesToTbcc(ab, url, poolId, savedOnly, source, caption, galleryJobId);
}

/** Fetch multiple session URLs and POST to /import/saved-batch in chunks (Telegram albums ≤10). */
async function tbccResolveSessionTabId(sender, msg) {
  if (sender && sender.tab && sender.tab.id != null) return sender.tab.id;
  if (msg && msg.tabId != null) return msg.tabId;
  try {
    const got = await chrome.storage.local.get([STORAGE_GALLERY_DOCKED_TAB, STORAGE_LAST_TAB]);
    const dock = got[STORAGE_GALLERY_DOCKED_TAB];
    if (dock && dock.tabId != null) return dock.tabId;
    if (got[STORAGE_LAST_TAB] != null) return got[STORAGE_LAST_TAB];
  } catch (_) {}
  return null;
}

async function importViaExtensionBytesSavedBatch(urls, caption, tabId) {
  const cap = caption && String(caption).trim() ? String(caption).trim() : "";
  const parts = await fetchUrlsWithConcurrency(
    urls,
    async (url) => {
    let u = normalizeTbccMediaUrlForImport(url);
    if (isEromeMediaUrl(u) && tabId != null) u = await eromeResolveUrlFromActiveTab(tabId, u);
    const ab = await fetchUrlWithBrowserSession(u, "", tabId);
    const prep = await tbccPrepareImportArrayBuffer(ab, url);
    return { ab: prep.buffer, name: prep.name, type: prep.type };
  },
    fetchConcurrencyForUrls(urls)
  );
  for (let i = 0; i < parts.length; i += SAVED_ALBUM_CHUNK) {
    const chunk = parts.slice(i, i + SAVED_ALBUM_CHUNK);
    const form = new FormData();
    chunk.forEach((p, j) => {
      form.append("files", new Blob([p.ab], { type: p.type }), p.name || `media_${j}`);
    });
    if (cap) form.append("caption", cap);
    const r = await tbccFetchApi("/import/saved-batch", { method: "POST", body: form });
    const text = await r.text();
    let data = {};
    try {
      data = text ? JSON.parse(text) : {};
    } catch (_) {}
    if (!r.ok && !data.error) data.error = text ? text.slice(0, 200) : `HTTP ${r.status}`;
    if (data.error) return { error: data.error };
  }
  return { ok: true };
}

function tbccIsInjectableHttpUrl(url) {
  return url && typeof url === "string" && /^https?:\/\//i.test(url);
}

const STORAGE_USH_APPROVED_HOSTS = "tbccUsernameSearchApprovedHosts";
const STORAGE_USH_FAB_DENIED_HOSTS = "tbccUsernameSearchFabDeniedHosts";

function tbccNormalizeUshHost(hostname) {
  return String(hostname || "")
    .toLowerCase()
    .replace(/^www\./, "")
    .trim();
}

function tbccIsBuiltinUsernameSearchHost(hostname) {
  const h = tbccNormalizeUshHost(hostname);
  if (!h) return false;
  const roots = [
    "stripchat.com",
    "chaturbate.com",
    "onlyfans.com",
    "fansly.com",
    "instagram.com",
    "x.com",
    "twitter.com",
    "xhamsterlive.com",
    "cambb.xxx",
    "nudecams.xxx",
  ];
  return roots.some((r) => h === r || h.endsWith("." + r));
}

async function tbccUsernameSearchHostAllowed(url) {
  try {
    const host = tbccNormalizeUshHost(new URL(url).hostname);
    if (!host) return false;
    if (tbccIsBuiltinUsernameSearchHost(host)) return true;
    const d = await chrome.storage.local.get(STORAGE_USH_APPROVED_HOSTS);
    const arr = Array.isArray(d[STORAGE_USH_APPROVED_HOSTS]) ? d[STORAGE_USH_APPROVED_HOSTS] : [];
    return arr.map(tbccNormalizeUshHost).includes(host);
  } catch (_) {
    return false;
  }
}

async function tbccInjectUsernameSearchOverlay(tabId) {
  try {
    await chrome.scripting.executeScript({
      target: { tabId },
      files: ["tbcc-module-gate.js", "username-search-history-shared.js", "username-search-overlay.js"],
    });
    return { ok: true };
  } catch (e) {
    return { ok: false, error: String((e && e.message) || e) };
  }
}

async function tbccMaybeInjectUsernameSearchOverlay(tabId, url) {
  if (tabId == null || !tbccIsInjectableHttpUrl(url)) return { ok: false, skipped: true };
  if (!(await tbccUsernameSearchHostAllowed(url))) return { ok: false, skipped: true };
  try {
    if (typeof TBCC_EXT_MODULES !== "undefined") {
      const map = await TBCC_EXT_MODULES.getEnabledMap();
      if (!TBCC_EXT_MODULES.isEnabled(map, "username_search_overlay")) {
        return { ok: false, skipped: true, reason: "module_off" };
      }
    }
  } catch (_) {}
  return tbccInjectUsernameSearchOverlay(tabId);
}

async function tbccApproveUsernameSearchHost(hostname) {
  const host = tbccNormalizeUshHost(hostname);
  if (!host) return { ok: false, error: "bad_host" };
  const d = await chrome.storage.local.get([STORAGE_USH_APPROVED_HOSTS, STORAGE_USH_FAB_DENIED_HOSTS]);
  const arr = Array.isArray(d[STORAGE_USH_APPROVED_HOSTS]) ? d[STORAGE_USH_APPROVED_HOSTS].slice() : [];
  const norm = arr.map(tbccNormalizeUshHost);
  if (!norm.includes(host)) arr.push(host);
  const denied = Array.isArray(d[STORAGE_USH_FAB_DENIED_HOSTS])
    ? d[STORAGE_USH_FAB_DENIED_HOSTS].filter((h) => tbccNormalizeUshHost(h) !== host)
    : [];
  await chrome.storage.local.set({
    [STORAGE_USH_APPROVED_HOSTS]: arr,
    [STORAGE_USH_FAB_DENIED_HOSTS]: denied,
  });
  return { ok: true, host };
}

async function tbccRevokeUsernameSearchHost(hostname) {
  const host = tbccNormalizeUshHost(hostname);
  const d = await chrome.storage.local.get([STORAGE_USH_APPROVED_HOSTS, STORAGE_USH_FAB_DENIED_HOSTS]);
  const arr = (Array.isArray(d[STORAGE_USH_APPROVED_HOSTS]) ? d[STORAGE_USH_APPROVED_HOSTS] : []).filter(
    (h) => tbccNormalizeUshHost(h) !== host
  );
  let denied = Array.isArray(d[STORAGE_USH_FAB_DENIED_HOSTS]) ? d[STORAGE_USH_FAB_DENIED_HOSTS].slice() : [];
  if (tbccIsBuiltinUsernameSearchHost(host) && !denied.map(tbccNormalizeUshHost).includes(host)) {
    denied.push(host);
  }
  await chrome.storage.local.set({
    [STORAGE_USH_APPROVED_HOSTS]: arr,
    [STORAGE_USH_FAB_DENIED_HOSTS]: denied,
  });
  return { ok: true, host };
}

async function tbccReadGalleryJobs() {
  const data = await chrome.storage.local.get(STORAGE_GALLERY_JOBS);
  let jobs = Array.isArray(data[STORAGE_GALLERY_JOBS]) ? data[STORAGE_GALLERY_JOBS] : [];
  const now = Date.now();
  const pruned = jobs.filter((j) => j && now - (j.startedAt || 0) < TBCC_GALLERY_JOB_MAX_AGE_MS);
  if (pruned.length !== jobs.length) {
    await chrome.storage.local.set({ [STORAGE_GALLERY_JOBS]: pruned });
  }
  return pruned;
}

async function tbccWriteGalleryJobs(jobs) {
  await chrome.storage.local.set({ [STORAGE_GALLERY_JOBS]: jobs });
  await tbccSyncDockPanelLockFromJobs(jobs);
}

function tbccImportPollAlarmName(galleryJobId) {
  return TBCC_IMPORT_POLL_ALARM_PREFIX + String(galleryJobId || "");
}

function tbccIsBackendImportTerminal(status) {
  return typeof tbccIsImportTerminal === "function"
    ? tbccIsImportTerminal(status)
    : ["done", "failed", "skipped", "cancelled"].includes(String(status || "").toLowerCase());
}

async function tbccFetchBackendImportJob(backendJobId) {
  const r = await tbccFetchApi(`/import/jobs/${encodeURIComponent(backendJobId)}`, {
    cache: "no-store",
  });
  const text = await r.text();
  let data = {};
  try {
    data = text ? JSON.parse(text) : {};
  } catch (_) {
    data = { error: text ? text.slice(0, 200) : `HTTP ${r.status}` };
  }
  if (!r.ok && !data.error) data.error = text ? text.slice(0, 200) : `HTTP ${r.status}`;
  return data;
}

async function tbccApplyBackendImportStatusToGalleryJob(galleryJobId, data) {
  const jobs = await tbccReadGalleryJobs();
  const j = jobs.find((x) => x && x.id === galleryJobId);
  if (!j) return { found: false, terminal: true };
  if (data.job_id) j.backendJobId = String(data.job_id);
  if (data.status != null) j.status = String(data.status);
  if (data.stage != null) j.stage = String(data.stage);
  if (data.error) j.error = String(data.error);
  j.label =
    typeof tbccImportStageLabel === "function"
      ? tbccImportStageLabel(data.stage, data.status || j.status)
      : data.stage || data.status || j.label;
  await tbccWriteGalleryJobs(jobs);
  return { found: true, terminal: tbccIsBackendImportTerminal(data.status) };
}

async function tbccScheduleImportPollAlarm(galleryJobId, backendJobId) {
  if (!galleryJobId || !backendJobId) return;
  const jobs = await tbccReadGalleryJobs();
  const j = jobs.find((x) => x && x.id === galleryJobId);
  if (j) {
    if (!j.backendJobId) j.backendJobId = String(backendJobId);
    await tbccWriteGalleryJobs(jobs);
  }
  try {
    await chrome.alarms.create(tbccImportPollAlarmName(galleryJobId), {
      delayInMinutes: TBCC_IMPORT_POLL_DELAY_MIN,
    });
  } catch (e) {
    console.warn("TBCC import poll alarm", e);
  }
}

async function tbccClearImportPollAlarm(galleryJobId) {
  try {
    await chrome.alarms.clear(tbccImportPollAlarmName(galleryJobId));
  } catch (_) {}
}

async function tbccPollImportJobViaAlarm(galleryJobId, backendJobId) {
  let data = {};
  try {
    data = await tbccFetchBackendImportJob(backendJobId);
  } catch (e) {
    await chrome.alarms.create(tbccImportPollAlarmName(galleryJobId), {
      delayInMinutes: 0.25,
    });
    return;
  }
  if (data.error === "not_found") {
    await tbccClearImportPollAlarm(galleryJobId);
    return;
  }
  const { terminal } = await tbccApplyBackendImportStatusToGalleryJob(galleryJobId, data);
  if (terminal) {
    await tbccClearImportPollAlarm(galleryJobId);
    return;
  }
  await chrome.alarms.create(tbccImportPollAlarmName(galleryJobId), {
    delayInMinutes: TBCC_IMPORT_POLL_DELAY_MIN,
  });
}

async function tbccReattachImportPollAlarms() {
  const jobs = await tbccReadGalleryJobs();
  for (const j of jobs) {
    if (!j || !j.backendJobId) continue;
    if (tbccIsBackendImportTerminal(j.status)) continue;
    await tbccScheduleImportPollAlarm(j.id, j.backendJobId);
  }
}

async function tbccReconcileGalleryJobsWithServer() {
  const local = await tbccReadGalleryJobs();
  let serverJobs = [];
  try {
    const r = await tbccFetchApi("/import/jobs?active=true", { cache: "no-store" });
    const body = await r.json();
    serverJobs = Array.isArray(body.jobs) ? body.jobs : [];
  } catch (_) {
    serverJobs = [];
  }
  let changed = false;
  const byBackend = new Map(local.filter((j) => j && j.backendJobId).map((j) => [j.backendJobId, j]));
  const byGalleryId = new Map(local.filter((j) => j && j.id).map((j) => [j.id, j]));

  for (const sj of serverJobs) {
    const gid = sj.extension_job_id;
    let j = (gid && byGalleryId.get(gid)) || (sj.job_id && byBackend.get(sj.job_id));
    if (!j) continue;
    const prevStatus = j.status;
    if (sj.job_id) j.backendJobId = String(sj.job_id);
    if (sj.status != null) j.status = String(sj.status);
    if (sj.stage != null) j.stage = String(sj.stage);
    if (sj.error) j.error = String(sj.error);
    j.label =
      typeof tbccImportStageLabel === "function"
        ? tbccImportStageLabel(sj.stage, sj.status)
        : sj.stage || sj.status || j.label;
    if (prevStatus !== j.status) changed = true;
    if (!tbccIsBackendImportTerminal(j.status)) {
      await tbccScheduleImportPollAlarm(j.id, j.backendJobId);
    } else {
      await tbccClearImportPollAlarm(j.id);
    }
  }

  for (const j of local) {
    if (!j || !j.backendJobId || tbccIsBackendImportTerminal(j.status)) continue;
    const onServer = serverJobs.some((sj) => sj.job_id === j.backendJobId);
    if (onServer) continue;
    try {
      const data = await tbccFetchBackendImportJob(j.backendJobId);
      if (data.error === "not_found") continue;
      const prevStatus = j.status;
      if (data.status != null) j.status = String(data.status);
      if (data.stage != null) j.stage = String(data.stage);
      if (data.error) j.error = String(data.error);
      j.label =
        typeof tbccImportStageLabel === "function"
          ? tbccImportStageLabel(data.stage, data.status)
          : data.stage || data.status || j.label;
      if (prevStatus !== j.status) changed = true;
      if (tbccIsBackendImportTerminal(j.status)) await tbccClearImportPollAlarm(j.id);
      else await tbccScheduleImportPollAlarm(j.id, j.backendJobId);
    } catch (_) {}
  }

  await tbccWriteGalleryJobs(local);
  return { ok: true, jobs: local, serverActive: serverJobs.length, changed };
}

async function tbccBootstrapImportJobRecovery() {
  await tbccReconcileGalleryJobsWithServer();
  await tbccReattachImportPollAlarms();
}

/** In-memory mirror so side-panel open can run synchronously on user gesture (no await before open). */
let _tbccDockLockMemory = null;

function tbccRefreshDockLockMemoryFromStorage() {
  try {
    chrome.storage.local.get(STORAGE_GALLERY_DOCK_LOCK, (data) => {
      _tbccDockLockMemory = data[STORAGE_GALLERY_DOCK_LOCK] || null;
    });
  } catch (_) {}
}

chrome.storage.onChanged.addListener((changes, area) => {
  if (area !== "local" || !changes[STORAGE_GALLERY_DOCK_LOCK]) return;
  _tbccDockLockMemory = changes[STORAGE_GALLERY_DOCK_LOCK].newValue || null;
});

tbccRefreshDockLockMemoryFromStorage();

function tbccIsGalleryToolbarLockedSync() {
  const lock = _tbccDockLockMemory;
  return !!(lock && lock.locked && (lock.jobCount || 0) > 0);
}

/**
 * Must run synchronously in the user-gesture stack (context menu / click).
 * Do not await before calling chrome.sidePanel.open().
 */
function tbccTryOpenGallerySidePanelSync(tab) {
  const windowId = tab && tab.windowId != null ? tab.windowId : null;
  const tabId = tab && tab.id != null ? tab.id : null;
  if (windowId == null) return { ok: false, reason: "no-window-id" };
  try {
    void chrome.sidePanel.open({ windowId });
  } catch (e) {
    return { ok: false, reason: "open-failed", error: e };
  }
  try {
    if (chrome.sidePanel.setOptions && tabId != null) {
      void chrome.sidePanel.setOptions({ tabId, path: "gallery.html", enabled: true });
    }
  } catch (_) {}
  return { ok: true, windowId, tabId };
}

function tbccFallbackOpenGalleryAfterGesture(tab) {
  void (async () => {
    try {
      let windowId = tab && tab.windowId != null ? tab.windowId : null;
      if (windowId == null) {
        const [active] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
        windowId = active && active.windowId != null ? active.windowId : null;
        tab = active || tab;
      }
      if (windowId != null) {
        try {
          await chrome.sidePanel.open({ windowId });
          if (chrome.sidePanel.setOptions && tab && tab.id != null) {
            await chrome.sidePanel.setOptions({ tabId: tab.id, path: "gallery.html", enabled: true });
          }
          return;
        } catch (_) {}
      }
      await chrome.tabs.create({ url: chrome.runtime.getURL("gallery.html") });
    } catch (e) {
      notifyThrottled("open-fail", "TBCC", String((e && e.message) || e), 8000);
    }
  })();
}

function tbccHandleActionOpenGalleryClick(tab) {
  if (tbccIsGalleryToolbarLockedSync()) {
    const lock = _tbccDockLockMemory;
    notifyThrottled(
      "dock-lock",
      "TBCC",
      `${lock?.jobCount || 0} task(s) still running on ${lock?.hostname || lock?.title || "docked tab"}. Wait for the finished notification.`,
      15000
    );
    return;
  }
  const opened = tbccTryOpenGallerySidePanelSync(tab);
  if (!opened.ok) {
    tbccFallbackOpenGalleryAfterGesture(tab);
  }
}

async function tbccGetDockPanelLock() {
  const data = await chrome.storage.local.get(STORAGE_GALLERY_DOCK_LOCK);
  const lock = data[STORAGE_GALLERY_DOCK_LOCK] || null;
  _tbccDockLockMemory = lock;
  return lock;
}

async function tbccSyncDockPanelLockFromJobs(jobs) {
  const lock = await tbccGetDockPanelLock();
  if (!lock || !lock.locked) {
    await tbccUpdateGalleryPanelOpenMode();
    return;
  }
  const count = jobs.length;
  if (count <= 0) {
    await chrome.storage.local.remove(STORAGE_GALLERY_DOCK_LOCK);
    await tbccUpdateGalleryPanelOpenMode();
    return;
  }
  await chrome.storage.local.set({
    [STORAGE_GALLERY_DOCK_LOCK]: { ...lock, jobCount: count, lockedAt: lock.lockedAt || Date.now() },
  });
  await tbccUpdateGalleryPanelOpenMode();
}

async function tbccIsGalleryToolbarLocked() {
  const lock = await tbccGetDockPanelLock();
  return !!(lock && lock.locked && (lock.jobCount || 0) > 0);
}

/** Native instant open when idle; custom handler only while docked work is in flight. */
async function tbccUpdateGalleryPanelOpenMode() {
  const locked = await tbccIsGalleryToolbarLocked();
  try {
    await chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: !locked });
  } catch (_) {}
}

async function tbccCloseGallerySidePanelForDock(dock) {
  try {
    const tab = await chrome.tabs.get(dock.tabId);
    const sp = chrome.sidePanel;
    if (sp && typeof sp.close === "function" && tab && tab.windowId != null) {
      await sp.close({ windowId: tab.windowId });
      return;
    }
  } catch (_) {}
  try {
    await chrome.runtime.sendMessage({ action: "tbcc-gallery-request-close" });
  } catch (_) {}
}

async function tbccOnLeftDockedTab(dock) {
  const jobs = await tbccReadGalleryJobs();
  if (jobs.length === 0) return;
  await tbccCloseGallerySidePanelForDock(dock);
  await chrome.storage.local.set({
    [STORAGE_GALLERY_DOCK_LOCK]: {
      locked: true,
      dockTabId: dock.tabId,
      hostname: dock.hostname || "",
      title: dock.title || "",
      jobCount: jobs.length,
      lockedAt: Date.now(),
    },
  });
  await tbccUpdateGalleryPanelOpenMode();
  notifyThrottled(
    "dock-panel-closed",
    "TBCC",
    `${jobs.length} task(s) still running on ${dock.hostname || dock.title || "docked tab"}. Gallery reopens when finished.`,
    20000
  );
}

/** Track last http(s) tab only — extension/chrome pages must not overwrite (tab capture needs real page id). */
chrome.tabs.onActivated.addListener(({ tabId }) => {
  chrome.tabs.get(tabId).then((tab) => {
    if (tab && tbccIsInjectableHttpUrl(tab.url)) {
      chrome.storage.local.set({ [STORAGE_LAST_TAB]: tabId });
    }
  }).catch(() => {});
  void hydrateLazyModelSearchTab(tabId);
  void (async () => {
    try {
      const data = await chrome.storage.local.get(STORAGE_GALLERY_DOCKED_TAB);
      const dock = data[STORAGE_GALLERY_DOCKED_TAB];
      if (dock && Number(dock.tabId) !== tabId) {
        await tbccOnLeftDockedTab(dock);
      }
    } catch (_) {}
  })();
});

/**
 * Locoloader-style sites resolve media on their backend; TBCC cannot call locoloader.com.
 * For OnlyFans we mirror DevTools Network by recording completed media-like requests (webRequest).
 */
const TBCC_TAB_URL_CACHE = new Map();
/** Media gallery pages can load many photo CDN requests; keep a larger cap for OnlyFans. */
const TBCC_NET_MEDIA_MAX = 400;
const TBCC_NET_MANIFEST_MAX = 48;

function tbccTabPageLooksLikeOnlyfans(url) {
  if (!url || typeof url !== "string") return false;
  try {
    const h = new URL(url).hostname.toLowerCase();
    return h === "onlyfans.com" || h.endsWith(".onlyfans.com");
  } catch (_) {
    return false;
  }
}

/** X / Twitter: feed video is often MSE/blob in DOM; real progressive/HLS URLs load from video.twimg.com (sniff via webRequest). */
function tbccTabPageLooksLikeTwitterX(url) {
  if (!url || typeof url !== "string") return false;
  try {
    const h = new URL(url).hostname.toLowerCase();
    return /(^|\.)x\.com$/i.test(h) || /(^|\.)twitter\.com$/i.test(h);
  } catch (_) {
    return false;
  }
}

/** Only full container / manifest URLs — avoid flooding storage with per-segment .m4s/.ts requests. */
function tbccWebRequestUrlLooksLikeTwitterCdnVideo(url) {
  if (!url || typeof url !== "string") return false;
  if (url.length > 8000) return false;
  try {
    const u = new URL(url);
    if (u.hostname.toLowerCase() !== "video.twimg.com") return false;
    const path = u.pathname.toLowerCase();
    return /\.(mp4|webm|m4v|m3u8|mpd)(\?|$)/i.test(path);
  } catch (_) {
    return false;
  }
}

function tbccWebRequestUrlLooksLikeMedia(url) {
  if (!url || typeof url !== "string") return false;
  if (url.length > 8000) return false;
  try {
    const x = new URL(url);
    const path = x.pathname.toLowerCase();
    const full = url.toLowerCase();
    if (/\.(mp4|m4v|webm|m3u8|mpd|mov|mkv)(\?|$)/i.test(path)) return true;
    if (/\.m4s(\?|$)/i.test(path)) return true;
    if (
      /\.(ts|aac)(\?|$)/i.test(path) &&
      (full.includes("stream") || full.includes("hls") || full.includes("video") || full.includes("chunk"))
    )
      return true;
    const host = x.hostname.toLowerCase();
    if (host.includes("cloudfront") && (path.includes("/mp4") || path.includes("/video") || path.includes("/dash"))) return true;
    return false;
  } catch (_) {
    return false;
  }
}

/**
 * Photo CDN URLs for onlyfans.com tabs (checked only after tab is OnlyFans — avoids recording random images globally).
 * Thumbnails still match; gallery refresh + resource-timing scoring prefers full-res when both appear.
 */
function tbccWebRequestUrlLooksLikeOnlyfansImage(url) {
  if (!url || typeof url !== "string") return false;
  if (url.length > 8000) return false;
  try {
    const x = new URL(url);
    const path = x.pathname.toLowerCase();
    const full = url.toLowerCase();
    if (!/\.(jpe?g|png|gif|webp|avif)(\?|$)/i.test(path)) return false;
    if (full.includes("favicon") || full.includes("emoji") || full.includes("/icon")) return false;
    if (full.includes("avatar") && full.includes("thumb")) return false;
    const h = x.hostname.toLowerCase();
    if (h.includes("onlyfans.com")) return true;
    if (h.includes("cloudfront") || h.includes("amazonaws")) {
      return (
        full.includes("onlyfans") ||
        /\/(files|photos?|media|static|stream)\//i.test(path) ||
        path.includes("/of/")
      );
    }
    return false;
  } catch (_) {
    return false;
  }
}

async function tbccAppendObservedMediaUrl(tabId, url) {
  const key = `tbcc_net_media_${tabId}`;
  const got = await chrome.storage.session.get(key);
  const cur = Array.isArray(got[key]) ? got[key] : [];
  if (cur.includes(url)) return;
  const next = [...cur, url].slice(-TBCC_NET_MEDIA_MAX);
  await chrome.storage.session.set({ [key]: next });
}

function tbccWebRequestUrlLooksLikeHlsManifest(url) {
  if (!url || typeof url !== "string") return false;
  if (url.length > 8000) return false;
  try {
    const path = new URL(url).pathname.toLowerCase();
    return /\.(m3u8|mpd)(\?|$)/i.test(path);
  } catch (_) {
    return false;
  }
}

async function tbccAppendObservedManifestUrl(tabId, url) {
  const key = `tbcc_net_manifest_${tabId}`;
  const got = await chrome.storage.session.get(key);
  const cur = Array.isArray(got[key]) ? got[key] : [];
  if (cur.includes(url)) return;
  const next = [...cur, url].slice(-TBCC_NET_MANIFEST_MAX);
  await chrome.storage.session.set({ [key]: next });
}

chrome.tabs.onUpdated.addListener((tabId, info, tab) => {
  if (info.url) {
    const prev = TBCC_TAB_URL_CACHE.get(tabId);
    if (prev != null && prev !== info.url) {
      void chrome.storage.session.remove(`tbcc_net_media_${tabId}`);
      void chrome.storage.session.remove(`tbcc_net_manifest_${tabId}`);
    }
    TBCC_TAB_URL_CACHE.set(tabId, info.url);
  } else if (tab && tab.url) {
    TBCC_TAB_URL_CACHE.set(tabId, tab.url);
  }
  if (info.status === "complete" && tab && tab.active && tab.id && tbccIsInjectableHttpUrl(tab.url)) {
    chrome.storage.local.set({ [STORAGE_LAST_TAB]: tab.id });
    void tbccMaybeInjectUsernameSearchOverlay(tab.id, tab.url);
  }
});
chrome.tabs.onRemoved.addListener((tabId) => {
  TBCC_TAB_URL_CACHE.delete(tabId);
  void chrome.storage.session.remove(`tbcc_net_media_${tabId}`);
  void (async () => {
    try {
      const data = await chrome.storage.local.get(STORAGE_GALLERY_DOCKED_TAB);
      const dock = data[STORAGE_GALLERY_DOCKED_TAB];
      if (dock && Number(dock.tabId) === tabId) {
        await chrome.storage.local.remove(STORAGE_GALLERY_DOCKED_TAB);
      }
    } catch (_) {}
  })();
});

async function tbccSeedTabUrlCache() {
  try {
    const tabs = await chrome.tabs.query({});
    for (const t of tabs) {
      if (t.id != null && t.url) TBCC_TAB_URL_CACHE.set(t.id, t.url);
    }
  } catch (_) {}
}
tbccSeedTabUrlCache();

try {
  chrome.webRequest.onCompleted.addListener(
    (details) => {
      if (details.tabId == null || details.tabId < 0) return;
      if (details.statusCode && details.statusCode >= 400) return;
      const u = details.url;
      const looksVideo = tbccWebRequestUrlLooksLikeMedia(u);
      const isManifest = tbccWebRequestUrlLooksLikeHlsManifest(u);
      chrome.tabs
        .get(details.tabId)
        .then((tab) => {
          const pageUrl = tab && tab.url;
          if (!tbccIsInjectableHttpUrl(pageUrl)) return;
          if (tbccTabPageLooksLikeOnlyfans(pageUrl)) {
            if (looksVideo || tbccWebRequestUrlLooksLikeOnlyfansImage(u)) void tbccAppendObservedMediaUrl(details.tabId, u);
          } else if (tbccTabPageLooksLikeTwitterX(pageUrl)) {
            /** Do not use generic `looksVideo` here — twimg serves many `.m4s` segments we must not log. */
            if (tbccWebRequestUrlLooksLikeTwitterCdnVideo(u)) void tbccAppendObservedMediaUrl(details.tabId, u);
          } else if (looksVideo && tbccInboxWorthyNetVideoUrl(u)) {
            void tbccAppendObservedMediaUrl(details.tabId, u);
          }
          if (isManifest) void tbccAppendObservedManifestUrl(details.tabId, u);
        })
        .catch(() => {});
    },
    { urls: ["https://*/*", "http://*/*"] }
  );
} catch (e) {
  console.warn("TBCC: webRequest listener failed", e);
}

const TBCC_THUMB_PROXY_MAX_BYTES = Math.floor(2.75 * 1024 * 1024);

/**
 * Throttle thumb-proxy fetches. The sidebar can mount 200–500 tiles at once;
 * if we let every tile's session-fetch fly in parallel, Chrome's per-renderer
 * socket pool / blob memory budget pops with net::ERR_INSUFFICIENT_RESOURCES
 * (especially on OF where each "thumb" used to be a 3 MB CDN file).
 *
 * Strategy:
 *   - Hard cap of N in-flight fetches (per service-worker, not per-tab).
 *   - Excess requests sit in an in-memory FIFO queue.
 *   - Tiny LRU of completed dataUrls so re-render / re-sort doesn't refetch.
 *
 * Cap chosen by feel: 4 keeps OF's CloudFront happy without strangling
 * smaller batches.
 */
const TBCC_THUMB_PROXY_MAX_INFLIGHT = 4;
const TBCC_THUMB_PROXY_CACHE_LIMIT = 256;
let _tbccThumbInflight = 0;
const _tbccThumbQueue = [];
const _tbccThumbCache = new Map();

function _tbccThumbCachePut(url, dataUrl) {
  if (_tbccThumbCache.has(url)) _tbccThumbCache.delete(url);
  _tbccThumbCache.set(url, dataUrl);
  while (_tbccThumbCache.size > TBCC_THUMB_PROXY_CACHE_LIMIT) {
    const k = _tbccThumbCache.keys().next().value;
    _tbccThumbCache.delete(k);
  }
}

function _tbccThumbDrainQueue() {
  while (_tbccThumbInflight < TBCC_THUMB_PROXY_MAX_INFLIGHT && _tbccThumbQueue.length) {
    const job = _tbccThumbQueue.shift();
    _tbccThumbInflight++;
    job().finally(() => {
      _tbccThumbInflight--;
      _tbccThumbDrainQueue();
    });
  }
}

function _tbccThumbSchedule(jobFactory) {
  return new Promise((resolve) => {
    const job = async () => {
      try { resolve(await jobFactory()); }
      catch (_) { resolve({ ok: false }); }
    };
    _tbccThumbQueue.push(job);
    _tbccThumbDrainQueue();
  });
}

function tbccDetectMediaMime(bytes, hint) {
  const h = String(hint || "").toLowerCase();
  if (h.startsWith("video/") || h.startsWith("image/") || h.startsWith("audio/")) return h.split(";")[0];
  if (bytes.length >= 3 && bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff) return "image/jpeg";
  if (bytes.length >= 8 && bytes[0] === 0x89 && bytes[1] === 0x50 && bytes[2] === 0x4e && bytes[3] === 0x47) return "image/png";
  if (bytes.length >= 6 && bytes[0] === 0x47 && bytes[1] === 0x49 && bytes[2] === 0x46) return "image/gif";
  if (bytes.length >= 4 && bytes[0] === 0x52 && bytes[1] === 0x49 && bytes[2] === 0x46 && bytes[3] === 0x46) return "image/webp";
  // ISO BMFF (mp4/m4v/mov): ....ftyp
  if (bytes.length >= 8) {
    const box = String.fromCharCode(bytes[4], bytes[5], bytes[6], bytes[7]);
    if (box === "ftyp") return "video/mp4";
  }
  return "application/octet-stream";
}

function tbccArrayBufferToDataUrl(ab, mimeHint) {
  const bytes = new Uint8Array(ab);
  const mime = tbccDetectMediaMime(bytes, mimeHint);
  let binary = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk));
  }
  return `data:${mime};base64,${btoa(binary)}`;
}

/** MV3 service workers have no URL.createObjectURL — prefer remote URL like GM_download. */
function tbccChromeDownloadsDownload(opts) {
  return new Promise((resolve, reject) => {
    try {
      chrome.downloads.download(opts, (id) => {
        const err = chrome.runtime.lastError;
        if (err || !id) {
          reject(new Error(err ? err.message : "Download failed"));
          return;
        }
        resolve(id);
      });
    } catch (e) {
      reject(e);
    }
  });
}

/** Download-routing "circuit board": skip downloads this extension itself already named. */
chrome.downloads.onDeterminingFilename.addListener((item, suggest) => {
  if (item && item.byExtensionId === chrome.runtime.id) {
    suggest();
    return;
  }
  void (async () => {
    try {
      const data = await chrome.storage.local.get([STORAGE_DOWNLOAD_ROUTES, STORAGE_DOWNLOAD_ROUTING_SETTINGS]);
      const settings = data[STORAGE_DOWNLOAD_ROUTING_SETTINGS] || {};
      const router = typeof TbccDownloadRouter !== "undefined" ? TbccDownloadRouter : null;
      if (settings.enabled === false || !router) {
        suggest();
        return;
      }
      const routes = Array.isArray(data[STORAGE_DOWNLOAD_ROUTES]) ? data[STORAGE_DOWNLOAD_ROUTES] : [];
      const route = router.matchRoute(routes, item);
      const filename = route ? router.buildRoutedFilename(route, item) : null;
      if (!filename) {
        suggest();
        return;
      }
      suggest({ filename, conflictAction: (route && route.conflictAction) || "uniquify" });
    } catch (e) {
      console.warn("TBCC download routing", e);
      suggest();
    }
  })();
  return true;
});

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.action === "tbcc-get-sender-tab-id") {
    const tabId = _sender && _sender.tab && _sender.tab.id != null ? _sender.tab.id : null;
    sendResponse({ ok: true, tabId });
    return true;
  }
  if (msg.action === "tbcc-playwright-record") {
    void (async () => {
      const bases = ["http://127.0.0.1:8000", "http://localhost:8000"];
      let key = "";
      try {
        const d = await chrome.storage.local.get("tbccInternalApiKey");
        key = String(d.tbccInternalApiKey || "").trim();
      } catch (_) {}
      if (!key) {
        sendResponse({
          ok: false,
          error: "Set Internal API key in extension options (same as launch stack).",
        });
        return;
      }
      const body = {
        url: String(msg.url || "https://www.erome.com/").trim(),
        name: String(msg.name || "erome-session").trim() || "erome-session",
        load_auth: true,
        use_erome_auth: true,
      };
      let lastErr = "unreachable";
      for (const base of bases) {
        try {
          const res = await fetch(`${base}/internal/playwright/record`, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "X-TBCC-Internal-Key": key,
            },
            body: JSON.stringify(body),
          });
          const data = await res.json().catch(() => ({}));
          if (res.ok && data.ok) {
            sendResponse(data);
            return;
          }
          lastErr = data.error || data.detail || `HTTP ${res.status}`;
        } catch (e) {
          lastErr = String(e.message || e);
        }
      }
      sendResponse({ ok: false, error: lastErr });
    })();
    return true;
  }
  if (msg.action === "tbcc-notify") {
    notify(String(msg.title || "TBCC"), String(msg.message || ""), msg.clickAction || null);
    sendResponse({ ok: true });
    return true;
  }
  if (msg.action === "tbcc-launch-reverse-image") {
    void launchReverseImageSearch(String(msg.url || "").trim()).then(() => sendResponse({ ok: true }));
    return true;
  }
  if (msg.action === "tbcc-x-profile-open-gallery") {
    void (async () => {
      try {
        const tabId = _sender && _sender.tab && _sender.tab.id != null ? _sender.tab.id : null;
        let windowId = _sender && _sender.tab && _sender.tab.windowId != null ? _sender.tab.windowId : null;
        if (windowId == null) {
          const [active] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
          windowId = active && active.windowId != null ? active.windowId : null;
        }
        if (windowId != null) {
          await chrome.sidePanel.open({ windowId });
          if (chrome.sidePanel.setOptions && tabId != null) {
            await chrome.sidePanel.setOptions({ tabId, path: "gallery.html", enabled: true });
          }
        }
        sendResponse({ ok: true });
      } catch (e) {
        sendResponse({ ok: false, error: String(e.message || e) });
      }
    })();
    return true;
  }
  if (msg.action === "tbcc-x-open-side-panel-sync") {
    try {
      const tabId = _sender && _sender.tab && _sender.tab.id != null ? _sender.tab.id : null;
      let windowId = _sender && _sender.tab && _sender.tab.windowId != null ? _sender.tab.windowId : null;
      if (windowId != null) {
        try {
          chrome.sidePanel.open({ windowId });
        } catch (_) {}
        if (chrome.sidePanel.setOptions && tabId != null) {
          void chrome.sidePanel.setOptions({ tabId, path: "gallery.html", enabled: true });
        }
      }
      sendResponse({ ok: true });
    } catch (e) {
      sendResponse({ ok: false, error: String(e.message || e) });
    }
    return true;
  }
  if (msg.action === "tbcc-motherless-gallery-bulk") {
    (async () => {
      try {
        let tab = _sender && _sender.tab;
        if (!tab || tab.id == null) {
          const [active] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
          tab = active;
        }
        const mode = msg.mode === "download" ? "download" : "zip";
        const r = await tbccMotherlessGalleryBulkFromTab(tab, mode);
        sendResponse(r);
      } catch (e) {
        sendResponse({ ok: false, error: String((e && e.message) || e) });
      }
    })();
    return true;
  }
  if (msg.action === "tbcc-x-profile-merge-to-gallery") {
    let panelOpenErr = null;
    if (msg.openPanel !== false) {
      const tabIdSync = _sender && _sender.tab && _sender.tab.id != null ? _sender.tab.id : null;
      let windowIdSync = _sender && _sender.tab && _sender.tab.windowId != null ? _sender.tab.windowId : null;
      if (windowIdSync != null) {
        try {
          chrome.sidePanel.open({ windowId: windowIdSync });
        } catch (e) {
          panelOpenErr = e;
        }
        if (chrome.sidePanel.setOptions && tabIdSync != null) {
          try {
            void chrome.sidePanel.setOptions({ tabId: tabIdSync, path: "gallery.html", enabled: true });
          } catch (_) {}
        }
      }
    }
    void (async () => {
      try {
        const mergePayload = {
          action: "tbcc-gallery-merge-harvest",
          items: Array.isArray(msg.items) ? msg.items : [],
          sourceUrl: msg.sourceUrl || "",
          adapter: msg.adapter || "x-profile",
          autoZip: !!msg.autoZip,
          loomsZip: !!msg.loomsZip,
          mergeId: msg.mergeId || "mh-" + Date.now() + "-" + Math.random().toString(36).slice(2, 8),
          selectAll: msg.selectAll !== false,
          sourceTabId:
            _sender && _sender.tab && _sender.tab.id != null
              ? _sender.tab.id
              : msg.tabId != null
                ? msg.tabId
                : null,
        };
        try {
          await chrome.storage.session.set({ tbccPendingGalleryMerge: mergePayload });
        } catch (_) {}
        tbccPostGalleryPanelMessage(mergePayload);
        sendResponse({
          ok: true,
          panelWarning: panelOpenErr ? String(panelOpenErr.message || panelOpenErr) : undefined,
        });
      } catch (e) {
        sendResponse({ ok: false, error: String(e.message || e) });
      }
    })();
    return true;
  }
  if (msg.action === "tbcc-sync-context-menu-settings") {
    void Promise.all([
      tbccSyncExtensionContextMenuSettings(),
      tbccSyncAofPools(),
      tbccSyncStorageHubTopics(),
    ]).then(([ok]) =>
      sendResponse({ ok: !!ok })
    );
    return true;
  }
  if (msg.action === "tbcc-notification-open") {
    void tbccHandleNotificationClickAction(msg.clickAction).then(() => sendResponse({ ok: true }));
    return true;
  }
  if (msg.action === "tbcc-gallery-job-begin") {
    (async () => {
      try {
        const id = `job-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
        const jobs = await tbccReadGalleryJobs();
        jobs.push({
          id,
          type: String(msg.type || "task"),
          label: String(msg.label || msg.type || "Gallery task"),
          stage: "starting",
          status: "running",
          tabId: msg.tabId != null ? Number(msg.tabId) : null,
          startedAt: Date.now(),
        });
        await tbccWriteGalleryJobs(jobs);
        sendResponse({ ok: true, id });
      } catch (e) {
        sendResponse({ ok: false, error: String(e.message || e) });
      }
    })();
    return true;
  }
  if (msg.action === "tbcc-gallery-job-update") {
    (async () => {
      try {
        const jobs = await tbccReadGalleryJobs();
        const j = jobs.find((x) => x.id === msg.id);
        if (j) {
          if (msg.stage != null) j.stage = String(msg.stage);
          if (msg.status != null) j.status = String(msg.status);
          if (msg.backendJobId) {
            j.backendJobId = String(msg.backendJobId);
            void tbccScheduleImportPollAlarm(j.id, j.backendJobId);
          }
          if (msg.error) j.error = String(msg.error);
          if (msg.label) j.label = String(msg.label);
          else if (msg.stage) j.label = tbccImportStageLabel(msg.stage, msg.status || j.status);
          await tbccWriteGalleryJobs(jobs);
        }
        sendResponse({ ok: true });
      } catch (e) {
        sendResponse({ ok: false, error: String(e.message || e) });
      }
    })();
    return true;
  }
  if (msg.action === "tbcc-health-system") {
    (async () => {
      try {
        const r = await tbccFetchApi("/health/system");
        const data = await r.json();
        sendResponse({ ok: r.ok, data });
      } catch (e) {
        sendResponse({ ok: false, error: String(e.message || e) });
      }
    })();
    return true;
  }
  if (msg.action === "tbcc-focus-apply") {
    (async () => {
      try {
        const profile = msg.profile ? String(msg.profile).trim().toLowerCase() : "off";
        const reason = msg.reason ? String(msg.reason) : "Extension gallery";
        const path = profile === "off" ? "/ops/focus/restore" : "/ops/focus";
        const opts =
          profile === "off"
            ? { method: "POST" }
            : {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ profile, reason }),
              };
        const r = await tbccFetchApi(path, opts);
        const data = await r.json().catch(() => ({}));
        sendResponse({ ok: r.ok, data, error: r.ok ? "" : String(data.detail || data.error || r.status) });
      } catch (e) {
        sendResponse({ ok: false, error: String(e.message || e) });
      }
    })();
    return true;
  }
  if (msg.action === "tbcc-gallery-job-list") {
    (async () => {
      try {
        const jobs = await tbccReadGalleryJobs();
        sendResponse({ ok: true, jobs });
      } catch (e) {
        sendResponse({ ok: false, error: String(e.message || e), jobs: [] });
      }
    })();
    return true;
  }
  if (msg.action === "tbcc-gallery-job-clear-stale") {
    (async () => {
      try {
        const jobs = await tbccReadGalleryJobs();
        const now = Date.now();
        const staleMs = 15 * 60 * 1000;
        const next = jobs.filter((j) => {
          if (!j) return false;
          if (now - (j.startedAt || 0) >= staleMs) {
            void tbccClearImportPollAlarm(j.id);
            return false;
          }
          if (tbccIsBackendImportTerminal(j.status)) {
            void tbccClearImportPollAlarm(j.id);
            return false;
          }
          return true;
        });
        const removed = jobs.length - next.length;
        await tbccWriteGalleryJobs(next);
        sendResponse({ ok: true, removed, jobs: next });
      } catch (e) {
        sendResponse({ ok: false, error: String(e.message || e) });
      }
    })();
    return true;
  }
  if (msg.action === "tbcc-gallery-job-purge-types") {
    (async () => {
      try {
        const types = new Set(Array.isArray(msg.types) ? msg.types.map(String) : []);
        const jobs = await tbccReadGalleryJobs();
        const next = jobs.filter((j) => !j || !types.has(String(j.type || "")));
        const removed = jobs.length - next.length;
        if (removed) await tbccWriteGalleryJobs(next);
        sendResponse({ ok: true, removed, jobs: next });
      } catch (e) {
        sendResponse({ ok: false, error: String(e.message || e) });
      }
    })();
    return true;
  }
  if (msg.action === "tbcc-import-poll-arm") {
    (async () => {
      try {
        await tbccScheduleImportPollAlarm(msg.galleryJobId, msg.backendJobId);
        sendResponse({ ok: true });
      } catch (e) {
        sendResponse({ ok: false, error: String(e.message || e) });
      }
    })();
    return true;
  }
  if (msg.action === "tbcc-import-reconcile") {
    (async () => {
      try {
        const r = await tbccReconcileGalleryJobsWithServer();
        sendResponse(r);
      } catch (e) {
        sendResponse({ ok: false, error: String(e.message || e), jobs: [] });
      }
    })();
    return true;
  }
  if (msg.action === "tbcc-import-cancel") {
    (async () => {
      try {
        const backendJobId = msg.backendJobId ? String(msg.backendJobId) : "";
        if (backendJobId && typeof tbccCancelBackendImportJob === "function") {
          await tbccCancelBackendImportJob(backendJobId);
        }
        if (msg.galleryJobId) {
          await tbccClearImportPollAlarm(msg.galleryJobId);
          const jobs = await tbccReadGalleryJobs();
          const j = jobs.find((x) => x && x.id === msg.galleryJobId);
          if (j) {
            j.status = "cancelled";
            j.stage = "cancelled";
            j.label = "Cancelled";
            await tbccWriteGalleryJobs(jobs);
          }
        }
        sendResponse({ ok: true });
      } catch (e) {
        sendResponse({ ok: false, error: String(e.message || e) });
      }
    })();
    return true;
  }
  if (msg.action === "tbcc-import-queue-pause-get") {
    (async () => {
      try {
        const data = await chrome.storage.local.get(STORAGE_IMPORT_QUEUE_PAUSED);
        sendResponse({ ok: true, paused: !!data[STORAGE_IMPORT_QUEUE_PAUSED] });
      } catch (e) {
        sendResponse({ ok: false, paused: false });
      }
    })();
    return true;
  }
  if (msg.action === "tbcc-import-queue-pause-set") {
    (async () => {
      try {
        await chrome.storage.local.set({ [STORAGE_IMPORT_QUEUE_PAUSED]: !!msg.paused });
        sendResponse({ ok: true, paused: !!msg.paused });
      } catch (e) {
        sendResponse({ ok: false, error: String(e.message || e) });
      }
    })();
    return true;
  }
  if (msg.action === "tbcc-import-queue-status") {
    (async () => {
      try {
        const r = await tbccFetchApi("/import/queue/status", { cache: "no-store" });
        const data = await r.json();
        sendResponse({ ok: r.ok, data });
      } catch (e) {
        sendResponse({ ok: false, error: String(e.message || e) });
      }
    })();
    return true;
  }
  if (msg.action === "tbcc-maybe-inject-username-search") {
    void (async () => {
      const tab = _sender && _sender.tab;
      if (!tab || tab.id == null) {
        sendResponse({ ok: false, error: "no_tab" });
        return;
      }
      sendResponse(await tbccMaybeInjectUsernameSearchOverlay(tab.id, tab.url || msg.url || ""));
    })();
    return true;
  }
  if (msg.action === "tbcc-approve-username-search-host") {
    void (async () => {
      const host =
        msg.host ||
        (_sender && _sender.tab && _sender.tab.url
          ? tbccNormalizeUshHost(new URL(_sender.tab.url).hostname)
          : "");
      const r = await tbccApproveUsernameSearchHost(host);
      if (r.ok && _sender && _sender.tab && _sender.tab.id != null) {
        await tbccInjectUsernameSearchOverlay(_sender.tab.id);
      }
      sendResponse(r);
    })();
    return true;
  }
  if (msg.action === "tbcc-revoke-username-search-host") {
    void (async () => {
      const host =
        msg.host ||
        (_sender && _sender.tab && _sender.tab.url
          ? tbccNormalizeUshHost(new URL(_sender.tab.url).hostname)
          : "");
      sendResponse(await tbccRevokeUsernameSearchHost(host));
    })();
    return true;
  }
  if (msg.action === "tbcc-username-search-host-status") {
    void (async () => {
      try {
        const url = String((_sender && _sender.tab && _sender.tab.url) || msg.url || "");
        const host = tbccNormalizeUshHost(new URL(url).hostname);
        const d = await chrome.storage.local.get([STORAGE_USH_APPROVED_HOSTS, STORAGE_USH_FAB_DENIED_HOSTS]);
        const approved = (Array.isArray(d[STORAGE_USH_APPROVED_HOSTS]) ? d[STORAGE_USH_APPROVED_HOSTS] : []).map(
          tbccNormalizeUshHost
        );
        const denied = (Array.isArray(d[STORAGE_USH_FAB_DENIED_HOSTS]) ? d[STORAGE_USH_FAB_DENIED_HOSTS] : []).map(
          tbccNormalizeUshHost
        );
        sendResponse({
          ok: true,
          host,
          builtin: tbccIsBuiltinUsernameSearchHost(host),
          approved: approved.includes(host),
          fabDenied: denied.includes(host),
          allowed: await tbccUsernameSearchHostAllowed(url),
        });
      } catch (e) {
        sendResponse({ ok: false, error: String((e && e.message) || e) });
      }
    })();
    return true;
  }
  if (msg.action === "tbcc-macro-model-search") {
    (async () => {
      try {
        const pageUrl = String((_sender && _sender.tab && _sender.tab.url) || msg.pageUrl || "");
        const r = await launchMacroModelSearch(msg.username || "", {
          source: msg.source || undefined,
          pageUrl,
        });
        sendResponse(r);
      } catch (e) {
        sendResponse({ ok: false, error: String(e.message || e) });
      }
    })();
    return true;
  }
  if (msg.action === "tbcc-list-macro-sources") {
    (async () => {
      try {
        sendResponse(await listMacroSourcesWithStats());
      } catch (e) {
        sendResponse({ ok: false, error: String(e.message || e), sites: [] });
      }
    })();
    return true;
  }
  if (msg.action === "tbcc-open-model-search-url") {
    (async () => {
      try {
        const url = String(msg.url || "").trim();
        const username = normalizeUsernameCandidate(msg.username || "");
        let finalUrl = url;
        if ((!finalUrl || !/^https?:\/\//i.test(finalUrl)) && username && msg.siteId) {
          const cfg = await getMergedModelSearchSites();
          const site = (cfg.sites || []).find((s) => s.id === msg.siteId);
          if (site) finalUrl = buildModelSearchUrl(site.url, username);
        }
        const r = await openModelSearchUrlLazy(finalUrl, {
          lazy: msg.lazy !== false,
          active: msg.active !== false,
        });
        sendResponse(r);
      } catch (e) {
        sendResponse({ ok: false, error: String(e.message || e) });
      }
    })();
    return true;
  }
  if (msg.action === "tbcc-launch-model-search-tabs") {
    (async () => {
      try {
        const pageUrl = String((_sender && _sender.tab && _sender.tab.url) || msg.pageUrl || "");
        await launchModelSearch(msg.username || "", null, msg.category || null, {
          source: msg.source || undefined,
          pageUrl,
        });
        sendResponse({ ok: true });
      } catch (e) {
        sendResponse({ ok: false, error: String(e.message || e) });
      }
    })();
    return true;
  }
  if (msg.action === "tbcc-page-menu-pack-pool") {
    (async () => {
      try {
        const url = String(msg.url || "").trim();
        if (!url) {
          sendResponse({ ok: false, error: "No URL." });
          return;
        }
        const r = await tbccFetchApi("/loot/pack-pool/queue", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            url,
            source_note: "extension:context-menu",
            wire_packs_scheduler: false,
          }),
        });
        const data = await r.json().catch(() => ({}));
        if (!r.ok) {
          notify("TBCC", data.detail || data.error || "Pack pool queue failed.");
          sendResponse({ ok: false, error: data.detail || data.error || "queue_failed" });
          return;
        }
        if (data.duplicate) {
          notify("TBCC", "Already in AOF pack / loot pool.");
        } else {
          notify("TBCC", "Queued for AOF packs + loot room (resolved + wrapped).");
        }
        sendResponse({ ok: true, ...data });
      } catch (e) {
        sendResponse({ ok: false, error: String(e.message || e) });
      }
    })();
    return true;
  }
  if (msg.action === "tbcc-list-storage-hub-topics") {
    (async () => {
      try {
        await tbccSyncStorageHubTopics();
        const topics = await tbccGetStorageHubTopics();
        sendResponse({ ok: true, topics });
      } catch (e) {
        sendResponse({ ok: false, error: String(e.message || e), topics: TBCC_STORAGE_HUB_TOPICS_FALLBACK });
      }
    })();
    return true;
  }
  if (msg.action === "tbcc-page-menu-storage-hub") {
    (async () => {
      try {
        const url = String(msg.url || "").trim();
        const tid = parseInt(msg.messageThreadId, 10);
        if (!url) {
          sendResponse({ ok: false, error: "No URL." });
          return;
        }
        if (!Number.isFinite(tid) || tid < 1) {
          sendResponse({ ok: false, error: "Invalid topic." });
          return;
        }
        const tabId =
          _sender && _sender.tab && _sender.tab.id != null
            ? _sender.tab.id
            : msg.tabId != null
              ? msg.tabId
              : null;
        const result = await tbccSendUrlToStorageHubTopic({
          url,
          messageThreadId: tid,
          networkKey: msg.networkKey || "",
          refererPageUrl: msg.refererPageUrl || (_sender && _sender.tab && _sender.tab.url) || "",
          tabId,
        });
        const topics = await tbccGetStorageHubTopics();
        const row = topics.find((t) => parseInt(t.message_thread_id, 10) === tid);
        const label = (row && (row.short_label || row.menu_label)) || `topic ${tid}`;
        notify("TBCC Storage Hub", `Sent → ${label}`);
        sendResponse({ ok: true, ...result, label });
      } catch (e) {
        notify("TBCC Storage Hub failed", String((e && e.message) || e));
        sendResponse({ ok: false, error: String(e.message || e) });
      }
    })();
    return true;
  }
  if (msg.action === "tbcc-page-menu-archive-url") {
    (async () => {
      try {
        const r = await tbccAppendSavedVideoUrl(msg.url || "", msg.refererPageUrl || "", { destType: "archive" });
        if (!r.ok) {
          sendResponse({ ok: false, error: r.error || "Could not save." });
          return;
        }
        if (r.archived) {
          notify("TBCC", "Saved to master archive — click to open.", { type: "gallery_master_archive" });
        } else if (r.duplicate) {
          notify("TBCC", "Already in master archive.", { type: "gallery_master_archive" });
        } else {
          notify("TBCC", "Saved to master archive — click to open.", { type: "gallery_master_archive" });
        }
        sendResponse({ ok: true, ...r });
      } catch (e) {
        sendResponse({ ok: false, error: String(e.message || e) });
      }
    })();
    return true;
  }
  if (msg.action === "tbcc-page-menu-archive-all-videos") {
    (async () => {
      try {
        const tabId = _sender && _sender.tab && _sender.tab.id != null ? _sender.tab.id : null;
        if (tabId == null) {
          sendResponse({ ok: false, error: "No tab to scan." });
          return;
        }
        const urls = await tbccCollectVideoUrlsFromTab(tabId);
        const r = await tbccAppendSavedVideoUrlsBulk(urls, msg.refererPageUrl || "", { destType: "archive" });
        if (!r.ok) {
          notify("TBCC", r.error || "No video URLs found.");
          sendResponse({ ok: false, error: r.error || "No video URLs found." });
          return;
        }
        notify("TBCC", `Saved ${r.added || urls.length} URL(s) to master archive.`, {
          type: "gallery_master_archive",
        });
        sendResponse({ ok: true, ...r });
      } catch (e) {
        sendResponse({ ok: false, error: String(e.message || e) });
      }
    })();
    return true;
  }
  if (msg.action === "tbcc-gallery-archive-urls-from-page") {
    (async () => {
      try {
        const dockData = await chrome.storage.local.get([STORAGE_GALLERY_DOCKED_TAB]);
        const dock = dockData[STORAGE_GALLERY_DOCKED_TAB];
        let tabId = dock && dock.tabId != null ? dock.tabId : null;
        if (tabId == null) {
          const [active] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
          tabId = active && active.id != null ? active.id : null;
        }
        if (tabId == null) {
          sendResponse({ ok: false, error: "No active tab." });
          return;
        }
        const tab = await chrome.tabs.get(tabId);
        const urls = await tbccCollectHttpUrlsFromTab(tabId);
        if (!urls.length) {
          sendResponse({ ok: false, error: "No http(s) URLs found on page." });
          return;
        }
        const r = await tbccAppendSavedVideoUrlsBulk(urls, tab.url || "", { destType: "archive" });
        if (!r.ok) {
          sendResponse({ ok: false, error: r.error || "Archive failed." });
          return;
        }
        notify("TBCC", `Archived ${r.added || urls.length} URL(s) to master archive.`, {
          type: "gallery_master_archive",
        });
        sendResponse({ ok: true, ...r, count: urls.length });
      } catch (e) {
        sendResponse({ ok: false, error: String(e.message || e) });
      }
    })();
    return true;
  }
  if (msg.action === "tbcc-gallery-archive-urls-from-clipboard") {
    (async () => {
      try {
        let text = "";
        if (navigator.clipboard && navigator.clipboard.readText) {
          text = await navigator.clipboard.readText();
        }
        const urls = tbccExtractHttpUrlsFromText(text);
        if (!urls.length) {
          sendResponse({ ok: false, error: "Clipboard has no http(s) URLs." });
          return;
        }
        const r = await tbccAppendSavedVideoUrlsBulk(urls, "clipboard", { destType: "archive" });
        if (!r.ok) {
          sendResponse({ ok: false, error: r.error || "Archive failed." });
          return;
        }
        notify("TBCC", `Archived ${r.added || urls.length} URL(s) from clipboard.`, {
          type: "gallery_master_archive",
        });
        sendResponse({ ok: true, ...r, count: urls.length });
      } catch (e) {
        sendResponse({ ok: false, error: String(e.message || e) });
      }
    })();
    return true;
  }
  if (msg.action === "tbcc-gallery-save-tab-archive") {
    (async () => {
      try {
        const dockData = await chrome.storage.local.get([STORAGE_GALLERY_DOCKED_TAB]);
        const dock = dockData[STORAGE_GALLERY_DOCKED_TAB];
        let tabId = dock && dock.tabId != null ? dock.tabId : null;
        if (tabId == null) {
          const [active] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
          tabId = active && active.id != null ? active.id : null;
        }
        if (tabId == null) {
          sendResponse({ ok: false, error: "No active tab." });
          return;
        }
        const tab = await chrome.tabs.get(tabId);
        const url = tab && tab.url ? String(tab.url).split("#")[0] : "";
        if (!tbccIsStorableHttpUrl(url)) {
          sendResponse({ ok: false, error: "Tab URL is not storable." });
          return;
        }
        const r = await tbccAppendSavedVideoUrl(url, url, { destType: "archive" });
        sendResponse({ ok: !!r.ok, ...r });
      } catch (e) {
        sendResponse({ ok: false, error: String(e.message || e) });
      }
    })();
    return true;
  }
  if (msg.action === "tbcc-record-username-archive") {
    (async () => {
      try {
        const accept =
          typeof TbccUsernameFilter !== "undefined" && TbccUsernameFilter.acceptUsernameForArchive
            ? TbccUsernameFilter.acceptUsernameForArchive
            : normalizeUsernameCandidate;
        const clean =
          typeof TbccUsernameFilter !== "undefined" && TbccUsernameFilter.acceptUsernameForArchive
            ? accept(msg.username || "", {
                source: msg.source || "copy",
                ref: msg.ref || msg.pageUrl || "",
              })
            : normalizeUsernameCandidate(msg.username || "");
        if (clean && typeof TbccMasterArchive !== "undefined") {
          await TbccMasterArchive.recordUsername(clean, {
            source: msg.source || "copy",
            ref: msg.ref || msg.pageUrl || "",
          });
        }
        sendResponse({ ok: true, recorded: !!clean });
      } catch (e) {
        sendResponse({ ok: false, error: String(e.message || e) });
      }
    })();
    return true;
  }
  if (msg.action === "tbcc-resolve-copy-media-url") {
    (async () => {
      try {
        const tabId = _sender && _sender.tab && _sender.tab.id != null ? _sender.tab.id : null;
        const resolved = await tbccResolveBestCopyableMediaUrl(tabId, msg.url || "");
        if (resolved && tbccIsStorableHttpUrl(resolved) && typeof TbccMasterArchive !== "undefined") {
          void TbccMasterArchive.recordUrl(resolved, {
            source: "copy_media",
            ref: msg.pageUrl || "",
          });
        }
        sendResponse({ ok: true, url: resolved || msg.url || "" });
      } catch (e) {
        sendResponse({ ok: false, url: msg.url || "", error: String(e.message || e) });
      }
    })();
    return true;
  }
  if (msg.action === "tbcc-gallery-job-end") {
    (async () => {
      try {
        const jobs = await tbccReadGalleryJobs();
        const job = jobs.find((j) => j.id === msg.id);
        const next = jobs.filter((j) => j.id !== msg.id);
        await tbccWriteGalleryJobs(next);
        const outcome = msg.outcome && typeof msg.outcome === "object" ? msg.outcome : null;
        if (outcome && outcome.message && outcome.notifySystem) {
          notifyThrottled(
            "job-outcome-" + (job && job.type ? job.type : "task"),
            outcome.title || "TBCC",
            outcome.message,
            12000,
            outcome.clickAction || null
          );
        }
        if (next.length === 0) {
          const lock = await tbccGetDockPanelLock();
          if (lock && lock.locked) {
            await chrome.storage.local.remove(STORAGE_GALLERY_DOCK_LOCK);
            await tbccUpdateGalleryPanelOpenMode();
            notifyThrottled(
              "dock-done",
              "TBCC",
              "Docked gallery tasks finished — you can open TBCC again.",
              30000
            );
          }
        }
        sendResponse({ ok: true, remaining: next.length });
      } catch (e) {
        sendResponse({ ok: false, error: String(e.message || e) });
      }
    })();
    return true;
  }
  if (msg.action === "tbcc-gallery-dock-get") {
    (async () => {
      try {
        const jobs = await tbccReadGalleryJobs();
        if (!jobs.length) {
          await chrome.storage.local.remove(STORAGE_GALLERY_DOCK_LOCK);
          await tbccUpdateGalleryPanelOpenMode();
        }
        const data = await chrome.storage.local.get(STORAGE_GALLERY_DOCKED_TAB);
        const dock = data[STORAGE_GALLERY_DOCKED_TAB] || null;
        if (dock && dock.tabId != null) {
          try {
            const t = await chrome.tabs.get(dock.tabId);
            if (!t || !tbccIsInjectableHttpUrl(t.url)) {
              await chrome.storage.local.remove(STORAGE_GALLERY_DOCKED_TAB);
              sendResponse({ docked: false, dock: null });
              return;
            }
            sendResponse({ docked: true, dock });
          } catch (_) {
            await chrome.storage.local.remove(STORAGE_GALLERY_DOCKED_TAB);
            sendResponse({ docked: false, dock: null, stale: true });
          }
        } else {
          sendResponse({ docked: false, dock: null });
        }
      } catch (e) {
        sendResponse({ docked: false, error: String(e.message || e) });
      }
    })();
    return true;
  }
  if (msg.action === "tbcc-gallery-dock-set") {
    (async () => {
      try {
        if (msg.clear) {
          await chrome.storage.local.remove(STORAGE_GALLERY_DOCKED_TAB);
          await chrome.storage.local.remove(STORAGE_GALLERY_DOCK_LOCK);
          await tbccUpdateGalleryPanelOpenMode();
          sendResponse({ ok: true, docked: false });
          return;
        }
        const tabId = msg.tabId;
        if (tabId == null) {
          sendResponse({ ok: false, error: "tabId required" });
          return;
        }
        const t = await chrome.tabs.get(tabId);
        const r = await tbccSetGalleryDockedTab(t);
        sendResponse(r);
      } catch (e) {
        sendResponse({ ok: false, error: String(e.message || e) });
      }
    })();
    return true;
  }
  if (msg.action === "tbcc-proxy-thumb") {
    (async () => {
      const url = normalizeTbccMediaUrlForImport(msg.url);
      if (!url || !/^https?:\/\//i.test(url)) {
        sendResponse({ ok: false });
        return;
      }
      let pathLow = "";
      try {
        pathLow = new URL(url).pathname.toLowerCase();
      } catch (_) {
        sendResponse({ ok: false });
        return;
      }
      if (/\.(mp4|webm|m4v|m3u8|mpd|mov)(\?|$)/i.test(pathLow)) {
        sendResponse({ ok: false });
        return;
      }
      const cached = _tbccThumbCache.get(url);
      if (cached) {
        sendResponse({ ok: true, dataUrl: cached, cached: true });
        return;
      }
      const result = await _tbccThumbSchedule(async () => {
        try {
          const ab = await fetchUrlWithBrowserSession(url, "");
          if (!ab || ab.byteLength < 24 || ab.byteLength > TBCC_THUMB_PROXY_MAX_BYTES) {
            return { ok: false };
          }
          const dataUrl = tbccArrayBufferToDataUrl(ab);
          _tbccThumbCachePut(url, dataUrl);
          return { ok: true, dataUrl };
        } catch (_) {
          return { ok: false };
        }
      });
      sendResponse(result);
    })();
    return true;
  }
  if (msg.action === "tbcc-import-bytes-session") {
    (async () => {
      try {
        const sessionTabId = await tbccResolveSessionTabId(_sender, msg);
        const data = await importViaExtensionBytes(
          msg.url,
          msg.poolId ?? 1,
          !!msg.savedOnly,
          msg.source || "extension:gallery-session",
          msg.caption,
          msg.refererPageUrl || "",
          sessionTabId,
          msg.galleryJobId || null
        );
        sendResponse(data);
      } catch (e) {
        sendResponse({ error: String(e.message || e) });
      }
    })();
    return true;
  }
  if (msg.action === "tbcc-import-bytes-session-saved-batch") {
    (async () => {
      try {
        const urls = Array.isArray(msg.urls) ? msg.urls : [];
        if (!urls.length) {
          sendResponse({ error: "No URLs" });
          return;
        }
        const batchTabId = await tbccResolveSessionTabId(_sender, msg);
        const data = await importViaExtensionBytesSavedBatch(urls, msg.caption, batchTabId);
        sendResponse(data);
      } catch (e) {
        sendResponse({ error: String(e.message || e) });
      }
    })();
    return true;
  }
  if (msg.action === "tbcc-looms-zip-progress") {
    const tabId = msg.sourceTabId != null ? msg.sourceTabId : _sender && _sender.tab && _sender.tab.id;
    if (tabId != null) {
      chrome.tabs.sendMessage(tabId, msg).catch(() => {});
    }
    sendResponse({ ok: true });
    return true;
  }
  if (msg.action === "tbcc-content-fetch-bytes") {
    (async () => {
      try {
        const tabId = await tbccResolveSessionTabId(_sender, msg);
        const fetchOpts =
          msg.stallTimeoutMs != null && Number(msg.stallTimeoutMs) > 0
            ? { stallTimeoutMs: Number(msg.stallTimeoutMs) }
            : undefined;
        const buffer = await fetchUrlWithBrowserSession(
          normalizeTbccMediaUrlForImport(msg.url),
          msg.refererPageUrl || "",
          tabId,
          fetchOpts
        );
        sendResponse({ ok: true, buffer });
      } catch (e) {
        sendResponse({ ok: false, error: String(e.message || e) });
      }
    })();
    return true;
  }
function tbccInboxRelPath(prefix, leafName) {
  const leaf = String(leafName || "media.bin").split(/[\\/]/).pop() || "media.bin";
  return `${prefix}/${leaf}`.replace(/\/+/g, "/");
}

  if (msg.action === "tbcc-x-media-download") {
    (async () => {
      try {
        const rawUrl = String(msg.url || "").trim();
        if (!rawUrl || !/^https?:\/\//i.test(rawUrl)) {
          sendResponse({ ok: false, error: "Invalid media URL" });
          return;
        }
        const url = normalizeTbccMediaUrlForImport(rawUrl);
        const referer =
          String(msg.refererPageUrl || "").trim() ||
          (_sender && _sender.tab && _sender.tab.url) ||
          "https://x.com/";
        const kind = tbccGuessMediaKind(url, "");
        const extHint =
          kind === "video"
            ? "mp4"
            : (() => {
                try {
                  const p = new URL(url).pathname.toLowerCase();
                  if (/\.png(\?|$)/i.test(p)) return "png";
                  if (/\.webp(\?|$)/i.test(p)) return "webp";
                  if (/\.gif(\?|$)/i.test(p)) return "gif";
                } catch (_) {}
                return "jpg";
              })();
        const naming = typeof TbccZipNaming !== "undefined" ? TbccZipNaming : null;
        const profileHint = String(msg.profileHint || "").trim().replace(/^@+/, "");
        let profile =
          (naming && naming.sanitizeSegment ? naming.sanitizeSegment(profileHint) : "") ||
          (naming && naming.profileNameFromSourceUrl
            ? naming.profileNameFromSourceUrl(referer) || naming.profileNameFromSourceUrl(url)
            : "") ||
          "media";
        const indexHint = Number(msg.indexHint);
        const index =
          Number.isFinite(indexHint) && indexHint >= 1
            ? Math.floor(indexHint)
            : Math.floor(10000 + Math.random() * 90000);
        let fileName = await tbccBuildAofDownloadName(url, referer, extHint, {
          profileHint: profile,
          index,
        });
        const prefix = await tbccGetWatchInboxPrefix();
        let relMedia = tbccInboxRelPath(prefix, fileName);
        let sidecarName = fileName.replace(/\.[^.]+$/, "") + ".tbcc-meta.json";
        let relSidecar = tbccInboxRelPath(prefix, sidecarName);
        const meta = {
          tags: [],
          source_url: url,
          page_url: referer,
          aof_preprocessed: false,
          watermark_applied: false,
          defer_preprocess: true,
          name: profile,
          source_file: fileName,
          route_hint: "x_feed_download",
        };
        const dlOpts = { filename: relMedia, saveAs: false, conflictAction: "uniquify" };

        async function writeInboxSidecar() {
          try {
            const metaJson = JSON.stringify(meta, null, 2);
            const metaDataUrl =
              "data:application/json;base64," + btoa(unescape(encodeURIComponent(metaJson)));
            await tbccChromeDownloadsDownload({
              url: metaDataUrl,
              filename: relSidecar,
              saveAs: false,
              conflictAction: "uniquify",
            });
          } catch (sideErr) {
            console.warn("[TBCC] x feed inbox sidecar skipped", sideErr);
          }
        }

        // Photos: always fetch + sniff/convert — X CDN often serves WebP bytes as .jpg (direct download breaks ZIP/viewers).
        if (kind !== "video") {
          const tabId = await tbccResolveSessionTabId(_sender, msg);
          const ab = await fetchUrlWithBrowserSession(url, referer, tabId, { stallTimeoutMs: 45000 });
          const prep = await tbccPrepareImportArrayBuffer(ab, url);
          fileName = prep.name || fileName;
          meta.source_file = fileName;
          relMedia = tbccInboxRelPath(prefix, fileName);
          sidecarName = fileName.replace(/\.[^.]+$/, "") + ".tbcc-meta.json";
          relSidecar = tbccInboxRelPath(prefix, sidecarName);
          const dataUrl = tbccArrayBufferToDataUrl(prep.buffer, prep.type || "application/octet-stream");
          if (dataUrl.length > 80 * 1024 * 1024) {
            sendResponse({
              ok: false,
              error: "Image too large for extension download — open the post and retry.",
            });
            return;
          }
          const id = await tbccChromeDownloadsDownload({ filename: relMedia, saveAs: false, conflictAction: "uniquify", url: dataUrl });
          await writeInboxSidecar();
          sendResponse({ ok: true, downloadId: id, via: "photo-prep", filename: relMedia });
          return;
        }

        // Path A — direct CDN URL (videos; XEnhancer GM_download parity).
        try {
          const id = await tbccChromeDownloadsDownload({ ...dlOpts, url });
          await writeInboxSidecar();
          sendResponse({ ok: true, downloadId: id, via: "direct", filename: relMedia });
          return;
        } catch (directErr) {
          console.warn("[TBCC] x direct download failed, trying session fetch", directErr);
        }

        // Path B — session fetch then data: URL (no createObjectURL in service workers).
        const tabId = await tbccResolveSessionTabId(_sender, msg);
        const ab = await fetchUrlWithBrowserSession(url, referer, tabId, { stallTimeoutMs: 45000 });
        const prep = await tbccPrepareImportArrayBuffer(ab, url);
        fileName = prep.name || fileName;
        meta.source_file = fileName;
        relMedia = tbccInboxRelPath(prefix, fileName);
        sidecarName = fileName.replace(/\.[^.]+$/, "") + ".tbcc-meta.json";
        relSidecar = tbccInboxRelPath(prefix, sidecarName);
        const dataUrl = tbccArrayBufferToDataUrl(prep.buffer, prep.type);
        // Chrome rejects enormous data: URLs — fail clearly instead of createObjectURL.
        if (dataUrl.length > 80 * 1024 * 1024) {
          sendResponse({
            ok: false,
            error: "Media too large for SW fallback — open the post and retry (direct CDN download).",
          });
          return;
        }
        const id = await tbccChromeDownloadsDownload({ filename: relMedia, saveAs: false, conflictAction: "uniquify", url: dataUrl });
        await writeInboxSidecar();
        sendResponse({ ok: true, downloadId: id, via: "data-url", filename: relMedia });
      } catch (e) {
        sendResponse({ ok: false, error: String(e.message || e) });
      }
    })();
    return true;
  }
  /** Fetch each motherless ?full page and map detail URL → direct full-size image URL. */
  if (msg.action === "tbcc-resolve-motherless") {
    (async () => {
      const detailUrls = Array.isArray(msg.detailUrls) ? [...new Set(msg.detailUrls.filter(Boolean))] : [];
      const map = {};
      const CONC = 4;
      for (let i = 0; i < detailUrls.length; i += CONC) {
        const chunk = detailUrls.slice(i, i + CONC);
        await Promise.all(
          chunk.map(async (du) => {
            try {
              const html = await fetchMotherlessHtml(du);
              const media = parseMotherlessMediaFromHtml(html);
              if (media) map[du] = media;
            } catch (e) {
              console.warn("tbcc-resolve-motherless", du, e);
            }
          })
        );
      }
      sendResponse({ map });
    })();
    return true;
  }
  /** Coomer/Kemono: fetch /api/v1/.../post/ JSON and map post page URL → full CDN /data/… URLs. */
  if (msg.action === "tbcc-resolve-coomer") {
    (async () => {
      const postUrls = Array.isArray(msg.postUrls) ? [...new Set(msg.postUrls.filter(Boolean))] : [];
      const map = {};
      const CONC = 4;
      for (let i = 0; i < postUrls.length; i += CONC) {
        const chunk = postUrls.slice(i, i + CONC);
        await Promise.all(
          chunk.map(async (pu) => {
            try {
              const data = await fetchCoomerPostJson(pu);
              const urls = coomerFullUrlsFromPostJson(data);
              if (urls.length) map[pu] = urls;
            } catch (e) {
              console.warn("tbcc-resolve-coomer", pu, e);
            }
          })
        );
      }
      sendResponse({ map });
    })();
    return true;
  }
  /** Same-origin gallery: fetch detail HTML and map detail URL → og:image / main asset (see capture detailPageUrl). */
  if (msg.action === "tbcc-resolve-detail-page") {
    (async () => {
      const detailUrls = Array.isArray(msg.detailUrls) ? [...new Set(msg.detailUrls.filter(Boolean))] : [];
      const map = {};
      const CONC = 4;
      for (let i = 0; i < detailUrls.length; i += CONC) {
        const chunk = detailUrls.slice(i, i + CONC);
        await Promise.all(
          chunk.map(async (du) => {
            try {
              const html = await fetchDetailPageHtml(du);
              if (!html) return;
              let media = "";
              try {
                const uo = new URL(du);
                const host = (uo.hostname || "").toLowerCase();
                const path = uo.pathname || "";
                if (host === "fetlife.com" || host.endsWith(".fetlife.com")) {
                  if (/\/pictures\/\d/i.test(path)) {
                    media =
                      parseDetailPagePrimaryImageFromHtml(html) ||
                      parseMotherlessMediaFromHtml(html) ||
                      parseFetlifeStreamFromHtml(html);
                  } else {
                    media = parseFetlifeStreamFromHtml(html) || parseMotherlessMediaFromHtml(html);
                  }
                } else if (host === "erome.com" || host.endsWith(".erome.com")) {
                  media = parseEromeMediaFromHtml(html) || parseMotherlessMediaFromHtml(html);
                } else if (host === "redgifs.com" || host.endsWith(".redgifs.com")) {
                  media =
                    parseRedgifsMediaFromHtml(html) ||
                    (await fetchRedgifsMediaViaApi(du)) ||
                    parseMotherlessMediaFromHtml(html);
                } else {
                  media = parseMotherlessMediaFromHtml(html);
                }
              } catch (_) {
                media = parseMotherlessMediaFromHtml(html);
              }
              if (media) map[du] = media;
            } catch (e) {
              console.warn("tbcc-resolve-detail-page", du, e);
            }
          })
        );
      }
      sendResponse({ map });
    })();
    return true;
  }
  return false;
});

async function tbccSyncAofPools() {
  try {
    const r = await tbccFetchApi("/extension/aof-pools", { cache: "no-store" });
    if (!r.ok) return false;
    const data = await r.json();
    const pools = Array.isArray(data.pools) ? data.pools : [];
    await chrome.storage.local.set({ [STORAGE_AOF_POOLS]: pools, tbccAofPoolsSyncedAt: Date.now() });
    installContextMenus();
    return true;
  } catch (_) {
    return false;
  }
}

async function tbccSyncStorageHubTopics() {
  try {
    const bases = await tbccResolveApiBases();
    for (const base of bases) {
      try {
        const r = await fetch(base.replace(/\/+$/, "") + "/extension/storage-hub", { cache: "no-store" });
        if (!r.ok) continue;
        const data = await r.json();
        const topics = Array.isArray(data.topics) ? data.topics : [];
        if (!topics.length) continue;
        await chrome.storage.local.set({
          [STORAGE_STORAGE_HUB_TOPICS]: topics,
          tbccStorageHubTopicsSyncedAt: Date.now(),
        });
        installContextMenus();
        return true;
      } catch (_) {}
    }
  } catch (_) {}
  return false;
}

async function tbccGetStorageHubTopics() {
  try {
    const data = await chrome.storage.local.get(STORAGE_STORAGE_HUB_TOPICS);
    const topics = Array.isArray(data[STORAGE_STORAGE_HUB_TOPICS]) ? data[STORAGE_STORAGE_HUB_TOPICS] : [];
    if (topics.length) return topics;
  } catch (_) {}
  return TBCC_STORAGE_HUB_TOPICS_FALLBACK.slice();
}

function tbccInstallStorageHubContextMenus(mac) {
  mac({
    id: "tbccStorageHubParent",
    title: "TBCC: Send to Storage Hub",
    contexts: ["image", "video", "link"],
  });
  void tbccGetStorageHubTopics().then((topics) => {
    for (const t of topics) {
      const tid = parseInt(t.message_thread_id, 10);
      if (!Number.isFinite(tid) || tid < 1) continue;
      const title = String(t.menu_label || t.short_label || t.topic_title || `Topic ${tid}`).slice(0, 64);
      mac({
        id: `tbccStorageHub_${tid}`,
        parentId: "tbccStorageHubParent",
        title,
        contexts: ["image", "video", "link"],
      });
    }
    if (!topics.length) {
      mac({
        id: "tbccStorageHub_empty",
        parentId: "tbccStorageHubParent",
        title: "(No Storage Hub topics)",
        contexts: ["image", "video", "link"],
        enabled: false,
      });
    }
  });
}

/**
 * Fetch media → optional watermark → POST to Storage Hub forum topic.
 */
async function tbccSendUrlToStorageHubTopic(opts) {
  const raw = String((opts && opts.url) || "").trim();
  if (!raw || !/^https?:\/\//i.test(raw)) throw new Error("Only http(s) media URLs supported.");
  const tid = parseInt(opts && opts.messageThreadId, 10);
  if (!Number.isFinite(tid) || tid < 1) throw new Error("Invalid Storage Hub topic id.");
  let downloadUrl = normalizeTbccMediaUrlForImport(raw);
  const refererPageUrl = String((opts && opts.refererPageUrl) || "").trim();
  const tabId = opts && opts.tabId != null ? opts.tabId : null;
  const networkKey = String((opts && opts.networkKey) || "").trim();

  let ab = await fetchUrlWithBrowserSession(downloadUrl, refererPageUrl || downloadUrl, tabId, {
    stallTimeoutMs: 45000,
  });
  if (!ab || !ab.byteLength) throw new Error("Empty media body");
  let prep;
  try {
    prep = await tbccPrepareImportArrayBuffer(ab, downloadUrl);
  } catch (_) {
    prep = { buffer: ab, type: "application/octet-stream" };
  }
  let body = (prep && prep.buffer) || ab;
  const mime = (prep && prep.type) || "";
  const kind = tbccGuessMediaKind(downloadUrl, mime);
  let skipWatermark = false;
  try {
    const wm = await tbccApplySaveAofWatermark(body, kind, mime);
    if (wm && wm.buffer && wm.buffer.byteLength) {
      body = wm.buffer;
      skipWatermark = true; // already burned in
    }
  } catch (e) {
    console.warn("[TBCC] Storage Hub pre-watermark skipped", e);
    // Backend may still watermark; continue with original bytes
    skipWatermark = false;
  }

  const bases = await tbccResolveApiBases();
  let lastErr = null;
  for (const base of bases) {
    try {
      const blob = new Blob([body], {
        type: kind === "video" ? "video/mp4" : mime || "application/octet-stream",
      });
      const form = new FormData();
      form.append("file", blob, kind === "video" ? "media.mp4" : "media.jpg");
      form.append("media_type", kind === "video" ? "video" : "photo");
      form.append("message_thread_id", String(tid));
      form.append("skip_watermark", skipWatermark ? "true" : "false");
      if (networkKey) form.append("network_key", networkKey);
      const r = await fetch(base.replace(/\/+$/, "") + "/extension/storage-hub/send", {
        method: "POST",
        body: form,
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok || data.ok === false) {
        lastErr = new Error((data && data.error) || `HTTP ${r.status} @ ${base}`);
        continue;
      }
      return { ok: true, messageThreadId: tid, networkKey, via: base, result: data };
    } catch (e) {
      lastErr = e;
    }
  }
  throw lastErr || new Error("Storage Hub send unreachable — is backend on :8000?");
}

async function tbccAofPoolLabel(poolId) {
  const data = await chrome.storage.local.get(STORAGE_AOF_POOLS);
  const pools = Array.isArray(data[STORAGE_AOF_POOLS]) ? data[STORAGE_AOF_POOLS] : [];
  const row = pools.find((p) => parseInt(p.id, 10) === poolId);
  if (!row) return `pool ${poolId}`;
  return String(row.short_label || row.display_name || row.name || `pool ${poolId}`);
}

function tbccInstallAofPoolContextMenus(mac) {
  mac({
    id: "tbccAofPoolParent",
    title: "TBCC: Send to AOF pool",
    contexts: ["image", "video", "link"],
  });
  chrome.storage.local.get(STORAGE_AOF_POOLS, (data) => {
    const pools = Array.isArray(data[STORAGE_AOF_POOLS]) ? data[STORAGE_AOF_POOLS] : [];
    for (const p of pools) {
      const pid = parseInt(p.id, 10);
      if (!Number.isFinite(pid) || pid < 1) continue;
      const title = String(p.short_label || p.display_name || p.name || `Pool ${pid}`).slice(0, 64);
      mac({
        id: `tbccAofPool_${pid}`,
        parentId: "tbccAofPoolParent",
        title,
        contexts: ["image", "video", "link"],
      });
    }
    if (!pools.length) {
      mac({
        id: "tbccAofPool_empty",
        parentId: "tbccAofPoolParent",
        title: "(Backend offline — no pools)",
        contexts: ["image", "video", "link"],
        enabled: false,
      });
    }
  });
}

async function tbccSyncExtensionContextMenuSettings() {
  try {
    const r = await tbccFetchApi("/extension/context-menu", { cache: "no-store" });
    if (!r.ok) return false;
    const data = await r.json();
    const pageMenu = data && data.pageMenu && typeof data.pageMenu === "object" ? data.pageMenu : null;
    if (pageMenu) {
      await chrome.storage.local.set({
        [STORAGE_PAGE_MENU_ITEMS]: pageMenu,
        tbccPageMenuItemsSyncedAt: Date.now(),
      });
    }
    return true;
  } catch (_) {
    return false;
  }
}

function tbccEnsureContextMenuSyncAlarm() {
  void chrome.alarms.create(TBCC_CTX_MENU_SYNC_ALARM, { periodInMinutes: 3 });
}

function installContextMenus() {
  void tbccUpdateGalleryPanelOpenMode();
  chrome.contextMenus.removeAll(() => {
    const mac = (props) => {
      chrome.contextMenus.create(props, () => {
        const err = chrome.runtime.lastError;
        if (err) console.warn("TBCC contextMenus.create", props && props.id, err.message);
      });
    };
    mac({ id: "sendToTBCC", title: "TBCC: Save to pool (default)", contexts: ["image", "video", "link"] });
    mac({
      id: "saveAofWatch",
      title: "TBCC: Save AOF (watermark + watch)",
      contexts: ["image", "video", "link"],
    });
    mac({
      id: "uploadR2Library",
      title: "TBCC: Watermark → R2 aof-media (library)",
      contexts: ["image", "video", "link"],
    });
    mac({
      id: "uploadR2SfwXPromo",
      title: "TBCC: Watermark → R2 SFW X promo",
      contexts: ["image", "video", "link"],
    });
    tbccInstallAofPoolContextMenus(mac);
    tbccInstallStorageHubContextMenus(mac);
    mac({ id: "sendToSaved", title: "TBCC: Saved Messages", contexts: ["image", "video", "link"] });
    mac({ id: "sendPageToTBCC", title: "TBCC: Save to pool (this tab URL)", contexts: ["page", "frame"] });
    mac({ id: "sendPageToSaved", title: "TBCC: Saved Messages (this tab URL)", contexts: ["page", "frame"] });
    mac({ id: "sendSelectionToTBCC", title: "TBCC: Save to pool (selected URL)", contexts: ["selection"] });
    mac({ id: "sendSelectionToSaved", title: "TBCC: Saved Messages (selected URL)", contexts: ["selection"] });
    mac({
      id: "tbccCaptureSecretSelection",
      title: "TBCC: Save selection as API key to .env (browser)",
      contexts: ["selection"],
    });
    mac({
      id: "tbccAddVideoUrlToList",
      title: "TBCC: Save URL to master archive",
      contexts: ["selection", "link", "page", "frame", "video"],
    });
    mac({
      id: "tbccAddAllVideoUrlsToList",
      title: "TBCC: Save all video URLs to master archive",
      contexts: ["page", "frame", "video", "link"],
    });
    mac({
      id: "tbccReverseImageFanout",
      title: "TBCC: Reverse image search",
      contexts: ["image"],
    });
    mac({
      id: "tbccCaptureTabReverse",
      title: "TBCC: Capture tab for reverse search",
      contexts: ["page", "frame"],
    });
    mac({
      id: "tbccMotherlessGalleryZip",
      title: "TBCC: Motherless gallery → ZIP",
      contexts: ["page", "frame", "link"],
      documentUrlPatterns: [
        "*://motherless.com/*",
        "*://*.motherless.com/*",
        "*://motherless.xxx/*",
        "*://*.motherless.xxx/*",
      ],
    });
    mac({
      id: "tbccMotherlessGalleryDownload",
      title: "TBCC: Motherless gallery → download files",
      contexts: ["page", "frame", "link"],
      documentUrlPatterns: [
        "*://motherless.com/*",
        "*://*.motherless.com/*",
        "*://motherless.xxx/*",
        "*://*.motherless.xxx/*",
      ],
    });
    mac({
      id: "tbccDockGallery",
      title: "TBCC: Dock gallery to this tab",
      contexts: ["page", "frame"],
    });
    mac({ id: "tbccActionOpenGallery", title: "TBCC: Open gallery", contexts: ["action"] });
    mac({
      id: "tbccActionDockGallery",
      title: "TBCC: Open gallery (docked to this tab)",
      contexts: ["action"],
    });
    mac({
      id: "tbccActionStartApi",
      title: "TBCC: Launch full stack (daemon/API)",
      contexts: ["action"],
    });
    if (typeof TBCC_EXT_MODULES !== "undefined" && TBCC_EXT_MODULES.installActionMenus) {
      TBCC_EXT_MODULES.installActionMenus(mac);
      void TBCC_EXT_MODULES.refreshMenuLabels();
    }
    void (async () => {
      try {
        await addModelSearchContextMenus(mac);
      } catch (e) {
        console.warn("TBCC model search context menus", e);
      }
    })();
  });
}

async function addModelSearchContextMenus(mac) {
  const CTX_MS = ["selection", "link", "page", "frame", "video"];
  let cfg;
  try {
    cfg = await getMergedModelSearchSites();
  } catch (_) {
    return;
  }
  const data = await chrome.storage.local.get(STORAGE_MODEL_SEARCH_ENABLED);
  const enabled = data[STORAGE_MODEL_SEARCH_ENABLED] || {};
  const sites = (cfg.sites || []).filter((s) => enabled[s.id] !== false);
  if (!sites.length) return;
  const onlyfansSites = sites.filter((s) => normalizeModelSearchCategory(s.category) === MODEL_SEARCH_CATEGORY_ONLYFANS);
  const livecamSites = sites.filter((s) => normalizeModelSearchCategory(s.category) === MODEL_SEARCH_CATEGORY_LIVECAMS);
  const videoSites = sites.filter((s) => normalizeModelSearchCategory(s.category) === MODEL_SEARCH_CATEGORY_VIDEOS);
  mac({
    id: "tbccModelSearchRoot",
    title: "TBCC: Look up username",
    contexts: CTX_MS,
  });
  mac({
    id: "tbccms_all_onlyfans",
    parentId: "tbccModelSearchRoot",
    title: "Open all enabled OnlyFans sources",
    contexts: CTX_MS,
  });
  mac({
    id: "tbccms_all_livecams",
    parentId: "tbccModelSearchRoot",
    title: "Open all enabled live cam sources",
    contexts: CTX_MS,
  });
  mac({
    id: "tbccms_all_videos",
    parentId: "tbccModelSearchRoot",
    title: "Open all enabled video sources",
    contexts: CTX_MS,
  });
  mac({
    id: "tbccms_macro",
    parentId: "tbccModelSearchRoot",
    title: "Macro search (native report, all macro sources)",
    contexts: CTX_MS,
  });
  mac({
    id: "tbccms_approve_overlay_host",
    parentId: "tbccModelSearchRoot",
    title: "Enable macrosearch overlay on this site",
    contexts: ["page", "action"],
  });
  mac({
    id: "tbccms_sep_clip",
    parentId: "tbccModelSearchRoot",
    type: "separator",
    contexts: CTX_MS,
  });
  mac({
    id: "tbccms_clip_onlyfans",
    parentId: "tbccModelSearchRoot",
    title: "Search copied username (OnlyFans sources)",
    contexts: CTX_MS,
  });
  mac({
    id: "tbccms_clip_livecams",
    parentId: "tbccModelSearchRoot",
    title: "Search copied username (live cam sources)",
    contexts: CTX_MS,
  });
  mac({
    id: "tbccms_clip_videos",
    parentId: "tbccModelSearchRoot",
    title: "Search copied username (video sources)",
    contexts: CTX_MS,
  });
  mac({
    id: "tbccms_sep0",
    parentId: "tbccModelSearchRoot",
    type: "separator",
    contexts: CTX_MS,
  });
  mac({
    id: "tbccms_group_onlyfans",
    parentId: "tbccModelSearchRoot",
    title: "OnlyFans sources",
    contexts: CTX_MS,
  });
  for (const s of onlyfansSites) {
    mac({
      id: tbccMenuIdForSite(s.id),
      parentId: "tbccms_group_onlyfans",
      title: String(s.name || s.id).slice(0, 120),
      contexts: CTX_MS,
    });
  }
  mac({
    id: "tbccms_group_livecams",
    parentId: "tbccModelSearchRoot",
    title: "Live cam sources",
    contexts: CTX_MS,
  });
  for (const s of livecamSites) {
    mac({
      id: tbccMenuIdForSite(s.id),
      parentId: "tbccms_group_livecams",
      title: String(s.name || s.id).slice(0, 120),
      contexts: CTX_MS,
    });
  }
  mac({
    id: "tbccms_group_videos",
    parentId: "tbccModelSearchRoot",
    title: "Video sources",
    contexts: CTX_MS,
  });
  for (const s of videoSites) {
    mac({
      id: tbccMenuIdForSite(s.id),
      parentId: "tbccms_group_videos",
      title: String(s.name || s.id).slice(0, 120),
      contexts: CTX_MS,
    });
  }
  mac({
    id: "tbccms_bot_videofind",
    parentId: "tbccModelSearchRoot",
    title: "Send /macrosearch in payment bot",
    contexts: CTX_MS,
  });
  mac({
    id: "tbccms_sep_saved_videos",
    parentId: "tbccModelSearchRoot",
    type: "separator",
    contexts: CTX_MS,
  });
  mac({
    id: "tbccAddVideoUrlToListNested",
    parentId: "tbccModelSearchRoot",
    title: "Add URL to TBCC inbox",
    contexts: CTX_MS,
  });
  mac({
    id: "tbccAddAllVideoUrlsToListNested",
    parentId: "tbccModelSearchRoot",
    title: "Save all video URLs to inbox (this page)",
    contexts: CTX_MS,
  });
}

const TBCC_OPS_ALERTS_ALARM = "tbcc-ops-alerts";
const TBCC_OPS_ALERTS_SEEN_KEY = "tbccOpsAlertsSeenIds";

async function tbccPollOpsAlerts() {
  try {
    const r = await tbccFetchApi("/ops/alerts/poll", { cache: "no-store" });
    if (!r.ok) return;
    const data = await r.json();
    if (data && data.enabled === false) return;
    if (data && data.restart_grace && data.restart_grace.active) return;
    const alerts = Array.isArray(data.alerts) ? data.alerts : [];
    if (!alerts.length) return;
    const stored = await chrome.storage.session.get(TBCC_OPS_ALERTS_SEEN_KEY);
    const seen = new Set(Array.isArray(stored[TBCC_OPS_ALERTS_SEEN_KEY]) ? stored[TBCC_OPS_ALERTS_SEEN_KEY] : []);
    const fresh = [];
        for (const a of alerts) {
          if (!a || !a.id || seen.has(a.id)) continue;
          const kind = String(a.kind || "").toLowerCase();
          const code = String(a.code || "").toLowerCase();
          if (kind === "error_hub" || code === "error_hub_digest") continue;
          if (!data.hub_toast && kind === "error_hub") continue;
          seen.add(a.id);
          fresh.push(a);
        }
    if (!fresh.length) return;
    const trimmed = [...seen].slice(-120);
    await chrome.storage.session.set({ [TBCC_OPS_ALERTS_SEEN_KEY]: trimmed });
    for (const a of fresh) {
      const isCritical = String(a.severity || "").toLowerCase() === "critical";
      const title = a.title || "TBCC alert";
      const message = a.message || title;
      notifyThrottled(
        "ops-alert:" + a.id,
        title,
        message,
        isCritical ? 90000 : 120000,
        { type: "url", url: "http://127.0.0.1:5173/" }
      );
      try {
        chrome.runtime.sendMessage({ action: "tbcc-ops-alert-toast", alert: a }, () => void chrome.runtime.lastError);
      } catch (_) {}
    }
  } catch (_) {}
}

function tbccEnsureOpsAlertsAlarm() {
  void chrome.alarms.create(TBCC_OPS_ALERTS_ALARM, { periodInMinutes: 1 });
}

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm && alarm.name === TBCC_CTX_MENU_SYNC_ALARM) {
    void tbccSyncExtensionContextMenuSettings();
    void tbccSyncAofPools();
    void tbccSyncStorageHubTopics();
    return;
  }
  if (alarm && alarm.name === TBCC_OPS_ALERTS_ALARM) {
    void tbccPollOpsAlerts();
    return;
  }
  if (!alarm || !alarm.name || !alarm.name.startsWith(TBCC_IMPORT_POLL_ALARM_PREFIX)) return;
  const galleryJobId = alarm.name.slice(TBCC_IMPORT_POLL_ALARM_PREFIX.length);
  void (async () => {
    const jobs = await tbccReadGalleryJobs();
    const j = jobs.find((x) => x && x.id === galleryJobId);
    if (!j || !j.backendJobId) {
      await tbccClearImportPollAlarm(galleryJobId);
      return;
    }
    if (tbccIsBackendImportTerminal(j.status)) {
      await tbccClearImportPollAlarm(galleryJobId);
      return;
    }
    await tbccPollImportJobViaAlarm(galleryJobId, j.backendJobId);
  })();
});

chrome.runtime.onInstalled.addListener((details) => {
  installContextMenus();
  tbccEnsureOpsAlertsAlarm();
  tbccEnsureContextMenuSyncAlarm();
  void tbccSyncExtensionContextMenuSettings();
  void tbccSyncAofPools();
  void tbccSyncStorageHubTopics();
  void tbccPollOpsAlerts();
  void tbccBootstrapImportJobRecovery();
  if (details && details.reason === "update") {
    void (async () => {
      try {
        const tabs = await chrome.tabs.query({
          url: [
            "*://erome.com/*",
            "*://www.erome.com/*",
            "*://x.com/*",
            "*://twitter.com/*",
          ],
        });
        if (tabs.length) {
          notify(
            "TBCC updated",
            "Reload open X / Erome tabs (Ctrl+R) so enhancer & overlay scripts run."
          );
        }
      } catch (_) {}
    })();
  }
  void (async () => {
    try {
      if (typeof TbccMasterArchive !== "undefined") {
        const arch = await TbccMasterArchive.restoreFromBackupIfEmpty();
        if (arch.restored) {
          notify("TBCC", `Restored ${arch.count} master archive entries from backup.`);
        }
        const inbox = await TbccMasterArchive.restoreInboxFromMirrorIfEmpty(
          async () => {
            const data = await chrome.storage.local.get(STORAGE_SAVED_VIDEO_URLS);
            return Array.isArray(data[STORAGE_SAVED_VIDEO_URLS]) ? data[STORAGE_SAVED_VIDEO_URLS] : [];
          },
          async (rows) => {
            await chrome.storage.local.set({ [STORAGE_SAVED_VIDEO_URLS]: rows.slice(0, TBCC_SAVED_VIDEO_URLS_CAP) });
          }
        );
        if (inbox.restored) {
          notify("TBCC", `Restored ${inbox.count} URL inbox entries from mirror.`);
        }
      }
    } catch (e) {
      console.warn("TBCC storage recovery", e);
    }
  })();
});

chrome.runtime.onStartup.addListener(() => {
  installContextMenus();
  tbccEnsureOpsAlertsAlarm();
  tbccEnsureContextMenuSyncAlarm();
  void tbccSyncExtensionContextMenuSettings();
  void tbccSyncAofPools();
  void tbccSyncStorageHubTopics();
  void tbccPollOpsAlerts();
  void tbccBootstrapImportJobRecovery();
  void (async () => {
    const jobs = await tbccReadGalleryJobs();
    if (!jobs.length) {
      await chrome.storage.local.remove(STORAGE_GALLERY_DOCK_LOCK);
    }
    await tbccUpdateGalleryPanelOpenMode();
  })();
});

chrome.storage.onChanged.addListener((changes, area) => {
  if (area !== "local") return;
  if (
    changes[STORAGE_MODEL_SEARCH_ENABLED] ||
    changes[STORAGE_MODEL_SEARCH_CUSTOM_SITES]
  ) {
    installContextMenus();
  }
});

/** Gallery closed: disable on-page overlay so checkboxes do not linger on tabs. */
async function clearPageOverlayModeForClosedGallery() {
  try {
    const { tbccOverlayMode } = await chrome.storage.local.get("tbccOverlayMode");
    if (!tbccOverlayMode) return;
    await chrome.storage.local.set({ tbccOverlayMode: false });
  } catch (_) {}
}

/** Only runs when dock lock is active (openPanelOnActionClick is false). Normal clicks use native side-panel open. */
chrome.action.onClicked.addListener((tab) => {
  void (async () => {
    const lock = await tbccGetDockPanelLock();
    if (!lock || !lock.locked || !(lock.jobCount > 0)) return;
    notifyThrottled(
      "dock-lock",
      "TBCC",
      `${lock.jobCount} task(s) still running on ${lock.hostname || lock.title || "docked tab"}. Wait for the finished notification, or use pop-out (⎘) on that tab.`,
      15000
    );
    void tab;
  })();
});

chrome.runtime.onConnect.addListener((port) => {
  if (port.name !== "tbcc-gallery-sidepanel") return;
  port.onDisconnect.addListener(() => {
    void clearPageOverlayModeForClosedGallery();
  });
});

try {
  const sp = chrome.sidePanel;
  if (sp && typeof sp.onClosed?.addListener === "function") {
    sp.onClosed.addListener(() => {
      void clearPageOverlayModeForClosedGallery();
    });
  }
} catch (_) {}

const _tbccNotifyThrottleAt = new Map();

/** System notifications — keep cadence low so alerts stay meaningful. */
function notifyThrottled(key, title, message, minIntervalMs = 12000, clickAction = null) {
  const k = String(key || title || "tbcc");
  const now = Date.now();
  const last = _tbccNotifyThrottleAt.get(k) || 0;
  if (now - last < minIntervalMs) return;
  _tbccNotifyThrottleAt.set(k, now);
  notify(title, message, clickAction || null);
}

/**
 * Packaged PNG only — data: URLs and tiny/decoding edge cases often throw
 * "Unable to download all specified images" (extensions::notifications) in Brave/Chromium MV3.
 */
function tbccFormatImportError(msg) {
  const s = String(msg || "Import failed").trim();
  if (/telegram session|wrong session id|admin\.session|login_telethon_sessions/i.test(s)) {
    return s.length > 420 ? s.slice(0, 420) + "…" : s;
  }
  if (s.includes("fetch") || s.includes("Failed to fetch")) {
    return "Cannot reach TBCC API. Set Options → API base (e.g. https://api.powercore.app) + Internal key, or start home tray backend.";
  }
  return s.length > 280 ? s.slice(0, 280) + "…" : s;
}

const TBCC_NOTIFICATION_ACTIONS_KEY = "tbccNotificationActions";

async function tbccStoreNotificationAction(notificationId, clickAction) {
  if (!clickAction || typeof clickAction !== "object") return;
  try {
    const data = await chrome.storage.session.get(TBCC_NOTIFICATION_ACTIONS_KEY);
    const map = data[TBCC_NOTIFICATION_ACTIONS_KEY] || {};
    map[notificationId] = clickAction;
    await chrome.storage.session.set({ [TBCC_NOTIFICATION_ACTIONS_KEY]: map });
  } catch (_) {}
}

async function tbccTakeNotificationAction(notificationId) {
  try {
    const data = await chrome.storage.session.get(TBCC_NOTIFICATION_ACTIONS_KEY);
    const map = data[TBCC_NOTIFICATION_ACTIONS_KEY] || {};
    const action = map[notificationId] || null;
    if (action) {
      delete map[notificationId];
      await chrome.storage.session.set({ [TBCC_NOTIFICATION_ACTIONS_KEY]: map });
    }
    return action;
  } catch (_) {
    return null;
  }
}

async function tbccOpenTelegramSavedMessages() {
  try {
    const r = await tbccFetchApi("/telegram/open-saved", { method: "POST", cache: "no-store" });
    if (r.ok) return;
  } catch (_) {}

  let userId = null;
  let username = "";
  try {
    const r = await tbccFetchApi("/health/telegram/import", { cache: "no-store" });
    const j = await r.json();
    if (j && j.ok) {
      userId = j.user_id != null ? Number(j.user_id) : null;
      username = String(j.username || "").trim().replace(/^@+/, "");
    }
  } catch (_) {}
  if (!userId && !username) {
    try {
      const r = await tbccFetchApi("/health/telegram", { cache: "no-store" });
      const j = await r.json();
      if (j && j.ok) {
        userId = j.user_id != null ? Number(j.user_id) : null;
        username = String(j.username || "").trim().replace(/^@+/, "");
      }
    } catch (_) {}
  }
  const tgUrls = [];
  if (Number.isFinite(userId) && userId > 0) tgUrls.push("tg://user?id=" + userId);
  if (username) tgUrls.push("tg://resolve?domain=" + encodeURIComponent(username));
  for (const url of tgUrls) {
    try {
      await chrome.tabs.create({ url, active: true });
      return;
    } catch (_) {}
  }
}

const TBCC_NOTIFY_ICON = "icons/icon16.png";

async function tbccGetNotificationStyle() {
  try {
    const data = await chrome.storage.local.get("tbcc_gallery_settings");
    const s = data.tbcc_gallery_settings;
    const v = s && s.notificationStyle ? String(s.notificationStyle) : "full";
    if (v === "app_name_only" || v === "body_only" || v === "minimal") return v;
    return "full";
  } catch (_) {
    return "full";
  }
}

function tbccFormatNotificationText(title, message, style) {
  const t = String(title || "TBCC").trim() || "TBCC";
  const m = String(message || "").trim();
  if (style === "app_name_only") return { title: "TBCC", message: m || t };
  if (style === "body_only") return { title: " ", message: m || t };
  if (style === "minimal") return { title: "TBCC", message: m ? m.slice(0, 120) : "" };
  return { title: t, message: m };
}

async function tbccEnsureGallerySidePanelOpen() {
  try {
    const wins = await chrome.windows.getAll({ windowTypes: ["normal"] });
    let windowId = null;
    for (const w of wins) {
      if (w.focused && w.id != null) {
        windowId = w.id;
        break;
      }
    }
    if (windowId == null) {
      for (const w of wins) {
        if (w.id != null) {
          windowId = w.id;
          break;
        }
      }
    }
    if (windowId != null) await chrome.sidePanel.open({ windowId });
  } catch (_) {}
}

function tbccPostGalleryPanelMessage(payload) {
  const attempt = () => {
    try {
      chrome.runtime.sendMessage(payload, () => void chrome.runtime.lastError);
    } catch (_) {}
  };
  attempt();
  [450, 1100, 2200, 3500].forEach((ms) => window.setTimeout(attempt, ms));
}

async function tbccOpenGalleryInbox(url) {
  await tbccEnsureGallerySidePanelOpen();
  tbccPostGalleryPanelMessage({ action: "tbcc-gallery-open-inbox", url: url || null });
}

async function tbccOpenGalleryMasterArchive() {
  await tbccEnsureGallerySidePanelOpen();
  tbccPostGalleryPanelMessage({ action: "tbcc-gallery-open-archive" });
}

async function tbccOpenGalleryDestPanel() {
  await tbccEnsureGallerySidePanelOpen();
  tbccPostGalleryPanelMessage({ action: "tbcc-gallery-open-dest" });
}

async function tbccOpenGalleryCollected() {
  await tbccEnsureGallerySidePanelOpen();
  tbccPostGalleryPanelMessage({ action: "tbcc-gallery-open-collected" });
}

async function tbccHandleNotificationClickAction(clickAction) {
  if (!clickAction || typeof clickAction !== "object") return;
  if (clickAction.type === "telegram_saved") {
    await tbccOpenTelegramSavedMessages();
    return;
  }
  if (clickAction.type === "gallery_inbox") {
    await tbccOpenGalleryInbox(clickAction.url || null);
    return;
  }
  if (clickAction.type === "gallery_master_archive") {
    await tbccOpenGalleryMasterArchive();
    return;
  }
  if (clickAction.type === "gallery_dest") {
    await tbccOpenGalleryDestPanel();
    return;
  }
  if (clickAction.type === "gallery_sidepanel") {
    await tbccEnsureGallerySidePanelOpen();
    return;
  }
  if (clickAction.type === "gallery_collected") {
    await tbccOpenGalleryCollected();
    return;
  }
  const url = String(clickAction.url || "").trim();
  if (clickAction.type === "url" && /^https?:\/\//i.test(url)) {
    try {
      await chrome.tabs.create({ url, active: true });
    } catch (_) {}
  }
}

function tbccGradePrefixForOsNotify(title, message) {
  try {
    const sev = typeof TBCC_SEVERITY_TOAST !== "undefined" ? TBCC_SEVERITY_TOAST : null;
    if (!sev) return "";
    const blob = `${title || ""} ${message || ""}`.toLowerCase();
    let kind = "info";
    if (/sale|payment|💰/.test(blob)) kind = "payment";
    else if (/pending|invoice|checkout/.test(blob)) kind = "pending";
    else if (/critical|urgent|unreachable|fail/.test(blob)) kind = "critical";
    else if (/overdue|stall|warn|circuit/.test(blob)) kind = "warning";
    else if (/success|saved|imported|done/.test(blob)) kind = "success";
    const calm = sev.calmToastStyle(kind);
    return calm && calm.emoji ? `${calm.emoji} ` : "";
  } catch (_) {
    return "";
  }
}

function notify(title, message, clickAction) {
  void (async () => {
    try {
      const style = await tbccGetNotificationStyle();
      const formatted = tbccFormatNotificationText(title, message, style);
      const grade = tbccGradePrefixForOsNotify(formatted.title, formatted.message);
      const iconUrl = chrome.runtime.getURL(TBCC_NOTIFY_ICON);
      const id = "tbcc-" + Date.now();
      if (clickAction) await tbccStoreNotificationAction(id, clickAction);
      chrome.notifications.create(
        id,
        {
          type: "basic",
          iconUrl,
          title: grade + formatted.title,
          message: formatted.message,
        },
        () => {
          const err = chrome.runtime.lastError;
          if (err) console.warn("TBCC notification:", err.message);
        }
      );
    } catch (e) {
      console.log("TBCC:", title, message, e);
    }
  })();
}

chrome.notifications.onClicked.addListener((notificationId) => {
  void (async () => {
    const action = await tbccTakeNotificationAction(notificationId);
    if (action) await tbccHandleNotificationClickAction(action);
    try {
      chrome.notifications.clear(notificationId);
    } catch (_) {}
  })();
});

function isSavedMenuId(id) {
  return id === "sendToSaved" || id === "sendPageToSaved" || id === "sendSelectionToSaved";
}

async function tbccExtensionPageMenuBlocked(id) {
  if (typeof TBCC_EXT_MODULES === "undefined") return false;
  const pageIds =
    id === "sendToTBCC" ||
    isSavedMenuId(id) ||
    id === "sendPageToTBCC" ||
    id === "sendSelectionToTBCC" ||
    id === "tbccAddVideoUrlToList" ||
    id === "tbccAddVideoUrlToListNested" ||
    id === "tbccAddAllVideoUrlsToList" ||
    id === "tbccAddAllVideoUrlsToListNested" ||
    id === "tbccReverseImageFanout" ||
    id === "tbccCaptureTabReverse" ||
    id === "tbccDockGallery" ||
    String(id).startsWith("tbccAofPool_") ||
    String(id).startsWith("tbccStorageHub_") ||
    String(id).startsWith("tbccms_");
  if (!pageIds) return false;
  const map = await TBCC_EXT_MODULES.getEnabledMap();
  if (!TBCC_EXT_MODULES.isEnabled(map, "context_menus")) return true;
  if (isSavedMenuId(id) && !TBCC_EXT_MODULES.isEnabled(map, "send_saved")) return true;
  return false;
}

function tbccNormalizeAutoTagToken(raw) {
  const u = typeof TbccAutoTagUtils !== "undefined" ? TbccAutoTagUtils : null;
  if (u && u.normalizeAutoTagCandidate) return u.normalizeAutoTagCandidate(raw);
  const s = String(raw || "")
    .trim()
    .replace(/^#+/u, "")
    .replace(/[_\-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  if (!s || s.length < 2 || s.length > 64) return "";
  const low = s.toLowerCase();
  if (TBCC_AUTOTAG_STOPWORDS.has(low)) return "";
  if (/^\d+$/u.test(s)) return "";
  return s;
}

function tbccDisplayTagToHashtag(tag) {
  const raw = String(tag || "")
    .trim()
    .replace(/^#+/u, "");
  if (!raw) return "";
  const u = typeof TbccAutoTagUtils !== "undefined" ? TbccAutoTagUtils : null;
  if (u && u.isJunkAutoTagToken && u.isJunkAutoTagToken(raw)) return "";
  const compact = raw.replace(/\s+/gu, "");
  if (!compact) return "";
  const capped = compact.length > 42 ? compact.slice(0, 42) : compact;
  return "#" + capped;
}

function tbccCollectSemanticTagsFromUrl(rawUrl, outSet) {
  const u = typeof TbccAutoTagUtils !== "undefined" ? TbccAutoTagUtils : null;
  if (!u || !u.extractSemanticTagsFromUrl) return;
  for (const t of u.extractSemanticTagsFromUrl(rawUrl)) {
    if (u.isTraceSourceLabel && u.isTraceSourceLabel(t)) continue;
    const b = tbccNormalizeAutoTagToken(t);
    if (b) outSet.add(b);
  }
}

function tbccIsTraceSourceLabel(raw) {
  const u = typeof TbccAutoTagUtils !== "undefined" ? TbccAutoTagUtils : null;
  return !!(u && u.isTraceSourceLabel && u.isTraceSourceLabel(raw));
}

function tbccBuildAutoTagPayload(url, refererPageUrl) {
  const tags = new Set();
  const ref = String(refererPageUrl || "").trim();
  const primary = ref && /^https?:\/\//i.test(ref) ? ref : String(url || "").trim();
  tbccCollectSemanticTagsFromUrl(primary, tags);
  const list = [...tags];
  const csv = list.join(", ");
  const hashtags = list.map((t) => tbccDisplayTagToHashtag(t)).filter(Boolean);
  const caption = hashtags.join(" ").trim().slice(0, 900);
  return { tagsCsv: csv, caption };
}

async function tbccBuildAutoTagPayloadAsync(url, refererPageUrl, tabId) {
  const tags = new Set();
  const ref = String(refererPageUrl || "").trim();
  const primary = ref && /^https?:\/\//i.test(ref) ? ref : String(url || "").trim();
  tbccCollectSemanticTagsFromUrl(primary, tags);

  let titleLine = "";
  let descLine = "";
  if (tabId != null) {
    try {
      await chrome.scripting.executeScript({
        target: { tabId },
        files: ["media-url-guards.js", "auto-tag-utils.js", "capture.js"],
      });
      const exec = await chrome.scripting.executeScript({
        target: { tabId },
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
        const bundle = res.bundle || {};
        titleLine = String(bundle.title || "").trim();
        descLine = String(bundle.description || "").trim();
        if (Array.isArray(res.hints)) {
          for (const h of res.hints) {
            if (tbccIsTraceSourceLabel(h)) continue;
            const t = tbccNormalizeAutoTagToken(h);
            if (t) tags.add(t);
          }
        }
      }
    } catch (_) {}
  }

  try {
    const r = await tbccFetchApi("/tags/enrich-send", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        items: [{ source_page_url: primary, media_url: String(url || "").trim(), page_host: "" }],
        manual_tags: [],
        fast: true,
        max_lustpress_pages: 1,
        max_nsfw_samples: 1,
      }),
    });
    if (r.ok) {
      const j = await r.json();
      if (j && Array.isArray(j.labels)) {
        for (const lbl of j.labels) {
          if (tbccIsTraceSourceLabel(lbl)) continue;
          const t = tbccNormalizeAutoTagToken(lbl);
          if (t) tags.add(t);
        }
      }
      if (!titleLine && j && j.caption_line) titleLine = String(j.caption_line).trim();
    }
  } catch (_) {}

  const list = [...tags].filter((t) => !tbccIsTraceSourceLabel(t));
  const csv = list.join(", ");
  const hashtags = list.map((t) => tbccDisplayTagToHashtag(t)).filter(Boolean);
  const tagLine = hashtags.join(" ").trim();
  const capParts = [titleLine, descLine].filter((p) => p && !tbccIsTraceSourceLabel(p));
  let caption = capParts.length ? capParts.join("\n\n") : "";
  if (tagLine) caption = caption ? `${caption}\n\n${tagLine}` : tagLine;
  caption = caption.trim().slice(0, 900);
  return { tagsCsv: csv, caption };
}


const STORAGE_WATCH_INBOX_PREFIX = "tbccWatchInboxPrefix";
const STORAGE_SAVE_AOF_ON_DOWNLOAD = "tbccSaveAofOnDownload";
const STORAGE_API_BASE = "tbccApiBase";
const API_WATERMARK_BYTES_PATH = "/import/watermark-bytes";
/** Soft size gate for SW data: URL downloads after watermark (bytes). */
const TBCC_SAVE_AOF_MAX_DATA_URL = 55 * 1024 * 1024;
/** Soft size gate for SW → R2 multipart upload (bytes). */
const TBCC_R2_UPLOAD_MAX_BYTES = 80 * 1024 * 1024;
/** Soft size gate for SW → zip flywheel (bytes). Large packs need Pixeldrain on API. */
const TBCC_ZIP_FLYWHEEL_MAX_BYTES = 200 * 1024 * 1024;
const TBCC_WM_TEXT = "telegram.me/aofmainhub";

async function tbccGetPromoWatermarkConfigFromStorage() {
  try {
    const data = await chrome.storage.local.get("tbcc_gallery_settings");
    const s = data.tbcc_gallery_settings || {};
    if (typeof TbccPromoWatermark !== "undefined" && TbccPromoWatermark.promoWatermarkFromGallerySettings) {
      return TbccPromoWatermark.promoWatermarkFromGallerySettings(s);
    }
    return { enabled: s.skipPromoWatermark !== true };
  } catch (_) {
    return typeof TbccPromoWatermark !== "undefined"
      ? TbccPromoWatermark.normalizePromoWatermark({})
      : { enabled: true };
  }
}

async function tbccWatermarkBytesViaApi(arrayBuffer, mediaTypeHint) {
  const bases = await tbccResolveApiBases();
  const cfg = await tbccGetPromoWatermarkConfigFromStorage();
  let lastErr = null;
  for (const base of bases) {
    try {
      const blob = new Blob([arrayBuffer], {
        type: mediaTypeHint === "video" ? "video/mp4" : "application/octet-stream",
      });
      const form = new FormData();
      form.append("file", blob, mediaTypeHint === "video" ? "media.mp4" : "media.jpg");
      form.append("media_type", mediaTypeHint === "video" ? "video" : "photo");
      form.append("skip_watermark", cfg.enabled ? "false" : "true");
      if (typeof TbccPromoWatermark !== "undefined" && TbccPromoWatermark.appendWatermarkConfigToForm) {
        TbccPromoWatermark.appendWatermarkConfigToForm(form, cfg);
      }
      const headers = await tbccInternalApiHeaders();
      const r = await fetch(base.replace(/\/+$/, "") + API_WATERMARK_BYTES_PATH, {
        method: "POST",
        body: form,
        headers,
      });
      if (!r.ok) {
        lastErr = new Error(`watermark-bytes HTTP ${r.status} @ ${base}`);
        continue;
      }
      const ab = await r.arrayBuffer();
      if (ab && ab.byteLength) return ab;
      lastErr = new Error(`empty watermark response @ ${base}`);
    } catch (e) {
      lastErr = e;
    }
  }
  throw lastErr || new Error("watermark-bytes unreachable");
}

/**
 * POST browse-intel rows. Resolves ingest URL from hint or Options tbccApiBase.
 * Runs in SW so HTTPS pages (erome.com) are not blocked by mixed-content on http://127.0.0.1.
 */
async function tbccPushBrowseIntelRows(rows, urlHint) {
  const list = Array.isArray(rows) ? rows : [];
  if (!list.length) throw new Error("No intel rows to push");

  const hint = String(urlHint || "").trim().replace(/\/$/, "");
  const candidates = [];
  if (hint && /^https?:\/\//i.test(hint)) candidates.push(hint);

  const bases = await tbccResolveApiBases();
  for (const base of bases) {
    candidates.push(`${String(base).replace(/\/+$/, "")}/analytics/erome-browse-intel`);
  }
  const urls = [...new Set(candidates.filter(Boolean))];
  const headers = await tbccInternalApiHeaders();
  let lastErr = "unreachable";
  for (const url of urls) {
    try {
      const res = await fetch(url, {
        method: "POST",
        headers,
        body: JSON.stringify({ rows: list }),
      });
      let data = {};
      try {
        data = await res.json();
      } catch (_) {}
      if (res.ok) {
        return {
          ok: true,
          url,
          appended: data.appended != null ? data.appended : list.length,
          scanned: data.scanned != null ? data.scanned : list.length,
          data,
        };
      }
      const detail = data.detail || data.error || `HTTP ${res.status}`;
      lastErr = `${url} → ${detail}`;
      if (res.status === 403) {
        lastErr =
          `${url} → 403 Forbidden — set Internal API key in extension Options ` +
          `(island has TBCC_API_REQUIRE_INTERNAL=1)`;
      }
    } catch (e) {
      lastErr = `${url} → ${(e && e.message) || e}`;
    }
  }
  throw new Error(
    `TBCC API unreachable (${lastErr}). Start tray backend on :8000, or set Options → API base ` +
      `(e.g. island) + Internal key. Export JSONL as backup.`
  );
}

/**
 * GET browse-intel /summary via SW — avoids Brave/Chrome "access other apps/local network"
 * prompts when HTTPS pages (erome.com) would otherwise fetch http://127.0.0.1 directly.
 */
async function tbccFetchBrowseIntelSummary(urlHint, days) {
  const d = Math.max(1, Math.min(90, Number(days) || 30));
  const hint = String(urlHint || "").trim().replace(/\/$/, "");
  const candidates = [];
  const pushSummary = (ingestBase) => {
    const b = String(ingestBase || "").trim().replace(/\/$/, "");
    if (!b || !/^https?:\/\//i.test(b)) return;
    candidates.push(`${b}/summary?days=${d}`);
  };
  pushSummary(hint);
  const bases = await tbccResolveApiBases();
  for (const base of bases) {
    pushSummary(`${String(base).replace(/\/+$/, "")}/analytics/erome-browse-intel`);
  }
  const urls = [...new Set(candidates.filter(Boolean))];
  const headers = await tbccInternalApiHeaders();
  let lastErr = "unreachable";
  for (const url of urls) {
    try {
      const res = await fetch(url, { method: "GET", headers, cache: "no-store" });
      let data = {};
      try {
        data = await res.json();
      } catch (_) {}
      if (res.ok) return { ok: true, url, data };
      lastErr = `${url} → ${data.detail || data.error || `HTTP ${res.status}`}`;
    } catch (e) {
      lastErr = `${url} → ${(e && e.message) || e}`;
    }
  }
  throw new Error(`Intel summary unreachable (${lastErr})`);
}

/** SW-local image burn-in when API is down (photos only). */
async function tbccWatermarkImageBytesLocal(arrayBuffer, mimeHint, cfg) {
  const wmCfg = cfg || (await tbccGetPromoWatermarkConfigFromStorage());
  if (!wmCfg.enabled) return arrayBuffer;
  if (typeof TbccPromoWatermark !== "undefined" && TbccPromoWatermark.applyPromoWatermarkBlob) {
    const mime = String(mimeHint || "image/jpeg").split(";")[0] || "image/jpeg";
    const blob = new Blob([arrayBuffer], { type: mime.startsWith("image/") ? mime : "image/jpeg" });
    const out = await TbccPromoWatermark.applyPromoWatermarkBlob(blob, "photo", wmCfg);
    return await out.arrayBuffer();
  }
  if (typeof createImageBitmap !== "function" || typeof OffscreenCanvas === "undefined") {
    throw new Error("OffscreenCanvas unavailable");
  }
  const mime = String(mimeHint || "image/jpeg").split(";")[0] || "image/jpeg";
  const blob = new Blob([arrayBuffer], { type: mime.startsWith("image/") ? mime : "image/jpeg" });
  const bmp = await createImageBitmap(blob);
  try {
    const w = bmp.width || 1;
    const h = bmp.height || 1;
    const canvas = new OffscreenCanvas(w, h);
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("2d context missing");
    ctx.drawImage(bmp, 0, 0);
    const fontSize = Math.max(14, Math.round(Math.min(w, h) * 0.032));
    ctx.font = `700 ${fontSize}px system-ui,Segoe UI,sans-serif`;
    ctx.textBaseline = "bottom";
    ctx.lineWidth = Math.max(2, Math.round(fontSize / 8));
    ctx.strokeStyle = "rgba(0,0,0,0.72)";
    ctx.fillStyle = "rgba(255,255,255,0.92)";
    const pad = Math.round(fontSize * 0.55);
    const x = pad;
    const y = h - pad;
    ctx.strokeText(TBCC_WM_TEXT, x, y);
    ctx.fillText(TBCC_WM_TEXT, x, y);
    const outType = mime.includes("png") ? "image/png" : "image/jpeg";
    const outBlob = await canvas.convertToBlob(
      outType === "image/png" ? { type: outType } : { type: "image/jpeg", quality: 0.92 }
    );
    return await outBlob.arrayBuffer();
  } finally {
    try {
      bmp.close();
    } catch (_) {}
  }
}

async function tbccApplySaveAofWatermark(body, kind, mime) {
  const asVideo = kind === "video";
  try {
    const wm = await tbccWatermarkBytesViaApi(body, asVideo ? "video" : "photo");
    if (wm && wm.byteLength) return { buffer: wm, applied: true, via: "api" };
  } catch (e) {
    console.warn("[TBCC] Save AOF API watermark failed", e);
    if (asVideo) {
      throw new Error(
        `Video watermark needs TBCC backend (127.0.0.1:8000): ${e && e.message ? e.message : e}`
      );
    }
  }
  if (!asVideo) {
    try {
      const wmCfg = await tbccGetPromoWatermarkConfigFromStorage();
      const local = await tbccWatermarkImageBytesLocal(body, mime, wmCfg);
      if (local && local.byteLength) return { buffer: local, applied: true, via: "local" };
    } catch (e) {
      console.warn("[TBCC] Save AOF local image watermark failed", e);
      throw new Error(
        `Image watermark failed (API + local): ${e && e.message ? e.message : e}`
      );
    }
  }
  throw new Error("Watermark produced empty body");
}

/** Low-CPU tags: URL semantics + page hints only (no /tags/enrich-send). */
async function tbccBuildLocalPageTagsAsync(url, refererPageUrl, tabId) {
  const tags = new Set();
  const ref = String(refererPageUrl || "").trim();
  const primary = ref && /^https?:\/\//i.test(ref) ? ref : String(url || "").trim();
  tbccCollectSemanticTagsFromUrl(primary, tags);
  if (tabId != null) {
    try {
      await chrome.scripting.executeScript({
        target: { tabId },
        files: ["media-url-guards.js", "auto-tag-utils.js", "capture.js"],
      });
      const exec = await chrome.scripting.executeScript({
        target: { tabId },
        func: () =>
          typeof window.__tbccCollectTagHints === "function" ? window.__tbccCollectTagHints() : [],
      });
      const hints = exec && exec[0] && exec[0].result;
      if (Array.isArray(hints)) {
        for (const h of hints) {
          if (tbccIsTraceSourceLabel(h)) continue;
          const tok = tbccNormalizeAutoTagToken(h);
          if (tok) tags.add(tok);
        }
      }
    } catch (_) {}
  }
  return [...tags].filter((x) => !tbccIsTraceSourceLabel(x));
}

async function tbccGetWatchInboxPrefix() {
  try {
    const d = await chrome.storage.local.get(STORAGE_WATCH_INBOX_PREFIX);
    const raw = String(d[STORAGE_WATCH_INBOX_PREFIX] || "tbcc/inbox").trim().replace(/\\/g, "/");
    return raw.replace(/^\/+|\/+$/g, "") || "tbcc/inbox";
  } catch (_) {
    return "tbcc/inbox";
  }
}

function tbccGuessMediaKind(url, mime) {
  const m = String(mime || "").toLowerCase();
  if (m.startsWith("video/")) return "video";
  const path = String(url || "").toLowerCase();
  if (/\.(mp4|webm|mov|mkv|m4v)(\?|$)/i.test(path)) return "video";
  return "photo";
}

async function tbccGetExportNamingPrefs() {
  try {
    const data = await chrome.storage.local.get(["tbcc_gallery_settings", "tbccXProfileGallerySettings"]);
    const s =
      data.tbcc_gallery_settings && typeof data.tbcc_gallery_settings === "object"
        ? data.tbcc_gallery_settings
        : {};
    const looms =
      data.tbccXProfileGallerySettings && typeof data.tbccXProfileGallerySettings === "object"
        ? data.tbccXProfileGallerySettings
        : {};
    const naming = typeof TbccZipNaming !== "undefined" ? TbccZipNaming : null;
    const heuristicNaming = s.zipHeuristicNaming !== false;
    const entryTemplate =
      (s.zipEntryTemplate && String(s.zipEntryTemplate).trim()) ||
      (looms.zipNameTemplate && String(looms.zipNameTemplate).trim()) ||
      (naming ? naming.DEFAULT_TEMPLATE : "");
    return { heuristicNaming, entryTemplate, naming };
  } catch (_) {
    const naming = typeof TbccZipNaming !== "undefined" ? TbccZipNaming : null;
    return {
      heuristicNaming: true,
      entryTemplate: naming ? naming.DEFAULT_TEMPLATE : "",
      naming,
    };
  }
}

async function tbccBuildAofDownloadName(url, refererPageUrl, extHint, opts) {
  const o = opts && typeof opts === "object" ? opts : {};
  const prefs = await tbccGetExportNamingPrefs();
  const naming = prefs.naming;
  const ext =
    (extHint || "").replace(/^\./, "") ||
    (() => {
      try {
        const p = new URL(url).pathname;
        const base = (p.split("/").pop() || "").split("?")[0];
        const dot = base.lastIndexOf(".");
        if (dot > 0) return base.slice(dot + 1).toLowerCase().replace(/[^\w]/g, "").slice(0, 5);
      } catch (_) {}
      return "jpg";
    })();
  const index =
    o.index != null && Number.isFinite(Number(o.index)) && Number(o.index) >= 1
      ? Math.floor(Number(o.index))
      : Math.floor(10000 + Math.random() * 90000);
  if (naming && naming.buildExportFilename) {
    return naming.buildExportFilename({
      sourceUrl: refererPageUrl || url || "",
      pageTitle: o.pageTitle || "",
      profileHint: o.profileHint || o.profileName || "",
      index,
      ext,
      baseName: o.baseName,
      mime: o.mime,
      template: prefs.entryTemplate,
      heuristicNaming: prefs.heuristicNaming,
    });
  }
  let name = "media";
  if (naming && naming.inferZipContext) {
    name = naming.inferZipContext({ sourceUrl: refererPageUrl || url || "" }).name;
  } else if (naming) {
    name =
      naming.profileNameFromSourceUrl(refererPageUrl || "") ||
      naming.profileNameFromSourceUrl(url || "") ||
      "media";
  }
  if (naming && naming.buildZipFilename) {
    return naming.buildZipFilename(naming.DEFAULT_TEMPLATE, { name, index, ext });
  }
  const seg = String(name || "media").replace(/[^\w.\-]+/g, "_").slice(0, 64) || "media";
  return `AOF_${seg}_${String(index).padStart(5, "0")}_telegram.me_aofmainhub.${ext || "jpg"}`;
}

/**
 * Fetch → watermark (when small enough) → AOF name → Downloads/{inboxPrefix}/ + sidecar.
 * Large / failed watermark: still drop file with aof_preprocessed:false for organizer.
 */
async function tbccSaveAofMediaToWatch(opts) {
  const raw = String((opts && opts.url) || "").trim();
  if (!raw || !/^https?:\/\//i.test(raw)) throw new Error("Only http(s) media URLs supported.");
  let downloadUrl = normalizeTbccMediaUrlForImport(raw);
  const preferFull = !opts || opts.preferFull !== false;
  const refererPageUrl = String((opts && opts.refererPageUrl) || "").trim();
  const tabId = opts && opts.tabId != null ? opts.tabId : null;

  try {
    const u = new URL(downloadUrl);
    const isRedgifs = /(^|\.)redgifs\.com$/i.test(u.hostname || "");
    const hasRedItem = /^\/(?:watch|ifr|gifs)\/[^/?#]+/i.test(u.pathname || "") || !!redgifsIdFromAnyUrl(downloadUrl);
    if (preferFull && isRedgifs) {
      const candidate = hasRedItem ? downloadUrl : refererPageUrl;
      const resolved = candidate ? await fetchRedgifsMediaViaApi(candidate) : "";
      if (resolved && /^https?:\/\//i.test(resolved)) downloadUrl = normalizeTbccMediaUrlForImport(resolved);
    }
  } catch (_) {}

  const tags = await tbccBuildLocalPageTagsAsync(downloadUrl, refererPageUrl, tabId);
  const prefix = await tbccGetWatchInboxPrefix();
  let ab = null;
  let mime = "";
  try {
    ab = await fetchUrlWithBrowserSession(downloadUrl, refererPageUrl || downloadUrl, tabId, {
      stallTimeoutMs: 45000,
    });
  } catch (e) {
    throw new Error(`Fetch failed: ${e && e.message ? e.message : e}`);
  }
  if (!ab || !ab.byteLength) throw new Error("Empty media body");

  let prep;
  try {
    prep = await tbccPrepareImportArrayBuffer(ab, downloadUrl);
  } catch (_) {
    prep = { buffer: ab, type: "application/octet-stream" };
  }
  mime = (prep && prep.type) || "";
  let body = (prep && prep.buffer) || ab;
  const kind = tbccGuessMediaKind(downloadUrl, mime);
  let watermarkApplied = false;
  let preprocessed = false;
  let watermarkVia = "";

  // Always watermark before AOF name drop (images: API then local canvas; video: API required).
  // Soft size gate: huge videos still try API once; on failure defer to organizer with clear flag.
  const tooBigForSwWm = kind === "video" && body.byteLength >= 40 * 1024 * 1024;
  if (!tooBigForSwWm) {
    try {
      const wm = await tbccApplySaveAofWatermark(body, kind, mime);
      body = wm.buffer;
      watermarkApplied = !!wm.applied;
      watermarkVia = wm.via || "";
      preprocessed = watermarkApplied;
      if (wm.via === "local" && mime && !mime.includes("png")) {
        mime = "image/jpeg";
      }
    } catch (e) {
      console.warn("[TBCC] Save AOF watermark failed", e);
      if (kind === "video") {
        // Fall through: CDN download + sidecar defer so watch organizer can burn-in when API is up
        watermarkApplied = false;
        preprocessed = false;
      } else {
        throw e;
      }
    }
  }

  const extHint =
    kind === "video"
      ? "mp4"
      : mime.includes("png")
        ? "png"
        : mime.includes("webp")
          ? "webp"
          : mime.includes("gif")
            ? "gif"
            : "jpg";
  const fileName = await tbccBuildAofDownloadName(downloadUrl, refererPageUrl, extHint);

  const relMedia = `${prefix}/${fileName}`.replace(/\/+/g, "/");
  const sidecarName = fileName.replace(/\.[^.]+$/, "") + ".tbcc-meta.json";
  const relSidecar = `${prefix}/${sidecarName}`.replace(/\/+/g, "/");

  const meta = {
    tags,
    source_url: downloadUrl,
    page_url: refererPageUrl || "",
    aof_preprocessed: !!watermarkApplied,
    watermark_applied: !!watermarkApplied,
    watermark_via: watermarkVia || undefined,
    name:
      (typeof TbccZipNaming !== "undefined" && TbccZipNaming.inferZipContext
        ? TbccZipNaming.inferZipContext({ sourceUrl: refererPageUrl || downloadUrl }).name
        : typeof TbccZipNaming !== "undefined" && TbccZipNaming.profileNameFromSourceUrl
          ? TbccZipNaming.profileNameFromSourceUrl(refererPageUrl || downloadUrl)
          : "") || "media",
    source_file: fileName,
    route_hint: "extension_save_aof",
  };

  const useDataUrl = watermarkApplied && body && body.byteLength;
  let dataUrl = "";
  if (useDataUrl) {
    dataUrl = tbccArrayBufferToDataUrl(body, mime || (kind === "video" ? "video/mp4" : "image/jpeg"));
  }
  if (!useDataUrl || dataUrl.length > TBCC_SAVE_AOF_MAX_DATA_URL) {
    // Unwatermarked or too large for SW — direct CDN download + sidecar; organizer post-processes
    meta.aof_preprocessed = false;
    meta.watermark_applied = false;
    meta.defer_preprocess = true;
    await tbccChromeDownloadsDownload({
      url: downloadUrl,
      filename: relMedia,
      saveAs: false,
      conflictAction: "uniquify",
    });
  } else {
    await tbccChromeDownloadsDownload({
      url: dataUrl,
      filename: relMedia,
      saveAs: false,
      conflictAction: "uniquify",
    });
  }

  const metaJson = JSON.stringify(meta, null, 2);
  const metaDataUrl =
    "data:application/json;base64," +
    btoa(unescape(encodeURIComponent(metaJson)));
  await tbccChromeDownloadsDownload({
    url: metaDataUrl,
    filename: relSidecar,
    saveAs: false,
    conflictAction: "uniquify",
  });

  return {
    ok: true,
    filename: relMedia,
    tags,
    watermarkApplied: meta.watermark_applied,
    preprocessed: meta.aof_preprocessed,
    watermarkVia,
    deferred: !!meta.defer_preprocess,
  };
}

async function tbccClipboardWriteText(text) {
  const t = String(text || "").trim();
  if (!t) return false;
  try {
    if (typeof navigator !== "undefined" && navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(t);
      return true;
    }
  } catch (_) {}
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab || tab.id == null) return false;
    await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      args: [t],
      func: async (value) => {
        try {
          await navigator.clipboard.writeText(value);
        } catch (_) {
          const ta = document.createElement("textarea");
          ta.value = value;
          document.body.appendChild(ta);
          ta.select();
          document.execCommand("copy");
          ta.remove();
        }
      },
    });
    return true;
  } catch (_) {
    return false;
  }
}

/**
 * POST zip/media blob → /import/zip-flywheel (hybrid R2/Pixeldrain → gate → modifier/SKU).
 * action: host_gated | loot_modifier | shop_bundle
 */
async function tbccZipFlywheelUpload(opts) {
  const blob = opts && opts.blob;
  if (!blob || !(blob instanceof Blob) || !blob.size) throw new Error("Empty zip blob");
  if (blob.size > TBCC_ZIP_FLYWHEEL_MAX_BYTES) {
    throw new Error(
      `Zip too large for flywheel (${Math.round(blob.size / (1024 * 1024))} MB); max ~200 MB via extension`
    );
  }
  const action = String((opts && opts.action) || "host_gated").trim() || "host_gated";
  const host = String((opts && opts.host) || "auto").trim() || "auto";
  const preferR2 = !!(opts && opts.preferR2);
  const naming = typeof TbccZipNaming !== "undefined" ? TbccZipNaming : null;
  let filename = String((opts && opts.filename) || "").trim();
  if (!filename && naming && typeof naming.buildDestinationFilename === "function") {
    filename = naming.buildDestinationFilename(action === "shop_bundle" ? "shop_bundle" : "host_gated", {
      name: (opts && opts.name) || "",
      profileName: (opts && opts.profileName) || "",
      sourceUrl: (opts && opts.sourceUrl) || "",
      ext: "zip",
    });
  }
  if (!filename) filename = `pack_${Date.now()}.zip`;
  if (!/\.zip$/i.test(filename)) filename += ".zip";
  // Quiet leaf for object storage (strip tbcc/ prefix)
  filename = filename.replace(/^tbcc\//i, "").split("/").pop() || filename;

  const form = new FormData();
  form.append("file", blob, filename);
  form.append("action", action);
  form.append("host", host);
  form.append("prefer_r2", preferR2 ? "true" : "false");
  form.append("filename", filename);
  if (opts && opts.label) form.append("label", String(opts.label).slice(0, 200));
  if (opts && opts.planId) form.append("plan_id", String(opts.planId));
  form.append("source_note", String((opts && opts.sourceNote) || "ext_zip_flywheel").slice(0, 200));

  const r = await tbccFetchApi("/import/zip-flywheel", { method: "POST", body: form });
  let data = null;
  try {
    data = await r.json();
  } catch (_) {
    data = null;
  }
  if (!r.ok || !data || !data.ok) {
    const err = (data && data.error) || `zip-flywheel HTTP ${r.status}`;
    throw new Error(err);
  }
  const primary = String(data.primary_url || data.destination_url || "").trim();
  if (primary) {
    try {
      await tbccClipboardWriteText(primary);
    } catch (_) {}
  }
  try {
    chrome.notifications.create({
      type: "basic",
      iconUrl: "icons/icon128.png",
      title: "TBCC zip flywheel",
      message: `${action} · ${data.host || "?"} · ${(primary || "").slice(0, 80)}`,
    });
  } catch (_) {}
  return data;
}

/**
 * Fetch → watermark via API → upload to R2 (library/ or sfw-x-promo/).
 * Context menus: Watermark → R2 aof-media (library) / R2 SFW X promo.
 */
async function tbccWatermarkUploadToR2(opts) {
  const raw = String((opts && opts.url) || "").trim();
  if (!raw || !/^https?:\/\//i.test(raw)) throw new Error("Only http(s) media URLs supported.");
  let downloadUrl = normalizeTbccMediaUrlForImport(raw);
  const preferFull = !opts || opts.preferFull !== false;
  const refererPageUrl = String((opts && opts.refererPageUrl) || "").trim();
  const tabId = opts && opts.tabId != null ? opts.tabId : null;
  const destination = String((opts && opts.destination) || "library").trim() || "library";

  try {
    const u = new URL(downloadUrl);
    const isRedgifs = /(^|\.)redgifs\.com$/i.test(u.hostname || "");
    const hasRedItem = /^\/(?:watch|ifr|gifs)\/[^/?#]+/i.test(u.pathname || "") || !!redgifsIdFromAnyUrl(downloadUrl);
    if (preferFull && isRedgifs) {
      const candidate = hasRedItem ? downloadUrl : refererPageUrl;
      const resolved = candidate ? await fetchRedgifsMediaViaApi(candidate) : "";
      if (resolved && /^https?:\/\//i.test(resolved)) downloadUrl = normalizeTbccMediaUrlForImport(resolved);
    }
  } catch (_) {}

  let ab = null;
  let mime = "";
  try {
    ab = await fetchUrlWithBrowserSession(downloadUrl, refererPageUrl || downloadUrl, tabId, {
      stallTimeoutMs: 45000,
    });
  } catch (e) {
    throw new Error(`Fetch failed: ${e && e.message ? e.message : e}`);
  }
  if (!ab || !ab.byteLength) throw new Error("Empty media body");
  if (ab.byteLength > TBCC_R2_UPLOAD_MAX_BYTES) {
    throw new Error(
      `File too large for R2 upload (${Math.round(ab.byteLength / (1024 * 1024))} MB); max ~80 MB via extension`
    );
  }

  let prep;
  try {
    prep = await tbccPrepareImportArrayBuffer(ab, downloadUrl);
  } catch (_) {
    prep = { buffer: ab, type: "application/octet-stream" };
  }
  mime = (prep && prep.type) || "";
  const body = (prep && prep.buffer) || ab;
  const kind = tbccGuessMediaKind(downloadUrl, mime);
  const fileName = await tbccBuildAofDownloadName(
    downloadUrl,
    refererPageUrl,
    kind === "video" ? "mp4" : mime.includes("png") ? "png" : mime.includes("webp") ? "webp" : mime.includes("gif") ? "gif" : "jpg"
  );

  const form = new FormData();
  form.append(
    "file",
    new Blob([body], { type: mime || (kind === "video" ? "video/mp4" : "application/octet-stream") }),
    fileName
  );
  form.append("media_type", kind === "video" ? "video" : "photo");
  form.append("destination", destination);
  form.append("filename", fileName);
  form.append("skip_watermark", "false");

  const r = await tbccFetchApi("/import/watermark-upload-r2", { method: "POST", body: form });
  const text = await r.text();
  let data = {};
  try {
    data = text ? JSON.parse(text) : {};
  } catch (_) {}
  if (!r.ok || data.ok === false) {
    throw new Error((data && data.error) || text || `HTTP ${r.status}`);
  }
  const directUrl = String((data && data.direct_url) || "").trim();
  if (!directUrl) throw new Error("R2 upload returned no public URL");

  const clipped = await tbccClipboardWriteText(directUrl);
  return {
    ok: true,
    directUrl,
    objectKey: data.object_key || "",
    watermarked: !!data.watermarked,
    destination: data.destination || destination,
    filename: data.filename || fileName,
    clipped,
  };
}

async function tbccApplyTagsToImportedMediaIds(mediaIds, tagsCsv) {
  const csv = String(tagsCsv || "").trim();
  if (!csv) return;
  const ids = [...new Set((mediaIds || []).map((x) => parseInt(x, 10)).filter((x) => Number.isFinite(x)))];
  if (!ids.length) return;
  const r = await tbccFetchApi("/media/bulk/tags", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ids, tags: csv, tags_merge: true }),
  });
  const text = await r.text();
  let data = {};
  try {
    data = text ? JSON.parse(text) : {};
  } catch (_) {}
  if (!r.ok || data.error) throw new Error(data.error || data.detail || text || `HTTP ${r.status}`);
}

function resolveUrlFromContextClick(info, tab) {
  const id = String(info.menuItemId || "");
  if (id === "sendPageToTBCC" || id === "sendPageToSaved") {
    return (info.pageUrl || tab?.url || "").trim();
  }
  if (id === "sendSelectionToTBCC" || id === "sendSelectionToSaved") {
    let t = (info.selectionText || "").trim().replace(/^["'\s]+|["'\s]+$/g, "");
    const m = t.match(/https?:\/\/[^\s"'<>\])]+/i);
    if (m) return m[0];
    return "";
  }
  return (info.srcUrl || info.linkUrl || "").trim();
}

function tbccIsStorableHttpUrl(u) {
  const s = String(u || "").trim();
  return s && /^https?:\/\//i.test(s) && !s.startsWith("blob:") && !s.startsWith("data:");
}

/** Prefer link / watch page over raw media src when several are present. */
function resolveUrlForSavedVideoList(info, tab) {
  const link = (info.linkUrl || "").trim();
  if (tbccIsStorableHttpUrl(link)) return link;
  const src = (info.srcUrl || "").trim();
  if (tbccIsStorableHttpUrl(src)) return src;
  const page = (info.pageUrl || tab?.url || "").trim();
  if (tbccIsStorableHttpUrl(page) && !/^chrome-extension:/i.test(page)) return page;
  let t = (info.selectionText || "").trim().replace(/^["'\s]+|["'\s]+$/g, "");
  const m = t.match(/https?:\/\/[^\s"'<>\])]+/i);
  if (m) return m[0].replace(/[.,);:]+$/g, "");
  return "";
}

/** Skip HLS/DASH segment noise when logging or bulk-saving video URLs. */
function tbccInboxWorthyNetVideoUrl(url) {
  if (!tbccIsStorableHttpUrl(url)) return false;
  try {
    const path = new URL(url).pathname.toLowerCase();
    if (/\.(m4s|ts|aac)(\?|$)/i.test(path)) return false;
    return tbccWebRequestUrlLooksLikeMedia(url) || tbccWebRequestUrlLooksLikeHlsManifest(url);
  } catch (_) {
    return false;
  }
}

async function tbccCollectVideoUrlsFromTab(tabId) {
  if (tabId == null || tabId < 0) return [];
  const merged = new Set();
  try {
    await chrome.scripting.executeScript({
      target: { tabId, allFrames: true },
      files: ["media-url-guards.js", "auto-tag-utils.js", "capture.js"],
    });
    const injected = await chrome.scripting.executeScript({
      target: { tabId, allFrames: true },
      func: () =>
        typeof window.__tbccCollectVideoUrlsForInbox === "function"
          ? window.__tbccCollectVideoUrlsForInbox()
          : [],
    });
    for (const row of injected || []) {
      const list = row && row.result;
      if (!Array.isArray(list)) continue;
      for (const u of list) {
        if (tbccIsStorableHttpUrl(u)) merged.add(String(u).trim());
      }
    }
  } catch (e) {
    console.warn("TBCC collectVideoUrlsFromTab inject", e);
  }
  try {
    const got = await chrome.storage.session.get([
      `tbcc_net_media_${tabId}`,
      `tbcc_net_manifest_${tabId}`,
    ]);
    const net = got[`tbcc_net_media_${tabId}`];
    if (Array.isArray(net)) {
      for (const u of net) {
        if (tbccInboxWorthyNetVideoUrl(u)) merged.add(String(u).trim());
      }
    }
    const mans = got[`tbcc_net_manifest_${tabId}`];
    if (Array.isArray(mans)) {
      for (const u of mans) {
        if (tbccIsStorableHttpUrl(u)) merged.add(String(u).trim());
      }
    }
  } catch (_) {}
  return [...merged];
}

function tbccExtractHttpUrlsFromText(text) {
  const merged = new Set();
  const re = /https?:\/\/[^\s<>"')\]]+/gi;
  for (const m of String(text || "").match(re) || []) {
    const u = String(m)
      .trim()
      .replace(/[.,;)]+$/g, "");
    if (tbccIsStorableHttpUrl(u)) merged.add(u);
  }
  return [...merged];
}

async function tbccCollectHttpUrlsFromTab(tabId) {
  if (tabId == null || tabId < 0) return [];
  const merged = new Set();
  try {
    const injected = await chrome.scripting.executeScript({
      target: { tabId, allFrames: true },
      func: () => {
        const re = /https?:\/\/[^\s<>"')\]]+/gi;
        const chunks = [];
        if (document.body && document.body.innerText) chunks.push(document.body.innerText);
        for (const a of document.querySelectorAll("a[href]")) {
          const h = a.getAttribute("href");
          if (h && /^https?:\/\//i.test(h)) chunks.push(h);
        }
        const out = new Set();
        for (const blob of chunks) {
          for (const m of String(blob).match(re) || []) {
            out.add(m.replace(/[.,;)]+$/g, ""));
          }
        }
        return [...out];
      },
    });
    for (const row of injected || []) {
      const list = row && row.result;
      if (!Array.isArray(list)) continue;
      for (const u of list) {
        if (tbccIsStorableHttpUrl(u)) merged.add(String(u).trim());
      }
    }
  } catch (e) {
    console.warn("TBCC collectHttpUrlsFromTab", e);
  }
  return [...merged];
}

async function tbccAppendSavedVideoUrlsBulk(urls, refPageUrl, opts) {
  const cleanList = [...new Set(urls.map((u) => String(u || "").trim()).filter((u) => tbccIsStorableHttpUrl(u)))];
  if (!cleanList.length) return { ok: false, error: "No video URLs found on this page.", added: 0, duplicate: 0 };
  const data = await chrome.storage.local.get([STORAGE_SAVED_VIDEO_URLS, "tbccPoolId"]);
  let arr = Array.isArray(data[STORAGE_SAVED_VIDEO_URLS]) ? data[STORAGE_SAVED_VIDEO_URLS] : [];
  const existing = new Set(arr.map((x) => (x && x.url ? String(x.url).trim() : "")).filter(Boolean));
  const ref = String(refPageUrl || "").trim();
  const refOk = ref && tbccIsStorableHttpUrl(ref) && !/^chrome-extension:/i.test(ref) ? ref : undefined;
  let poolId = opts && opts.poolId != null ? parseInt(opts.poolId, 10) : NaN;
  if (!Number.isFinite(poolId) || poolId < 1) {
    const fromStorage = parseInt(data.tbccPoolId, 10);
    poolId = Number.isFinite(fromStorage) && fromStorage > 0 ? fromStorage : null;
  } else {
    poolId = poolId > 0 ? poolId : null;
  }
  const tagsCsv = opts && opts.tagsCsv ? String(opts.tagsCsv).trim() : "";
  const note = opts && opts.note ? String(opts.note).trim() : "";
  let destType =
    opts && opts.destType === "loot_modifier"
      ? "loot_modifier"
      : opts && opts.destType === "archive"
        ? "archive"
        : opts && opts.destType === "pool"
          ? "pool"
          : null;
  if (!destType) {
    const destStored = await chrome.storage.local.get(["tbccInboxDefaultDestV1"]);
    const stored = destStored.tbccInboxDefaultDestV1;
    if (stored === "loot_modifier") destType = "loot_modifier";
    else if (stored === "pool") destType = "pool";
    else destType = "archive";
  }
  if (destType === "archive") {
    if (typeof TbccMasterArchive !== "undefined") {
      for (const url of cleanList) {
        void TbccMasterArchive.recordUrl(url, {
          source: "inbox",
          ref: refOk,
          tags: tagsCsv,
          note,
        });
      }
    }
    return { ok: true, added: cleanList.length, duplicate: 0, total: cleanList.length, archived: true };
  }
  let added = 0;
  let duplicate = 0;
  const newRows = [];
  const baseTs = Date.now();
  for (let i = 0; i < cleanList.length; i++) {
    const url = cleanList[i];
    if (existing.has(url)) {
      duplicate++;
      continue;
    }
    existing.add(url);
    newRows.push({
      url,
      addedAt: baseTs - i,
      ref: refOk,
      destType,
      poolId: destType === "pool" ? poolId : null,
      tagsCsv,
      note,
      status: "queued",
    });
    added++;
  }
  if (!newRows.length) return { ok: true, added: 0, duplicate, total: cleanList.length };
  arr = [...newRows, ...arr].slice(0, TBCC_SAVED_VIDEO_URLS_CAP);
  await chrome.storage.local.set({ [STORAGE_SAVED_VIDEO_URLS]: arr });
  await tbccAfterInboxSave(arr, newRows.map((r) => r.url));
  return { ok: true, added, duplicate, total: cleanList.length };
}

async function tbccAppendSavedVideoUrl(url, refPageUrl, opts) {
  const clean = String(url || "").trim();
  if (!tbccIsStorableHttpUrl(clean)) return { ok: false, error: "Need an http(s) URL (not blob/data)." };
  const data = await chrome.storage.local.get([STORAGE_SAVED_VIDEO_URLS, "tbccPoolId"]);
  let arr = Array.isArray(data[STORAGE_SAVED_VIDEO_URLS]) ? data[STORAGE_SAVED_VIDEO_URLS] : [];
  const dup = arr.some((x) => x && String(x.url).trim() === clean);
  if (dup) return { ok: true, duplicate: true };
  const ref = String(refPageUrl || "").trim();
  const refOk = ref && tbccIsStorableHttpUrl(ref) && !/^chrome-extension:/i.test(ref) ? ref : undefined;
  let poolId = opts && opts.poolId != null ? parseInt(opts.poolId, 10) : NaN;
  if (!Number.isFinite(poolId) || poolId < 1) {
    const fromStorage = parseInt(data.tbccPoolId, 10);
    poolId = Number.isFinite(fromStorage) && fromStorage > 0 ? fromStorage : null;
  } else {
    poolId = poolId > 0 ? poolId : null;
  }
  const tagsCsv = opts && opts.tagsCsv ? String(opts.tagsCsv).trim() : "";
  const note = opts && opts.note ? String(opts.note).trim() : "";
  let destType =
    opts && opts.destType === "loot_modifier"
      ? "loot_modifier"
      : opts && opts.destType === "archive"
        ? "archive"
        : opts && opts.destType === "pool"
          ? "pool"
          : null;
  if (!destType) {
    const destStored = await chrome.storage.local.get(["tbccInboxDefaultDestV1"]);
    const stored = destStored.tbccInboxDefaultDestV1;
    if (stored === "loot_modifier") destType = "loot_modifier";
    else if (stored === "pool") destType = "pool";
    else destType = "archive";
  }
  if (destType === "archive") {
    if (typeof TbccMasterArchive !== "undefined") {
      void TbccMasterArchive.recordUrl(clean, {
        source: "inbox",
        ref: refOk,
        tags: tagsCsv,
        note,
      });
    }
    return { ok: true, duplicate: false, archived: true };
  }
  arr = [
    {
      url: clean,
      addedAt: Date.now(),
      ref: refOk,
      destType,
      poolId: destType === "pool" ? poolId : null,
      tagsCsv,
      note,
      status: "queued",
    },
    ...arr,
  ].slice(0, TBCC_SAVED_VIDEO_URLS_CAP);
  await chrome.storage.local.set({ [STORAGE_SAVED_VIDEO_URLS]: arr });
  await tbccAfterInboxSave(arr, [clean]);
  return { ok: true, duplicate: false };
}

async function tbccSavedImportNotifyMessage(data) {
  let account = "";
  try {
    const r = await tbccFetchApi("/health/telegram/import", { cache: "no-store" });
    const j = await r.json();
    if (j && j.ok && j.username) account = "@" + String(j.username).replace(/^@+/, "");
    else if (j && j.ok && j.user_id) account = "user " + j.user_id;
  } catch (_) {}
  const mid = data && data.telegram_message_id != null ? Number(data.telegram_message_id) : null;
  const parts = ["Saved to Saved Messages"];
  if (account) parts.push(account);
  if (mid) parts.push("msg " + mid);
  parts.push("— click to open");
  return parts.join(" ");
}

async function importUrlViaTbcc(url, savedOnly, source, refererPageUrl, autoTagPayload, tabId, poolIdOverride) {
  let cleanUrl = String(url || "").trim();
  if (!cleanUrl) return { ok: false, error: "No URL for this action." };
  if (tabId != null) {
    cleanUrl = await resolveMediaUrlFromTab(tabId, cleanUrl);
  }
  if (!/^https?:\/\//i.test(cleanUrl)) {
    if (/^blob:|^data:/i.test(cleanUrl)) {
      return { ok: false, error: "Blob/data URLs cannot be imported. Play the video on the page, then right-click the video." };
    }
    return { ok: false, error: "Only http(s) URLs are supported." };
  }
  if (isEromeMediaUrl(cleanUrl) && tabId != null) {
    cleanUrl = await eromeResolveUrlFromActiveTab(tabId, cleanUrl);
  }
  let referer = String(refererPageUrl || "").trim().split("#")[0];
  if (isEromeMediaUrl(cleanUrl)) {
    const album = eromeAlbumPageFromMediaUrl(cleanUrl);
    if (album) referer = album;
    else if (referer && !isEromeAlbumPageUrl(referer)) {
      try {
        if (!isEromeHost(new URL(referer).hostname)) referer = "";
      } catch (_) {
        referer = "";
      }
    }
  }
  if (!referer && tabId != null) {
    try {
      const tab = await chrome.tabs.get(tabId);
      if (tab && tab.url && tbccIsInjectableHttpUrl(tab.url)) referer = tab.url.split("#")[0];
    } catch (_) {}
  }
  let poolId;
  if (poolIdOverride != null && Number.isFinite(Number(poolIdOverride)) && Number(poolIdOverride) > 0) {
    poolId = Number(poolIdOverride);
  } else {
    const { tbccPoolId } = await chrome.storage.local.get("tbccPoolId");
    poolId = tbccPoolId ?? 1;
  }
  const autoTagsCsv =
    autoTagPayload && autoTagPayload.tagsCsv ? String(autoTagPayload.tagsCsv).trim() : "";
  const autoCaption =
    autoTagPayload && autoTagPayload.caption ? String(autoTagPayload.caption).trim() : "";
  const body = { url: cleanUrl, pool_id: poolId };
  if (savedOnly) body.saved_only = true;
  if (savedOnly && autoCaption) body.caption = autoCaption;

  let data;

  if (savedOnly) {
    // Cherry-pick from websites: browser session (cookies/referer) first — backend URL fetch alone often
    // returns HTML/login pages that previously reported saved_only without visible media.
    if (tabId != null) {
      if (referer) {
        const tabBytes = await fetchMediaBytesFromTab(tabId, cleanUrl, referer);
        if (tabBytes instanceof ArrayBuffer && tabBytes.byteLength > 0) {
          data = await postBytesToTbcc(
            tabBytes,
            cleanUrl,
            poolId,
            true,
            (source || "extension:context-menu") + ":tab-fetch",
            autoCaption
          );
          if (data && !data.error && data.status === "saved_only") return { ok: true, data };
        }
      }
      data = await importViaExtensionBytes(
        cleanUrl,
        poolId,
        true,
        source || "extension:context-menu",
        autoCaption,
        referer,
        tabId
      );
      if (data && !data.error && data.status === "saved_only") return { ok: true, data };
    }

    const backendTry = await tryBackendSavedImport(body);
    if (backendTry.ok) return { ok: true, data: backendTry.data };
  } else if (hostNeedsSessionFetch(cleanUrl)) {
    data = await importViaExtensionBytes(
      cleanUrl,
      poolId,
      false,
      source || "extension:context-menu",
      autoCaption,
      referer,
      tabId
    );
  } else {
    const resp = await tbccFetchApi("/import/url", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const text = await resp.text();
    try {
      data = text ? JSON.parse(text) : {};
    } catch (_) {
      return { ok: false, error: resp.ok ? "Invalid server response." : `Server error ${resp.status}` };
    }
    if (data.error && shouldFallbackToSessionFetch(data.error)) {
      try {
        data = await importViaExtensionBytes(
          cleanUrl,
          poolId,
          false,
          (source || "extension:context-menu") + "-fallback",
          autoCaption,
          referer,
          tabId
        );
      } catch (_) {
        return { ok: false, error: String(data.error || "Import blocked (403)") };
      }
    }
  }
  if (data && data.error) return { ok: false, error: String(data.error), data };
  if (savedOnly && (!data || data.status !== "saved_only")) {
    return { ok: false, error: (data && data.reason) || "Did not save to Saved Messages", data };
  }
  if (!savedOnly && data && data.media_id && autoTagsCsv) {
    try {
      await tbccApplyTagsToImportedMediaIds([data.media_id], autoTagsCsv);
    } catch (e) {
      return { ok: false, error: "Auto-tag failed: " + String(e && e.message ? e.message : e), data };
    }
  }
  if (!savedOnly && data && data.media_id) {
    try {
      chrome.storage.local.get(STORAGE_COLLECTED, (o) => {
        const arr = Array.isArray(o[STORAGE_COLLECTED]) ? o[STORAGE_COLLECTED] : [];
        arr.push({ url: cleanUrl, type: "image", addedAt: Date.now(), source: source || "context_menu", media_id: data.media_id });
        chrome.storage.local.set({ [STORAGE_COLLECTED]: arr.slice(-500) });
      });
    } catch (_) {}
  }
  return { ok: true, data };
}

async function tbccSetGalleryDockedTab(tab, opts) {
  const openPanel = !!(opts && opts.openPanel);
  if (!tab || tab.id == null || !tbccIsInjectableHttpUrl(tab.url)) {
    return { ok: false, error: "Need an http(s) tab to dock." };
  }
  let hostname = "";
  try {
    hostname = new URL(tab.url).hostname.replace(/^www\./, "");
  } catch (_) {}
  const payload = {
    tabId: tab.id,
    url: tab.url || "",
    hostname,
    title: (tab.title || hostname || "Tab").slice(0, 120),
    dockedAt: Date.now(),
  };
  if (openPanel) {
    tbccTryOpenGallerySidePanelSync(tab);
  }
  await chrome.storage.local.set({ [STORAGE_GALLERY_DOCKED_TAB]: payload });
  return { ok: true, dock: payload };
}

const TBCC_CAPTURE_SECRET_BASES = ["http://127.0.0.1:8000", "http://localhost:8000"];

async function tbccFetchCaptureSecret(path, options) {
  let lastErr = null;
  for (const base of TBCC_CAPTURE_SECRET_BASES) {
    try {
      const r = await fetch(base + path, options);
      return r;
    } catch (e) {
      lastErr = e;
    }
  }
  throw lastErr || new Error("capture-secret unreachable");
}

async function tbccOpenCaptureSecretPrompt(value, pageUrl) {
  const q = new URLSearchParams({
    value: String(value || ""),
    page_url: String(pageUrl || ""),
  });
  await chrome.windows.create({
    url: chrome.runtime.getURL(`capture-secret-prompt.html?${q.toString()}`),
    type: "popup",
    width: 420,
    height: 320,
    focused: true,
  });
}

async function tbccCaptureSecretFromSelection(info, tab) {
  const value = String((info && info.selectionText) || "").trim();
  if (!value) {
    notifyThrottled("cap-secret-empty", "TBCC", "Highlight the API key text first, then right-click.", 6000);
    return;
  }
  const pageUrl = (tab && tab.url) || "";
  try {
    const r = await tbccFetchCaptureSecret("/extension/capture-secret", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ value, page_url: pageUrl }),
    });
    const data = await r.json().catch(() => ({}));
    if (r.ok && data && data.ok) {
      notifyThrottled(
        "cap-secret-ok",
        "TBCC",
        `Saved ${data.key} to .env` + (data.backed_up_credential_manager ? " (+ Credential Manager)" : ""),
        6000
      );
      return;
    }
    if (r.status === 422 || (data && data.detail && data.detail.error === "key_required") || !data || !data.key) {
      await tbccOpenCaptureSecretPrompt(value, pageUrl);
      return;
    }
    const detail =
      (data && data.detail && (data.detail.message || data.detail.error || data.detail)) ||
      data.detail ||
      r.statusText ||
      "capture failed";
    notifyThrottled("cap-secret-fail", "TBCC", String(detail), 8000);
  } catch (e) {
    try {
      await tbccOpenCaptureSecretPrompt(value, pageUrl);
      notifyThrottled(
        "cap-secret-offline",
        "TBCC",
        "API unreachable — picker opened; start TBCC API if save fails.",
        8000
      );
    } catch (_) {
      notifyThrottled(
        "cap-secret-offline",
        "TBCC",
        "Backend offline — start TBCC API, or use Windows desktop menu.",
        8000
      );
    }
  }
}

chrome.contextMenus.onClicked.addListener((info, tab) => {
  const id = String(info.menuItemId || "");

  if (id === "tbccActionOpenGallery") {
    tbccHandleActionOpenGalleryClick(tab);
    return;
  }

  void tbccContextMenuClickedAsync(info, tab);
});

async function tbccContextMenuClickedAsync(info, tab) {
  const id = String(info.menuItemId || "");

  if (id === "tbccCaptureSecretSelection") {
    void tbccCaptureSecretFromSelection(info, tab);
    return;
  }

  if (id.startsWith("tbccExtMod__") && typeof TBCC_EXT_MODULES !== "undefined") {
    try {
      const r = await TBCC_EXT_MODULES.handleActionClick(info);
      if (r && r.ok) {
        if (r.action === "restart") {
          notifyThrottled(
            "ext-mod-restart",
            "TBCC",
            `${r.title}: restarted${r.count != null ? ` (${r.count} tab(s))` : ""}.`,
            5000
          );
        } else if (r.action === "toggle") {
          notifyThrottled(
            "ext-mod-toggle",
            "TBCC",
            `${r.title}: ${r.enabled ? "enabled" : "disabled"}.`,
            5000
          );
        }
      }
    } catch (e) {
      notifyThrottled("ext-mod-fail", "TBCC", String((e && e.message) || e), 6000);
    }
    return;
  }

  if (id === "tbccActionStartApi") {
    void (async () => {
      try {
        if (typeof tbccLaunchFullStack === "function") {
          await tbccLaunchFullStack();
        } else {
          notify("TBCC", "Launch helper missing — reload the extension.");
        }
      } catch (e) {
        notifyThrottled("api-start-fail", "TBCC", String((e && e.message) || e), 8000);
      }
    })();
    return;
  }

  if (id === "tbccActionDockGallery" || id === "tbccDockGallery") {
    let dockTab = tab;
    let openedPanelSync = false;
    if (dockTab && dockTab.id != null && tbccIsInjectableHttpUrl(dockTab.url)) {
      tbccTryOpenGallerySidePanelSync(dockTab);
      openedPanelSync = true;
    }
    if ((!dockTab || dockTab.id == null) && id === "tbccActionDockGallery") {
      const [active] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
      dockTab = active;
      if (!openedPanelSync && dockTab && dockTab.id != null && tbccIsInjectableHttpUrl(dockTab.url)) {
        tbccTryOpenGallerySidePanelSync(dockTab);
      }
    }
    if (!dockTab || dockTab.id == null) {
      notifyThrottled("dock-fail", "TBCC", "No tab to dock — focus an http(s) page first.", 8000);
      return;
    }
    if (!tbccIsInjectableHttpUrl(dockTab.url)) {
      notifyThrottled(
        "dock-fail",
        "TBCC",
        "Dock needs a normal http(s) page tab (not chrome:// or the extension).",
        8000
      );
      return;
    }
    try {
      const r = await tbccSetGalleryDockedTab(dockTab, { openPanel: false });
      if (!r.ok) {
        notifyThrottled("dock-fail", "TBCC", r.error || "Could not dock.", 8000);
        return;
      }
    } catch (e) {
      notifyThrottled("dock-fail", "TBCC", String(e && e.message ? e.message : e), 8000);
    }
    return;
  }

  if (await tbccExtensionPageMenuBlocked(id)) {
    notifyThrottled(
      "ext-mod-block",
      "TBCC",
      "That TBCC action is disabled — right-click extension icon → Site tools.",
      6000
    );
    return;
  }

  if (id === "tbccAddVideoUrlToList" || id === "tbccAddVideoUrlToListNested") {
    const url = resolveUrlForSavedVideoList(info, tab);
    if (!url) {
      notify(
        "TBCC",
        "No URL to save. Right-click a link, the page, a video, or select an https URL in text first."
      );
      return;
    }
    try {
      const r = await tbccAppendSavedVideoUrl(url, (tab && tab.url) || "");
      if (!r.ok) {
        notify("TBCC", r.error || "Could not save.");
        return;
      }
      if (r.archived) {
        notify("TBCC", "Saved to master archive — click to open.", { type: "gallery_master_archive" });
      } else if (r.duplicate) {
        notify("TBCC", "Already in URL inbox — click to open.", { type: "gallery_inbox", url });
      } else {
        notify("TBCC", "Added to URL inbox — click to open Inbox.", { type: "gallery_inbox", url });
      }
    } catch (e) {
      notify("TBCC", String(e && e.message ? e.message : e));
    }
    return;
  }

  if (id === "tbccAddAllVideoUrlsToList" || id === "tbccAddAllVideoUrlsToListNested") {
    if (!tab || tab.id == null) {
      notify("TBCC", "No active tab to scan.");
      return;
    }
    if (!tbccIsInjectableHttpUrl(tab.url)) {
      notify("TBCC", "Open an http(s) page first (not chrome:// or the extension).");
      return;
    }
    try {
      notify("TBCC", "Scanning page for video URLs…");
      const urls = await tbccCollectVideoUrlsFromTab(tab.id);
      const r = await tbccAppendSavedVideoUrlsBulk(urls, tab.url || "");
      if (!r.ok) {
        notify("TBCC", r.error || "No video URLs found.");
        return;
      }
      const parts = [];
      if (r.added) parts.push(`${r.added} added`);
      if (r.duplicate) parts.push(`${r.duplicate} already in inbox`);
      notify(
        "TBCC",
        parts.length
          ? parts.join(", ") + " — click to open Inbox"
          : `Found ${r.total || 0} URL(s); all were already in the inbox.`,
        r.added ? { type: "gallery_inbox" } : null
      );
    } catch (e) {
      notify("TBCC", String(e && e.message ? e.message : e));
    }
    return;
  }

  if (id === "tbccms_clip_onlyfans" || id === "tbccms_clip_livecams" || id === "tbccms_clip_videos") {
    const data = await chrome.storage.local.get(STORAGE_LAST_COPIED_USERNAME);
    const username = usernameFromText(data && data[STORAGE_LAST_COPIED_USERNAME] ? data[STORAGE_LAST_COPIED_USERNAME] : "");
    if (!username) {
      notify("TBCC", "No copied username found yet. Copy a username first (Ctrl+C).");
      return;
    }
    const category =
      id === "tbccms_clip_livecams"
        ? MODEL_SEARCH_CATEGORY_LIVECAMS
        : id === "tbccms_clip_videos"
          ? MODEL_SEARCH_CATEGORY_VIDEOS
          : MODEL_SEARCH_CATEGORY_ONLYFANS;
    await launchModelSearch(username, null, category);
    return;
  }

  if (id === "tbccms_macro") {
    const username = await resolveModelSearchUsernameFromContext(info, tab);
    if (!username) {
      notify("TBCC", "Could not detect a username. Try right-clicking directly on @username.");
      return;
    }
    await launchMacroModelSearch(username);
    return;
  }

  if (id === "tbccms_approve_overlay_host") {
    try {
      if (!tab || !tab.url || !tbccIsInjectableHttpUrl(tab.url)) {
        notify("TBCC", "Open a normal http(s) page first.");
        return;
      }
      const host = tbccNormalizeUshHost(new URL(tab.url).hostname);
      await tbccApproveUsernameSearchHost(host);
      await tbccInjectUsernameSearchOverlay(tab.id);
      notify("TBCC", `Macrosearch overlay enabled on ${host}`);
    } catch (e) {
      notify("TBCC", String((e && e.message) || e));
    }
    return;
  }

  if (id === "tbccms_all_onlyfans" || id === "tbccms_all_livecams" || id === "tbccms_all_videos") {
    const username = await resolveModelSearchUsernameFromContext(info, tab);
    if (!username) {
      notify("TBCC", "Could not detect a username. Try right-clicking directly on @username.");
      return;
    }
    const category =
      id === "tbccms_all_livecams"
        ? MODEL_SEARCH_CATEGORY_LIVECAMS
        : id === "tbccms_all_videos"
          ? MODEL_SEARCH_CATEGORY_VIDEOS
          : MODEL_SEARCH_CATEGORY_ONLYFANS;
    await launchModelSearch(username, null, category);
    return;
  }
  if (id === "tbccms_bot_videofind") {
    const username = await resolveModelSearchUsernameFromContext(info, tab);
    if (!username) {
      notify("TBCC", "Could not detect a username. Try right-clicking directly on @username.");
      return;
    }
    const data = await chrome.storage.local.get([
      STORAGE_MACRO_SEARCH_BOT_USERNAME,
      STORAGE_PAYMENT_BOT_USERNAME,
    ]);
    const bot = String(
      (data && data[STORAGE_MACRO_SEARCH_BOT_USERNAME]) ||
        (data && data[STORAGE_PAYMENT_BOT_USERNAME]) ||
        ""
    )
      .trim()
      .replace(/^@+/, "");
    if (!bot) {
      notify("TBCC", "Set Macro search bot username in Extension options (Model search).");
      return;
    }
    const deep = `https://t.me/${encodeURIComponent(bot)}?start=ms_${encodeURIComponent(username)}`;
    await chrome.tabs.create({ url: deep, active: true });
    notify("TBCC", `Opened Telegram deep link for /macrosearch ${username}`);
    return;
  }
  if (String(id).startsWith("tbccmsi_")) {
    const username = await resolveModelSearchUsernameFromContext(info, tab);
    if (!username) {
      notify("TBCC", "Could not detect a username. Try right-clicking directly on @username.");
      return;
    }
    const sid = tbccSiteIdFromMenuId(id);
    if (sid) await launchModelSearch(username, sid);
    return;
  }

  if (id === "tbccReverseImageFanout") {
    const imageUrl = (info.srcUrl || "").trim();
    await launchReverseImageSearch(imageUrl);
    return;
  }

  if (id === "tbccCaptureTabReverse") {
    let dataUrl;
    try {
      dataUrl = await chrome.tabs.captureVisibleTab(null, { format: "png" });
    } catch (e) {
      notify("TBCC", "Could not capture: " + String(e.message || e));
      return;
    }
    const key =
      "tbcc_ss_" + Date.now().toString(36) + "_" + Math.random().toString(36).slice(2, 10);
    try {
      await chrome.storage.local.set({ [key]: dataUrl });
    } catch (e) {
      notify("TBCC", "Could not store screenshot (too large?). " + String(e.message || e));
      return;
    }
    const pageUrl = chrome.runtime.getURL(`screenshot-reverse.html?k=${encodeURIComponent(key)}`);
    await chrome.tabs.create({ url: pageUrl, active: true });
    notify("TBCC", "Screenshot ready — click Copy image, then paste in each tab.");
    return;
  }

  if (id === "tbccMotherlessGalleryZip" || id === "tbccMotherlessGalleryDownload") {
    let targetTab = tab;
    if ((!targetTab || targetTab.id == null) && info && info.linkUrl) {
      // opened from a link — use active tab on motherless if possible
      const [active] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
      targetTab = active;
    }
    // Prefer navigating to linkUrl gallery when context is a gallery link
    if (info && info.linkUrl && tbccIsMotherlessGalleryPageUrl(info.linkUrl)) {
      try {
        if (targetTab && targetTab.id != null) {
          await chrome.tabs.update(targetTab.id, { url: info.linkUrl });
          await new Promise((r) => setTimeout(r, 1800));
          targetTab = await chrome.tabs.get(targetTab.id);
        }
      } catch (_) {}
    }
    try {
      const mode = id === "tbccMotherlessGalleryZip" ? "zip" : "download";
      await tbccMotherlessGalleryBulkFromTab(targetTab, mode);
    } catch (e) {
      notify("TBCC Motherless", String((e && e.message) || e));
    }
    return;
  }

  if (id === "saveAofWatch") {
    const url = resolveUrlFromContextClick(info, tab);
    if (!url) {
      notify("TBCC", "No media URL — right-click the image or video directly.");
      return;
    }
    try {
      const result = await tbccSaveAofMediaToWatch({
        url,
        refererPageUrl: (tab && tab.url) || "",
        tabId: tab && tab.id != null ? tab.id : null,
        preferFull: true,
      });
      const tagN = (result.tags && result.tags.length) || 0;
      notify(
        "TBCC Save AOF",
        `${result.filename} · ${tagN} tag(s)` +
          (result.watermarkApplied
            ? ` · watermarked${result.watermarkVia ? " (" + result.watermarkVia + ")" : ""}`
            : result.deferred
              ? " · deferred (backend/watch for video)"
              : " · pending watermark")
      );
    } catch (e) {
      notify("TBCC Save AOF failed", String((e && e.message) || e));
    }
    return;
  }

  if (id === "uploadR2Library" || id === "uploadR2SfwXPromo") {
    const url = resolveUrlFromContextClick(info, tab);
    if (!url) {
      notify("TBCC", "No media URL — right-click the image or video directly.");
      return;
    }
    const destination = id === "uploadR2SfwXPromo" ? "sfw_x_promo" : "library";
    const label = destination === "sfw_x_promo" ? "R2 SFW X promo" : "R2 library";
    try {
      notify(`TBCC ${label}`, "Uploading…");
      const result = await tbccWatermarkUploadToR2({
        url,
        destination,
        refererPageUrl: (tab && tab.url) || "",
        tabId: tab && tab.id != null ? tab.id : null,
        preferFull: true,
      });
      notify(
        `TBCC ${label}`,
        `${result.directUrl}` +
          (result.watermarked ? " · watermarked" : "") +
          (result.clipped ? " · copied" : ""),
        result.directUrl ? { type: "url", url: result.directUrl } : null
      );
    } catch (e) {
      notify(`TBCC ${label} failed`, String((e && e.message) || e));
    }
    return;
  }

  if (id === "tbccAofPool_empty") {
    notify("TBCC", "AOF pools not loaded — is the backend running on :8000? Reload the extension.");
    return;
  }

  if (id === "tbccStorageHub_empty") {
    notify("TBCC", "Storage Hub topics missing — reload the extension.");
    return;
  }

  if (String(id).startsWith("tbccStorageHub_")) {
    const tid = parseInt(String(id).slice("tbccStorageHub_".length), 10);
    const url = resolveUrlFromContextClick(info, tab);
    if (!url) {
      notify("TBCC", "No media URL — right-click the image or video directly.");
      return;
    }
    if (!Number.isFinite(tid) || tid < 1) {
      notify("TBCC", "Unknown Storage Hub topic — reload the extension.");
      return;
    }
    const topics = await tbccGetStorageHubTopics();
    const row = topics.find((t) => parseInt(t.message_thread_id, 10) === tid);
    const label = (row && (row.short_label || row.menu_label)) || `topic ${tid}`;
    try {
      await tbccSendUrlToStorageHubTopic({
        url,
        messageThreadId: tid,
        networkKey: (row && row.network_key) || "",
        refererPageUrl: (tab && tab.url) || "",
        tabId: tab && tab.id != null ? tab.id : null,
      });
      notify("TBCC Storage Hub", `Sent → ${label}`);
    } catch (e) {
      notify("TBCC Storage Hub failed", String((e && e.message) || e));
    }
    return;
  }

  if (String(id).startsWith("tbccAofPool_")) {
    const poolId = parseInt(String(id).slice("tbccAofPool_".length), 10);
    const url = resolveUrlFromContextClick(info, tab);
    if (!url) {
      notify("TBCC", "No media URL — right-click the image or video directly.");
      return;
    }
    if (!Number.isFinite(poolId) || poolId < 1) {
      notify("TBCC", "Unknown AOF pool — reload the extension.");
      return;
    }
    const poolLabel = await tbccAofPoolLabel(poolId);
    try {
      const { [STORAGE_AUTO_TAG_ON_EXPORT]: autoTagOnExport } = await chrome.storage.local.get(
        STORAGE_AUTO_TAG_ON_EXPORT
      );
      const autoTagPayload =
        autoTagOnExport === false
          ? null
          : await tbccBuildAutoTagPayloadAsync(url, (tab && tab.url) || "", tab && tab.id != null ? tab.id : null);
      const result = await importUrlViaTbcc(
        url,
        false,
        "extension:aof-pool",
        (tab && tab.url) || "",
        autoTagPayload,
        tab && tab.id != null ? tab.id : null,
        poolId
      );
      if (!result.ok) {
        notify("TBCC Import Failed", tbccFormatImportError(result.error || "Import failed"));
        return;
      }
      const data = result.data || {};
      await chrome.storage.local.set({ tbccPoolId: poolId });
      if (data.media_id) {
        notify(
          "TBCC",
          `#${data.media_id} → ${poolLabel} (pending). Curate: Dashboard → Curate → ${poolLabel}.`
        );
      } else if (data.status === "skipped") {
        notify("TBCC", `${poolLabel}: ${data.reason || "Skipped (duplicate or unsupported)"}`);
      } else {
        notify("TBCC", `Added to ${poolLabel} (or duplicate).`);
      }
    } catch (e) {
      notify("TBCC Import Failed", tbccFormatImportError(e && e.message ? e.message : String(e)));
    }
    return;
  }

  const savedOnly = isSavedMenuId(id);
  const url = resolveUrlFromContextClick(info, tab);

  if (!url) {
    notify(
      "TBCC",
      id.includes("Selection")
        ? "Select an https URL in the page, then right-click the selection."
        : "No URL for this action."
    );
    return;
  }
  try {
    const { [STORAGE_AUTO_TAG_ON_EXPORT]: autoTagOnExport } = await chrome.storage.local.get(STORAGE_AUTO_TAG_ON_EXPORT);
    const autoTagPayload =
      autoTagOnExport === false
        ? null
        : await tbccBuildAutoTagPayloadAsync(url, (tab && tab.url) || "", tab && tab.id != null ? tab.id : null);
    const result = await importUrlViaTbcc(
      url,
      savedOnly,
      "extension:context-menu",
      (tab && tab.url) || "",
      autoTagPayload,
      tab && tab.id != null ? tab.id : null
    );
    if (!result.ok) {
      notify(
        "TBCC Import Failed",
        tbccFormatImportError(result.error || "Import failed")
      );
      return;
    }
    const data = result.data || {};
    if (savedOnly) {
      notify("TBCC", await tbccSavedImportNotifyMessage(data), { type: "telegram_saved" });
    } else if (data.media_id) {
      notify("TBCC", `Imported as media #${data.media_id}`);
    } else if (data.status === "skipped") {
      notify("TBCC", data.reason || "Skipped (duplicate or unsupported)");
    } else {
      notify("TBCC", "Added (or duplicate).");
    }
  } catch (e) {
    const msg = e && e.message ? e.message : "Unknown error";
    notify(
      "TBCC Import Failed",
      tbccFormatImportError(msg)
    );
  }
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.action === "tbcc-intel-export-jsonl") {
    (async () => {
      try {
        const text = String(msg.text || "");
        const filename = String(msg.filename || "browse-intel.jsonl")
          .replace(/[<>:"/\\|?*\x00-\x1f]/g, "_")
          .slice(0, 180) || "browse-intel.jsonl";
        // MV3 SW: no createObjectURL — data URL (UTF-8 via base64)
        const bytes = new TextEncoder().encode(text);
        let binary = "";
        const chunk = 0x8000;
        for (let i = 0; i < bytes.length; i += chunk) {
          binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk));
        }
        const dataUrl = `data:application/x-ndjson;base64,${btoa(binary)}`;
        const id = await tbccChromeDownloadsDownload({
          url: dataUrl,
          filename,
          saveAs: true,
          conflictAction: "uniquify",
        });
        sendResponse({ ok: true, downloadId: id, filename });
      } catch (e) {
        sendResponse({ ok: false, error: e && e.message ? e.message : String(e) });
      }
    })();
    return true;
  }
  if (msg.action === "tbcc-browse-intel-push") {
    (async () => {
      try {
        const result = await tbccPushBrowseIntelRows(msg.rows || [], msg.url || "");
        sendResponse(result);
      } catch (e) {
        sendResponse({ ok: false, error: e && e.message ? e.message : String(e) });
      }
    })();
    return true;
  }
  if (msg.action === "tbcc-browse-intel-summary") {
    (async () => {
      try {
        const result = await tbccFetchBrowseIntelSummary(msg.url || "", msg.days);
        sendResponse(result);
      } catch (e) {
        sendResponse({ ok: false, error: e && e.message ? e.message : String(e) });
      }
    })();
    return true;
  }
  if (msg.action === "tbcc-watermark-upload-r2") {
    (async () => {
      try {
        const url = String(msg.url || "").trim();
        if (!url || !/^https?:\/\//i.test(url)) {
          sendResponse({ ok: false, error: "Only http(s) media URLs supported." });
          return;
        }
        const destination = String(msg.destination || "library").trim() || "library";
        const tabId =
          msg.tabId != null
            ? msg.tabId
            : _sender && _sender.tab && _sender.tab.id != null
              ? _sender.tab.id
              : null;
        const result = await tbccWatermarkUploadToR2({
          url,
          destination,
          refererPageUrl: String(msg.refererPageUrl || (_sender && _sender.tab && _sender.tab.url) || "").trim(),
          tabId,
          preferFull: msg.preferFull !== false,
        });
        sendResponse({ ok: true, ...result });
      } catch (e) {
        sendResponse({ ok: false, error: e && e.message ? e.message : String(e) });
      }
    })();
    return true;
  }
  if (msg.action === "tbcc-zip-flywheel") {
    (async () => {
      try {
        let blob = msg.blob || null;
        if (!blob && msg.arrayBuffer) {
          blob = new Blob([msg.arrayBuffer], { type: "application/zip" });
        }
        if (!blob && Array.isArray(msg.bytes)) {
          blob = new Blob([new Uint8Array(msg.bytes)], { type: "application/zip" });
        }
        const data = await tbccZipFlywheelUpload({
          blob,
          action: msg.flywheelAction || msg.actionDest || "host_gated",
          host: msg.host || "auto",
          preferR2: !!msg.preferR2,
          filename: msg.filename || "",
          name: msg.name || "",
          profileName: msg.profileName || "",
          sourceUrl: msg.sourceUrl || "",
          label: msg.label || "",
          planId: msg.planId || "",
          sourceNote: msg.sourceNote || "ext_gallery_zip",
        });
        sendResponse({ ok: true, ...data });
      } catch (e) {
        sendResponse({ ok: false, error: e && e.message ? e.message : String(e) });
      }
    })();
    return true;
  }
  if (msg.action === "tbcc-download-url-from-page-menu" || msg.action === "tbcc-save-aof-to-watch") {
    (async () => {
      try {
        let useAof;
        if (msg.saveAof === false) {
          useAof = false;
        } else if (msg.action === "tbcc-save-aof-to-watch" || msg.saveAof === true) {
          useAof = true;
        } else {
          try {
            const d = await chrome.storage.local.get(STORAGE_SAVE_AOF_ON_DOWNLOAD);
            useAof = d[STORAGE_SAVE_AOF_ON_DOWNLOAD] !== false;
          } catch (_) {
            useAof = true;
          }
        }
        if (useAof) {
          const tabId =
            _sender && _sender.tab && _sender.tab.id != null
              ? _sender.tab.id
              : msg.tabId != null
                ? msg.tabId
                : null;
          const result = await tbccSaveAofMediaToWatch({
            url: msg.url,
            refererPageUrl: msg.refererPageUrl || (_sender && _sender.tab && _sender.tab.url) || "",
            tabId,
            preferFull: msg.preferFull !== false,
          });
          notify(
            "TBCC Save AOF",
            `${result.filename}` +
              (result.watermarkApplied
                ? ` · watermarked${result.watermarkVia ? " (" + result.watermarkVia + ")" : ""}`
                : result.deferred
                  ? " · deferred (start backend / watch for video burn-in)"
                  : " · pending watermark")
          );
          sendResponse({ ok: true, ...result });
          return;
        }
        const raw = String(msg.url || "").trim();
        if (!raw || !/^https?:\/\//i.test(raw)) {
          sendResponse({ ok: false, error: "Only http(s) URLs can be downloaded." });
          return;
        }
        const finalUrl = normalizeTbccMediaUrlForImport(raw);
        const preferFull = msg.preferFull !== false;
        const refererPageUrl = String(msg.refererPageUrl || "").trim();
        let downloadUrl = finalUrl;
        try {
          const u = new URL(finalUrl);
          const isRedgifs = /(^|\.)redgifs\.com$/i.test(u.hostname || "");
          const hasRedItem =
            /^\/(?:watch|ifr|gifs)\/[^/?#]+/i.test(u.pathname || "") || !!redgifsIdFromAnyUrl(finalUrl);
          if (preferFull && isRedgifs) {
            const candidate = hasRedItem ? finalUrl : refererPageUrl;
            const resolved = candidate ? await fetchRedgifsMediaViaApi(candidate) : "";
            if (resolved && /^https?:\/\//i.test(resolved)) downloadUrl = normalizeTbccMediaUrlForImport(resolved);
          }
        } catch (_) {}
        const path = (() => {
          try {
            const u = new URL(downloadUrl);
            const base = (u.pathname.split("/").pop() || "media").replace(/[^\w.\-]+/g, "_");
            const dot = base.lastIndexOf(".");
            return dot > 0 ? base.slice(dot + 1).toLowerCase().replace(/[^\w]/g, "").slice(0, 5) : "jpg";
          } catch (_) {
            return "jpg";
          }
        })();
        const leaf = await tbccBuildAofDownloadName(downloadUrl, refererPageUrl, path, { index: 1 });
        const naming = typeof TbccZipNaming !== "undefined" ? TbccZipNaming : null;
        const filename =
          naming && naming.tbccDownloadFolderPath ? naming.tbccDownloadFolderPath(leaf) : "tbcc/" + leaf;
        chrome.downloads.download(
          {
            url: downloadUrl,
            filename,
            saveAs: false,
            conflictAction: "uniquify",
          },
          (id) => {
            const err = chrome.runtime.lastError;
            if (err || !id) {
              sendResponse({ ok: false, error: err ? err.message : "Download failed." });
              return;
            }
            notify("TBCC", "Download started — click to open gallery.", { type: "gallery_sidepanel" });
            sendResponse({ ok: true, downloadId: id });
          }
        );
      } catch (e) {
        sendResponse({ ok: false, error: String(e && e.message ? e.message : e) });
      }
    })();
    return true;
  }

  if (msg.action === "tbcc-import-url-from-page-menu") {
    (async () => {
      try {
        const { [STORAGE_AUTO_TAG_ON_EXPORT]: autoTagOnExport } = await chrome.storage.local.get(
          STORAGE_AUTO_TAG_ON_EXPORT
        );
        const autoTagPayload =
          autoTagOnExport === false
            ? null
            : await tbccBuildAutoTagPayloadAsync(
                msg.url,
                msg.refererPageUrl || "",
                _sender && _sender.tab && _sender.tab.id != null ? _sender.tab.id : null
              );
        const result = await importUrlViaTbcc(
          msg.url,
          !!msg.savedOnly,
          "extension:page-media-menu",
          msg.refererPageUrl || "",
          autoTagPayload,
          _sender && _sender.tab && _sender.tab.id != null ? _sender.tab.id : null
        );
        if (!result.ok) {
          sendResponse({ ok: false, error: result.error || "Import failed" });
          return;
        }
        const data = result.data || {};
        if (msg.savedOnly) notify("TBCC", await tbccSavedImportNotifyMessage(data), { type: "telegram_saved" });
        else if (data.media_id) notify("TBCC", `Imported as media #${data.media_id}`, { type: "gallery_dest" });
        else if (data.status === "skipped") notify("TBCC", data.reason || "Skipped (duplicate or unsupported)");
        else notify("TBCC", "Added (or duplicate).");
        sendResponse({ ok: true, data });
      } catch (e) {
        sendResponse({ ok: false, error: String(e && e.message ? e.message : e) });
      }
    })();
    return true;
  }
  return false;
});
