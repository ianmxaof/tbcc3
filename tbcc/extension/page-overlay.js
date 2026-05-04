/**
 * Optional on-page checkboxes for every img/video (toggle via storage tbccOverlayMode).
 * Selection syncs with sidebar via tbccSelectionUrls in chrome.storage.local.
 */
(function () {
  if (window.__tbccPageOverlayLoaded) return;
  window.__tbccPageOverlayLoaded = true;

  const STYLE_ID = "tbcc-page-overlay-styles";
  const ROOT_ID = "tbcc-overlay-root";

  /** After extension reload/update, content scripts keep running but `chrome.runtime.id` is gone — all storage API calls reject. */
  function isExtensionContextAlive() {
    try {
      return !!(typeof chrome !== "undefined" && chrome.runtime && chrome.runtime.id);
    } catch (_) {
      return false;
    }
  }

  async function storageLocalGet(keys) {
    if (!isExtensionContextAlive()) return {};
    try {
      return await chrome.storage.local.get(keys);
    } catch (_) {
      return {};
    }
  }

  async function storageLocalSet(obj) {
    if (!isExtensionContextAlive()) return false;
    try {
      await chrome.storage.local.set(obj);
      return true;
    } catch (_) {
      return false;
    }
  }

  let overlayMode = false;
  const tracked = [];
  let tbccLastContextUsername = "";
  const STORAGE_LAST_COPIED_USERNAME = "tbccLastCopiedUsername";

  function normalizeUsernameCandidate(raw) {
    if (!raw) return "";
    let s = String(raw).trim();
    s = s.replace(/^@+/, "");
    s = s.replace(/^[^\w]+|[^\w.:-]+$/g, "");
    if (!s) return "";
    if (!/^[a-zA-Z0-9._-]{2,64}$/.test(s)) return "";
    return s;
  }

  function extractUsernameFromText(text) {
    if (!text) return "";
    const s = String(text);
    const tagged = s.match(/@([a-zA-Z0-9._-]{2,64})/);
    if (tagged && tagged[1]) return normalizeUsernameCandidate(tagged[1]);
    const plain = s.match(/\b([a-zA-Z0-9._-]{2,64})\b/);
    return plain && plain[1] ? normalizeUsernameCandidate(plain[1]) : "";
  }

  function extractUsernameFromUrl(rawUrl) {
    if (!rawUrl) return "";
    const str = String(rawUrl).trim();
    const tagged = str.match(/@([a-zA-Z0-9._-]{2,64})/);
    if (tagged && tagged[1]) return normalizeUsernameCandidate(tagged[1]);
    try {
      const u = new URL(str, document.baseURI || location.href);
      for (const key of ["username", "user", "u", "model", "handle", "nick", "q"]) {
        const val = u.searchParams.get(key);
        const n = normalizeUsernameCandidate(val);
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

  function resolveContextUsername(target) {
    if (!target) return "";
    let el = target.nodeType === Node.ELEMENT_NODE ? target : target.parentElement;
    while (el && el !== document.documentElement) {
      if (el.matches && el.matches("a[href]")) {
        const fromLink = extractUsernameFromUrl(el.getAttribute("href") || el.href || "");
        if (fromLink) return fromLink;
        const fromText = extractUsernameFromText(el.textContent || "");
        if (fromText) return fromText;
      }
      el = el.parentElement;
    }
    const selected = window.getSelection ? String(window.getSelection() || "").trim() : "";
    const fromSel = extractUsernameFromText(selected);
    if (fromSel) return fromSel;
    const text =
      (target && target.textContent) ||
      (target && target.nodeValue) ||
      (target && target.innerText) ||
      "";
    return extractUsernameFromText(text);
  }

  async function storeLastCopiedUsername(username) {
    const clean = normalizeUsernameCandidate(username);
    if (!clean) return;
    await storageLocalSet({
      [STORAGE_LAST_COPIED_USERNAME]: clean,
      tbccLastCopiedUsernameAt: Date.now(),
    });
  }

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
    const ssAttr = el.getAttribute("srcset") || el.getAttribute("data-srcset") || "";
    const ssLive = typeof el.srcset === "string" && el.srcset && el.srcset !== ssAttr ? el.srcset : "";
    const fromSet = bestUrlFromSrcset(ssAttr) || bestUrlFromSrcset(ssLive);
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
      if (isLikelyDirectImageAssetUrl(href)) push(href);
    }
  }

  function isLikelyDirectImageAssetUrl(url) {
    if (!url) return false;
    if (/\.(jpe?g|png|gif|webp|bmp|avif)(\?|$)/i.test(url)) return true;
    try {
      const u = new URL(url, location.href);
      const p = (u.pathname || "").toLowerCase();
      if (/\/attachments\//i.test(p) && /-(?:jpe?g|jpg|png|gif|webp|avif|bmp)\.\d+\/?$/i.test(p)) return true;
      if (/\/data\/attachments\//i.test(p) && /\.(?:jpe?g|jpg|png|gif|webp|avif|bmp)(?:\?|$)/i.test(p)) return true;
      return false;
    } catch (_) {
      return false;
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

  /** Nearest sibling <img> (or inner <img>) for a <video> tile — use its src as poster/thumb. */
  function nearbyImageForVideo(videoEl) {
    if (!videoEl) return "";
    try {
      const within = videoEl.querySelector("img");
      if (within) {
        const cands = [];
        pushImageCandidates(within, cands);
        const src = bestUrlFromCandidates(cands);
        if (src) return absUrl(src);
      }
    } catch (_) {}
    let n = videoEl.parentElement;
    for (let d = 0; d < 8 && n; d++) {
      const imgs = n.querySelectorAll ? n.querySelectorAll("img") : [];
      if (imgs && imgs.length) {
        const vidR = videoEl.getBoundingClientRect();
        let best = "";
        let bestOv = 0;
        for (const im of imgs) {
          let ir;
          try {
            ir = im.getBoundingClientRect();
          } catch (_) {
            continue;
          }
          const ix = Math.max(0, Math.min(vidR.right, ir.right) - Math.max(vidR.left, ir.left));
          const iy = Math.max(0, Math.min(vidR.bottom, ir.bottom) - Math.max(vidR.top, ir.top));
          const ov = ix * iy;
          if (ov > bestOv) {
            bestOv = ov;
            const cands = [];
            pushImageCandidates(im, cands);
            const src = bestUrlFromCandidates(cands);
            if (src) best = absUrl(src);
          }
        }
        if (best) return best;
      }
      n = n.parentElement;
    }
    return "";
  }

  function buildOverlayMetaForElement(el, url) {
    const meta = {
      url,
      pageUrl: location.href.split("#")[0],
      pageHost: (location.hostname || "").toLowerCase(),
      capturedAt: Date.now(),
    };
    const tag = (el.tagName || "").toUpperCase();
    if (tag === "VIDEO") {
      meta.mediaType = "video";
      meta.tagName = "video";
      try {
        const poster = el.getAttribute("poster") || "";
        if (poster && /^https?:\/\//i.test(absUrl(poster.trim()))) meta.posterUrl = absUrl(poster.trim());
      } catch (_) {}
      try {
        const nearby = nearbyImageForVideo(el);
        if (nearby) meta.thumbUrl = nearby;
        if (!meta.posterUrl && nearby) meta.posterUrl = nearby;
      } catch (_) {}
      try {
        if (typeof el.duration === "number" && isFinite(el.duration) && el.duration > 0) {
          meta.durationSec = el.duration;
        }
      } catch (_) {}
      try {
        const w = el.videoWidth || el.width || 0;
        const h = el.videoHeight || el.height || 0;
        if (w > 0 && h > 0) {
          meta.width = w;
          meta.height = h;
          meta.naturalWidth = w;
          meta.naturalHeight = h;
        }
      } catch (_) {}
    } else if (tag === "IMG") {
      meta.mediaType = "image";
      meta.tagName = "img";
      try {
        const w = el.naturalWidth || el.width || 0;
        const h = el.naturalHeight || el.height || 0;
        if (w > 0 && h > 0) {
          meta.width = w;
          meta.height = h;
          meta.naturalWidth = w;
          meta.naturalHeight = h;
        }
      } catch (_) {}
    }
    return meta;
  }

  async function storeOverlayMetaForUrl(url, meta) {
    if (!url || !meta) return;
    try {
      const { tbccSelectionMeta = {} } = await storageLocalGet("tbccSelectionMeta");
      const map = tbccSelectionMeta && typeof tbccSelectionMeta === "object" ? { ...tbccSelectionMeta } : {};
      map[url] = meta;
      const keys = Object.keys(map);
      if (keys.length > 400) {
        keys
          .sort((a, b) => (map[a].capturedAt || 0) - (map[b].capturedAt || 0))
          .slice(0, keys.length - 400)
          .forEach((k) => delete map[k]);
      }
      await storageLocalSet({ tbccSelectionMeta: map });
    } catch (_) {}
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
        let r = { width: 9999, height: 9999 };
        try {
          r = el.getBoundingClientRect();
        } catch (_) {}
        if (r.width < 64 && r.height < 64) return;
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
    const { tbccSelectionUrls = [] } = await storageLocalGet("tbccSelectionUrls");
    return new Set(tbccSelectionUrls);
  }

  async function toggleUrl(url, el) {
    const { tbccSelectionUrls = [] } = await storageLocalGet("tbccSelectionUrls");
    const set = new Set(tbccSelectionUrls);
    const nowChecked = !set.has(url);
    if (set.has(url)) set.delete(url);
    else set.add(url);
    await storageLocalSet({ tbccSelectionUrls: [...set] });
    if (nowChecked && el) {
      try {
        const meta = buildOverlayMetaForElement(el, url);
        await storeOverlayMetaForUrl(url, meta);
      } catch (_) {}
    }
  }

  async function selectAllOnPage() {
    const entries = collectMediaEntries();
    const urls = entries.map((e) => e.url).filter(Boolean);
    const { tbccSelectionUrls = [], tbccSelectionMeta = {} } = await storageLocalGet([
      "tbccSelectionUrls",
      "tbccSelectionMeta",
    ]);
    const merged = [...new Set([...tbccSelectionUrls, ...urls])];
    const metaMap = tbccSelectionMeta && typeof tbccSelectionMeta === "object" ? { ...tbccSelectionMeta } : {};
    for (const { el, url } of entries) {
      if (!url) continue;
      if (metaMap[url]) continue;
      try {
        metaMap[url] = buildOverlayMetaForElement(el, url);
      } catch (_) {}
    }
    const metaKeys = Object.keys(metaMap);
    if (metaKeys.length > 400) {
      metaKeys
        .sort((a, b) => (metaMap[a].capturedAt || 0) - (metaMap[b].capturedAt || 0))
        .slice(0, metaKeys.length - 400)
        .forEach((k) => delete metaMap[k]);
    }
    await storageLocalSet({ tbccSelectionUrls: merged, tbccSelectionMeta: metaMap });
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
    if (!isExtensionContextAlive()) {
      overlayMode = false;
      tearDown();
      return;
    }
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
        void toggleUrl(url, el).catch(() => {});
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
    if (!isExtensionContextAlive()) {
      overlayMode = false;
      tearDown();
      return;
    }
    const { tbccOverlayMode } = await storageLocalGet("tbccOverlayMode");
    overlayMode = !!tbccOverlayMode;
    if (overlayMode) await buildOverlay();
    else tearDown();
  }

  chrome.storage.onChanged.addListener((changes, area) => {
    if (!isExtensionContextAlive()) return;
    if (area !== "local") return;
    if (changes.tbccOverlayMode) {
      overlayMode = !!changes.tbccOverlayMode.newValue;
      if (overlayMode) void buildOverlay().catch(() => tearDown());
      else tearDown();
    }
    if (changes.tbccSelectionUrls && overlayMode) {
      void syncChecksFromStorage().catch(() => {});
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
    const safeSend = (payload) => {
      try {
        sendResponse(payload);
      } catch (_) {
        /* Port may already be gone (navigation / tab discard). */
      }
    };
    if (!isExtensionContextAlive()) {
      safeSend({ ok: false, error: "Extension context invalidated — reload this tab after updating TBCC." });
      return false;
    }
    if (msg.action === "tbcc-get-context-username") {
      safeSend({ username: tbccLastContextUsername || "" });
      return true;
    }
    if (msg.action === "tbcc-overlay-select-all") {
      selectAllOnPage()
        .then(() => safeSend({ ok: true }))
        .catch((e) => safeSend({ ok: false, error: String(e && e.message ? e.message : e) }));
      return true;
    }
    if (msg.action === "tbcc-overlay-refresh") {
      if (overlayMode) {
        buildOverlay()
          .then(() => safeSend({ ok: true }))
          .catch((e) => safeSend({ ok: false, error: String(e && e.message ? e.message : e) }));
      } else safeSend({ ok: true });
      return true;
    }
    return false;
  });

  function boot() {
    document.addEventListener("copy", () => {
      const selected = window.getSelection ? String(window.getSelection() || "").trim() : "";
      const picked = extractUsernameFromText(selected);
      if (picked) void storeLastCopiedUsername(picked);
    });
    document.addEventListener(
      "contextmenu",
      (e) => {
        tbccLastContextUsername = resolveContextUsername(e.target) || "";
      },
      true
    );
    void applyModeFromStorage().catch(() => tearDown());
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
