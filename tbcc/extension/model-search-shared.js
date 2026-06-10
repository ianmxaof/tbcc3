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
  const m = html.match(/(\d[\d,]*)\s*(results?|entries|posts?|items?|found|hits?|videos?|photos?|models?)\b/i);
  if (m) return parseInt(m[1].replace(/,/g, ""), 10) || null;
  const m2 = html.match(/(?:total|about|count|results?)\s*[:\s]*\s*(\d[\d,]*)/i);
  if (m2) return parseInt(m2[1].replace(/,/g, ""), 10) || null;
  const m3 = html.match(/"total(?:Count|_count)?"\s*:\s*(\d+)/i);
  if (m3) return parseInt(m3[1], 10) || null;
  return null;
}

/**
 * Best-effort: does this search/profile page look like it has content?
 * Returns { hasResults, count, reason } where reason is ok | none | blocked | error.
 */
function analyzeModelSearchHtml(html, finalUrl, username) {
  if (!html || typeof html !== "string" || html.length < 40) {
    return { hasResults: false, count: 0, reason: "empty", confidence: "none", signal: "empty" };
  }
  const lower = html.toLowerCase();
  const userLc = String(username || "").trim().toLowerCase();
  const blocked =
    /just a moment|cf-browser-verification|attention required|enable javascript|ddos protection|checking your browser|cloudflare/i.test(
      html
    );
  if (blocked) return { hasResults: false, count: 0, reason: "blocked", confidence: "none", signal: "blocked" };

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
    /\bno\s+results\b|\b0\s+results\b|nothing\s+found|no\s+matches|not\s+found|keine\s+ergebnisse|aucun\s+résultat/i.test(
      lower
    );
  let count = guessResultCountFromHtml(html);
  let signal = count != null ? "count_regex" : "none";
  if (explicitEmpty && (count == null || count === 0)) {
    return { hasResults: false, count: 0, reason: "none", confidence: "none", signal: "explicit_empty" };
  }

  if (count == null) {
    const patterns = [
      /class="[^"]*(?:video-card|result-item|post-item|model-card|thumb-card|grid-item|album-item)/gi,
      /<article\b/gi,
      /data-post-id=/gi,
      /class="[^"]*post\b[^"]*"/gi,
    ];
    let cards = 0;
    for (const p of patterns) {
      const m = html.match(p);
      if (m) cards = Math.max(cards, m.length);
    }
    if (cards >= 2) {
      count = cards;
      signal = "cards";
    } else if (cards === 1) {
      count = 1;
      signal = "cards";
    }
  }

  if ((count == null || count === 0) && /404|page not found|doesn't exist|user not found|model not found/i.test(lower)) {
    return { hasResults: false, count: 0, reason: "none", confidence: "none", signal: "not_found" };
  }

  let hasResults = count != null && count > 0;
  if (hasResults && userLc && !lower.includes(userLc)) {
    hasResults = false;
    count = 0;
    signal = "no_username_in_html";
  }

  let confidence = "none";
  if (hasResults) {
    confidence = signal === "json" || signal === "json_total" || (count || 0) >= 2 ? "high" : "medium";
  }

  return {
    hasResults,
    count: hasResults ? count : 0,
    reason: hasResults ? "ok" : "none",
    confidence,
    signal,
    finalUrl: finalUrl || "",
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
