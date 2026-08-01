/**
 * Optional on-page checkboxes for every img/video (toggle via storage tbccOverlayMode).
 * Selection syncs with sidebar via tbccSelectionUrls in chrome.storage.local.
 */
(function () {
  if (typeof tbccWaitForModule !== "function") return;
  tbccWaitForModule("page_overlay", function () {
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
  const STORAGE_PAGE_MENU_ITEMS = "tbccPageMenuItems";
  const TBCC_PAGE_MENU_ID = "tbcc-page-media-menu";
  const DEFAULT_PAGE_MENU_ITEMS = {
    "save-archive": true,
    "save-archive-all": true,
    "send-pack-pool": true,
    "send-storage-hub": true,
    "save-pool": true,
    "save-saved": true,
    "download-direct": true,
    "download-url": true,
    "download-frame": true,
    "toggle-select": true,
    "copy-url": true,
    "open-url": true,
    "reverse-image": true,
    "lookup-username": true,
  };
  let pageMenuItems = { ...DEFAULT_PAGE_MENU_ITEMS };
  let tbccPageMenu = null;
  let tbccPageMenuUrl = "";
  let tbccPageMenuFrameUrl = "";
  let tbccPageMenuEl = null;
  let tbccPageMenuOpenedAt = 0;
  let tbccPageMenuUsername = "";
  let pageMediaMenuEnabled = true;
  let rightClickFallbackCtx = null;
  const tbccIsRedgifsHost = /(^|\.)redgifs\.com$/i.test(location.hostname || "");

  function shouldUseCustomPageMenuForEvent(e) {
    if (!pageMediaMenuEnabled) return false;
    if (tbccIsRedgifsHost) return true;
    return !!(e && e.altKey);
  }

  function normalizeUsernameCandidate(raw) {
    const f = globalThis.TbccUsernameFilter;
    if (f && typeof f.normalizeUsernameCandidate === "function") return f.normalizeUsernameCandidate(raw);
    if (!raw) return "";
    let s = String(raw).trim().replace(/^@+/, "");
    if (!/^[a-zA-Z0-9._-]{2,64}$/.test(s)) return "";
    return s;
  }

  function acceptedContextUsername(raw) {
    const f = globalThis.TbccUsernameFilter;
    const ref = String(location.href || "").split("#")[0];
    if (f && typeof f.acceptUsernameForArchive === "function") {
      return f.acceptUsernameForArchive(raw, { source: "context_menu", ref }) || "";
    }
    return normalizeUsernameCandidate(raw);
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
    const ref = String(location.href || "").split("#")[0];
    const f = globalThis.TbccUsernameFilter;
    const clean =
      f && typeof f.acceptUsernameForArchive === "function"
        ? f.acceptUsernameForArchive(username, { source: "copy", ref })
        : normalizeUsernameCandidate(username);
    if (!clean) return;
    await storageLocalSet({
      [STORAGE_LAST_COPIED_USERNAME]: clean,
      tbccLastCopiedUsernameAt: Date.now(),
    });
    try {
      chrome.runtime.sendMessage({
        action: "tbcc-record-username-archive",
        username: clean,
        source: "copy",
        ref,
        pageUrl: ref,
      });
    } catch (_) {}
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

  function isPerchanceHost() {
    try {
      return /(^|\.)perchance\.org$/i.test(location.hostname);
    } catch (_) {
      return false;
    }
  }

  function mediaUrlFromCanvas(el) {
    if (!el || el.tagName !== "CANVAS") return "";
    const w = el.width || 0;
    const h = el.height || 0;
    if (w < 48 || h < 48) return "";
    try {
      const cr = el.getBoundingClientRect();
      if (cr.width < 24 && cr.height < 24) return "";
    } catch (_) {}
    try {
      let dataUrl = isPerchanceHost() ? el.toDataURL("image/png") : el.toDataURL("image/jpeg", 0.9);
      if (!dataUrl || dataUrl.length < 200) return "";
      if (dataUrl.length > 14000000) dataUrl = el.toDataURL("image/jpeg", 0.82);
      return dataUrl;
    } catch (_) {
      return "";
    }
  }

  function mediaUrlFromElement(el) {
    const tag = (el.tagName || "").toUpperCase();
    if (tag === "CANVAS") {
      return mediaUrlFromCanvas(el);
    }
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
    } else if (tag === "CANVAS") {
      meta.mediaType = "image";
      meta.tagName = "canvas";
      try {
        const w = el.width || 0;
        const h = el.height || 0;
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

  function metaStorageKey(url) {
    const u = String(url || "");
    if (u.startsWith("data:")) return "data:" + u.length + ":" + u.slice(12, 56);
    if (u.length > 480) return u.slice(0, 480);
    return u;
  }

  async function storeOverlayMetaForUrl(url, meta) {
    if (!url || !meta) return;
    try {
      const { tbccSelectionMeta = {} } = await storageLocalGet("tbccSelectionMeta");
      const map = tbccSelectionMeta && typeof tbccSelectionMeta === "object" ? { ...tbccSelectionMeta } : {};
      const key = metaStorageKey(url);
      map[key] = { ...meta, url: meta.url || url.slice(0, 120) };
      const keys = Object.keys(map);
      if (keys.length > 120) {
        keys
          .sort((a, b) => (map[a].capturedAt || 0) - (map[b].capturedAt || 0))
          .slice(0, keys.length - 120)
          .forEach((k) => delete map[k]);
      }
      await storageLocalSet({ tbccSelectionMeta: map });
    } catch (_) {}
  }

  function collectMediaEntries() {
    const seen = new Set();
    const out = [];
    function add(el, url) {
      if (!url) return;
      if (!url.startsWith("data:") && url.length > 8000) return;
      if (url.startsWith("data:")) {
        const isImgData = /^data:image\/(png|jpe?g|webp|gif);/i.test(url);
        const maxLen = isImgData ? 15000000 : 50000;
        if (url.length > maxLen) return;
      }
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
        const minSide = isPerchanceHost() ? 40 : 64;
        if (r.width < minSide && r.height < minSide) return;
        const u = mediaUrlFromElement(el);
        if (u) add(el, u);
      } else if (t === "CANVAS") {
        const u = mediaUrlFromElement(el);
        if (u) add(el, u);
      } else if (t === "VIDEO") {
        const u = mediaUrlFromElement(el);
        if (u) add(el, u);
      }
    });
    return out;
  }

  function pageMenuItemEnabled(act) {
    if (!act) return false;
    if (act === "lookup-username") return pageMenuItems["lookup-username"] !== false;
    return pageMenuItems[act] !== false;
  }

  function isImageMediaUrl(url, el) {
    if (el) {
      const tag = (el.tagName || "").toUpperCase();
      if (tag === "IMG" || tag === "CANVAS") return true;
      if (tag === "VIDEO") {
        try {
          const poster = el.getAttribute && el.getAttribute("poster");
          if (poster && /^https?:\/\//i.test(poster)) return true;
        } catch (_) {}
        return false;
      }
    }
    const u = String(url || "").trim();
    if (!u) return false;
    if (/^data:image\//i.test(u)) return true;
    if (!/^https?:\/\//i.test(u)) return false;
    const path = u.split("#")[0].split("?")[0];
    return /\.(jpe?g|png|gif|webp|bmp|avif)(\?|$)/i.test(path);
  }

  function injectStyles() {
    if (document.getElementById(STYLE_ID)) return;
    const s = document.createElement("style");
    s.id = STYLE_ID;
    s.textContent =
      ".tbcc-page-overlay-cb{position:fixed;z-index:2147483647;width:20px;height:20px;cursor:pointer;accent-color:#89b4fa;pointer-events:auto;box-sizing:border-box;margin:0;padding:0;}" +
      ".tbcc-page-menu{position:fixed;z-index:2147483647;margin:0;padding:0;border:0;background:transparent;font:12px/1.25 'Segoe UI',Tahoma,sans-serif;}" +
      ".tbcc-page-menu[hidden]{display:none!important;}" +
      ".tbcc-page-menu__inner{min-width:188px;max-width:min(88vw,280px);padding:5px;border-radius:6px;border:1px solid rgba(255,255,255,.1);background:#1a1a22;box-shadow:0 8px 28px rgba(0,0,0,.55);color:#e8e8ef;}" +
      ".tbcc-page-menu__inner button{display:block;width:100%;text-align:left;background:transparent;border:0;color:inherit;padding:6px 9px;border-radius:5px;cursor:pointer;font:inherit;font-size:12px;}" +
      ".tbcc-page-menu__inner button:hover{background:rgba(255,255,255,.08);}";
    (document.head || document.documentElement).appendChild(s);
  }

  function populatePageMenu(menu) {
    const inner = menu.querySelector(".tbcc-page-menu__inner") || menu;
    inner.querySelectorAll("button[data-act]").forEach((b) => b.remove());
    const items = [
      { act: "save-archive", label: "Save URL to master archive" },
      { act: "save-archive-all", label: "Save all video URLs to master archive" },
      { act: "send-pack-pool", label: "Send to AOF pack / loot pool" },
      { act: "send-storage-hub", label: "Send to Storage Hub ▸" },
      { act: "save-pool", label: "Save to pool" },
      { act: "save-saved", label: "Save to Saved Messages" },
      { act: "download-direct", label: "Direct download" },
      { act: "download-url", label: "Save AOF (watch)" },
      { act: "download-frame", label: "Save frame AOF" },
      { act: "toggle-select", label: "Toggle overlay select" },
      { act: "copy-url", label: "Copy media URL" },
      { act: "open-url", label: "Open media URL" },
    ];
    if (isImageMediaUrl(tbccPageMenuUrl, tbccPageMenuEl)) {
      items.push({ act: "reverse-image", label: "Reverse image search" });
    }
    if (tbccPageMenuUsername) {
      items.push({
        act: "lookup-username",
        label: "Look up username (@" + tbccPageMenuUsername + ")",
      });
    }
    for (const item of items) {
      if (!pageMenuItemEnabled(item.act)) continue;
      const btn = document.createElement("button");
      btn.type = "button";
      btn.dataset.act = item.act;
      btn.textContent = item.label;
      inner.appendChild(btn);
    }
  }

  function ensurePageMenu() {
    injectStyles();
    if (tbccPageMenu && tbccPageMenu.isConnected) return tbccPageMenu;
    if (!document.body) return null;
    const root = document.createElement("div");
    root.id = TBCC_PAGE_MENU_ID;
    root.className = "tbcc-page-menu";
    root.hidden = true;
    const inner = document.createElement("div");
    inner.className = "tbcc-page-menu__inner";
    root.appendChild(inner);
    root.addEventListener("click", (e) => {
      const btn = e.target && e.target.closest ? e.target.closest("button[data-act]") : null;
      if (!btn) return;
      const action = btn.getAttribute("data-act") || "";
      void handlePageMenuAction(action).catch(() => {});
    });
    document.body.appendChild(root);
    tbccPageMenu = root;
    return root;
  }

  function closePageMenu() {
    if (!tbccPageMenu) return;
    tbccPageMenu.hidden = true;
    tbccPageMenuUrl = "";
    tbccPageMenuFrameUrl = "";
    tbccPageMenuEl = null;
    tbccPageMenuUsername = "";
  }

  /**
   * Reddit and other hosts ship a Permissions-Policy that blocks clipboard-write
   * for embedded/extension contexts. Probing the policy avoids the noisy
   * "Clipboard API has been blocked" console error before falling back.
   */
  function clipboardWriteAllowed() {
    try {
      const fp = document.permissionsPolicy || document.featurePolicy;
      if (fp && typeof fp.allowsFeature === "function") {
        return !!fp.allowsFeature("clipboard-write");
      }
    } catch (_) {}
    return true;
  }

  function copyTextViaExecCommand(text) {
    try {
      const ta = document.createElement("textarea");
      ta.value = String(text == null ? "" : text);
      ta.setAttribute("readonly", "");
      ta.style.cssText =
        "position:fixed;top:-1000px;left:-1000px;width:1px;height:1px;opacity:0;pointer-events:none;";
      (document.body || document.documentElement).appendChild(ta);
      const prevActive = document.activeElement;
      ta.focus();
      ta.select();
      try {
        ta.setSelectionRange(0, ta.value.length);
      } catch (_) {}
      let ok = false;
      try {
        ok = !!document.execCommand("copy");
      } catch (_) {}
      ta.remove();
      try {
        if (prevActive && typeof prevActive.focus === "function") prevActive.focus();
      } catch (_) {}
      return ok;
    } catch (_) {
      return false;
    }
  }

  async function copyTextToClipboard(text) {
    const s = String(text == null ? "" : text);
    if (!s) return false;
    if (
      clipboardWriteAllowed() &&
      typeof navigator !== "undefined" &&
      navigator.clipboard &&
      typeof navigator.clipboard.writeText === "function"
    ) {
      try {
        await navigator.clipboard.writeText(s);
        return true;
      } catch (_) {}
    }
    return copyTextViaExecCommand(s);
  }

  function openPageMenu(x, y, url, el, frameUrl, username) {
    const menu = ensurePageMenu();
    if (!menu || !url) return;
    tbccPageMenuUrl = url;
    tbccPageMenuFrameUrl = frameUrl || url;
    tbccPageMenuEl = el || null;
    tbccPageMenuUsername = username || "";
    populatePageMenu(menu);
    menu.hidden = false;
    menu.style.left = "0px";
    menu.style.top = "0px";
    const vw = window.innerWidth || document.documentElement.clientWidth || 0;
    const vh = window.innerHeight || document.documentElement.clientHeight || 0;
    const r = menu.getBoundingClientRect();
    const pad = 8;
    const left = Math.max(pad, Math.min(Math.round(x), Math.max(pad, vw - r.width - pad)));
    const top = Math.max(pad, Math.min(Math.round(y), Math.max(pad, vh - r.height - pad)));
    menu.style.left = left + "px";
    menu.style.top = top + "px";
    tbccPageMenuOpenedAt = Date.now();
  }

  async function openStorageHubTopicPicker(mediaUrl, mediaEl) {
    const menu = ensurePageMenu();
    if (!menu) return;
    tbccPageMenuUrl = mediaUrl || tbccPageMenuUrl;
    tbccPageMenuEl = mediaEl || tbccPageMenuEl;
    const inner = menu.querySelector(".tbcc-page-menu__inner") || menu;
    inner.querySelectorAll("button[data-act]").forEach((b) => b.remove());
    const back = document.createElement("button");
    back.type = "button";
    back.dataset.act = "storage-hub-back";
    back.textContent = "◂ Back";
    inner.appendChild(back);
    const loading = document.createElement("button");
    loading.type = "button";
    loading.disabled = true;
    loading.textContent = "Loading topics…";
    inner.appendChild(loading);
    menu.hidden = false;
    let topics = [];
    try {
      topics = await new Promise((resolve) => {
        chrome.runtime.sendMessage({ action: "tbcc-list-storage-hub-topics" }, (r) => {
          if (chrome.runtime.lastError) resolve([]);
          else resolve((r && r.topics) || []);
        });
      });
    } catch (_) {
      topics = [];
    }
    loading.remove();
    if (!topics.length) {
      const empty = document.createElement("button");
      empty.type = "button";
      empty.disabled = true;
      empty.textContent = "(No topics — start backend)";
      inner.appendChild(empty);
      return;
    }
    for (const t of topics) {
      const tid = parseInt(t.message_thread_id, 10);
      if (!Number.isFinite(tid) || tid < 1) continue;
      const btn = document.createElement("button");
      btn.type = "button";
      btn.dataset.act = `storage-hub:${tid}`;
      btn.textContent = String(t.menu_label || t.short_label || t.topic_title || tid);
      inner.appendChild(btn);
    }
  }

  async function handlePageMenuAction(action) {
    const url = tbccPageMenuUrl;
    const frameUrl = tbccPageMenuFrameUrl || tbccPageMenuUrl;
    const el = tbccPageMenuEl;
    const isHubNav =
      action === "send-storage-hub" ||
      action === "storage-hub-back" ||
      (typeof action === "string" && action.startsWith("storage-hub:"));
    if (!isHubNav) closePageMenu();
    if (!url && action !== "storage-hub-back") return;
    if (action === "copy-url") {
      let copyUrl = url;
      try {
        const resolved = await new Promise((resolve) => {
          chrome.runtime.sendMessage(
            {
              action: "tbcc-resolve-copy-media-url",
              url,
              pageUrl: location.href.split("#")[0],
            },
            (r) => {
              if (chrome.runtime.lastError) resolve(url);
              else resolve((r && r.url) || url);
            }
          );
        });
        if (resolved) copyUrl = resolved;
      } catch (_) {}
      const ok = await copyTextToClipboard(copyUrl);
      if (ok) {
        const clip = globalThis.TbccClipboard;
        if (clip && clip.showCopied) {
          if (copyUrl !== url && /\.(m3u8|mpd|mp4|webm)(\?|$)/i.test(copyUrl)) {
            clip.showCopied({ message: "Copied stream URL" });
          } else {
            clip.showCopied();
          }
        }
      }
      return;
    }
    if (action === "open-url") {
      try {
        window.open(url, "_blank", "noopener,noreferrer");
      } catch (_) {}
      return;
    }
    if (action === "toggle-select") {
      if (el) await toggleUrl(url, el);
      return;
    }
    if (action === "download-direct") {
      try {
        await new Promise((resolve) => {
          chrome.runtime.sendMessage(
            {
              action: "tbcc-download-url-from-page-menu",
              url,
              preferFull: true,
              saveAof: false,
              refererPageUrl: location.href.split("#")[0],
            },
            () => resolve()
          );
        });
      } catch (_) {}
      return;
    }
    if (action === "download-url") {
      try {
        await new Promise((resolve) => {
          chrome.runtime.sendMessage(
            {
              action: "tbcc-download-url-from-page-menu",
              url,
              preferFull: true,
              saveAof: true,
              refererPageUrl: location.href.split("#")[0],
            },
            () => resolve()
          );
        });
      } catch (_) {}
      return;
    }
    if (action === "download-frame") {
      try {
        await new Promise((resolve) => {
          chrome.runtime.sendMessage(
            {
              action: "tbcc-download-url-from-page-menu",
              url: frameUrl,
              preferFull: false,
              refererPageUrl: location.href.split("#")[0],
            },
            () => resolve()
          );
        });
      } catch (_) {}
      return;
    }
    if (action === "save-pool" || action === "save-saved") {
      try {
        await new Promise((resolve) => {
          chrome.runtime.sendMessage(
            {
              action: "tbcc-import-url-from-page-menu",
              url,
              savedOnly: action === "save-saved",
              refererPageUrl: location.href.split("#")[0],
            },
            () => resolve()
          );
        });
      } catch (_) {}
      return;
    }
    if (action === "send-pack-pool") {
      const packUrl = url || String(location.href || "").split("#")[0];
      try {
        await new Promise((resolve) => {
          chrome.runtime.sendMessage(
            {
              action: "tbcc-page-menu-pack-pool",
              url: packUrl,
              refererPageUrl: location.href.split("#")[0],
            },
            () => resolve()
          );
        });
      } catch (_) {}
      return;
    }
    if (action === "send-storage-hub") {
      await openStorageHubTopicPicker(url, el);
      return;
    }
    if (action.startsWith("storage-hub:")) {
      const tid = parseInt(action.slice("storage-hub:".length), 10);
      closePageMenu();
      if (!Number.isFinite(tid) || tid < 1) return;
      try {
        await new Promise((resolve) => {
          chrome.runtime.sendMessage(
            {
              action: "tbcc-page-menu-storage-hub",
              url,
              messageThreadId: tid,
              refererPageUrl: location.href.split("#")[0],
            },
            () => resolve()
          );
        });
      } catch (_) {}
      return;
    }
    if (action === "storage-hub-back") {
      const menu = ensurePageMenu();
      if (!menu) return;
      populatePageMenu(menu);
      menu.hidden = false;
      return;
    }
    if (action === "save-archive") {
      const saveUrl = url || String(location.href || "").split("#")[0];
      try {
        await new Promise((resolve) => {
          chrome.runtime.sendMessage(
            {
              action: "tbcc-page-menu-archive-url",
              url: saveUrl,
              refererPageUrl: location.href.split("#")[0],
            },
            () => resolve()
          );
        });
      } catch (_) {}
      return;
    }
    if (action === "save-archive-all") {
      try {
        await new Promise((resolve) => {
          chrome.runtime.sendMessage(
            {
              action: "tbcc-page-menu-archive-all-videos",
              refererPageUrl: location.href.split("#")[0],
            },
            () => resolve()
          );
        });
      } catch (_) {}
      return;
    }
    if (action === "lookup-username") {
      const u = tbccPageMenuUsername;
      if (!u) return;
      try {
        await new Promise((resolve) => {
          chrome.runtime.sendMessage(
            {
              action: "tbcc-record-username-archive",
              username: u,
              source: "user_pick",
              ref: location.href.split("#")[0],
              pageUrl: location.href.split("#")[0],
            },
            () => resolve()
          );
        });
        await new Promise((resolve) => {
          chrome.runtime.sendMessage({ action: "tbcc-launch-model-search-tabs", username: u }, () => resolve());
        });
      } catch (_) {}
      return;
    }
    if (action === "reverse-image") {
      let searchUrl = url;
      try {
        const resolved = await new Promise((resolve) => {
          chrome.runtime.sendMessage(
            {
              action: "tbcc-resolve-copy-media-url",
              url,
              pageUrl: location.href.split("#")[0],
            },
            (r) => {
              if (chrome.runtime.lastError) resolve(url);
              else resolve((r && r.url) || url);
            }
          );
        });
        if (resolved) searchUrl = resolved;
      } catch (_) {}
      try {
        await new Promise((resolve) => {
          chrome.runtime.sendMessage({ action: "tbcc-launch-reverse-image", url: searchUrl }, () => resolve());
        });
      } catch (_) {}
    }
  }

  function nearestMediaElementFromTarget(target) {
    if (!target) return null;
    let el = target.nodeType === Node.ELEMENT_NODE ? target : target.parentElement;
    if (!el) return null;
    if (el.closest) {
      const direct = el.closest("img,video,source");
      if (direct) return direct;
    }
    let node = el;
    for (let d = 0; d < 8 && node; d++) {
      if (node.querySelector) {
        const found = node.querySelector("video, img, source");
        if (found) return found;
      }
      node = node.parentElement;
    }
    return null;
  }

  function redgifsWatchUrlFromHref(href) {
    if (!href) return "";
    try {
      const u = new URL(href, location.href);
      if (!/(^|\.)redgifs\.com$/i.test(u.hostname)) return "";
      const m = (u.pathname || "").match(/^\/(?:watch|ifr|gifs)\/([^/?#]+)/i);
      if (!m || !m[1]) return "";
      return "https://www.redgifs.com/watch/" + m[1];
    } catch (_) {
      return "";
    }
  }

  function redgifsWatchUrlFromAnyText(raw) {
    if (!raw) return "";
    const s = String(raw);
    const m = s.match(/(?:https?:\/\/(?:www\.)?redgifs\.com)?\/(?:watch|ifr|gifs)\/([a-z0-9]+)/i);
    if (!m || !m[1]) return "";
    return "https://www.redgifs.com/watch/" + m[1];
  }

  function bestLinkUrlFromTarget(target) {
    let el = target && target.nodeType === Node.ELEMENT_NODE ? target : target && target.parentElement;
    if (!el) return "";
    if (el.closest) {
      const a0 = el.closest("a[href]");
      if (a0 && a0.href) return String(a0.href).split("#")[0];
    }
    let node = el;
    for (let d = 0; d < 8 && node; d++) {
      if (node.getAttribute) {
        const dataHref = node.getAttribute("data-href") || node.getAttribute("data-url");
        if (dataHref) {
          try {
            return new URL(dataHref, location.href).href.split("#")[0];
          } catch (_) {}
        }
      }
      if (node.querySelector) {
        const a = node.querySelector("a[href]");
        if (a && a.href) return String(a.href).split("#")[0];
      }
      node = node.parentElement;
    }
    return "";
  }

  function bestRedgifsItemUrlFromTarget(target) {
    let el = target && target.nodeType === Node.ELEMENT_NODE ? target : target && target.parentElement;
    if (!el) return "";
    const cands = [];
    const push = (v) => {
      if (!v) return;
      const s = String(v).trim();
      if (!s) return;
      cands.push(s);
    };
    let node = el;
    for (let d = 0; d < 9 && node; d++) {
      try {
        push(node.getAttribute && node.getAttribute("href"));
        push(node.getAttribute && node.getAttribute("src"));
        push(node.getAttribute && node.getAttribute("poster"));
        push(node.getAttribute && node.getAttribute("data-href"));
        push(node.getAttribute && node.getAttribute("data-url"));
        push(node.getAttribute && node.getAttribute("data-src"));
        push(node.getAttribute && node.getAttribute("data-gif-id"));
        push(node.getAttribute && node.getAttribute("data-id"));
        push(node.getAttribute && node.getAttribute("data-video-id"));
      } catch (_) {}
      if (node.querySelectorAll) {
        const picks = node.querySelectorAll("a[href], video[src], video[poster], source[src], img[src]");
        for (let i = 0; i < picks.length && i < 24; i++) {
          const p = picks[i];
          push(p.getAttribute && p.getAttribute("href"));
          push(p.getAttribute && p.getAttribute("src"));
          push(p.getAttribute && p.getAttribute("poster"));
        }
      }
      node = node.parentElement;
    }
    for (const c of cands) {
      const w = redgifsWatchUrlFromAnyText(c);
      if (w) return w;
    }
    return "";
  }

  function mediaContextFromTarget(target) {
    const mediaEl = nearestMediaElementFromTarget(target);
    const mediaUrl = mediaEl ? mediaUrlFromElement(mediaEl) : "";
    if (mediaUrl && /^https?:\/\//i.test(mediaUrl)) return { el: mediaEl, url: mediaUrl };
    if (/(^|\.)redgifs\.com$/i.test(location.hostname || "")) {
      const redItem = bestRedgifsItemUrlFromTarget(target);
      if (redItem) return { el: mediaEl, url: redItem };
    }
    const linked = bestLinkUrlFromTarget(target);
    if (linked) {
      const red = redgifsWatchUrlFromHref(linked);
      if (red) return { el: mediaEl, url: red };
      if (/^https?:\/\//i.test(linked) && !/redgifs\.com\/users\//i.test(linked)) return { el: mediaEl, url: linked };
    }
    return { el: mediaEl || null, url: "" };
  }

  function mediaContextFromPoint(x, y, fallbackTarget) {
    const seen = new Set();
    const candidates = [];
    if (fallbackTarget) candidates.push(fallbackTarget);
    try {
      const stack = document.elementsFromPoint ? document.elementsFromPoint(x || 0, y || 0) : [];
      for (const el of stack || []) {
        if (!el || seen.has(el)) continue;
        seen.add(el);
        candidates.push(el);
      }
    } catch (_) {}
    for (const c of candidates) {
      const ctx = mediaContextFromTarget(c);
      if (ctx && ctx.url && /^https?:\/\//i.test(ctx.url)) return ctx;
    }
    return { el: null, url: "" };
  }

  function redgifsBestGuessUrlFromPoint(x, y) {
    const seen = new Set();
    const pull = (raw) => {
      const w = redgifsWatchUrlFromAnyText(raw || "");
      if (w) return w;
      const s = String(raw || "").trim();
      if (!s || !/^https?:\/\//i.test(s)) return "";
      if (/redgifs\.com\/users\//i.test(s)) return "";
      return s.split("#")[0];
    };
    try {
      const stack = document.elementsFromPoint ? document.elementsFromPoint(x || 0, y || 0) : [];
      for (const el of stack || []) {
        if (!el || seen.has(el)) continue;
        seen.add(el);
        let n = el;
        for (let d = 0; d < 8 && n; d++) {
          const attrs = [
            n.getAttribute && n.getAttribute("href"),
            n.getAttribute && n.getAttribute("src"),
            n.getAttribute && n.getAttribute("poster"),
            n.getAttribute && n.getAttribute("data-href"),
            n.getAttribute && n.getAttribute("data-url"),
            n.getAttribute && n.getAttribute("data-src"),
            n.getAttribute && n.getAttribute("data-gif-id"),
            n.getAttribute && n.getAttribute("data-id"),
            n.getAttribute && n.getAttribute("data-video-id"),
          ];
          for (const a of attrs) {
            const u = pull(a);
            if (u) return u;
          }
          n = n.parentElement;
        }
      }
    } catch (_) {}
    try {
      const vids = document.querySelectorAll("video");
      let best = "";
      let area = 0;
      for (const v of vids) {
        let r;
        try {
          r = v.getBoundingClientRect();
        } catch (_) {
          continue;
        }
        const a = Math.max(0, r.width) * Math.max(0, r.height);
        if (a < 64 * 64) continue;
        const src = v.currentSrc || v.src || "";
        const u = pull(src);
        if (u && a > area) {
          area = a;
          best = u;
        }
      }
      if (best) return best;
    } catch (_) {}
    try {
      const links = document.querySelectorAll("a[href*='/watch/'],a[href*='/ifr/'],a[href*='/gifs/']");
      for (const a of links) {
        const u = pull(a.href || "");
        if (u) return u;
      }
    } catch (_) {}
    return "";
  }

  function tryOpenTbccMenuFromEvent(e) {
    const rawUser = resolveContextUsername(e.target) || "";
    tbccLastContextUsername = rawUser;
    const acceptedUser = acceptedContextUsername(rawUser);
    if (!shouldUseCustomPageMenuForEvent(e)) return false;
    const x = e.clientX || 0;
    const y = e.clientY || 0;
    const ctx = mediaContextFromPoint(x, y, e.target);
    const mediaEl = ctx.el;
    let mediaUrl = ctx.url;
    let frameUrl = ctx.url;
    if (tbccIsRedgifsHost) {
      const redFull = redgifsBestGuessUrlFromPoint(x, y) || "";
      if (redFull && /^https?:\/\//i.test(redFull)) mediaUrl = redFull;
    }
    if (!mediaUrl || !/^https?:\/\//i.test(mediaUrl)) {
      if (!tbccIsRedgifsHost) return false;
      mediaUrl = String(location.href || "").split("#")[0];
    }
    e.preventDefault();
    e.stopPropagation();
    openPageMenu(x + 2, y + 2, mediaUrl, mediaEl, frameUrl, acceptedUser);
    return true;
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
    const { tbccOverlayMode, tbccPageMediaMenuEnabled, tbccPageMenuItems } = await storageLocalGet([
      "tbccOverlayMode",
      "tbccPageMediaMenuEnabled",
      STORAGE_PAGE_MENU_ITEMS,
    ]);
    overlayMode = !!tbccOverlayMode;
    pageMediaMenuEnabled = tbccIsRedgifsHost ? true : tbccPageMediaMenuEnabled !== false;
    pageMenuItems = {
      ...DEFAULT_PAGE_MENU_ITEMS,
      ...(tbccPageMenuItems && typeof tbccPageMenuItems === "object" ? tbccPageMenuItems : {}),
    };
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
    if (changes.tbccPageMediaMenuEnabled) {
      pageMediaMenuEnabled = tbccIsRedgifsHost ? true : changes.tbccPageMediaMenuEnabled.newValue !== false;
      if (!pageMediaMenuEnabled) closePageMenu();
    }
    if (changes[STORAGE_PAGE_MENU_ITEMS]) {
      const next = changes[STORAGE_PAGE_MENU_ITEMS].newValue;
      pageMenuItems = {
        ...DEFAULT_PAGE_MENU_ITEMS,
        ...(next && typeof next === "object" ? next : {}),
      };
      if (tbccPageMenu && !tbccPageMenu.hidden) populatePageMenu(tbccPageMenu);
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
    injectStyles();
    document.addEventListener("copy", () => {
      const selected = window.getSelection ? String(window.getSelection() || "").trim() : "";
      const picked = extractUsernameFromText(selected);
      if (picked) void storeLastCopiedUsername(picked);
    });
    window.addEventListener(
      "contextmenu",
      (e) => {
        tryOpenTbccMenuFromEvent(e);
      },
      true
    );
    document.addEventListener(
      "contextmenu",
      (e) => {
        tryOpenTbccMenuFromEvent(e);
      },
      true
    );
    window.addEventListener(
      "pointerdown",
      (e) => {
        if (!shouldUseCustomPageMenuForEvent(e)) {
          rightClickFallbackCtx = null;
          return;
        }
        if (e.button !== 2) return;
        const ctx = mediaContextFromPoint(e.clientX || 0, e.clientY || 0, e.target);
        if (!ctx || !ctx.url || !/^https?:\/\//i.test(ctx.url)) {
          rightClickFallbackCtx = null;
          return;
        }
        rightClickFallbackCtx = { x: e.clientX || 0, y: e.clientY || 0, ctx };
      },
      true
    );
    window.addEventListener(
      "mouseup",
      (e) => {
        if (!shouldUseCustomPageMenuForEvent(e)) return;
        if (e.button !== 2) return;
        if (!rightClickFallbackCtx) return;
        if (tbccPageMenu && !tbccPageMenu.hidden) return;
        const data = rightClickFallbackCtx;
        rightClickFallbackCtx = null;
        e.preventDefault();
        e.stopPropagation();
        const frameUrl = data && data.ctx ? data.ctx.url : "";
        let mediaUrl = frameUrl;
        if (tbccIsRedgifsHost) {
          const redFull = redgifsBestGuessUrlFromPoint(data.x || 0, data.y || 0) || "";
          if (redFull && /^https?:\/\//i.test(redFull)) mediaUrl = redFull;
        }
        if (!mediaUrl || !/^https?:\/\//i.test(mediaUrl)) mediaUrl = String(location.href || "").split("#")[0];
        const acceptedUser = acceptedContextUsername(tbccLastContextUsername || resolveContextUsername(data.ctx.el));
        openPageMenu(data.x + 2, data.y + 2, mediaUrl, data.ctx.el, frameUrl, acceptedUser);
      },
      true
    );
    document.addEventListener(
      "click",
      (e) => {
        if (!tbccPageMenu || tbccPageMenu.hidden) return;
        if (typeof e.button === "number" && e.button !== 0) return;
        if (Date.now() - tbccPageMenuOpenedAt < 250) return;
        if (tbccPageMenu.contains(e.target)) return;
        closePageMenu();
      },
      true
    );
    document.addEventListener(
      "keydown",
      (e) => {
        if (e.key === "Escape") closePageMenu();
      },
      true
    );
    void applyModeFromStorage().catch(() => tearDown());
  }
  boot();
  if (typeof tbccBindModuleDisableListener === "function") {
    tbccBindModuleDisableListener("page_overlay", function () {
      try {
        tearDown();
      } catch (_) {}
    });
  }
  /* Bootstrap macrosearch FAB on approved / builtin hosts (dynamic inject). */
  try {
    if (isExtensionContextAlive()) {
      chrome.runtime.sendMessage({ action: "tbcc-maybe-inject-username-search" }, function () {
        void chrome.runtime.lastError;
      });
    }
  } catch (_) {}
  });
})();
