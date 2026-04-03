/* global chrome */
/** Shared by background service worker, options page, and aggregator tab. */
const STORAGE_MODEL_SEARCH_CUSTOM_SITES = "tbccModelSearchCustomSites";

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
  return {
    version: builtIn.version,
    sites: [...(builtIn.sites || []), ...custom],
  };
}

function buildModelSearchUrl(template, username) {
  return template.split("{username}").join(encodeURIComponent(String(username).trim()));
}
