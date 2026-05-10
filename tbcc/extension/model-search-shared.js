/* global chrome */
/** Shared by background service worker, options page, and aggregator tab. */
const STORAGE_MODEL_SEARCH_CUSTOM_SITES = "tbccModelSearchCustomSites";
const MODEL_SEARCH_CATEGORY_ONLYFANS = "onlyfans";
const MODEL_SEARCH_CATEGORY_LIVECAMS = "livecams";
const MODEL_SEARCH_CATEGORY_VIDEOS = "videos";

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
  return MODEL_SEARCH_CATEGORY_ONLYFANS;
}

function modelSearchCategoryLabel(cat) {
  const c = normalizeModelSearchCategory(cat);
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
