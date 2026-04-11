/**
 * Site-specific gallery resolution (adapter pipeline).
 * Order: Motherless → Coomer/Kemono → same-origin detail HTML.
 * Background handlers stay in background.js; message actions unchanged.
 */
(function () {
  function isLiteMode() {
    return new Promise((resolve) => {
      try {
        chrome.storage.local.get("tbccLiteMode", (o) => resolve(!!(o && o.tbccLiteMode)));
      } catch (_) {
        resolve(false);
      }
    });
  }

  async function resolveMotherlessGalleryItems(list) {
    const arr = Array.isArray(list) ? list : [];
    const tagged = arr.filter((i) => i && i.motherlessDetailUrl);
    if (!tagged.length) return arr;
    const unique = [...new Set(tagged.map((i) => i.motherlessDetailUrl))];
    const map = await new Promise((resolve) => {
      try {
        chrome.runtime.sendMessage({ action: "tbcc-resolve-motherless", detailUrls: unique }, (r) => {
          if (chrome.runtime.lastError) {
            console.warn("resolveMotherlessGalleryItems", chrome.runtime.lastError);
            resolve({});
            return;
          }
          resolve(r && r.map && typeof r.map === "object" ? r.map : {});
        });
      } catch (e) {
        console.warn(e);
        resolve({});
      }
    });
    const seenResolved = new Set();
    const out = [];
    for (const entry of arr) {
      if (!entry) continue;
      if (!entry.motherlessDetailUrl) {
        out.push(entry);
        continue;
      }
      const resolved = map[entry.motherlessDetailUrl];
      if (!resolved) {
        out.push(entry);
        continue;
      }
      if (seenResolved.has(resolved)) continue;
      seenResolved.add(resolved);
      const next = { ...entry };
      delete next.motherlessDetailUrl;
      next.url = resolved;
      next.thumbUrl = entry.url;
      next.source = "motherless:full";
      next.mediaType = /\.(mp4|webm|mov|m4v)(\?|$)/i.test(resolved) ? "video" : "image";
      next.width = 0;
      next.height = 0;
      next.naturalWidth = 0;
      next.naturalHeight = 0;
      out.push(next);
    }
    return out;
  }

  async function resolveCoomerGalleryItems(list) {
    const arr = Array.isArray(list) ? list : [];
    const tagged = arr.filter((i) => i && i.coomerPostUrl);
    if (!tagged.length) return arr;
    const unique = [...new Set(tagged.map((i) => i.coomerPostUrl))];
    const map = await new Promise((resolve) => {
      try {
        chrome.runtime.sendMessage({ action: "tbcc-resolve-coomer", postUrls: unique }, (r) => {
          if (chrome.runtime.lastError) {
            console.warn("resolveCoomerGalleryItems", chrome.runtime.lastError);
            resolve({});
            return;
          }
          resolve(r && r.map && typeof r.map === "object" ? r.map : {});
        });
      } catch (e) {
        console.warn(e);
        resolve({});
      }
    });
    const seenPost = new Set();
    const out = [];
    for (const entry of arr) {
      if (!entry) continue;
      if (!entry.coomerPostUrl) {
        out.push(entry);
        continue;
      }
      if (seenPost.has(entry.coomerPostUrl)) continue;
      seenPost.add(entry.coomerPostUrl);
      const fullList = map[entry.coomerPostUrl];
      if (!fullList || !Array.isArray(fullList) || !fullList.length) {
        out.push(entry);
        continue;
      }
      for (const u of fullList) {
        if (!u || typeof u !== "string") continue;
        out.push({
          ...entry,
          url: u,
          coomerPostUrl: undefined,
          thumbUrl: entry.url,
          source: "coomer:full",
          mediaType: /\.(mp4|webm|mov|m4v)(\?|$)/i.test(u) ? "video" : "image",
          width: 0,
          height: 0,
          naturalWidth: 0,
          naturalHeight: 0,
        });
      }
    }
    return out;
  }

  async function resolveDetailPageGalleryItems(list) {
    const arr = Array.isArray(list) ? list : [];
    const tagged = arr.filter((i) => i && i.detailPageUrl && !i.motherlessDetailUrl);
    if (!tagged.length) return arr;
    const unique = [...new Set(tagged.map((i) => i.detailPageUrl))].slice(0, 200);
    const map = await new Promise((resolve) => {
      try {
        chrome.runtime.sendMessage({ action: "tbcc-resolve-detail-page", detailUrls: unique }, (r) => {
          if (chrome.runtime.lastError) {
            console.warn("resolveDetailPageGalleryItems", chrome.runtime.lastError);
            resolve({});
            return;
          }
          resolve(r && r.map && typeof r.map === "object" ? r.map : {});
        });
      } catch (e) {
        console.warn(e);
        resolve({});
      }
    });
    const seenResolved = new Set();
    const out = [];
    for (const entry of arr) {
      if (!entry) continue;
      if (!entry.detailPageUrl) {
        out.push(entry);
        continue;
      }
      const resolved = map[entry.detailPageUrl];
      if (!resolved) {
        out.push(entry);
        continue;
      }
      if (seenResolved.has(resolved)) continue;
      seenResolved.add(resolved);
      const next = { ...entry };
      delete next.detailPageUrl;
      next.url = resolved;
      next.thumbUrl = entry.url;
      next.source = "detail-page";
      next.mediaType = /\.(mp4|webm|mov|m4v)(\?|$)/i.test(resolved) ? "video" : "image";
      next.width = 0;
      next.height = 0;
      next.naturalWidth = 0;
      next.naturalHeight = 0;
      out.push(next);
    }
    return out;
  }

  /**
   * After capture: Motherless full → Coomer API → generic detail HTML.
   */
  async function runGalleryResolvePipeline(list) {
    if (await isLiteMode()) return list;
    let out = list;
    out = await resolveMotherlessGalleryItems(out);
    out = await resolveCoomerGalleryItems(out);
    out = await resolveDetailPageGalleryItems(out);
    return out;
  }

  /**
   * OnlyFans: merge URLs observed via chrome.webRequest (session storage per tab).
   * Any tab: merge HLS/DASH manifest URLs (tbcc_net_manifest_) for backend /import/hls-url.
   */
  async function mergeOnlyfansWebRequestUrls(tabId, deduped, seenKeys) {
    const lite = await isLiteMode();
    const netKey = `tbcc_net_media_${tabId}`;
    const scoreNet =
      typeof tbccScoreVideoUrl === "function"
        ? tbccScoreVideoUrl
        : function (u) {
            var z = (u || "").toLowerCase();
            return /\.m3u8(\?|$)/i.test(z) ? 50 : 0;
          };
    try {
      const sess = await chrome.storage.session.get(netKey);
      const netUrls = Array.isArray(sess[netKey]) ? sess[netKey] : [];
      const sortedNet = [...netUrls].sort((a, b) => scoreNet(b) - scoreNet(a));
      for (const netU of sortedNet) {
        const nk = (netU || "").slice(0, 400);
        if (!nk || seenKeys.has(nk)) continue;
        seenKeys.add(nk);
        const low = nk.toLowerCase();
        const isVideo =
          /\.(mp4|m4v|webm|m3u8|mpd|mov|mkv)(\?|$)/i.test(low) ||
          /\.m4s(\?|$)/i.test(low) ||
          (/\.(ts|aac)(\?|$)/i.test(low) && (low.includes("stream") || low.includes("hls") || low.includes("video")));
        deduped.push({
          url: netU,
          width: 0,
          height: 0,
          tagName: isVideo ? "video" : "img",
          naturalWidth: 0,
          naturalHeight: 0,
          mediaType: isVideo ? "video" : "image",
          tbccCaptureSource: "web-request",
        });
      }
    } catch (_) {}
    if (!lite) {
      const manKey = `tbcc_net_manifest_${tabId}`;
      try {
        const ms = await chrome.storage.session.get(manKey);
        const mans = Array.isArray(ms[manKey]) ? ms[manKey] : [];
        for (const mu of mans) {
          const mk = (mu || "").slice(0, 400);
          if (!mk || seenKeys.has(mk)) continue;
          seenKeys.add(mk);
          deduped.push({
            url: mu,
            width: 0,
            height: 0,
            tagName: "video",
            naturalWidth: 0,
            naturalHeight: 0,
            mediaType: "video",
            tbccCaptureSource: "web-request-manifest",
            tbccStreamManifest: true,
          });
        }
      } catch (_) {}
    }
  }

  window.tbccGalleryAdapters = {
    runGalleryResolvePipeline: runGalleryResolvePipeline,
    mergeOnlyfansWebRequestUrls: mergeOnlyfansWebRequestUrls,
    /** Registry metadata for options / future Pro gating */
    RESOLVER_ORDER: ["motherless", "coomer", "detailPage"],
  };
})();
