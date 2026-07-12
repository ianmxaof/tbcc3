/**
 * TBCC OnlyFans harvest (ISOLATED world).
 *
 * Companion to of-api-hook.js. The hook lives in the page's main JS world
 * and clones every /api2/v2/... JSON response, posting it to this file via
 * window.postMessage. Here we walk those JSON trees, pluck the source-quality
 * media URLs (the on-page <img> elements only carry 300×300 thumbnails — full
 * resolution lives only in API responses), and keep them in a deduped bag.
 *
 * The sidebar drives this via two runtime messages:
 *   - tbcc-of-harvest-snapshot   → return current bag as a list
 *   - tbcc-of-harvest-autoscroll → scroll the SPA until pagination exhausted,
 *                                  then return the bag
 *
 * This is a separate file (not part of capture.js) so it has its own load
 * guard. capture.js is sometimes already injected with stale code from prior
 * sessions; its top-of-file `__tbccCaptureLoaded` short-circuits new code.
 * A standalone file with a dedicated guard avoids that whole class of bug.
 */
(function () {
  if (typeof tbccWaitForModule !== "function") return;
  tbccWaitForModule("onlyfans_harvest", function () {
  if (window.__tbccOfHarvestLoaded) return;
  window.__tbccOfHarvestLoaded = true;

  function isOnlyfansLoc() {
    try {
      var h = (location.hostname || "").toLowerCase();
      return h === "onlyfans.com" || h.endsWith(".onlyfans.com");
    } catch (_) {
      return false;
    }
  }

  if (!isOnlyfansLoc()) return;

  var bag = (window.__tbccOfHarvestBag = window.__tbccOfHarvestBag || {});
  var meta = (window.__tbccOfHarvestMeta = window.__tbccOfHarvestMeta || {
    hookSeen: 0,
    apiResponses: 0,
    lastApiAt: 0,
    apiUrlSamples: [],
  });

  function isHttpUrl(u) {
    return typeof u === "string" && /^https?:\/\//i.test(u);
  }

  function urlKey(u) {
    try {
      var x = new URL(u);
      return (x.hostname + x.pathname).toLowerCase();
    } catch (_) {
      return String(u || "").toLowerCase();
    }
  }

  function pickBestImageUrl(files) {
    if (!files || typeof files !== "object") return null;
    var candidates = [];
    var keys = ["full", "source", "view", "preview", "thumb", "squarePreview"];
    for (var i = 0; i < keys.length; i++) {
      var k = keys[i];
      var node = files[k];
      if (node && isHttpUrl(node.url)) {
        candidates.push({
          url: node.url,
          w: Number(node.width || 0) || 0,
          h: Number(node.height || 0) || 0,
          key: k,
        });
      }
    }
    if (!candidates.length) return null;
    candidates.sort(function (a, b) {
      var aw = a.w * a.h || (a.key === "full" || a.key === "source" ? 9e8 : 0);
      var bw = b.w * b.h || (b.key === "full" || b.key === "source" ? 9e8 : 0);
      return bw - aw;
    });
    return candidates[0];
  }

  function pickBestVideoUrl(media) {
    if (!media || typeof media !== "object") return null;
    var files = media.files || {};
    var sources = [];
    if (Array.isArray(media.videoSources)) sources = sources.concat(media.videoSources);
    if (files.full && isHttpUrl(files.full.url)) sources.push({ url: files.full.url, size: "full" });
    if (files.source && isHttpUrl(files.source.url)) sources.push({ url: files.source.url, size: "source" });
    if (files.video && isHttpUrl(files.video.url)) sources.push({ url: files.video.url, size: "video" });
    function rank(s) {
      var label = String(s.size || s.label || "").toLowerCase();
      if (label.indexOf("source") >= 0 || label.indexOf("original") >= 0 || label === "full") return 9000;
      var n = parseInt(label.replace(/[^0-9]/g, ""), 10);
      return Number.isFinite(n) ? n : 0;
    }
    sources.sort(function (a, b) { return rank(b) - rank(a); });
    var best = sources.find(function (s) { return isHttpUrl(s.url); });
    return best ? { url: best.url } : null;
  }

  function pickPosterUrl(files) {
    if (!files || typeof files !== "object") return null;
    var keys = ["preview", "squarePreview", "thumb", "manifest"];
    for (var i = 0; i < keys.length; i++) {
      var node = files[keys[i]];
      if (node && isHttpUrl(node.url)) return node.url;
    }
    return null;
  }

  function consumeMediaNode(node, post) {
    if (!node || typeof node !== "object" || Array.isArray(node)) return;
    var typeRaw = String(node.type || "").toLowerCase();
    var hasFiles = node.files && typeof node.files === "object";
    var hasVideoSources = Array.isArray(node.videoSources) && node.videoSources.length;
    if (!hasFiles && !hasVideoSources) return;

    var mediaId = node.id != null ? String(node.id) : null;
    var item;

    if (typeRaw === "video" || typeRaw === "gif" || hasVideoSources) {
      var v = pickBestVideoUrl(node);
      if (!v) return;
      item = {
        mediaType: "video",
        url: v.url,
        thumbUrl: pickPosterUrl(node.files),
        posterUrl: pickPosterUrl(node.files),
        width: Number((node.files && node.files.source && node.files.source.width) || node.width || 0) || 0,
        height: Number((node.files && node.files.source && node.files.source.height) || node.height || 0) || 0,
      };
    } else {
      var img = pickBestImageUrl(node.files);
      if (!img) return;
      item = {
        mediaType: "image",
        url: img.url,
        thumbUrl: pickPosterUrl(node.files) || img.url,
        width: img.w,
        height: img.h,
      };
    }

    if (!isHttpUrl(item.url)) return;

    var key = mediaId || urlKey(item.url);
    var existing = bag[key];
    if (existing && existing.url === item.url) return;
    if (existing) {
      existing.thumbUrl = existing.thumbUrl || item.thumbUrl;
      existing.posterUrl = existing.posterUrl || item.posterUrl;
      if (item.width > (existing.width || 0)) existing.width = item.width;
      if (item.height > (existing.height || 0)) existing.height = item.height;
      var prefersNew =
        (item.url || "").indexOf("source") >= 0 ||
        (item.mediaType === "video" && existing.mediaType === "image");
      if (prefersNew) {
        existing.url = item.url;
        existing.mediaType = item.mediaType;
      }
      return;
    }

    item.tbccOfMediaId = mediaId || "";
    item.tbccOfPostId = post && post.id != null ? String(post.id) : "";
    item.tbccCaptureSource = "of-api";
    bag[key] = item;
  }

  function harvestFromJson(json) {
    if (!json) return;
    var stack = [{ node: json, parent: null }];
    var visited = 0;
    while (stack.length && visited < 8000) {
      var entry = stack.pop();
      var node = entry.node;
      visited++;
      if (!node || typeof node !== "object") continue;
      if (Array.isArray(node)) {
        for (var i = 0; i < node.length; i++) stack.push({ node: node[i], parent: entry.parent });
        continue;
      }
      if (node.files || Array.isArray(node.videoSources)) {
        consumeMediaNode(node, entry.parent);
      }
      for (var k in node) {
        if (!Object.prototype.hasOwnProperty.call(node, k)) continue;
        var v = node[k];
        if (v && typeof v === "object") {
          stack.push({ node: v, parent: node.id != null ? node : entry.parent });
        }
      }
    }
  }

  window.addEventListener("message", function (ev) {
    try {
      if (ev.source !== window) return;
      var d = ev.data;
      if (!d || d.tbccOfHook !== true || !d.payload) return;
      meta.hookSeen++;
      meta.apiResponses++;
      meta.lastApiAt = Date.now();
      try {
        var u = String(d.payload.url || "");
        if (u && meta.apiUrlSamples.length < 12) meta.apiUrlSamples.push(u.slice(0, 200));
      } catch (_) {}
      harvestFromJson(d.payload.json);
    } catch (_) {}
  }, false);

  /**
   * Auto-scroll the SPA until bag size is stable for `idleTicks` consecutive
   * intervals or `hardCapMs` elapses.
   */
  window.__tbccOfHarvestAutoscroll = function (opts) {
    opts = opts || {};
    var tickMs = Number(opts.tickMs) > 0 ? Number(opts.tickMs) : 800;
    var idleTicks = Number(opts.idleTicks) > 0 ? Number(opts.idleTicks) : 7;
    var hardCapMs = Number(opts.hardCapMs) > 0 ? Number(opts.hardCapMs) : 240000;

    return new Promise(function (resolve) {
      var started = Date.now();
      var lastSize = Object.keys(bag).length;
      var idle = 0;
      var prevScrollTop = -1;
      var stuckScrollTicks = 0;

      function step() {
        if (Date.now() - started >= hardCapMs || idle >= idleTicks) {
          resolve({
            ok: true,
            size: Object.keys(bag).length,
            elapsedMs: Date.now() - started,
            meta: {
              hookSeen: meta.hookSeen,
              apiResponses: meta.apiResponses,
              lastApiAt: meta.lastApiAt,
              apiUrlSamples: meta.apiUrlSamples.slice(0, 12),
            },
          });
          return;
        }

        try {
          var doc = document.scrollingElement || document.documentElement;
          var scrollTop = doc.scrollTop || 0;
          var maxScroll = doc.scrollHeight - doc.clientHeight;
          if (scrollTop >= maxScroll - 8) {
            window.scrollTo({ top: 0, behavior: "auto" });
            setTimeout(function () {
              try { window.scrollTo({ top: maxScroll, behavior: "auto" }); } catch (_) {}
            }, 80);
          } else {
            window.scrollTo({ top: scrollTop + Math.max(600, doc.clientHeight - 100), behavior: "auto" });
          }
          if (scrollTop === prevScrollTop) {
            stuckScrollTicks++;
            if (stuckScrollTicks > 4) {
              try {
                var btns = document.querySelectorAll('button,[role="button"]');
                for (var i = 0; i < btns.length; i++) {
                  var t = (btns[i].textContent || "").toLowerCase();
                  if (t.indexOf("show more") >= 0 || t.indexOf("load more") >= 0) {
                    btns[i].click();
                    break;
                  }
                }
              } catch (_) {}
              stuckScrollTicks = 0;
            }
          } else {
            stuckScrollTicks = 0;
          }
          prevScrollTop = scrollTop;
        } catch (_) {}

        setTimeout(function () {
          var size = Object.keys(bag).length;
          if (size === lastSize) idle++;
          else { idle = 0; lastSize = size; }
          step();
        }, tickMs);
      }

      step();
    });
  };

  function bagAsList() {
    var out = [];
    for (var k in bag) {
      if (!Object.prototype.hasOwnProperty.call(bag, k)) continue;
      out.push(bag[k]);
    }
    return out;
  }
  window.__tbccOfHarvestSnapshot = bagAsList;

  chrome.runtime.onMessage.addListener(function (msg, _sender, sendResponse) {
    if (!msg || typeof msg.action !== "string") return;
    if (msg.action === "tbcc-of-harvest-snapshot") {
      try {
        sendResponse({ ok: true, list: bagAsList(), meta: meta });
      } catch (e) {
        sendResponse({ ok: false, error: String(e.message || e) });
      }
      return true;
    }
    if (msg.action === "tbcc-of-harvest-autoscroll") {
      try {
        Promise.resolve(window.__tbccOfHarvestAutoscroll(msg.options || {})).then(function (r) {
          sendResponse({ ok: true, list: bagAsList(), summary: r });
        }).catch(function (e) {
          sendResponse({ ok: false, error: String(e.message || e) });
        });
      } catch (e) {
        sendResponse({ ok: false, error: String(e.message || e) });
      }
      return true;
    }
  });
  });
})();
