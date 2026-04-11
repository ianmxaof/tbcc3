/**
 * Detect URLs that look like a video *page* (HTML) rather than a direct media file.
 * Used by capture.js (page context) and gallery.js (extension page — no pageHref).
 */
(function (global) {
  function tbccIsLikelyHtmlPageUrl(url, pageHref) {
    if (!url || typeof url !== "string") return true;
    var s = url.trim();
    if (s.startsWith("blob:") || s.startsWith("data:")) return false;
    if (!/^https?:\/\//i.test(s)) return true;
    try {
      var p = new URL(s);
      if (pageHref) {
        try {
          if (p.href.split("#")[0] === String(pageHref).split("#")[0]) return true;
        } catch (_) {}
      }
      var path = (p.pathname || "").replace(/\/+$/g, "") || "/";
      var last = path.split("/").filter(Boolean).pop() || "";
      if (/\.(mp4|webm|mov|m4v|mkv|m3u8|mpd|ogv)(\?|$)/i.test(last)) return false;
      if (/\.(mp4|webm|mov|m4v|mkv|m3u8|mpd|ogv)(\?|$)/i.test(path)) return false;
      if (/\/videos?\/[^/]+$/i.test(path) || /\/embed\/[^/]+$/i.test(path) || /\/watch\/[^/]+$/i.test(path) || /^\/v\/[^/]+$/i.test(path))
        return true;
      return false;
    } catch (_) {
      return true;
    }
  }
  global.tbccIsLikelyHtmlPageUrl = tbccIsLikelyHtmlPageUrl;

  /**
   * Prefer full-quality video URLs over preview/progressive tiny MP4s (e.g. OnlyFans player).
   * Used by capture.js (DOM <video>) and gallery-resolve (webRequest merge) — keep in sync.
   */
  function tbccScoreVideoUrl(u) {
    var s = (u || "").toLowerCase();
    if (s.indexOf("blob:") === 0 || s.indexOf("data:") === 0) return -500;
    var sc = 0;
    if (/\.m3u8(\?|$)/i.test(s)) sc += 130;
    if (/\.mpd(\?|$)/i.test(s)) sc += 125;
    if (s.indexOf("master") >= 0 && /\.m3u8/i.test(s)) sc += 35;
    if (s.indexOf("full-d") >= 0) sc += 100;
    if (/[\/._-]full[._-]/i.test(s) || /\/full\//i.test(s)) sc += 55;
    if (s.indexOf("2160") >= 0 || s.indexOf("4k") >= 0) sc += 45;
    if (s.indexOf("1440") >= 0) sc += 40;
    if (s.indexOf("1080") >= 0) sc += 35;
    if (s.indexOf("720") >= 0) sc += 18;
    if (s.indexOf("540") >= 0) sc += 8;
    if (s.indexOf("thumbnail-hq") >= 0) sc -= 8;
    if (s.indexOf("thumb") >= 0 || s.indexOf("thumbnail") >= 0) sc -= 38;
    if (s.indexOf("preview") >= 0 || s.indexOf("teaser") >= 0) sc -= 35;
    if (s.indexOf("sample") >= 0) sc -= 15;
    if (s.indexOf("snippet") >= 0 || s.indexOf("clip") >= 0) sc -= 25;
    if (/x240|_240_|\/240\/|\b240p\b/i.test(s)) sc -= 75;
    if (/\b360p\b|x360|_360_/i.test(s)) sc -= 55;
    if (/\b480p\b/i.test(s)) sc -= 35;
    if (/\b540p\b/i.test(s)) sc -= 18;
    sc += Math.min(s.length, 240) / 24;
    return sc;
  }
  global.tbccScoreVideoUrl = tbccScoreVideoUrl;
})(typeof window !== "undefined" ? window : self);
