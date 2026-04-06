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
    /**
     * blob: URLs are scoped to this document — the service worker cannot fetch them.
     * Many players assign MediaRecorder or stream output as blob URLs for <video>.
     */
    if (url && String(url).startsWith("blob:")) {
      return fetch(url)
        .then(function (r) {
          return r.blob();
        })
        .then(function (blob) {
          return blob.arrayBuffer().then(function (buffer) {
            return { buffer: buffer, url: url, blobMime: blob.type || "" };
          });
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

  /** True if URL path looks like a direct image file (not an HTML page). */
  function isDirectHttpImageUrl(url) {
    try {
      var p = new URL(url, location.href).pathname.toLowerCase();
      return /\.(jpe?g|png|gif|webp|bmp|avif)(\?|$)/i.test(p);
    } catch (_) {
      return false;
    }
  }

  /**
   * Find a same-origin link to a detail page near the thumb (wrapper or sibling, like motherless grids).
   */
  function findGenericGalleryLink(el) {
    var a = el.closest && el.closest("a[href]");
    if (a && a.href) {
      try {
        var u0 = new URL(a.href, location.href);
        if (
          (u0.protocol === "http:" || u0.protocol === "https:") &&
          !isDirectHttpImageUrl(a.href) &&
          u0.origin === new URL(location.href).origin
        )
          return a;
      } catch (_) {}
    }
    var node = el.parentElement;
    for (var d = 0; d < 12 && node; d++) {
      var ch = node.children;
      for (var i = 0; i < ch.length; i++) {
        var c = ch[i];
        if (c.tagName === "A" && c.href) {
          try {
            var u = new URL(c.href, location.href);
            if (
              (u.protocol === "http:" || u.protocol === "https:") &&
              !isDirectHttpImageUrl(c.href) &&
              u.origin === new URL(location.href).origin
            )
              return c;
          } catch (_) {}
        }
        if (c.querySelector) {
          var inner = c.querySelector("a[href]");
          if (inner && inner.href) {
            try {
              var u2 = new URL(inner.href, location.href);
              if (
                (u2.protocol === "http:" || u2.protocol === "https:") &&
                !isDirectHttpImageUrl(inner.href) &&
                u2.origin === new URL(location.href).origin
              )
                return inner;
            } catch (_) {}
          }
        }
      }
      node = node.parentElement;
    }
    return null;
  }

  /**
   * Same-origin gallery: thumb links to a detail HTML page → background fetch reads og:image / main image.
   * Skips motherless (handled separately) and links that already point to a raw image file.
   */
  /** coomer.st / kemono.party: SPA — no og:image in fetched HTML; resolver uses /api/v1 JSON instead. */
  function isCoomerLikeHost() {
    try {
      var h = location.hostname.toLowerCase();
      return /(^|\.)coomer\.(st|party)$/.test(h) || /(^|\.)kemono\.(party|su|si)$/.test(h);
    } catch (_) {
      return false;
    }
  }

  function coomerPostUrlFromHref(href) {
    try {
      var u = new URL(href, location.href);
      var hn = u.hostname.toLowerCase();
      if (!/(^|\.)coomer\.(st|party)$/.test(hn) && !/(^|\.)kemono\.(party|su|si)$/.test(hn)) return "";
      var path = (u.pathname || "").replace(/\/+$/, "");
      if (!/\/[^/]+\/user\/[^/]+\/post\/\d+$/.test(path)) return "";
      return u.origin + path;
    } catch (_) {
      return "";
    }
  }

  function findCoomerPostLink(el) {
    if (!isCoomerLikeHost() || !el) return null;
    var a = el.closest && el.closest("a[href]");
    if (a && coomerPostUrlFromHref(a.href)) return a;
    var node = el.parentElement;
    for (var d = 0; d < 14 && node; d++) {
      var ch = node.children;
      for (var i = 0; i < ch.length; i++) {
        var c = ch[i];
        if (c.tagName === "A" && c.href && coomerPostUrlFromHref(c.href)) return c;
        if (c.querySelector) {
          var inner = c.querySelector("a[href]");
          if (inner && inner.href && coomerPostUrlFromHref(inner.href)) return inner;
        }
      }
      node = node.parentElement;
    }
    return null;
  }

  function coomerPostDetailUrlIfEligible(el) {
    if (!isCoomerLikeHost() || !el) return "";
    var tag = el.tagName;
    if (tag !== "IMG" && tag !== "VIDEO") return "";
    var link = findCoomerPostLink(el);
    if (link && link.href) {
      var fromA = coomerPostUrlFromHref(link.href);
      if (fromA) return fromA;
    }
    return coomerPostUrlFromHref(location.href);
  }

  function genericDetailPageUrlIfEligible(el) {
    if (!el || el.tagName !== "IMG") return "";
    if (isMotherlessHost()) return "";
    if (isCoomerLikeHost()) return "";
    var link = findGenericGalleryLink(el);
    if (!link || !link.href) return "";
    try {
      var u = new URL(link.href, location.href);
      if (u.protocol !== "http:" && u.protocol !== "https:") return "";
      var cur = new URL(location.href);
      if (u.origin !== cur.origin) return "";
      if (u.href.split("#")[0] === cur.href.split("#")[0]) return "";
      if (isDirectHttpImageUrl(u.href)) return "";
      var path = u.pathname || "";
      if (path.length < 2) return "";
      return u.href.split("#")[0];
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
      if (extra && extra.coomerPostUrl) row.coomerPostUrl = extra.coomerPostUrl;
      if (extra && extra.detailPageUrl) row.detailPageUrl = extra.detailPageUrl;
      if (extra && extra.durationSec != null && typeof extra.durationSec === "number" && isFinite(extra.durationSec) && extra.durationSec > 0)
        row.durationSec = extra.durationSec;
      if (extra && extra.tbccCaptureSource) row.tbccCaptureSource = extra.tbccCaptureSource;
      if (extra && extra.tbccStreamManifest) row.tbccStreamManifest = true;
      out.push(row);
    }
    function tbccParseIso8601Duration(s) {
      if (!s || typeof s !== "string") return null;
      var m = /^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?$/i.exec(s.trim());
      if (!m) return null;
      var h = parseInt(m[1] || "0", 10) || 0;
      var mi = parseInt(m[2] || "0", 10) || 0;
      var se = parseFloat(m[3] || "0") || 0;
      return h * 3600 + mi * 60 + se;
    }
    function walkForVideoObject(obj, acc) {
      if (!obj || typeof obj !== "object") return;
      if (Array.isArray(obj)) {
        for (var i = 0; i < obj.length; i++) walkForVideoObject(obj[i], acc);
        return;
      }
      var t = obj["@type"];
      var types = Array.isArray(t) ? t : t ? [t] : [];
      var isVo = types.some(function (x) {
        return String(x).toLowerCase() === "videoobject";
      });
      if (isVo) acc.push(obj);
      for (var k in obj) {
        if (Object.prototype.hasOwnProperty.call(obj, k)) walkForVideoObject(obj[k], acc);
      }
    }
    function collectJsonLdVideoObjects() {
      var acc = [];
      var scripts = document.querySelectorAll('script[type="application/ld+json"]');
      for (var si = 0; si < scripts.length; si++) {
        var txt = scripts[si].textContent;
        if (!txt || !String(txt).trim()) continue;
        try {
          walkForVideoObject(JSON.parse(txt), acc);
        } catch (_) {}
      }
      return acc;
    }
    function pushUrlsFromVideoObject(vo, list) {
      var u = vo.contentUrl;
      if (typeof u === "string" && u.trim()) list.push(u.trim());
      else if (Array.isArray(u))
        u.forEach(function (x) {
          if (typeof x === "string" && x.trim()) list.push(x.trim());
        });
    }
    var jsonLdVos = collectJsonLdVideoObjects();
    for (var j = 0; j < jsonLdVos.length; j++) {
      var vo = jsonLdVos[j];
      var urlList = [];
      pushUrlsFromVideoObject(vo, urlList);
      var dIso = vo.duration;
      var dSec = typeof dIso === "string" ? tbccParseIso8601Duration(dIso) : null;
      var extraLd = {};
      if (dSec != null && isFinite(dSec) && dSec > 0) extraLd.durationSec = dSec;
      for (var ui = 0; ui < urlList.length; ui++) {
        var rawU = urlList[ui];
        if (!/^https?:\/\//i.test(rawU)) continue;
        var au = absUrl(rawU);
        if (typeof tbccIsLikelyHtmlPageUrl === "function" && tbccIsLikelyHtmlPageUrl(au, location.href)) continue;
        add(au, 0, 0, "video", 0, 0, extraLd);
      }
    }
    function processImg(el) {
      var cands = [];
      pushImageCandidates(el, cands);
      var src = bestUrlFromCandidates(cands);
      if (!src) return;
      var extra = {};
      var cp = coomerPostDetailUrlIfEligible(el);
      if (cp) extra.coomerPostUrl = cp;
      else {
        var md = motherlessDetailUrlIfEligible(el);
        if (md) extra.motherlessDetailUrl = md;
        else {
          var gdu = genericDetailPageUrlIfEligible(el);
          if (gdu) extra.detailPageUrl = gdu;
        }
      }
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
      var candidates = [];
      try {
        if (el.currentSrc) candidates.push(el.currentSrc);
        if (el.src) candidates.push(el.src);
        var dataAttrs = [
          "data-src",
          "data-mp4",
          "data-video",
          "data-video-src",
          "data-video-url",
          "data-url",
          "data-file",
          "data-original",
          "data-hls",
        ];
        for (var di = 0; di < dataAttrs.length; di++) {
          var dv = el.getAttribute && el.getAttribute(dataAttrs[di]);
          if (dv && String(dv).trim()) candidates.push(String(dv).trim());
        }
        var sources = el.querySelectorAll && el.querySelectorAll("source[src], source[srcset]");
        if (sources) {
          for (var si = 0; si < sources.length; si++) {
            var snode = sources[si];
            var su = snode.getAttribute("src");
            if (su) candidates.push(su);
            var sset = snode.getAttribute("srcset");
            if (sset) {
              var b = bestUrlFromSrcset(sset);
              if (b) candidates.push(b);
            }
          }
        }
      } catch (_) {}
      var seen = {};
      var best = "";
      for (var ci = 0; ci < candidates.length; ci++) {
        var c = candidates[ci];
        if (!c || seen[c]) continue;
        seen[c] = 1;
        if (!best) best = c;
        var low = c.toLowerCase().split("?")[0];
        if (/\.(mp4|m4v)(\?|$)/i.test(low)) {
          best = c;
          break;
        }
        if (/\.(webm|mov|mkv)(\?|$)/i.test(low) && !/\.(mp4|m4v)(\?|$)/i.test(String(best).toLowerCase())) best = c;
      }
      if (!best) return;
      var absBest = absUrl(best);
      if (typeof tbccIsLikelyHtmlPageUrl === "function" && tbccIsLikelyHtmlPageUrl(absBest, location.href)) return;
      var extra = {};
      var cpv = coomerPostDetailUrlIfEligible(el);
      if (cpv) extra.coomerPostUrl = cpv;
      else {
        var mdv = motherlessDetailUrlIfEligible(el);
        if (mdv) extra.motherlessDetailUrl = mdv;
      }
      try {
        var dur = el.duration;
        if (typeof dur === "number" && isFinite(dur) && dur > 0) extra.durationSec = dur;
      } catch (_) {}
      add(absBest, el.videoWidth || el.width, el.videoHeight || el.height, "video", 0, 0, extra);
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
      var vmetas = document.head.querySelectorAll(
        'meta[property="og:video:url"], meta[property="og:video:secure_url"], meta[property="og:video"], meta[name="twitter:player:stream"]'
      );
      vmetas.forEach(function (m) {
        var c = m.getAttribute("content");
        if (!c || c.length >= 8000 || !/^https?:\/\//i.test(c.trim())) return;
        var au = absUrl(c.trim());
        if (typeof tbccIsLikelyHtmlPageUrl === "function" && tbccIsLikelyHtmlPageUrl(au, location.href)) return;
        add(au, 0, 0, "video");
      });
    }
    /**
     * Same URLs DevTools Network shows for media requests: performance.getEntriesByType("resource").
     * Picks up CDN files like full-d.mp4 when the player loaded them even if <video> src was opaque.
     */
    function scoreResourceTimingVideoUrl(u) {
      var s = (u || "").toLowerCase();
      var sc = 0;
      if (s.indexOf("full-d") >= 0) sc += 100;
      if (/[\/._-]full[._-]/i.test(s) || /\/full\//i.test(s)) sc += 55;
      if (s.indexOf("2160") >= 0 || s.indexOf("4k") >= 0) sc += 45;
      if (s.indexOf("1080") >= 0) sc += 35;
      if (s.indexOf("720") >= 0) sc += 18;
      if (s.indexOf("thumbnail-hq") >= 0) sc -= 8;
      if (s.indexOf("thumb") >= 0 || s.indexOf("thumbnail") >= 0) sc -= 38;
      if (s.indexOf("preview") >= 0 || s.indexOf("teaser") >= 0) sc -= 28;
      if (s.indexOf("sample") >= 0) sc -= 15;
      return sc;
    }
    function mergeResourceTimingVideos() {
      try {
        if (typeof performance === "undefined" || !performance.getEntriesByType) return;
        var entries = performance.getEntriesByType("resource");
        var uniq = {};
        var list = [];
        for (var i = 0; i < entries.length; i++) {
          var name = (entries[i] && entries[i].name) || "";
          if (!name || name.indexOf("http") !== 0) continue;
          var pathOnly = name.split("?")[0].toLowerCase();
          if (!/\.(mp4|webm|m4v|mov|mkv)(\?|$)/i.test(pathOnly)) continue;
          if (uniq[name]) continue;
          uniq[name] = 1;
          list.push(name);
        }
        list.sort(function (a, b) {
          return scoreResourceTimingVideoUrl(b) - scoreResourceTimingVideoUrl(a);
        });
        var max = 28;
        for (var j = 0; j < list.length && j < max; j++) {
          var au = absUrl(list[j]);
          if (typeof tbccIsLikelyHtmlPageUrl === "function" && tbccIsLikelyHtmlPageUrl(au, location.href)) continue;
          add(au, 0, 0, "video", 0, 0, { tbccCaptureSource: "resource-timing" });
        }
      } catch (_) {}
    }
    /** OnlyFans often serves HLS/DASH; list manifests for discovery (full transmux needs ffmpeg elsewhere). */
    function mergeOnlyfansStreamManifests() {
      try {
        if (typeof performance === "undefined" || !performance.getEntriesByType) return;
        var h = (location.hostname || "").toLowerCase();
        if (h !== "onlyfans.com" && !h.endsWith(".onlyfans.com")) return;
        var entries = performance.getEntriesByType("resource");
        var seen = {};
        for (var i = 0; i < entries.length; i++) {
          var name = (entries[i] && entries[i].name) || "";
          if (!name || name.indexOf("http") !== 0) continue;
          var pathOnly = name.split("?")[0].toLowerCase();
          if (!/\.(m3u8|mpd)(\?|$)/i.test(pathOnly)) continue;
          if (seen[name]) continue;
          seen[name] = 1;
          var au = absUrl(name);
          if (typeof tbccIsLikelyHtmlPageUrl === "function" && tbccIsLikelyHtmlPageUrl(au, location.href)) continue;
          add(au, 0, 0, "video", 0, 0, {
            tbccCaptureSource: "resource-timing",
            tbccStreamManifest: true,
          });
        }
      } catch (_) {}
    }
    /**
     * OnlyFans /media: <img> may be a smaller variant; resource timing lists CDN URLs actually loaded.
     * Sort so paths hinting at full/original rank above obvious thumbs.
     */
    function scoreResourceTimingImageUrl(u) {
      var s = (u || "").toLowerCase();
      var sc = 0;
      if (s.indexOf("2160") >= 0 || s.indexOf("4k") >= 0) sc += 45;
      if (s.indexOf("1080") >= 0) sc += 35;
      if (s.indexOf("720") >= 0) sc += 18;
      if (/\/full\//i.test(s) || /[\/._-]full[._-]/i.test(s)) sc += 55;
      if (s.indexOf("original") >= 0) sc += 40;
      if (s.indexOf("thumb") >= 0 || s.indexOf("thumbnail") >= 0) sc -= 38;
      if (s.indexOf("avatar") >= 0) sc -= 50;
      if (s.indexOf("preview") >= 0) sc -= 28;
      if (s.indexOf("profile-photos") >= 0) sc -= 22;
      if (s.indexOf("icon") >= 0) sc -= 40;
      return sc;
    }
    function mergeOnlyfansResourceTimingImages() {
      try {
        if (typeof performance === "undefined" || !performance.getEntriesByType) return;
        var h2 = (location.hostname || "").toLowerCase();
        if (h2 !== "onlyfans.com" && !h2.endsWith(".onlyfans.com")) return;
        var entries2 = performance.getEntriesByType("resource");
        var uniq2 = {};
        var list2 = [];
        for (var ii = 0; ii < entries2.length; ii++) {
          var name2 = (entries2[ii] && entries2[ii].name) || "";
          if (!name2 || name2.indexOf("http") !== 0) continue;
          var pathOnly2 = name2.split("?")[0].toLowerCase();
          if (!/\.(jpe?g|png|gif|webp|avif)(\?|$)/i.test(pathOnly2)) continue;
          var low2 = name2.toLowerCase();
          if (low2.indexOf("avatar") >= 0 || low2.indexOf("/icon") >= 0 || low2.indexOf("emoji") >= 0 || low2.indexOf("favicon") >= 0)
            continue;
          if (uniq2[name2]) continue;
          uniq2[name2] = 1;
          list2.push(name2);
        }
        list2.sort(function (a, b) {
          return scoreResourceTimingImageUrl(b) - scoreResourceTimingImageUrl(a);
        });
        var maxImg = 96;
        for (var jj = 0; jj < list2.length && jj < maxImg; jj++) {
          var au2 = absUrl(list2[jj]);
          if (typeof tbccIsLikelyHtmlPageUrl === "function" && tbccIsLikelyHtmlPageUrl(au2, location.href)) continue;
          add(au2, 0, 0, "img", 0, 0, { tbccCaptureSource: "resource-timing" });
        }
      } catch (_) {}
    }
    mergeResourceTimingVideos();
    mergeOnlyfansStreamManifests();
    mergeOnlyfansResourceTimingImages();
    return out;
  }

  function blobMetaForUrl(url, blobMime) {
    if (blobMime && String(blobMime).indexOf("/") > 0) {
      var bm = String(blobMime).toLowerCase();
      if (bm.indexOf("video") >= 0) {
        if (bm.indexOf("webm") >= 0) return { name: "media.webm", type: blobMime };
        if (bm.indexOf("quicktime") >= 0 || bm.indexOf("mov") >= 0) return { name: "media.mov", type: blobMime };
        return { name: "media.mp4", type: blobMime };
      }
      if (bm.indexOf("image/") === 0) {
        if (bm.indexOf("png") >= 0) return { name: "media.png", type: blobMime };
        if (bm.indexOf("gif") >= 0) return { name: "media.gif", type: blobMime };
        if (bm.indexOf("webp") >= 0) return { name: "media.webp", type: blobMime };
        return { name: "media.jpg", type: blobMime };
      }
    }
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
    if (/\.m4v($|\/)/i.test(s)) return { name: "media.m4v", type: "video/x-m4v" };
    if (/\.mkv($|\/)/i.test(s)) return { name: "media.mkv", type: "video/x-matroska" };
    if (/\.m3u8($|\/)/i.test(s)) return { name: "playlist.m3u8", type: "application/vnd.apple.mpegurl" };
    if (/\.mpd($|\/)/i.test(s)) return { name: "manifest.mpd", type: "application/dash+xml" };
    if (/\.gif($|\/)/i.test(s)) return { name: "media.gif", type: "image/gif" };
    if (/\.png($|\/)/i.test(s)) return { name: "media.png", type: "image/png" };
    if (/\.webp($|\/)/i.test(s)) return { name: "media.webp", type: "image/webp" };
    if (/\.(jpg|jpeg)($|\/)/i.test(s)) return { name: "media.jpg", type: "image/jpeg" };
    return { name: "media.jpg", type: "application/octet-stream" };
  }

  function uploadBytes(buffer, poolId, savedOnly, source, mediaUrl, caption, blobMime) {
    var meta = blobMetaForUrl(mediaUrl || "", blobMime);
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
              var meta = blobMetaForUrl(p.url || "", p.blobMime);
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
          pairs.push({ buffer: one.buffer, url: url, blobMime: one.blobMime });
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
          return uploadBytes(one.buffer, poolId, savedOnly, source, url, cap, one.blobMime).then(function (data) {
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
