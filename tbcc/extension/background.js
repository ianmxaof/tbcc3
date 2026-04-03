importScripts("model-search-shared.js");

const API_URL = "http://localhost:8000/import/url";
const API_BYTES = "http://localhost:8000/import/bytes";
const API_SAVED_BATCH = "http://localhost:8000/import/saved-batch";
const SAVED_ALBUM_CHUNK = 10;
const STORAGE_LAST_TAB = "tbccLastActiveTabId";
const STORAGE_COLLECTED = "tbcc_collected";
const STORAGE_MODEL_SEARCH_ENABLED = "tbccModelSearchEnabledSites";
const STORAGE_MODEL_SEARCH_MODE = "tbccModelSearchOpenMode";
const STORAGE_REVERSE_IMAGE_ENABLED = "tbccReverseImageEnabledSites";
const STORAGE_REVERSE_IMAGE_MODE = "tbccReverseImageOpenMode";
const STORAGE_MODEL_SEARCH_LAST_SUMMARY = "tbccModelSearchLastSummary";

/**
 * Fan out username search across enabled sites (config JSON + options).
 * Modes: dashboard (single aggregator tab), foreground (first tab active), background (all inactive).
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
 * Uses session storage to pass long URLs into reverse-aggregator.html.
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
  const mode = data[STORAGE_REVERSE_IMAGE_MODE] || "dashboard";
  if (mode === "dashboard") {
    const key =
      "tbcc_ri_" + Date.now().toString(36) + "_" + Math.random().toString(36).slice(2, 10);
    await chrome.storage.session.set({ [key]: imageUrl });
    const pageUrl = chrome.runtime.getURL(`reverse-aggregator.html?k=${encodeURIComponent(key)}`);
    await chrome.tabs.create({ url: pageUrl, active: true });
    return;
  }
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

function guessResultCountFromHtml(html) {
  if (!html || typeof html !== "string") return null;
  const m = html.match(/(\d[\d,]*)\s*(results?|entries|posts?|items?|found|hits?)\b/i);
  if (m) return parseInt(m[1].replace(/,/g, ""), 10) || null;
  const m2 = html.match(/(?:total|about|count|results?)\s*[:\s]*\s*(\d[\d,]*)/i);
  if (m2) return parseInt(m2[1].replace(/,/g, ""), 10) || null;
  return null;
}

async function fetchCountsForSites(username, sites) {
  for (const site of sites) {
    const url = buildModelSearchUrl(site.url, username);
    let countHint = null;
    let fetchStatus = "ok";
    try {
      const r = await fetch(url, { credentials: "omit" });
      const text = await r.text();
      countHint = guessResultCountFromHtml(text);
      if (!r.ok) fetchStatus = "http_" + r.status;
    } catch (_) {
      fetchStatus = "err";
    }
    const data = await chrome.storage.local.get(STORAGE_MODEL_SEARCH_LAST_SUMMARY);
    const sum = data[STORAGE_MODEL_SEARCH_LAST_SUMMARY];
    if (!sum || !Array.isArray(sum.rows)) continue;
    const row = sum.rows.find((x) => x.siteId === site.id);
    if (row) {
      row.countHint = countHint;
      row.fetchStatus = fetchStatus;
    }
    await chrome.storage.local.set({ [STORAGE_MODEL_SEARCH_LAST_SUMMARY]: sum });
  }
}

async function launchModelSearch(username, onlySiteId = null) {
  const usernameEnc = encodeURIComponent(username.trim());
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
  if (onlySiteId) {
    sites = sites.filter((s) => s.id === onlySiteId);
  }
  if (!sites.length) {
    notify("TBCC", "No model search sources enabled — open Extension options (Model search).");
    return;
  }
  const mode = data[STORAGE_MODEL_SEARCH_MODE] || "dashboard";
  if (mode === "dashboard") {
    let url = chrome.runtime.getURL(`aggregator.html?q=${usernameEnc}`);
    if (onlySiteId) url += "&site=" + encodeURIComponent(onlySiteId);
    await chrome.tabs.create({ url, active: true });
    await recordModelSearchSummary(username, sites, onlySiteId);
    void fetchCountsForSites(username, sites);
    return;
  }
  const wantActive = mode === "foreground";
  let first = true;
  for (const s of sites) {
    const u = buildModelSearchUrl(s.url, username);
    await chrome.tabs.create({ url: u, active: wantActive && first });
    first = false;
  }
  await recordModelSearchSummary(username, sites, onlySiteId);
  void fetchCountsForSites(username, sites);
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
      h.endsWith(".erome.com")
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

/** CDN path …/albumId/file.mp4 → album https://www.erome.com/a/albumId */
function eromeReferrerChain(url) {
  try {
    const u = new URL(url);
    const host = u.hostname.toLowerCase();
    if (host !== "erome.com" && !host.endsWith(".erome.com")) return null;
    const chain = [];
    const parts = u.pathname.split("/").filter(Boolean);
    if (parts.length >= 2) {
      const last = parts[parts.length - 1].toLowerCase();
      if (/\.(mp4|webm|mov|m4v|mkv|jpe?g|png|gif|webp)$/i.test(last)) {
        let album = parts[parts.length - 2];
        if (/^\d+$/.test(album) && parts.length >= 3) album = parts[parts.length - 3];
        if (album && !/^\d+$/.test(album)) chain.push(`https://www.erome.com/a/${album}`);
      }
    }
    chain.push("https://www.erome.com/");
    return [...new Set(chain)];
  } catch (_) {
    return ["https://www.erome.com/"];
  }
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

async function fetchUrlWithBrowserSession(url) {
  const eromeChain = eromeReferrerChain(url);
  let cookieHeader = "";
  if (eromeChain) {
    cookieHeader = await mergeCookiesForUrls(eromeChain);
  } else {
    try {
      cookieHeader = (await chrome.cookies.getAll({ url })).map((c) => `${c.name}=${c.value}`).join("; ");
    } catch (_) {}
  }
  const base = {};
  if (cookieHeader) base.Cookie = cookieHeader;

  if (eromeChain) {
    for (const ref of eromeChain) {
      let res = await fetch(url, { method: "GET", credentials: "omit", headers: { ...base, Referer: ref } });
      if (res.ok) return await res.arrayBuffer();
      res = await fetch(url, {
        method: "GET",
        credentials: "omit",
        headers: { ...base, Referer: ref, Origin: "https://www.erome.com" },
      });
      if (res.ok) return await res.arrayBuffer();
    }
    throw new Error(
      "Erome CDN 403 — open the album on www.erome.com in this browser (same profile), then use the menu on the video/link."
    );
  }

  try {
    const u = new URL(url);
    const h = u.hostname.toLowerCase();
    if (h.includes("onlyfans.com")) base.Referer = "https://onlyfans.com/";
    else if (h.includes("motherless") || h.endsWith("motherlessmedia.com"))
      base.Referer = "https://motherless.com/";
    else base.Referer = `${u.protocol}//${u.hostname}/`;
  } catch (_) {
    base.Referer = "https://www.erome.com/";
  }
  const res = await fetch(url, { method: "GET", credentials: "omit", headers: base });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return await res.arrayBuffer();
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

/** Extract main image URL from motherless ?full HTML (og:image + fallbacks). */
function parseMotherlessFullImageFromHtml(html) {
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
  const m2 = html.match(
    /<img[^>]+(?:class|id)=["'][^"']*(?:static|media|full|main)[^"']*["'][^>]*src=["']([^"']+\.(?:jpe?g|png|gif|webp)[^"']*)["']/i
  );
  if (m2 && m2[1]) {
    const u2 = decodeHtmlAttr(m2[1].trim());
    if (/motherless|motherlessmedia|cdn/i.test(u2)) return u2.startsWith("//") ? "https:" + u2 : u2;
  }
  return "";
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
  return parseMotherlessFullImageFromHtml(html);
}

async function fetchMotherlessHtml(detailUrl) {
  let u = detailUrl.trim();
  if (u.indexOf("?") < 0) u = `${u}?full`;
  else if (u.toLowerCase().indexOf("full") < 0) u = `${u}${u.includes("?") ? "&" : "?"}full`;
  const cookieHeader = await mergeCookiesForUrls([u, "https://motherless.com/", "https://www.motherless.com/"]);
  const headers = {
    Accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    Referer: "https://motherless.com/",
    "User-Agent":
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
  };
  if (cookieHeader) headers.Cookie = cookieHeader;
  const res = await fetch(u, { method: "GET", credentials: "omit", headers });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return await res.text();
}

function blobNameAndTypeForUrl(url) {
  try {
    const path = new URL(url).pathname.toLowerCase();
    if (path.endsWith(".mp4") || path.endsWith(".m4v")) return { name: "media.mp4", type: "video/mp4" };
    if (path.endsWith(".webm")) return { name: "media.webm", type: "video/webm" };
    if (path.endsWith(".mov")) return { name: "media.mov", type: "video/quicktime" };
    if (path.endsWith(".gif")) return { name: "media.gif", type: "image/gif" };
    if (path.endsWith(".png")) return { name: "media.png", type: "image/png" };
    if (path.endsWith(".webp")) return { name: "media.webp", type: "image/webp" };
    if (path.endsWith(".jpg") || path.endsWith(".jpeg")) return { name: "media.jpg", type: "image/jpeg" };
  } catch (_) {}
  return { name: "media.jpg", type: "application/octet-stream" };
}

async function importViaExtensionBytes(url, poolId, savedOnly, source, caption) {
  url = normalizeTbccMediaUrlForImport(url);
  const ab = await fetchUrlWithBrowserSession(url);
  const { name, type } = blobNameAndTypeForUrl(url);
  const form = new FormData();
  form.append("file", new Blob([ab], { type }), name);
  form.append("pool_id", String(poolId));
  form.append("saved_only", savedOnly ? "true" : "false");
  form.append("source", source || "extension:session-fetch");
  if (savedOnly && caption && String(caption).trim()) {
    form.append("caption", String(caption).trim());
  }
  const r = await fetch(API_BYTES, { method: "POST", body: form });
  const text = await r.text();
  let data = {};
  try {
    data = text ? JSON.parse(text) : {};
  } catch (_) {}
  if (!r.ok && !data.error) data.error = text ? text.slice(0, 200) : `HTTP ${r.status}`;
  return data;
}

/** Fetch multiple session URLs and POST to /import/saved-batch in chunks (Telegram albums ≤10). */
async function importViaExtensionBytesSavedBatch(urls) {
  const parts = [];
  for (const url of urls) {
    const ab = await fetchUrlWithBrowserSession(normalizeTbccMediaUrlForImport(url));
    const { name, type } = blobNameAndTypeForUrl(url);
    parts.push({ ab, name, type });
  }
  for (let i = 0; i < parts.length; i += SAVED_ALBUM_CHUNK) {
    const chunk = parts.slice(i, i + SAVED_ALBUM_CHUNK);
    const form = new FormData();
    chunk.forEach((p, j) => {
      form.append("files", new Blob([p.ab], { type: p.type }), p.name || `media_${j}`);
    });
    const r = await fetch(API_SAVED_BATCH, { method: "POST", body: form });
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

/** Track which browser tab the user was on (side panel focus can make active-tab queries wrong). */
chrome.tabs.onActivated.addListener(({ tabId }) => {
  chrome.storage.local.set({ [STORAGE_LAST_TAB]: tabId });
});
chrome.tabs.onUpdated.addListener((tabId, info, tab) => {
  if (info.status === "complete" && tab && tab.active && tab.id) {
    chrome.storage.local.set({ [STORAGE_LAST_TAB]: tab.id });
  }
});

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.action === "tbcc-import-bytes-session") {
    (async () => {
      try {
        const data = await importViaExtensionBytes(
          msg.url,
          msg.poolId ?? 1,
          !!msg.savedOnly,
          msg.source || "extension:gallery-session",
          msg.caption
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
        const data = await importViaExtensionBytesSavedBatch(urls, msg.caption);
        sendResponse(data);
      } catch (e) {
        sendResponse({ error: String(e.message || e) });
      }
    })();
    return true;
  }
  /** Content script in-tab upload path: same cookie/Referer logic as context menu, CSP-safe. */
  if (msg.action === "tbcc-content-fetch-bytes") {
    (async () => {
      try {
        const buffer = await fetchUrlWithBrowserSession(normalizeTbccMediaUrlForImport(msg.url));
        sendResponse({ ok: true, buffer });
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
  return false;
});

function installContextMenus() {
  /** Toolbar icon opens/closes the gallery side panel (no default_popup — popup would block this). */
  chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(() => {});
  chrome.contextMenus.removeAll(() => {
    const mac = chrome.contextMenus.create.bind(chrome.contextMenus);
    mac({ id: "sendToTBCC", title: "TBCC → Pool queue (media/link)", contexts: ["image", "video", "link"] });
    mac({
      id: "tbccReverseImageFanout",
      title: "Reverse image search (fan-out)",
      contexts: ["image"],
    });
    mac({
      id: "tbccCaptureTabReverse",
      title: "Capture tab → screenshot for reverse search",
      contexts: ["page", "frame"],
    });
    mac({ id: "sendToSaved", title: "TBCC → Saved Messages (media/link)", contexts: ["image", "video", "link"] });
    mac({ id: "sendPageToTBCC", title: "TBCC → Pool queue (this tab URL)", contexts: ["page", "frame"] });
    mac({ id: "sendPageToSaved", title: "TBCC → Saved Messages (this tab URL)", contexts: ["page", "frame"] });
    mac({ id: "sendSelectionToTBCC", title: "TBCC → Pool queue (selected URL text)", contexts: ["selection"] });
    mac({ id: "sendSelectionToSaved", title: "TBCC → Saved Messages (selected URL text)", contexts: ["selection"] });
    mac({ id: "tbccPageMenu", title: "TBCC", contexts: ["page", "frame"] });
    mac({
      id: "tbccToggleOverlay",
      parentId: "tbccPageMenu",
      title: "Toggle on-page checkboxes",
      contexts: ["page", "frame"],
    });
    mac({
      id: "tbccSelectAllPage",
      parentId: "tbccPageMenu",
      title: "Select all media on this page",
      contexts: ["page", "frame"],
    });
    /** Same actions when right-clicking an image/video/link — page/frame context is NOT used there. */
    mac({ id: "tbccMediaMenu", title: "TBCC (page tools)", contexts: ["image", "video", "link"] });
    mac({
      id: "tbccToggleOverlayMedia",
      parentId: "tbccMediaMenu",
      title: "Toggle on-page checkboxes",
      contexts: ["image", "video", "link"],
    });
    mac({
      id: "tbccSelectAllPageMedia",
      parentId: "tbccMediaMenu",
      title: "Select all media on this page",
      contexts: ["image", "video", "link"],
    });
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
  mac({
    id: "tbccModelSearchRoot",
    title: "TBCC — Look up username",
    contexts: ["selection"],
  });
  mac({
    id: "tbccms_all",
    parentId: "tbccModelSearchRoot",
    title: "Search all enabled sites",
    contexts: ["selection"],
  });
  mac({
    id: "tbccms_sep",
    parentId: "tbccModelSearchRoot",
    type: "separator",
    contexts: ["selection"],
  });
  for (const s of sites) {
    mac({
      id: tbccMenuIdForSite(s.id),
      parentId: "tbccModelSearchRoot",
      title: String(s.name || s.id).slice(0, 120),
      contexts: ["selection"],
    });
  }
}

chrome.runtime.onInstalled.addListener(() => {
  installContextMenus();
});

chrome.runtime.onStartup.addListener(() => {
  installContextMenus();
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

// 1x1 transparent PNG as data URL (avoids "Unable to download" with file icons in Brave)
const NOTIFY_ICON = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQHwAEBgIApD5fRAAAAABJRU5ErkJggg==";

function notify(title, message) {
  try {
    chrome.notifications.create("tbcc-" + Date.now(), {
      type: "basic",
      iconUrl: NOTIFY_ICON,
      title: title || "TBCC",
      message: message || "",
    });
  } catch (e) {
    console.log("TBCC:", title, message, e);
  }
}

function isSavedMenuId(id) {
  return id === "sendToSaved" || id === "sendPageToSaved" || id === "sendSelectionToSaved";
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

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  const id = String(info.menuItemId || "");

  if (id === "tbccms_all") {
    const raw = (info.selectionText || "").trim();
    if (!raw) {
      notify("TBCC", "Select a username first.");
      return;
    }
    if (raw.length > 200) {
      notify("TBCC", "Selection is too long for model search.");
      return;
    }
    if (/^https?:\/\//i.test(raw)) {
      notify("TBCC", "Model search expects a username, not a URL.");
      return;
    }
    await launchModelSearch(raw, null);
    return;
  }
  if (String(id).startsWith("tbccmsi_")) {
    const raw = (info.selectionText || "").trim();
    if (!raw) {
      notify("TBCC", "Select a username first.");
      return;
    }
    if (raw.length > 200) {
      notify("TBCC", "Selection is too long for model search.");
      return;
    }
    if (/^https?:\/\//i.test(raw)) {
      notify("TBCC", "Model search expects a username, not a URL.");
      return;
    }
    const sid = tbccSiteIdFromMenuId(id);
    if (sid) await launchModelSearch(raw, sid);
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

  if (id === "tbccToggleOverlay" || id === "tbccToggleOverlayMedia") {
    const { tbccOverlayMode } = await chrome.storage.local.get("tbccOverlayMode");
    await chrome.storage.local.set({ tbccOverlayMode: !tbccOverlayMode });
    notify("TBCC", !tbccOverlayMode ? "On-page checkboxes: ON" : "On-page checkboxes: OFF");
    return;
  }
  if (id === "tbccSelectAllPage" || id === "tbccSelectAllPageMedia") {
    if (!tab || tab.id == null) {
      notify("TBCC", "No active tab.");
      return;
    }
    try {
      await chrome.tabs.sendMessage(tab.id, { action: "tbcc-overlay-select-all" });
      notify("TBCC", "Selected all media on this page (merged into TBCC selection).");
    } catch (_) {
      notify("TBCC", "Could not reach this page — reload the tab or use the sidebar.");
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
  if (!/^https?:\/\//i.test(url)) {
    notify("TBCC", "Only http(s) URLs are supported.");
    return;
  }
  if (url.startsWith("blob:") || url.startsWith("data:")) {
    notify("TBCC", "Blob/data URLs cannot be imported. Use a direct link.");
    return;
  }

  const { tbccPoolId } = await chrome.storage.local.get("tbccPoolId");
  const poolId = tbccPoolId ?? 1;
  const body = { url, pool_id: poolId };
  if (savedOnly) body.saved_only = true;

  try {
    let data;
    if (hostNeedsSessionFetch(url)) {
      data = await importViaExtensionBytes(url, poolId, savedOnly, "extension:context-menu");
    } else {
      const resp = await fetch(API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const text = await resp.text();
      try {
        data = text ? JSON.parse(text) : {};
      } catch (_) {
        notify("TBCC Import Failed", resp.ok ? "Invalid server response." : `Server error ${resp.status}`);
        return;
      }
      if (data.error && /403|Forbidden|Could not download/i.test(String(data.error))) {
        try {
          data = await importViaExtensionBytes(url, poolId, savedOnly, "extension:context-menu-fallback");
        } catch (e2) {
          notify(
            "TBCC Import Failed",
            String(data.error).length > 280 ? String(data.error).slice(0, 280) + "…" : data.error
          );
          return;
        }
      }
    }
    if (data.error) {
      notify("TBCC Import Failed", String(data.error).length > 280 ? String(data.error).slice(0, 280) + "…" : data.error);
    } else if (savedOnly) {
      notify("TBCC", "Saved to Saved Messages");
    } else if (data.media_id) {
      notify("TBCC", `Imported as media #${data.media_id}`);
      try {
        chrome.storage.local.get(STORAGE_COLLECTED, (o) => {
          const arr = Array.isArray(o[STORAGE_COLLECTED]) ? o[STORAGE_COLLECTED] : [];
          arr.push({ url, type: "image", addedAt: Date.now(), source: "context_menu", media_id: data.media_id });
          chrome.storage.local.set({ [STORAGE_COLLECTED]: arr.slice(-500) });
        });
      } catch (_) {}
    } else if (data.status === "skipped") {
      notify("TBCC", data.reason || "Skipped (duplicate or unsupported)");
    } else {
      notify("TBCC", "Added (or duplicate).");
    }
  } catch (e) {
    const msg = e && e.message ? e.message : "Unknown error";
    notify(
      "TBCC Import Failed",
      msg.includes("fetch") || msg.includes("Failed")
        ? "Cannot reach backend at localhost:8000. Is it running?"
        : msg
    );
  }
});
