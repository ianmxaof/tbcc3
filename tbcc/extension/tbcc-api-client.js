/**
 * Shared TBCC API base resolution for extension SW, gallery, and import pipeline.
 * Prefers chrome.storage tbccApiBase (Options or set-extension-island-api.ps1).
 * Default probe order: island (api.powercore.app) → island IP → home localhost.
 */
const TBCC_DEFAULT_API_BASES = [
  "https://api.powercore.app",
  "http://5.161.53.91:8000",
  "http://127.0.0.1:8000",
  "http://localhost:8000",
];
const TBCC_STORAGE_API_BASE = "tbccApiBase";

function tbccNormalizeApiBase(base) {
  return String(base || "")
    .trim()
    .replace(/\/+$/, "");
}

async function tbccResolveApiBases() {
  const bases = [...TBCC_DEFAULT_API_BASES];
  try {
    const d = await chrome.storage.local.get(TBCC_STORAGE_API_BASE);
    const custom = tbccNormalizeApiBase(d[TBCC_STORAGE_API_BASE]);
    if (custom && /^https?:\/\//i.test(custom)) bases.unshift(custom);
  } catch (_) {}
  const seen = new Set();
  const out = [];
  for (const b of bases) {
    const n = tbccNormalizeApiBase(b);
    if (!n || seen.has(n)) continue;
    seen.add(n);
    out.push(n);
  }
  return out;
}

async function tbccPrimaryApiBase() {
  const bases = await tbccResolveApiBases();
  return bases[0] || TBCC_DEFAULT_API_BASES[0];
}

async function tbccInternalApiHeaders(extra) {
  const h = { ...(extra || {}) };
  try {
    const d = await chrome.storage.local.get("tbccInternalApiKey");
    const key = String(d.tbccInternalApiKey || "").trim();
    if (key) h["X-TBCC-Internal-Key"] = key;
  } catch (_) {}
  return h;
}

/**
 * Fetch path on first reachable API base. Returns Response (may be non-ok).
 * On connection errors, tries next base. Stops rotating on 401/403.
 */
async function tbccFetchApi(path, options) {
  const opts = options || {};
  const p = path.startsWith("/") ? path : "/" + path;
  const bases = await tbccResolveApiBases();
  const auth = await tbccInternalApiHeaders();
  const headers = { ...auth, ...(opts.headers || {}) };
  let lastErr = "unreachable";
  for (const base of bases) {
    const url = base + p;
    try {
      const r = await fetch(url, { ...opts, headers });
      if (r.ok) return r;
      const detail = await r.clone().text().catch(() => "");
      lastErr = `${url} → HTTP ${r.status}${detail ? ": " + detail.slice(0, 160) : ""}`;
      if (r.status === 401 || r.status === 403) return r;
    } catch (e) {
      lastErr = `${url} → ${(e && e.message) || e}`;
    }
  }
  throw new Error(lastErr);
}

async function tbccFetchApiJson(path, options) {
  const r = await tbccFetchApi(path, options);
  let data = {};
  const text = await r.text().catch(() => "");
  try {
    data = text ? JSON.parse(text) : {};
  } catch (_) {
    data = { error: text ? text.slice(0, 200) : `HTTP ${r.status}` };
  }
  if (!r.ok) {
    const msg = data.detail || data.error || text.slice(0, 200) || `HTTP ${r.status}`;
    throw new Error(msg);
  }
  return data;
}
