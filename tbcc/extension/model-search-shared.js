/* global chrome */
/** Shared by background service worker, options page, model search panel, and aggregator tab. */
const STORAGE_MODEL_SEARCH_CUSTOM_SITES = "tbccModelSearchCustomSites";
const MODEL_SEARCH_CATEGORY_ONLYFANS = "onlyfans";
const MODEL_SEARCH_CATEGORY_LIVECAMS = "livecams";
const MODEL_SEARCH_CATEGORY_VIDEOS = "videos";
const MODEL_SEARCH_CATEGORY_MACRO = "macro";

function normalizeModelSearchCategory(raw) {
  const s = String(raw || "").trim().toLowerCase();
  if (s === "archives" || s === "archive" || s === "onlyfans" || s === "onlyfans_search") {
    return MODEL_SEARCH_CATEGORY_ONLYFANS;
  }
  if (s === "cam" || s === "cams" || s === "livecams" || s === "live_cams") {
    return MODEL_SEARCH_CATEGORY_LIVECAMS;
  }
  if (s === "video" || s === "videos" || s === "video_search" || s === "clips") {
    return MODEL_SEARCH_CATEGORY_VIDEOS;
  }
  if (s === "macro" || s === "macro_search" || s === "native" || s === "engine") {
    return MODEL_SEARCH_CATEGORY_MACRO;
  }
  return MODEL_SEARCH_CATEGORY_ONLYFANS;
}

function modelSearchCategoryLabel(cat) {
  const c = normalizeModelSearchCategory(cat);
  if (c === MODEL_SEARCH_CATEGORY_MACRO) return "Macro search (native engine)";
  if (c === MODEL_SEARCH_CATEGORY_VIDEOS) return "Video search";
  return c === MODEL_SEARCH_CATEGORY_LIVECAMS ? "Live cam search" : "OnlyFans search";
}

/**
 * Built-in JSON + user-added sources from storage.
 */
async function getMergedModelSearchSites() {
  const r = await fetch(chrome.runtime.getURL("model-search-sites.json"));
  if (!r.ok) throw new Error("model-search-sites.json");
  const builtIn = await r.json();
  const data = await chrome.storage.local.get(STORAGE_MODEL_SEARCH_CUSTOM_SITES);
  const custom = Array.isArray(data[STORAGE_MODEL_SEARCH_CUSTOM_SITES])
    ? data[STORAGE_MODEL_SEARCH_CUSTOM_SITES]
    : [];
  const built = (builtIn.sites || []).map((s) => ({
    ...s,
    category: normalizeModelSearchCategory(s.category),
    __builtin: true,
  }));
  const customNorm = custom.map((s) => ({
    ...s,
    category: normalizeModelSearchCategory(s.category),
    __builtin: false,
  }));
  return {
    version: builtIn.version,
    sites: [...built, ...customNorm],
  };
}

function buildModelSearchUrl(template, username) {
  return template.split("{username}").join(encodeURIComponent(String(username).trim()));
}

function guessResultCountFromHtml(html) {
  if (!html || typeof html !== "string") return null;
  // Prefer counts near "search" / "result" headings — bare "10 videos" in sidebars is noise.
  const nearSearch = html.match(
    /(?:search|found|showing|results? for)[^.<]{0,80}?(\d[\d,]*)\s*(?:results?|entries|posts?|items?|videos?|photos?|models?)/i
  );
  if (nearSearch) return parseInt(nearSearch[1].replace(/,/g, ""), 10) || null;
  const m = html.match(/(\d[\d,]*)\s*(results?|entries)\b/i);
  if (m) return parseInt(m[1].replace(/,/g, ""), 10) || null;
  const m3 = html.match(/"total(?:Count|_count)?"\s*:\s*(\d+)/i);
  if (m3) return parseInt(m3[1], 10) || null;
  return null;
}

function escapeRegExp(s) {
  return String(s || "").replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * Count links that look like real profile/content hits for username — not the search form/URL echo.
 */
function countUsernameResultLinks(html, username, finalUrl) {
  const user = String(username || "").trim();
  if (!user || user.length < 2 || !html) return 0;
  const userLc = user.toLowerCase();
  const enc = encodeURIComponent(user).toLowerCase();
  let searchHost = "";
  let searchPath = "";
  try {
    const u = new URL(String(finalUrl || ""));
    searchHost = u.hostname.toLowerCase();
    searchPath = (u.pathname || "").toLowerCase();
  } catch (_) {}

  const hrefRe = /href\s*=\s*["']([^"']+)["']/gi;
  let n = 0;
  const seen = new Set();
  let m;
  while ((m = hrefRe.exec(html))) {
    let href = String(m[1] || "").trim();
    if (!href || href.startsWith("#") || href.startsWith("javascript:")) continue;
    const low = href.toLowerCase();
    if (/\.(css|js|png|jpe?g|gif|webp|svg|ico|woff2?)(\?|$)/i.test(low)) continue;
    if (/[?&](s|q|search|query|keyword)=/.test(low)) continue;
    if (/\/search\/|\/\?s=|index\.php\?search=/i.test(low) && (low.includes(userLc) || low.includes(enc))) continue;
    // Must reference username as a path segment (profile/album style), not only in query.
    const pathOk =
      new RegExp(`/(?:@)?${escapeRegExp(userLc)}(?:/|$|\\?|#)`, "i").test(low) ||
      new RegExp(`/(?:@)?${escapeRegExp(enc)}(?:/|$|\\?|#)`, "i").test(low);
    if (!pathOk) continue;
    // Skip self-link to the search page
    try {
      const abs = new URL(href, finalUrl || "https://example.com/");
      if (searchHost && abs.hostname.toLowerCase() === searchHost) {
        const p = (abs.pathname || "").toLowerCase();
        if (p === searchPath || /\/search\b/.test(p)) continue;
      }
      const key = abs.hostname + abs.pathname;
      if (seen.has(key)) continue;
      seen.add(key);
    } catch (_) {
      if (seen.has(low)) continue;
      seen.add(low);
    }
    n++;
  }
  return n;
}

/**
 * Site family for source-aware macro probing.
 * @returns {"livecams"|"onlyfans"|"videos"|"general"}
 */
function modelSearchSiteFamily(site) {
  const blob = `${(site && site.id) || ""} ${(site && site.name) || ""} ${(site && site.url) || ""} ${(site && site.category) || ""}`.toLowerCase();
  const cat = normalizeModelSearchCategory(site && site.category);
  if (
    /onlyfans|fapello|coomer|kemono|leaknude|erothot|whoreshub|thot|fansly|patreon|fanvue|loyalfans|badjojo|porn4fans|fapodrop|fapdungeon|leaks4fap|onlyxfinder|topfap|leakslink|modelsearcher/.test(
      blob
    )
  ) {
    return "onlyfans";
  }
  if (
    cat === MODEL_SEARCH_CATEGORY_LIVECAMS ||
    /cam|webcam|stripchat|chaturbate|bonga|recording|private|archivebate|showcam|onscreen|cumcam|cloudbate|bestcam|camwh|webcamrec|girlsinprivates|camlovin|privaterecord|someonesister|xcamlady|xhomealone|pusvid|livecam/.test(
      blob
    )
  ) {
    return "livecams";
  }
  if (cat === MODEL_SEARCH_CATEGORY_VIDEOS || /camwhores|video/.test(blob)) return "videos";
  if (cat === MODEL_SEARCH_CATEGORY_ONLYFANS) return "onlyfans";
  return "general";
}

/** Preferred site families when the username was captured on a given platform. */
function preferredFamiliesForUsernameSource(source) {
  const h =
    typeof TbccUsernameSearchHistory !== "undefined" && TbccUsernameSearchHistory.normalizeUsernameSearchSource
      ? TbccUsernameSearchHistory.normalizeUsernameSearchSource(source)
      : String(source || "").toLowerCase();
  if (["stripchat", "chaturbate", "cambb", "xhamsterlive"].includes(h)) {
    return ["livecams", "videos"];
  }
  if (["onlyfans", "fansly", "instagram"].includes(h)) {
    return ["onlyfans", "general"];
  }
  if (h === "erome" || h === "reddit" || h === "x") {
    return ["general", "onlyfans", "livecams", "videos"];
  }
  return null;
}

function hostFromUrl(url) {
  try {
    return new URL(String(url || "")).hostname.toLowerCase();
  } catch (_) {
    return "";
  }
}

function urlMatchesHost(url, hosts) {
  const host = hostFromUrl(url);
  if (!host) return false;
  return hosts.some((h) => host === h || host.endsWith("." + h));
}

/** Host-specific probe rules (ARNA parity). */
const SITE_PROBE_RULES = [
  {
    hosts: ["livecamrips.to"],
    denyContains: ["no records found", "no models found", "no results", "0 models found"],
    requireAny: ['class="video"', "model-card"],
  },
  {
    hosts: ["cumcams.cc"],
    denyRegex: [/<h1[^>]*>\s*404\s*<\/h1>/i, /performer\s+not\s+found/i],
    requireAny: ["profile-info", 'class="performer"'],
  },
  {
    hosts: ["allmy.cam"],
    requireAny: ['class="video-card"'],
  },
  {
    hosts: ["showcamrips.com"],
    denyContains: ["data:image/png;base64"],
  },
  {
    hosts: ["camshowrecordings.com"],
    requireAny: ['class="h1modelpage"'],
  },
  {
    hosts: ["livecamsrip.com"],
    denyContains: ["no records found"],
  },
  {
    hosts: ["camwhores.tv", "camwhoresbay.com"],
    denyRegex: [/there\s+is\s+no\s+data\s+in\s+this\s+list/i, /no\s+videos?\s+found/i, /\b0\s+videos\b/i],
  },
  {
    hosts: ["erothots.co", "erothots.com"],
    denyContains: ["parklogic", "redirecting"],
  },
  {
    hosts: ["fapello.com"],
    denyRegex: [/no\s+models?\s+found/i, /nothing\s+found/i],
  },
  {
    hosts: ["whoreshub.com"],
    denyRegex: [/no\s+videos?\s+found/i, /nothing\s+found/i, /0\s+videos/i],
  },
];

function extractTitleLower(html) {
  const m = String(html || "").match(/<title[^>]*>(.*?)<\/title>/is);
  if (!m) return "";
  return m[1].replace(/\s+/g, " ").trim().toLowerCase();
}

function applySiteProbeRules(html, finalUrl) {
  if (!html) return null;
  const lower = html.toLowerCase();
  for (const rule of SITE_PROBE_RULES) {
    if (!urlMatchesHost(finalUrl, rule.hosts)) continue;
    for (const needle of rule.denyContains || []) {
      if (lower.includes(String(needle).toLowerCase())) {
        return { action: "deny", signal: "site_deny", reason: "none" };
      }
    }
    for (const rx of rule.denyRegex || []) {
      if (rx.test(html)) {
        return { action: "deny", signal: "site_deny", reason: "none" };
      }
    }
    const required = rule.requireAny || [];
    if (required.length) {
      if (!required.some((marker) => lower.includes(String(marker).toLowerCase()))) {
        return { action: "deny", signal: "site_require", reason: "none" };
      }
      return { action: "confirm", count: 1, signal: "site_markers", reason: "ok" };
    }
  }
  return null;
}

/**
 * Best-effort: does this search/profile page look like it has content?
 * Strict: search boxes always echo the query — that alone is NOT a hit.
 * Returns { hasResults, count, reason, confidence, signal }.
 */
function analyzeModelSearchHtml(html, finalUrl, username) {
  if (!html || typeof html !== "string" || html.length < 40) {
    return { hasResults: false, count: 0, reason: "empty", confidence: "none", signal: "empty" };
  }
  const lower = html.toLowerCase();
  const userLc = String(username || "").trim().toLowerCase();
  const blocked =
    /just a moment|cf-browser-verification|attention required|enable javascript|ddos protection|checking your browser|cloudflare|parklogic|adblockingdetected/i.test(
      html
    );
  if (blocked) return { hasResults: false, count: 0, reason: "blocked", confidence: "none", signal: "blocked" };

  const siteRule = applySiteProbeRules(html, finalUrl);
  if (siteRule && siteRule.action === "deny") {
    return {
      hasResults: false,
      count: 0,
      reason: siteRule.reason || "none",
      confidence: "none",
      signal: siteRule.signal || "site_deny",
      finalUrl: finalUrl || "",
    };
  }

  const titleLc = extractTitleLower(html);
  if (titleLc && ["not found", "404", "error", "redirecting"].some((term) => titleLc.includes(term))) {
    return { hasResults: false, count: 0, reason: "none", confidence: "none", signal: "title_not_found", finalUrl: finalUrl || "" };
  }
  // Homepages / index shells are never hits
  if (titleLc && /\bindex page\b|\bhome\b\s*$/i.test(titleLc) && !/search results/i.test(titleLc)) {
    return { hasResults: false, count: 0, reason: "none", confidence: "none", signal: "index_shell", finalUrl: finalUrl || "" };
  }

  if (/^\s*[\[{]/.test(html.trim())) {
    try {
      const data = JSON.parse(html);
      const arr = Array.isArray(data) ? data : Array.isArray(data && data.items) ? data.items : null;
      if (arr) {
        const n = arr.length;
        const confidence = n >= 2 ? "high" : n === 1 ? "medium" : "none";
        return { hasResults: n > 0, count: n, reason: n > 0 ? "ok" : "none", confidence, signal: "json" };
      }
      if (data && typeof data === "object" && data.total != null) {
        const n = Number(data.total);
        if (Number.isFinite(n) && n >= 0) {
          const confidence = n >= 2 ? "high" : n === 1 ? "medium" : "none";
          return { hasResults: n > 0, count: n, reason: n > 0 ? "ok" : "none", confidence, signal: "json_total" };
        }
      }
    } catch (_) {}
  }

  const explicitEmpty =
    /\bno\s+results?\b|\b0\s+results?\b|nothing\s+found|no\s+matches|not\s+found|no\s+videos?\s+found|\b0\s+videos\b|does\s+not\s+exist|no\s+records\s+found|there\s+is\s+no\s+data\s+in\s+this\s+list|keine\s+ergebnisse|aucun\s+résultat|no\s+posts\s+found|sorry,\s*no\s+posts/i.test(
      lower
    );
  if (explicitEmpty) {
    return { hasResults: false, count: 0, reason: "none", confidence: "none", signal: "explicit_empty" };
  }

  const resultLinks = countUsernameResultLinks(html, username, finalUrl);
  let count = guessResultCountFromHtml(html);
  let signal = count != null ? "count_regex" : "none";

  // Card grids without username-bearing result links are almost always template chrome.
  if (resultLinks <= 0) {
    if (siteRule && siteRule.action === "confirm") {
      // Host-specific confirm still requires username somewhere meaningful in body beyond inputs
      const inputOnly =
        userLc &&
        (lower.match(new RegExp(`value=["'][^"']*${escapeRegExp(userLc)}[^"']*["']`, "gi")) || []).length > 0 &&
        resultLinks === 0;
      if (inputOnly || !userLc || !lower.includes(userLc)) {
        return { hasResults: false, count: 0, reason: "none", confidence: "none", signal: "confirm_without_links", finalUrl: finalUrl || "" };
      }
    }
    return {
      hasResults: false,
      count: 0,
      reason: "none",
      confidence: "none",
      signal: "no_result_links",
      finalUrl: finalUrl || "",
    };
  }

  // Prefer link evidence over inflated sidebar counts
  count = Math.max(resultLinks, count != null && count <= resultLinks * 3 ? count : resultLinks);
  signal = "result_links";

  if (siteRule && siteRule.action === "confirm") {
    count = Math.max(Number(siteRule.count) || 1, count);
    signal = siteRule.signal || "site_markers";
  }

  const confidence = resultLinks >= 2 || signal === "json" || signal === "site_markers" ? "high" : "medium";
  return {
    hasResults: true,
    count,
    reason: "ok",
    confidence,
    signal,
    finalUrl: finalUrl || "",
    resultLinks,
  };
}

/** Turn a completed search URL into a {username} template (panel helper). */
function deriveUsernameTemplateFromSearchUrl(rawUrl, sampleUsername) {
  const url = String(rawUrl || "").trim();
  const user = String(sampleUsername || "").trim();
  if (!url || !user) return null;
  const enc = encodeURIComponent(user);
  const variants = [user, enc, user.toLowerCase(), enc.toLowerCase()];
  for (const v of variants) {
    if (!v) continue;
    const idx = url.indexOf(v);
    if (idx >= 0) {
      return url.slice(0, idx) + "{username}" + url.slice(idx + v.length);
    }
  }
  return null;
}
