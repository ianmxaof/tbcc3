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
})(typeof window !== "undefined" ? window : self);
