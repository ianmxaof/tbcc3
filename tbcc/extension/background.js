importScripts("model-search-shared.js");

const API_URL = "http://localhost:8000/import/url";
const API_BYTES = "http://localhost:8000/import/bytes";
const API_SAVED_BATCH = "http://localhost:8000/import/saved-batch";
const API_MEDIA_BULK_TAGS = "http://localhost:8000/media/bulk/tags";
const SAVED_ALBUM_CHUNK = 10;
/** Match capture.js: overlap session fetches before sequential /import/saved-batch POSTs. */
const TBCC_FETCH_CONCURRENCY = 3;

/**
 * Run fetchFn(url, idx) for each URL with at most TBCC_FETCH_CONCURRENCY in flight; results match urls order.
 */
async function fetchUrlsWithConcurrency(urls, fetchFn) {
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
  const w = Math.min(TBCC_FETCH_CONCURRENCY, n);
  await Promise.all(Array.from({ length: w }, () => worker()));
  return results;
}
const STORAGE_LAST_TAB = "tbccLastActiveTabId";
const STORAGE_COLLECTED = "tbcc_collected";
const STORAGE_MODEL_SEARCH_ENABLED = "tbccModelSearchEnabledSites";
const STORAGE_MODEL_SEARCH_MODE = "tbccModelSearchOpenMode";
const STORAGE_LAST_COPIED_USERNAME = "tbccLastCopiedUsername";
const STORAGE_MODEL_SEARCH_HISTORY = "tbccModelSearchHistory";
const STORAGE_PAYMENT_BOT_USERNAME = "tbccPaymentBotUsername";
const STORAGE_REVERSE_IMAGE_ENABLED = "tbccReverseImageEnabledSites";
const STORAGE_REVERSE_IMAGE_MODE = "tbccReverseImageOpenMode";
const STORAGE_MODEL_SEARCH_LAST_SUMMARY = "tbccModelSearchLastSummary";
const STORAGE_AUTO_TAG_ON_EXPORT = "tbccAutoTagOnExport";
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

async function recordModelSearchHistory(username) {
  const clean = normalizeUsernameCandidate(username);
  if (!clean) return;
  let arr = [];
  try {
    const data = await chrome.storage.local.get(STORAGE_MODEL_SEARCH_HISTORY);
    arr = Array.isArray(data[STORAGE_MODEL_SEARCH_HISTORY]) ? data[STORAGE_MODEL_SEARCH_HISTORY] : [];
  } catch (_) {}
  const now = Date.now();
  const deduped = arr.filter((x) => x && x.username && String(x.username).toLowerCase() !== clean.toLowerCase());
  const next = [{ username: clean, ts: now }, ...deduped].slice(0, 200);
  await chrome.storage.local.set({ [STORAGE_MODEL_SEARCH_HISTORY]: next });
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

async function launchModelSearch(username, onlySiteId = null, onlyCategory = null) {
  const cleanUsername = normalizeUsernameCandidate(username);
  if (!cleanUsername) {
    notify("TBCC", "Model search expects a username.");
    return;
  }
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
  let first = true;
  for (const s of sites) {
    const u = buildModelSearchUrl(s.url, cleanUsername);
    await chrome.tabs.create({ url: u, active: wantActive && first });
    first = false;
  }
  await recordModelSearchSummary(cleanUsername, sites, onlySiteId);
  await recordModelSearchHistory(cleanUsername);
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
      h === "video.twimg.com"
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

async function fetchUrlWithBrowserSession(url, refererPageUrl) {
  const eromeChain = eromeReferrerChain(url);
  let cookieHeader = "";
  if (eromeChain) {
    cookieHeader = await mergeCookiesForUrls(eromeChain);
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
          if (res.ok) return await res.arrayBuffer();
          res = await fetch(url, {
            method: "GET",
            credentials: "omit",
            headers: { ...base, Referer: ref, Origin: `${u.protocol}//${u.hostname}` },
          });
          if (res.ok) return await res.arrayBuffer();
        } catch (_) {}
      }
    }
    /** Twitter / X: CDN rejects Referer https://video.twimg.com/ — must look like navigation from x.com. */
    if (h === "video.twimg.com") {
      const refs = [];
      const pushRef = (s) => {
        const t = String(s || "").trim().split("#")[0];
        if (t && /^https?:\/\//i.test(t) && !refs.includes(t)) refs.push(t);
      };
      pushRef(refererPageUrl);
      pushRef("https://x.com/");
      pushRef("https://twitter.com/");
      for (const ref of refs) {
        try {
          const origin = new URL(ref).origin;
          const res = await fetch(url, {
            method: "GET",
            credentials: "omit",
            headers: { ...base, Referer: ref, Origin: origin },
          });
          if (res.ok) return await res.arrayBuffer();
        } catch (_) {}
      }
      throw new Error(
        "Twitter / X video CDN blocked fetch — play the clip on X, tap Refresh in TBCC, then download the video.twimg.com tile (not a blob: entry)."
      );
    }
    if (h.includes("onlyfans.com")) base.Referer = "https://onlyfans.com/";
    else if (/(^|\.)fetlife\.com$/i.test(h) || h.includes("fetlife")) base.Referer = "https://fetlife.com/";
    else if (h.includes("motherless") || h.endsWith("motherlessmedia.com"))
      base.Referer = "https://motherless.com/";
    else if (/(^|\.)coomer\.(st|party)$/.test(h) || /^n\d+\.coomer\.(st|party)$/i.test(h))
      base.Referer = "https://coomer.st/";
    else if (/(^|\.)kemono\.(party|su|si)$/.test(h) || /^n\d+\.kemono\.(party|su|si)$/i.test(h))
      base.Referer = "https://kemono.party/";
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

async function importViaExtensionBytes(url, poolId, savedOnly, source, caption, refererPageUrl) {
  url = normalizeTbccMediaUrlForImport(url);
  const ab = await fetchUrlWithBrowserSession(url, refererPageUrl);
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
  const parts = await fetchUrlsWithConcurrency(urls, async (url) => {
    const ab = await fetchUrlWithBrowserSession(normalizeTbccMediaUrlForImport(url));
    const { name, type } = blobNameAndTypeForUrl(url);
    return { ab, name, type };
  });
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

function tbccIsInjectableHttpUrl(url) {
  return url && typeof url === "string" && /^https?:\/\//i.test(url);
}

/** Track last http(s) tab only — extension/chrome pages must not overwrite (tab capture needs real page id). */
chrome.tabs.onActivated.addListener(({ tabId }) => {
  chrome.tabs.get(tabId).then((tab) => {
    if (tab && tbccIsInjectableHttpUrl(tab.url)) {
      chrome.storage.local.set({ [STORAGE_LAST_TAB]: tabId });
    }
  }).catch(() => {});
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
  }
});
chrome.tabs.onRemoved.addListener((tabId) => {
  TBCC_TAB_URL_CACHE.delete(tabId);
  void chrome.storage.session.remove(`tbcc_net_media_${tabId}`);
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

function tbccArrayBufferToDataUrl(ab) {
  const bytes = new Uint8Array(ab);
  let mime = "image/jpeg";
  if (bytes.length >= 3 && bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff) mime = "image/jpeg";
  else if (bytes.length >= 8 && bytes[0] === 0x89 && bytes[1] === 0x50 && bytes[2] === 0x4e && bytes[3] === 0x47) mime = "image/png";
  else if (bytes.length >= 6 && bytes[0] === 0x47 && bytes[1] === 0x49 && bytes[2] === 0x46) mime = "image/gif";
  else if (bytes.length >= 4 && bytes[0] === 0x52 && bytes[1] === 0x49 && bytes[2] === 0x46 && bytes[3] === 0x46) mime = "image/webp";
  let binary = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk));
  }
  return `data:${mime};base64,${btoa(binary)}`;
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
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
      try {
        const ab = await fetchUrlWithBrowserSession(url, "");
        if (!ab || ab.byteLength < 24 || ab.byteLength > TBCC_THUMB_PROXY_MAX_BYTES) {
          sendResponse({ ok: false });
          return;
        }
        sendResponse({ ok: true, dataUrl: tbccArrayBufferToDataUrl(ab) });
      } catch (_) {
        sendResponse({ ok: false });
      }
    })();
    return true;
  }
  if (msg.action === "tbcc-import-bytes-session") {
    (async () => {
      try {
        const data = await importViaExtensionBytes(
          msg.url,
          msg.poolId ?? 1,
          !!msg.savedOnly,
          msg.source || "extension:gallery-session",
          msg.caption,
          msg.refererPageUrl || ""
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
        const buffer = await fetchUrlWithBrowserSession(
          normalizeTbccMediaUrlForImport(msg.url),
          msg.refererPageUrl || ""
        );
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

function installContextMenus() {
  /** Toolbar icon opens/closes the gallery side panel (no default_popup — popup would block this). */
  chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(() => {});
  chrome.contextMenus.removeAll(() => {
    const mac = (props) => {
      chrome.contextMenus.create(props, () => {
        const err = chrome.runtime.lastError;
        if (err) console.warn("TBCC contextMenus.create", props && props.id, err.message);
      });
    };
    mac({ id: "sendToTBCC", title: "TBCC: Save to pool", contexts: ["image", "video", "link"] });
    mac({ id: "sendToSaved", title: "TBCC: Saved Messages", contexts: ["image", "video", "link"] });
    mac({ id: "sendPageToTBCC", title: "TBCC: Save to pool (this tab URL)", contexts: ["page", "frame"] });
    mac({ id: "sendPageToSaved", title: "TBCC: Saved Messages (this tab URL)", contexts: ["page", "frame"] });
    mac({ id: "sendSelectionToTBCC", title: "TBCC: Save to pool (selected URL)", contexts: ["selection"] });
    mac({ id: "sendSelectionToSaved", title: "TBCC: Saved Messages (selected URL)", contexts: ["selection"] });
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
  const onlyfansSites = sites.filter((s) => normalizeModelSearchCategory(s.category) === MODEL_SEARCH_CATEGORY_ONLYFANS);
  const livecamSites = sites.filter((s) => normalizeModelSearchCategory(s.category) === MODEL_SEARCH_CATEGORY_LIVECAMS);
  const videoSites = sites.filter((s) => normalizeModelSearchCategory(s.category) === MODEL_SEARCH_CATEGORY_VIDEOS);
  mac({
    id: "tbccModelSearchRoot",
    title: "TBCC: Look up username",
    contexts: ["selection", "link", "page"],
  });
  mac({
    id: "tbccms_all_onlyfans",
    parentId: "tbccModelSearchRoot",
    title: "Open all enabled OnlyFans sources",
    contexts: ["selection", "link", "page"],
  });
  mac({
    id: "tbccms_all_livecams",
    parentId: "tbccModelSearchRoot",
    title: "Open all enabled live cam sources",
    contexts: ["selection", "link", "page"],
  });
  mac({
    id: "tbccms_all_videos",
    parentId: "tbccModelSearchRoot",
    title: "Open all enabled video sources",
    contexts: ["selection", "link", "page"],
  });
  mac({
    id: "tbccms_sep_clip",
    parentId: "tbccModelSearchRoot",
    type: "separator",
    contexts: ["selection", "link", "page"],
  });
  mac({
    id: "tbccms_clip_onlyfans",
    parentId: "tbccModelSearchRoot",
    title: "Search copied username (OnlyFans sources)",
    contexts: ["selection", "link", "page"],
  });
  mac({
    id: "tbccms_clip_livecams",
    parentId: "tbccModelSearchRoot",
    title: "Search copied username (live cam sources)",
    contexts: ["selection", "link", "page"],
  });
  mac({
    id: "tbccms_clip_videos",
    parentId: "tbccModelSearchRoot",
    title: "Search copied username (video sources)",
    contexts: ["selection", "link", "page"],
  });
  mac({
    id: "tbccms_sep0",
    parentId: "tbccModelSearchRoot",
    type: "separator",
    contexts: ["selection", "link", "page"],
  });
  mac({
    id: "tbccms_group_onlyfans",
    parentId: "tbccModelSearchRoot",
    title: "OnlyFans sources",
    contexts: ["selection", "link", "page"],
  });
  for (const s of onlyfansSites) {
    mac({
      id: tbccMenuIdForSite(s.id),
      parentId: "tbccms_group_onlyfans",
      title: String(s.name || s.id).slice(0, 120),
      contexts: ["selection", "link", "page"],
    });
  }
  mac({
    id: "tbccms_group_livecams",
    parentId: "tbccModelSearchRoot",
    title: "Live cam sources",
    contexts: ["selection", "link", "page"],
  });
  for (const s of livecamSites) {
    mac({
      id: tbccMenuIdForSite(s.id),
      parentId: "tbccms_group_livecams",
      title: String(s.name || s.id).slice(0, 120),
      contexts: ["selection", "link", "page"],
    });
  }
  mac({
    id: "tbccms_group_videos",
    parentId: "tbccModelSearchRoot",
    title: "Video sources",
    contexts: ["selection", "link", "page"],
  });
  for (const s of videoSites) {
    mac({
      id: tbccMenuIdForSite(s.id),
      parentId: "tbccms_group_videos",
      title: String(s.name || s.id).slice(0, 120),
      contexts: ["selection", "link", "page"],
    });
  }
  mac({
    id: "tbccms_bot_videofind",
    parentId: "tbccModelSearchRoot",
    title: "Send /videofind in payment bot",
    contexts: ["selection", "link", "page"],
  });
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

/** Gallery closed: disable on-page overlay so checkboxes do not linger on tabs. */
async function clearPageOverlayModeForClosedGallery() {
  try {
    const { tbccOverlayMode } = await chrome.storage.local.get("tbccOverlayMode");
    if (!tbccOverlayMode) return;
    await chrome.storage.local.set({ tbccOverlayMode: false });
  } catch (_) {}
}

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

/**
 * Packaged PNG only — data: URLs and tiny/decoding edge cases often throw
 * "Unable to download all specified images" (extensions::notifications) in Brave/Chromium MV3.
 */
function notify(title, message) {
  try {
    const iconUrl = chrome.runtime.getURL("icons/icon16.png");
    chrome.notifications.create(
      "tbcc-" + Date.now(),
      {
        type: "basic",
        iconUrl,
        title: title || "TBCC",
        message: message || "",
      },
      () => {
        const err = chrome.runtime.lastError;
        if (err) console.warn("TBCC notification:", err.message);
      }
    );
  } catch (e) {
    console.log("TBCC:", title, message, e);
  }
}

function isSavedMenuId(id) {
  return id === "sendToSaved" || id === "sendPageToSaved" || id === "sendSelectionToSaved";
}

function tbccNormalizeAutoTagToken(raw) {
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
  const compact = raw.replace(/\s+/gu, "");
  if (!compact) return "";
  const capped = compact.length > 42 ? compact.slice(0, 42) : compact;
  return "#" + capped;
}

function tbccCollectAutoTagsFromUrl(rawUrl, outSet, includeHost) {
  try {
    const u = new URL(String(rawUrl || "").trim());
    const host = String(u.hostname || "").replace(/^www\./i, "");
    if (includeHost) {
      const hNorm = tbccNormalizeAutoTagToken(host);
      if (hNorm) outSet.add(hNorm);
    }
    host
      .split(".")
      .filter(Boolean)
      .forEach((part) => {
        const p = tbccNormalizeAutoTagToken(part);
        if (p) outSet.add(p);
      });
    String(u.pathname || "")
      .split("/")
      .map((part) => decodeURIComponent(part || "").trim())
      .filter(Boolean)
      .forEach((part) => {
        part
          .split(/[^a-zA-Z0-9]+/g)
          .filter(Boolean)
          .forEach((bit) => {
            const b = tbccNormalizeAutoTagToken(bit);
            if (b) outSet.add(b);
          });
      });
  } catch (_) {}
}

function tbccBuildAutoTagPayload(url, refererPageUrl) {
  const tags = new Set();
  const ref = String(refererPageUrl || "").trim();
  const primary = ref && /^https?:\/\//i.test(ref) ? ref : String(url || "").trim();
  tbccCollectAutoTagsFromUrl(primary, tags, true);
  tbccCollectAutoTagsFromUrl(String(url || "").trim(), tags, false);
  const list = [...tags];
  const csv = list.join(", ");
  const hashtags = list.map((t) => tbccDisplayTagToHashtag(t)).filter(Boolean);
  const caption = hashtags.join(" ").trim().slice(0, 900);
  return { tagsCsv: csv, caption };
}

async function tbccApplyTagsToImportedMediaIds(mediaIds, tagsCsv) {
  const csv = String(tagsCsv || "").trim();
  if (!csv) return;
  const ids = [...new Set((mediaIds || []).map((x) => parseInt(x, 10)).filter((x) => Number.isFinite(x)))];
  if (!ids.length) return;
  const r = await fetch(API_MEDIA_BULK_TAGS, {
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

async function importUrlViaTbcc(url, savedOnly, source, refererPageUrl, autoTagPayload) {
  const cleanUrl = String(url || "").trim();
  if (!cleanUrl) return { ok: false, error: "No URL for this action." };
  if (!/^https?:\/\//i.test(cleanUrl)) return { ok: false, error: "Only http(s) URLs are supported." };
  if (cleanUrl.startsWith("blob:") || cleanUrl.startsWith("data:")) {
    return { ok: false, error: "Blob/data URLs cannot be imported. Use a direct link." };
  }
  const { tbccPoolId } = await chrome.storage.local.get("tbccPoolId");
  const poolId = tbccPoolId ?? 1;
  const autoTagsCsv =
    autoTagPayload && autoTagPayload.tagsCsv ? String(autoTagPayload.tagsCsv).trim() : "";
  const autoCaption =
    autoTagPayload && autoTagPayload.caption ? String(autoTagPayload.caption).trim() : "";
  const body = { url: cleanUrl, pool_id: poolId };
  if (savedOnly) body.saved_only = true;
  let data;
  if (savedOnly || hostNeedsSessionFetch(cleanUrl)) {
    data = await importViaExtensionBytes(
      cleanUrl,
      poolId,
      savedOnly,
      source || "extension:context-menu",
      autoCaption,
      refererPageUrl || ""
    );
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
      return { ok: false, error: resp.ok ? "Invalid server response." : `Server error ${resp.status}` };
    }
    if (data.error && /403|Forbidden|Could not download/i.test(String(data.error))) {
      try {
        data = await importViaExtensionBytes(
          cleanUrl,
          poolId,
          savedOnly,
          (source || "extension:context-menu") + "-fallback",
          autoCaption,
          refererPageUrl || ""
        );
      } catch (_) {
        return { ok: false, error: String(data.error || "Import blocked (403)") };
      }
    }
  }
  if (data && data.error) return { ok: false, error: String(data.error), data };
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

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  const id = String(info.menuItemId || "");

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
    const data = await chrome.storage.local.get(STORAGE_PAYMENT_BOT_USERNAME);
    const bot = String((data && data[STORAGE_PAYMENT_BOT_USERNAME]) || "").trim().replace(/^@+/, "");
    if (!bot) {
      notify("TBCC", "Set Payment bot username in Extension options first.");
      return;
    }
    const deep = `https://t.me/${encodeURIComponent(bot)}?start=vf_${encodeURIComponent(username)}`;
    await chrome.tabs.create({ url: deep, active: true });
    notify("TBCC", `Opened Telegram deep link for /videofind ${username}`);
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
    const autoTagPayload = autoTagOnExport === false ? null : tbccBuildAutoTagPayload(url, (tab && tab.url) || "");
    const result = await importUrlViaTbcc(
      url,
      savedOnly,
      "extension:context-menu",
      (tab && tab.url) || "",
      autoTagPayload
    );
    if (!result.ok) {
      notify(
        "TBCC Import Failed",
        String(result.error || "Import failed").length > 280
          ? String(result.error || "Import failed").slice(0, 280) + "…"
          : String(result.error || "Import failed")
      );
      return;
    }
    const data = result.data || {};
    if (savedOnly) {
      notify("TBCC", "Saved to Saved Messages");
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
      msg.includes("fetch") || msg.includes("Failed")
        ? "Cannot reach backend at localhost:8000. Is it running?"
        : msg
    );
  }
});

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.action === "tbcc-download-url-from-page-menu") {
    (async () => {
      try {
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
          const hasRedItem = /^\/(?:watch|ifr|gifs)\/[^/?#]+/i.test(u.pathname || "") || !!redgifsIdFromAnyUrl(finalUrl);
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
            return base || "media";
          } catch (_) {
            return "media";
          }
        })();
        chrome.downloads.download(
          {
            url: downloadUrl,
            filename: path,
            saveAs: false,
            conflictAction: "uniquify",
          },
          (id) => {
            const err = chrome.runtime.lastError;
            if (err || !id) {
              sendResponse({ ok: false, error: err ? err.message : "Download failed." });
              return;
            }
            notify("TBCC", "Download started.");
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
            : tbccBuildAutoTagPayload(msg.url, msg.refererPageUrl || "");
        const result = await importUrlViaTbcc(
          msg.url,
          !!msg.savedOnly,
          "extension:page-media-menu",
          msg.refererPageUrl || "",
          autoTagPayload
        );
        if (!result.ok) {
          sendResponse({ ok: false, error: result.error || "Import failed" });
          return;
        }
        const data = result.data || {};
        if (msg.savedOnly) notify("TBCC", "Saved to Saved Messages");
        else if (data.media_id) notify("TBCC", `Imported as media #${data.media_id}`);
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
