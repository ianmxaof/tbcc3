/**
 * Optional on-page checkboxes for every img/video (toggle via storage tbccOverlayMode).
 * Selection syncs with sidebar via tbccSelectionUrls in chrome.storage.local.
 */
(function () {
  if (window.__tbccPageOverlayLoaded) return;
  window.__tbccPageOverlayLoaded = true;

  const STYLE_ID = "tbcc-page-overlay-styles";
  const ROOT_ID = "tbcc-overlay-root";

  let overlayMode = false;
  const tracked = [];

  function absUrl(u) {
    try {
      return new URL(u, document.baseURI || location.href).href;
    } catch (_) {
      return u || "";
    }
  }

  function walkElements(node, callback) {
    if (!node) return;
    if (node.nodeType === 1) {
      try {
        callback(node);
      } catch (_) {}
      if (node.shadowRoot) walkElements(node.shadowRoot, callback);
    }
    for (let c = node.firstElementChild; c; c = c.nextElementSibling) {
      walkElements(c, callback);
    }
  }

  function bestUrlFromSrcset(srcset) {
    if (!srcset || !String(srcset).trim()) return "";
    const parts = String(srcset)
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    let best = "";
    let bestScore = 0;
    parts.forEach((part) => {
      const m = part.match(/^(\S+)\s+(\d+)w$/i);
      if (m) {
        const w = parseInt(m[2], 10);
        if (w > bestScore) {
          bestScore = w;
          best = m[1];
        }
        return;
      }
      const m2 = part.match(/^(\S+)\s+(\d+(?:\.\d+)?)x$/i);
      if (m2) {
        const x = parseFloat(m2[2]);
        const s = x * 10000;
        if (s > bestScore) {
          bestScore = s;
          best = m2[1];
        }
        return;
      }
      const first = part.split(/\s+/)[0];
      if (first && !best) best = first;
    });
    return best || "";
  }

  function scoreImageUrl(u) {
    if (!u || u.indexOf("data:") === 0) return -1000;
    const s = u.toLowerCase();
    let score = 0;
    if (s.indexOf("thumb") >= 0) score -= 35;
    if (s.indexOf("/small/") >= 0 || s.indexOf("_small") >= 0) score -= 30;
    if (s.indexOf("preview") >= 0 || s.indexOf("/mini/") >= 0) score -= 25;
    if (/_s\.(jpe?g|png|gif|webp)/i.test(s)) score -= 20;
    if (s.indexOf("avatar") >= 0 || s.indexOf("icon") >= 0) score -= 15;
    score += Math.min(s.length, 240) / 12;
    return score;
  }

  function heuristicUpgrade(u) {
    if (!u || u.indexOf("http") !== 0) return u;
    try {
      let x = u;
      x = x.replace(/\/thumbs?\//i, "/images/");
      x = x.replace(/\/thumb\//i, "/");
      x = x.replace(/_thumb\./i, ".");
      x = x.replace(/[?&]w=\d+/gi, "");
      x = x.replace(/[?&]width=\d+/gi, "");
      return x;
    } catch (_) {
      return u;
    }
  }

  function bestUrlFromCandidates(candidates) {
    const seen = {};
    const uniq = [];
    for (const raw of candidates) {
      if (!raw || typeof raw !== "string") continue;
      const u = absUrl(raw.trim());
      if (!u || seen[u]) continue;
      seen[u] = 1;
      uniq.push(u);
    }
    const extra = [];
    for (const u of uniq) {
      const h = heuristicUpgrade(u);
      if (h && h !== u && !seen[h]) {
        seen[h] = 1;
        extra.push(h);
      }
    }
    for (const e of extra) uniq.push(e);
    let best = "";
    let bestScore = -99999;
    for (const u of uniq) {
      const sc = scoreImageUrl(u);
      if (sc > bestScore) {
        bestScore = sc;
        best = u;
      }
    }
    return best;
  }

  function pushImageCandidates(el, arr) {
    const push = (u) => {
      if (u && typeof u === "string") arr.push(u);
    };
    const ss = el.getAttribute("srcset") || el.getAttribute("data-srcset") || "";
    const fromSet = bestUrlFromSrcset(ss);
    push(el.currentSrc);
    push(fromSet);
    push(el.getAttribute("src"));
    [
      "data-src",
      "data-lazy-src",
      "data-original",
      "data-zoom-src",
      "data-orig-file",
      "data-large",
      "data-full",
      "data-image",
      "data-href",
      "data-url",
      "data-big",
      "data-fullsrc",
    ].forEach((attr) => push(el.getAttribute(attr)));
    const pic = el.closest && el.closest("picture");
    if (pic) {
      const sources = pic.querySelectorAll("source[srcset]");
      for (let s = 0; s < sources.length; s++) {
        push(bestUrlFromSrcset(sources[s].getAttribute("srcset") || ""));
      }
    }
    const link = el.closest && el.closest("a[href]");
    if (link && link.href) {
      const href = link.href.split("#")[0];
      if (/\.(jpe?g|png|gif|webp|bmp)(\?|$)/i.test(href)) push(href);
    }
  }

  function mediaUrlFromElement(el) {
    const tag = (el.tagName || "").toUpperCase();
    if (tag === "IMG") {
      const cands = [];
      pushImageCandidates(el, cands);
      const src = bestUrlFromCandidates(cands);
      return src ? absUrl(src) : "";
    }
    if (tag === "VIDEO") {
      const src = el.currentSrc || el.src || (el.querySelector("source") && el.querySelector("source").src);
      return src ? absUrl(src) : "";
    }
    if (tag === "SOURCE" && el.parentNode && el.parentNode.tagName === "PICTURE") {
      const src = (el.srcset && bestUrlFromSrcset(el.srcset)) || el.src;
      return src ? absUrl(src) : "";
    }
    return "";
  }

  function collectMediaEntries() {
    const seen = new Set();
    const out = [];
    function add(el, url) {
      if (!url || url.length > 8000) return;
      if (url.startsWith("data:") && url.length > 50000) return;
      const key = url.slice(0, 200);
      if (seen.has(key)) return;
      seen.add(key);
      out.push({ el, url });
    }
    walkElements(document.documentElement, (el) => {
      const t = el.tagName;
      if (t === "IMG") {
        const u = mediaUrlFromElement(el);
        if (u) add(el, u);
      } else if (t === "VIDEO") {
        const u = mediaUrlFromElement(el);
        if (u) add(el, u);
      }
    });
    return out;
  }

  function injectStyles() {
    if (document.getElementById(STYLE_ID)) return;
    const s = document.createElement("style");
    s.id = STYLE_ID;
    s.textContent =
      ".tbcc-page-overlay-cb{position:fixed;z-index:2147483647;width:20px;height:20px;cursor:pointer;accent-color:#89b4fa;pointer-events:auto;box-sizing:border-box;margin:0;padding:0;}";
    (document.head || document.documentElement).appendChild(s);
  }

  function ensureRoot() {
    if (!document.body) return null;
    let root = document.getElementById(ROOT_ID);
    if (!root) {
      root = document.createElement("div");
      root.id = ROOT_ID;
      root.style.cssText =
        "position:fixed;inset:0;pointer-events:none;z-index:2147483646;margin:0;padding:0;border:0;";
      document.body.appendChild(root);
    }
    return root;
  }

  function tearDown() {
    const root = document.getElementById(ROOT_ID);
    if (root) root.remove();
    tracked.length = 0;
  }

  async function getSelectionSet() {
    const { tbccSelectionUrls = [] } = await chrome.storage.local.get("tbccSelectionUrls");
    return new Set(tbccSelectionUrls);
  }

  async function toggleUrl(url) {
    const { tbccSelectionUrls = [] } = await chrome.storage.local.get("tbccSelectionUrls");
    const set = new Set(tbccSelectionUrls);
    if (set.has(url)) set.delete(url);
    else set.add(url);
    await chrome.storage.local.set({ tbccSelectionUrls: [...set] });
  }

  async function selectAllOnPage() {
    const entries = collectMediaEntries();
    const urls = entries.map((e) => e.url).filter(Boolean);
    const { tbccSelectionUrls = [] } = await chrome.storage.local.get("tbccSelectionUrls");
    const merged = [...new Set([...tbccSelectionUrls, ...urls])];
    await chrome.storage.local.set({ tbccSelectionUrls: merged });
  }

  function placeCheckbox(cb, el) {
    const r = el.getBoundingClientRect();
    if (r.width < 2 && r.height < 2) {
      cb.style.display = "none";
      return;
    }
    cb.style.display = "";
    cb.style.left = Math.round(r.left + 4) + "px";
    cb.style.top = Math.round(r.top + 4) + "px";
  }

  async function buildOverlay() {
    injectStyles();
    tearDown();
    if (!overlayMode) return;
    const root = ensureRoot();
    if (!root) return;
    const entries = collectMediaEntries();
    const sel = await getSelectionSet();
    entries.forEach(({ el, url }) => {
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.className = "tbcc-page-overlay-cb";
      cb.title = "TBCC select";
      cb.checked = sel.has(url);
      cb.addEventListener("change", (e) => {
        e.stopPropagation();
        toggleUrl(url);
      });
      cb.addEventListener("click", (e) => e.stopPropagation());
      cb.addEventListener("mousedown", (e) => e.stopPropagation());
      root.appendChild(cb);
      tracked.push({ el, url, cb });
      placeCheckbox(cb, el);
    });
  }

  function updatePositions() {
    if (!overlayMode || !tracked.length) return;
    tracked.forEach(({ el, cb }) => {
      if (!el.isConnected) return;
      placeCheckbox(cb, el);
    });
  }

  async function applyModeFromStorage() {
    const { tbccOverlayMode } = await chrome.storage.local.get("tbccOverlayMode");
    overlayMode = !!tbccOverlayMode;
    if (overlayMode) await buildOverlay();
    else tearDown();
  }

  chrome.storage.onChanged.addListener((changes, area) => {
    if (area !== "local") return;
    if (changes.tbccOverlayMode) {
      overlayMode = !!changes.tbccOverlayMode.newValue;
      if (overlayMode) buildOverlay();
      else tearDown();
    }
    if (changes.tbccSelectionUrls && overlayMode) {
      syncChecksFromStorage();
    }
  });

  async function syncChecksFromStorage() {
    const sel = await getSelectionSet();
    tracked.forEach(({ url, cb }) => {
      cb.checked = sel.has(url);
    });
  }

  window.addEventListener(
    "scroll",
    () => {
      updatePositions();
    },
    true
  );
  window.addEventListener("resize", () => updatePositions());

  chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    if (msg.action === "tbcc-overlay-select-all") {
      selectAllOnPage().then(() => sendResponse({ ok: true }));
      return true;
    }
    if (msg.action === "tbcc-overlay-refresh") {
      if (overlayMode) buildOverlay().then(() => sendResponse({ ok: true }));
      else sendResponse({ ok: true });
      return true;
    }
    return false;
  });

  function boot() {
    applyModeFromStorage();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
