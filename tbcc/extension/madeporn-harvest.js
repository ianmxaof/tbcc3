/**
 * TBCC made.porn harvest (ISOLATED world).
 *
 * Gallery pages embed direct CDN URLs for every tile in the HTML
 * (/vs/…mp4 for video, /is/…jpg for images). This harvester scrolls
 * to trigger lazy-load, extracts all media from the DOM + page source,
 * deduplicates video codec variants (prefers H.264 _avc over _av1), and
 * maps thumbnails from grid links.
 *
 * Driven by gallery Crawl tab:
 *   tbcc-madeporn-harvest-run → scroll + extract → return item list
 */
(function () {
  if (typeof tbccWaitForModule !== "function") return;
  tbccWaitForModule("madeporn_harvest", function () {
    if (window.__tbccMadepornHarvestLoaded) return;
    window.__tbccMadepornHarvestLoaded = true;

    var HOST_RE = /(^|\.)made\.porn$/i;

    function isMadepornLoc() {
      try {
        return HOST_RE.test(location.hostname || "");
      } catch (_) {
        return false;
      }
    }

    if (!isMadepornLoc()) return;

    var MP4_RE = /https?:\/\/made\.porn\/vs\/[^"'<>\s\\]+\.mp4/gi;
    var IMG_RE = /https?:\/\/made\.porn\/is\/[^"'<>\s\\]+\.(?:jpe?g|webp)/gi;
    var THUMB_RE = /https?:\/\/made\.porn\/600\/is\/[^"'<>\s\\]+\.(?:jpe?g|webp)/gi;

    function variantRank(url) {
      var u = String(url || "").toLowerCase();
      if (u.indexOf("_avc.") >= 0) return 3;
      if (u.indexOf("_av1.") >= 0) return 2;
      return 1;
    }

    function mp4GroupKey(url) {
      return String(url || "")
        .replace(/_(?:av1|avc)\.mp4$/i, ".mp4")
        .split("?")[0]
        .toLowerCase();
    }

    function itemIdFromPageUrl(href) {
      try {
        var m = String(href || "").match(/\/(?:v|i)\/([A-Za-z0-9_-]+)/i);
        return m ? m[1] : "";
      } catch (_) {
        return "";
      }
    }

    function filenameFromUrl(url) {
      try {
        var p = new URL(url).pathname;
        return p.split("/").pop() || url;
      } catch (_) {
        return String(url || "");
      }
    }

    function uniqueMatches(re, text) {
      var seen = new Set();
      var out = [];
      var m;
      var r = new RegExp(re.source, re.flags);
      while ((m = r.exec(text)) !== null) {
        var u = m[0];
        if (!seen.has(u)) {
          seen.add(u);
          out.push(u);
        }
      }
      return out;
    }

    function dedupeMp4Urls(urls) {
      var best = new Map();
      for (var i = 0; i < urls.length; i++) {
        var u = urls[i];
        var key = mp4GroupKey(u);
        var prev = best.get(key);
        if (!prev || variantRank(u) > variantRank(prev)) best.set(key, u);
      }
      return Array.from(best.values());
    }

    function buildThumbMap() {
      var map = {};
      var links = document.querySelectorAll('a[href*="/v/"], a[href*="/i/"]');
      for (var i = 0; i < links.length; i++) {
        var a = links[i];
        var id = itemIdFromPageUrl(a.href);
        if (!id) continue;
        var img = a.querySelector("img");
        var src = img && (img.currentSrc || img.src || img.getAttribute("data-src"));
        if (src && /^https?:\/\//i.test(src)) map[id] = src;
      }
      return map;
    }

    function thumbForMediaUrl(mediaUrl, thumbMap) {
      var id = "";
      try {
        var m = String(mediaUrl).match(/\/([A-Za-z0-9_-]{8,})[-_.]/);
        if (m) id = m[1];
      } catch (_) {}
      if (id && thumbMap[id]) return thumbMap[id];
      return null;
    }

    function extractFromDocument() {
      var html = document.documentElement.innerHTML;
      var mp4s = dedupeMp4Urls(uniqueMatches(MP4_RE, html));
      var images = uniqueMatches(IMG_RE, html);
      var thumbs = uniqueMatches(THUMB_RE, html);
      var thumbMap = buildThumbMap();

      var items = [];
      var seen = new Set();

      for (var vi = 0; vi < mp4s.length; vi++) {
        var vurl = mp4s[vi];
        if (seen.has(vurl)) continue;
        seen.add(vurl);
        var vthumb = thumbForMediaUrl(vurl, thumbMap);
        items.push({
          url: vurl,
          media_type: "video",
          filename: filenameFromUrl(vurl),
          thumbnail_url: vthumb || undefined,
        });
      }

      for (var ii = 0; ii < images.length; ii++) {
        var iurl = images[ii];
        if (seen.has(iurl)) continue;
        seen.add(iurl);
        items.push({
          url: iurl,
          media_type: "image",
          filename: filenameFromUrl(iurl),
          thumbnail_url: iurl,
        });
      }

      // Thumbs-only tiles (no full /is/ in HTML yet) — keep poster for resolve pass
      for (var ti = 0; ti < thumbs.length; ti++) {
        var turl = thumbs[ti];
        var fullGuess = turl.replace("/600/is/", "/is/");
        if (seen.has(fullGuess) || seen.has(turl)) continue;
        // Only add thumb if we don't already have the full image or a video for same id
        var tid = itemIdFromPageUrl(turl);
        var hasFull = images.some(function (u) {
          return tid && u.indexOf(tid) >= 0;
        });
        if (hasFull) continue;
        seen.add(turl);
        items.push({
          url: fullGuess,
          media_type: "image",
          filename: filenameFromUrl(fullGuess),
          thumbnail_url: turl,
        });
      }

      return items;
    }

    function scrollStep() {
      try {
        var doc = document.scrollingElement || document.documentElement;
        var scrollTop = doc.scrollTop || 0;
        var maxScroll = Math.max(0, doc.scrollHeight - doc.clientHeight);
        if (scrollTop >= maxScroll - 12) {
          window.scrollTo({ top: 0, behavior: "auto" });
        } else {
          window.scrollTo({
            top: scrollTop + Math.max(700, (doc.clientHeight || 800) - 80),
            behavior: "auto",
          });
        }
      } catch (_) {}
    }

    function harvestWithScroll(opts) {
      opts = opts || {};
      var tickMs = Number(opts.tickMs) > 0 ? Number(opts.tickMs) : 450;
      var idleTicks = Number(opts.idleTicks) > 0 ? Number(opts.idleTicks) : 5;
      var hardCapMs = Number(opts.hardCapMs) > 0 ? Number(opts.hardCapMs) : 45000;
      var maxItems = Number(opts.maxItems) > 0 ? Number(opts.maxItems) : 500;
      var includeVideo = opts.includeVideo !== false;
      var includeImage = opts.includeImage !== false;

      return new Promise(function (resolve) {
        var started = Date.now();
        var lastCount = 0;
        var idle = 0;
        var bestItems = [];

        function filterItems(list) {
          return list.filter(function (it) {
            if (!it || !it.url) return false;
            if (it.media_type === "video" && !includeVideo) return false;
            if (it.media_type === "image" && !includeImage) return false;
            return true;
          });
        }

        function step() {
          var items = filterItems(extractFromDocument());
          if (items.length > bestItems.length) bestItems = items;

          if (Date.now() - started >= hardCapMs || idle >= idleTicks) {
            var finalList = bestItems.slice(0, maxItems);
            resolve({
              ok: true,
              list: finalList,
              truncated: bestItems.length > maxItems,
              summary: {
                sourceUrl: location.href,
                elapsedMs: Date.now() - started,
                totalFound: bestItems.length,
                returned: finalList.length,
              },
            });
            return;
          }

          scrollStep();
          setTimeout(function () {
            var count = filterItems(extractFromDocument()).length;
            if (count === lastCount) idle++;
            else {
              idle = 0;
              lastCount = count;
            }
            step();
          }, tickMs);
        }

        // Initial extract before scroll (many pages ship full grid in HTML)
        bestItems = filterItems(extractFromDocument());
        lastCount = bestItems.length;
        step();
      });
    }

    chrome.runtime.onMessage.addListener(function (msg, _sender, sendResponse) {
      if (!msg || typeof msg.action !== "string") return;
      if (msg.action === "tbcc-madeporn-harvest-run") {
        harvestWithScroll(msg.options || {})
          .then(function (r) {
            sendResponse(r);
          })
          .catch(function (e) {
            sendResponse({ ok: false, error: String((e && e.message) || e) });
          });
        return true;
      }
      if (msg.action === "tbcc-madeporn-harvest-snapshot") {
        try {
          var snap = extractFromDocument();
          sendResponse({ ok: true, list: snap, summary: { sourceUrl: location.href } });
        } catch (e) {
          sendResponse({ ok: false, error: String((e && e.message) || e) });
        }
        return true;
      }
    });
  });
})();
