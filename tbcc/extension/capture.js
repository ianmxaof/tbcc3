/**
 * TBCC content script: lists and fetches page media. Safe to re-inject (IIFE avoids redeclaration).
 */
(function () {
  if (typeof window.__tbccCaptureLoaded !== "undefined") return;
  window.__tbccCaptureLoaded = true;

  var API_BYTES = "http://localhost:8000/import/bytes";
  var API_SAVED_BATCH = "http://localhost:8000/import/saved-batch";
  var SAVED_ALBUM_CHUNK = 10;

  /**
   * Fetch bytes via background service worker (cookies + Referer rules).
   * Avoids CSP errors from inline MAIN-world script injection (e.g. erome.com blocks injectBridge).
   */
  function fetchOneInPage(url) {
    /** data: URLs (e.g. canvas export) only resolve in this document — background fetch cannot use them. */
    if (url && String(url).startsWith("data:")) {
      return fetch(url)
        .then(function (r) {
          return r.arrayBuffer();
        })
        .then(function (buffer) {
          return { buffer: buffer, url: url };
        })
        .catch(function (e) {
          return { error: String(e.message || e), url: url };
        });
    }
    return new Promise(function (resolve) {
      try {
        chrome.runtime.sendMessage({ action: "tbcc-content-fetch-bytes", url: url }, function (resp) {
          if (chrome.runtime.lastError) {
            resolve({ error: chrome.runtime.lastError.message, url: url });
            return;
          }
          if (!resp || !resp.ok) {
            resolve({ error: (resp && resp.error) || "Fetch failed", url: url });
            return;
          }
          resolve({ buffer: resp.buffer, url: url });
        });
      } catch (e) {
        resolve({ error: String(e.message || e), url: url });
      }
    });
  }

  function absUrl(u) {
    try {
      return new URL(u, document.baseURI || location.href).href;
    } catch (_) {
      return u || "";
    }
  }

  /** Walk DOM including open shadow roots (depth-first). */
  function walkElements(node, callback) {
    if (!node) return;
    if (node.nodeType === 1) {
      try {
        callback(node);
      } catch (_) {}
      if (node.shadowRoot) walkElements(node.shadowRoot, callback);
    }
    for (var c = node.firstElementChild; c; c = c.nextElementSibling) {
      walkElements(c, callback);
    }
  }

  function bestUrlFromSrcset(srcset) {
    if (!srcset || !String(srcset).trim()) return "";
    var parts = String(srcset)
      .split(",")
      .map(function (s) {
        return s.trim();
      })
      .filter(Boolean);
    var best = "";
    var bestScore = 0;
    parts.forEach(function (part) {
      var m = part.match(/^(\S+)\s+(\d+)w$/i);
      if (m) {
        var w = parseInt(m[2], 10);
        if (w > bestScore) {
          bestScore = w;
          best = m[1];
        }
        return;
      }
      var m2 = part.match(/^(\S+)\s+(\d+(?:\.\d+)?)x$/i);
      if (m2) {
        var x = parseFloat(m2[2]);
        var s = x * 10000;
        if (s > bestScore) {
          bestScore = s;
          best = m2[1];
        }
        return;
      }
      var first = part.split(/\s+/)[0];
      if (first && !best) best = first;
    });
    return best || "";
  }

  /** Prefer URLs that look like full-size; penalize common thumb/preview paths. */
  function scoreImageUrl(u) {
    if (!u || u.indexOf("data:") === 0) return -1000;
    var s = u.toLowerCase();
    var score = 0;
    if (s.indexOf("thumb") >= 0) score -= 35;
    if (s.indexOf("/small/") >= 0 || s.indexOf("_small") >= 0) score -= 30;
    if (s.indexOf("preview") >= 0 || s.indexOf("/mini/") >= 0) score -= 25;
    if (/_s\.(jpe?g|png|gif|webp)/i.test(s)) score -= 20;
    if (s.indexOf("avatar") >= 0 || s.indexOf("icon") >= 0) score -= 15;
    score += Math.min(s.length, 240) / 12;
    return score;
  }

  /** Heuristic URL variants (thumbs → full path segments). Safe no-ops when not applicable. */
  function heuristicUpgrade(u) {
    if (!u || u.indexOf("http") !== 0) return u;
    try {
      var x = u;
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
    var seen = {};
    var uniq = [];
    for (var i = 0; i < candidates.length; i++) {
      var u = candidates[i];
      if (!u || typeof u !== "string") continue;
      u = absUrl(u.trim());
      if (!u || seen[u]) continue;
      seen[u] = 1;
      uniq.push(u);
    }
    var extra = [];
    for (var j = 0; j < uniq.length; j++) {
      var h = heuristicUpgrade(uniq[j]);
      if (h && h !== uniq[j] && !seen[h]) {
        seen[h] = 1;
        extra.push(h);
      }
    }
    for (var k = 0; k < extra.length; k++) uniq.push(extra[k]);
    var best = "";
    var bestScore = -99999;
    for (var n = 0; n < uniq.length; n++) {
      var sc = scoreImageUrl(uniq[n]);
      if (sc > bestScore) {
        bestScore = sc;
        best = uniq[n];
      }
    }
    return best;
  }

  function pushImageCandidates(el, arr) {
    function push(u) {
      if (u && typeof u === "string") arr.push(u);
    }
    var ss = el.getAttribute("srcset") || el.getAttribute("data-srcset") || "";
    var fromSet = bestUrlFromSrcset(ss);
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
    ].forEach(function (attr) {
      push(el.getAttribute(attr));
    });
    var pic = el.closest && el.closest("picture");
    if (pic) {
      var sources = pic.querySelectorAll("source[srcset]");
      for (var s = 0; s < sources.length; s++) {
        var ss2 = sources[s].getAttribute("srcset") || "";
        push(bestUrlFromSrcset(ss2));
      }
    }
    var link = el.closest && el.closest("a[href]");
    if (link && link.href) {
      var href = link.href.split("#")[0];
      if (/\.(jpe?g|png|gif|webp|bmp)(\?|$)/i.test(href)) push(href);
    }
  }

  /** motherless.com: gallery thumbs link to /{id}; full image is on ?full (parsed server-side). */
  function isMotherlessHost() {
    try {
      return /(^|\.)motherless\.com$/i.test(location.hostname);
    } catch (_) {
      return false;
    }
  }

  var MOTHERLESS_RESERVED = {
    g: 1,
    images: 1,
    groups: 1,
    videos: 1,
    search: 1,
    members: 1,
    login: 1,
    register: 1,
    upload: 1,
    rules: 1,
    privacy: 1,
    dmca: 1,
    help: 1,
    faq: 1,
    about: 1,
    contact: 1,
    categories: 1,
    tags: 1,
    boards: 1,
    store: 1,
    chat: 1,
  };

  /**
   * Media id from any motherless path: /ITEM, /gallery/ITEM, /GI6FD29B3/0F72C29 → last segment.
   * Skips self-links to the current page (e.g. gallery root) and reserved paths.
   */
  function motherlessMediaIdFromHref(href) {
    try {
      var u = new URL(href, location.href);
      if (!/(^|\.)motherless\.com$/i.test(u.hostname)) return "";
      var parts = u.pathname.replace(/^\/+|\/+$/g, "").split("/").filter(Boolean);
      if (!parts.length) return "";
      var last = parts[parts.length - 1];
      if (!/^[A-Za-z0-9]{4,}$/.test(last)) return "";
      if (MOTHERLESS_RESERVED[last.toLowerCase()]) return "";
      var cur = new URL(location.href);
      var curParts = cur.pathname.replace(/^\/+|\/+$/g, "").split("/").filter(Boolean);
      if (parts.length === 1) {
        if (curParts.length === 1 && curParts[0].toLowerCase() === last.toLowerCase()) {
          if ((cur.search || "").toLowerCase().indexOf("full") !== -1) return "";
          return "";
        }
        return last;
      }
      return last;
    } catch (_) {
      return "";
    }
  }

  /**
   * Gallery grids often put <img> beside <a> (not inside). Walk up and find a link to a media id.
   */
  function findMotherlessMediaLink(el) {
    if (!isMotherlessHost() || !el) return null;
    var a = el.closest && el.closest("a[href]");
    if (a && motherlessMediaIdFromHref(a.href)) return a;
    var node = el.parentElement;
    for (var d = 0; d < 12 && node; d++) {
      var ch = node.children;
      for (var i = 0; i < ch.length; i++) {
        var c = ch[i];
        if (c.tagName === "A" && c.href && motherlessMediaIdFromHref(c.href)) return c;
        if (c.querySelector) {
          var inner = c.querySelector("a[href]");
          if (inner && inner.href && motherlessMediaIdFromHref(inner.href)) return inner;
        }
      }
      node = node.parentElement;
    }
    return null;
  }

  function motherlessDetailUrlIfEligible(el) {
    if (!isMotherlessHost() || !el) return "";
    var tag = el.tagName;
    if (tag !== "IMG" && tag !== "VIDEO") return "";
    var link = findMotherlessMediaLink(el);
    if (!link || !link.href) return "";
    var mediaId = motherlessMediaIdFromHref(link.href);
    if (!mediaId) return "";
    try {
      var cur = new URL(location.href);
      var curParts = cur.pathname.replace(/^\/+|\/+$/g, "").split("/").filter(Boolean);
      var curLast = curParts.length ? curParts[curParts.length - 1] : "";
      if (curLast.toLowerCase() === mediaId.toLowerCase() && (cur.search || "").toLowerCase().indexOf("full") !== -1) {
        return "";
      }
      return location.origin + "/" + mediaId + "?full";
    } catch (_) {
      return "";
    }
  }

  function getImageList() {
    var seen = new Set();
    var out = [];
    function add(url, width, height, tagName, naturalWidth, naturalHeight, extra) {
      if (!url) return;
      /** http(s) URLs only: skip absurdly long strings; data: URLs can be huge (canvas export). */
      if (!url.startsWith("data:") && url.length > 8000) return;
      /** Allow large data:image/* (e.g. canvas.toDataURL from generators like perchance.org). */
      if (url.startsWith("data:")) {
        var isImgData = /^data:image\/(png|jpe?g|webp|gif);/i.test(url);
        var maxLen = isImgData ? 15000000 : 50000;
        if (url.length > maxLen) return;
      }
      var key = url.slice(0, 200);
      if (seen.has(key)) return;
      seen.add(key);
      var type = (tagName || "").toLowerCase();
      if (type === "video") type = "video";
      else type = "image";
      var row = {
        url: url,
        width: width || 0,
        height: height || 0,
        tagName: tagName || "img",
        naturalWidth: naturalWidth || width || 0,
        naturalHeight: naturalHeight || height || 0,
        mediaType: type,
      };
      if (extra && extra.motherlessDetailUrl) row.motherlessDetailUrl = extra.motherlessDetailUrl;
      out.push(row);
    }
    function processImg(el) {
      var cands = [];
      pushImageCandidates(el, cands);
      var src = bestUrlFromCandidates(cands);
      if (!src) return;
      var extra = {};
      var md = motherlessDetailUrlIfEligible(el);
      if (md) extra.motherlessDetailUrl = md;
      add(absUrl(src), el.width, el.height, "img", el.naturalWidth, el.naturalHeight, extra);
    }
    /**
     * Many generators (e.g. perchance.org) paint to <canvas> with no <img> — export as JPEG data URL.
     * Tainted (cross-origin) canvases throw; skip those.
     */
    function processCanvas(el) {
      if (!el || el.tagName !== "CANVAS") return;
      var w = el.width || 0;
      var h = el.height || 0;
      if (w < 48 || h < 48) return;
      try {
        var cr = el.getBoundingClientRect();
        if (cr.width < 24 && cr.height < 24) return;
      } catch (_) {}
      try {
        var dataUrl = el.toDataURL("image/jpeg", 0.88);
        if (!dataUrl || dataUrl.length < 200) return;
        if (dataUrl.length > 14000000) {
          dataUrl = el.toDataURL("image/jpeg", 0.72);
        }
        add(dataUrl, w, h, "canvas", w, h, {});
      } catch (_) {}
    }
    function processVideo(el) {
      var src = el.currentSrc || el.src || (el.querySelector("source") && el.querySelector("source").src);
      if (!src) return;
      var extra = {};
      var md = motherlessDetailUrlIfEligible(el);
      if (md) extra.motherlessDetailUrl = md;
      add(absUrl(src), el.videoWidth || el.width, el.videoHeight || el.height, "video", 0, 0, extra);
    }
    walkElements(document.documentElement, function (el) {
      var t = el.tagName;
      if (t === "IMG") processImg(el);
      else if (t === "CANVAS") processCanvas(el);
      else if (t === "VIDEO") processVideo(el);
      else if (t === "SOURCE" && el.parentNode && el.parentNode.tagName === "PICTURE") {
        var src = (el.srcset && bestUrlFromSrcset(el.srcset)) || (el.srcset && el.srcset.split(/\s+/)[0]) || el.src;
        if (src) add(absUrl(src), 0, 0, "picture");
      } else if (el.hasAttribute && el.hasAttribute("data-src")) {
        var ds = el.getAttribute("data-src");
        if (ds && (el.tagName === "IMG" || /image|img|photo/i.test(el.className || "")))
          add(absUrl(ds), el.width, el.height, el.tagName);
      }
    });
    if (document.head) {
      var metas = document.head.querySelectorAll(
        'meta[property="og:image"], meta[property="og:image:url"], meta[name="twitter:image"], meta[name="twitter:image:src"]'
      );
      metas.forEach(function (m) {
        var c = m.getAttribute("content");
        if (c && c.length < 8000) add(absUrl(c.trim()), 0, 0, "meta");
      });
    }
    return out;
  }

  function blobMetaForUrl(url) {
    var u = url || "";
    var low = u.toLowerCase();
    if (low.startsWith("data:image/jpeg") || low.startsWith("data:image/jpg")) return { name: "media.jpg", type: "image/jpeg" };
    if (low.startsWith("data:image/png")) return { name: "media.png", type: "image/png" };
    if (low.startsWith("data:image/webp")) return { name: "media.webp", type: "image/webp" };
    if (low.startsWith("data:image/gif")) return { name: "media.gif", type: "image/gif" };
    var s = low.split("?")[0];
    if (/\.mp4($|\/)/i.test(s)) return { name: "media.mp4", type: "video/mp4" };
    if (/\.webm($|\/)/i.test(s)) return { name: "media.webm", type: "video/webm" };
    if (/\.mov($|\/)/i.test(s)) return { name: "media.mov", type: "video/quicktime" };
    if (/\.gif($|\/)/i.test(s)) return { name: "media.gif", type: "image/gif" };
    if (/\.png($|\/)/i.test(s)) return { name: "media.png", type: "image/png" };
    if (/\.webp($|\/)/i.test(s)) return { name: "media.webp", type: "image/webp" };
    if (/\.(jpg|jpeg)($|\/)/i.test(s)) return { name: "media.jpg", type: "image/jpeg" };
    return { name: "media.jpg", type: "application/octet-stream" };
  }

  function uploadBytes(buffer, poolId, savedOnly, source, mediaUrl, caption) {
    var meta = blobMetaForUrl(mediaUrl || "");
    var blob = new Blob([buffer], { type: meta.type });
    var form = new FormData();
    form.append("file", blob, meta.name);
    form.append("pool_id", String(poolId));
    form.append("saved_only", savedOnly ? "true" : "false");
    form.append("source", source || "extension:bytes");
    if (savedOnly && caption && String(caption).trim()) {
      form.append("caption", String(caption).trim());
    }
    return fetch(API_BYTES, { method: "POST", body: form })
      .then(function (r) { return r.text(); })
      .then(function (text) {
        var data = {};
        try { data = text ? JSON.parse(text) : {}; } catch (_) {}
        return data;
      });
  }

  function fetchAndUpload(urls, poolId, savedOnly, source, caption) {
    var cap = caption && String(caption).trim() ? String(caption).trim() : "";
    var results = { imported: 0, skipped: 0, errors: [], media_ids: [] };
    var total = urls.length;
    /** Saved Messages: batch POST /import/saved-batch so Telegram groups into albums (≤10). */
    if (savedOnly) {
      if (!urls.length) return Promise.resolve(results);
      var idx = 0;
      var pairs = [];
      function fetchAllForSaved() {
        if (idx >= urls.length) {
          if (!pairs.length) return Promise.resolve(results);
          var pos = 0;
          function uploadSavedChunks() {
            if (pos >= pairs.length) return Promise.resolve(results);
            var chunk = pairs.slice(pos, pos + SAVED_ALBUM_CHUNK);
            pos += SAVED_ALBUM_CHUNK;
            var form = new FormData();
            chunk.forEach(function (p) {
              var meta = blobMetaForUrl(p.url || "");
              var blob = new Blob([p.buffer], { type: meta.type });
              form.append("files", blob, meta.name);
            });
            if (cap) form.append("caption", cap);
            return fetch(API_SAVED_BATCH, { method: "POST", body: form })
              .then(function (r) {
                return r.text();
              })
              .then(function (text) {
                var data = {};
                try {
                  data = text ? JSON.parse(text) : {};
                } catch (_) {}
                if (data.status === "saved_only" && !data.error) {
                  results.skipped += chunk.length;
                } else {
                  results.errors.push({ error: data.error || "saved-batch failed" });
                }
                try {
                  chrome.runtime.sendMessage({ type: "tbcc-progress", index: pos, total: pairs.length });
                } catch (_) {}
                return uploadSavedChunks();
              });
          }
          return uploadSavedChunks();
        }
        var url = urls[idx];
        idx++;
        return fetchOneInPage(url).then(function (one) {
          if (one.error) {
            results.errors.push({ url: (url || "").slice(0, 80), error: one.error });
            return fetchAllForSaved();
          }
          pairs.push({ buffer: one.buffer, url: url });
          return fetchAllForSaved();
        });
      }
      return fetchAllForSaved();
    }
    var i = 0;
    function next() {
      if (i >= urls.length) return Promise.resolve(results);
      var url = urls[i];
      i++;
      return fetchOneInPage(url)
        .then(function (one) {
          if (one.error) {
            results.errors.push({ url: url.slice(0, 80), error: one.error });
            try { chrome.runtime.sendMessage({ type: "tbcc-progress", index: i, total: total, error: one.error }); } catch (_) {}
            return next();
          }
          return uploadBytes(one.buffer, poolId, savedOnly, source, url, cap).then(function (data) {
            if (data.status === "imported" && data.media_id) {
              results.imported += 1;
              results.media_ids.push(data.media_id);
            } else results.skipped += 1;
            try { chrome.runtime.sendMessage({ type: "tbcc-progress", index: i, total: total, mediaId: data.media_id }); } catch (_) {}
            return next();
          });
        })
        .catch(function (e) {
          results.errors.push({ url: url.slice(0, 80), error: String(e.message || e) });
          try { chrome.runtime.sendMessage({ type: "tbcc-progress", index: i, total: total, error: String(e.message || e) }); } catch (_) {}
          return next();
        });
    }
    return next();
  }

  /** Exposed for programmatic inject (side panel); avoids relying on runtime.sendMessage reaching this script. */
  window.__tbccGetImageList = getImageList;
  window.__tbccFetchAndUpload = fetchAndUpload;

  chrome.runtime.onMessage.addListener(function (msg, _sender, sendResponse) {
    if (msg.action === "tbcc-getImageList") {
      try {
        sendResponse({ list: getImageList() });
      } catch (e) {
        sendResponse({ error: String(e.message || e) });
      }
      return true;
    }
    if (msg.action === "tbcc-fetchAndUpload") {
      var urls = msg.urls || [];
      var poolId = msg.poolId != null ? msg.poolId : 1;
      var savedOnly = !!msg.savedOnly;
      var source = msg.source || "extension:bytes";
      fetchAndUpload(urls, poolId, savedOnly, source, msg.caption || "")
        .then(function (r) { sendResponse(r); })
        .catch(function (e) {
          sendResponse({ error: String(e.message || e), imported: 0, skipped: 0, errors: [] });
        });
      return true;
    }
  });
})();
