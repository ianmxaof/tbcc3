/**
 * Shared auto-tag filters + semantic page URL tagging (gallery, background, capture).
 */
(function (root) {
  const SHORT_OK = new Set([
    "mp4",
    "webm",
    "mov",
    "m4v",
    "mkv",
    "nsfw",
    "sfw",
    "hd",
    "4k",
    "uhd",
    "pic",
    "vid",
    "of",
    "user",
    "data",
  ]);

  const STOPWORDS = new Set([
    "www",
    "com",
    "net",
    "org",
    "the",
    "and",
    "for",
    "with",
    "from",
    "this",
    "that",
    "photo",
    "image",
    "images",
    "video",
    "videos",
    "media",
    "thumb",
    "thumbs",
    "thumbnail",
    "gallery",
    "post",
    "posts",
    "files",
    "file",
    "content",
    "static",
    "cdn",
    "large",
    "small",
    "original",
    "full",
    "profilepage",
    "profile page",
    "page",
  ]);

  function hexishRatio(alnum) {
    if (!alnum) return 0;
    return (alnum.match(/[0-9a-f]/gi) || []).length / alnum.length;
  }

  /** Mixed-case CDN path tokens (e.g. T47qarSG, azoiaQv3) — not usernames. */
  function looksLikeRandomCdnSlug(s) {
    const t = String(s || "")
      .trim()
      .replace(/^#+/u, "")
      .replace(/[\s_\-]/g, "");
    if (t.length < 5 || t.length > 14) return false;
    if (!/^[A-Za-z0-9]+$/.test(t)) return false;
    const low = t.toLowerCase();
    if (SHORT_OK.has(low)) return false;
    const digits = (t.match(/\d/g) || []).length;
    const hasUpper = /[A-Z]/.test(t);
    const hasLower = /[a-z]/.test(t);
    const lettersOnly = t.replace(/\d/g, "");
    if (/^[a-z][a-z0-9_.]{2,31}$/.test(t) && /[aeiou]/i.test(t) && digits <= 2) return false;
    if (t.length >= 6 && t.length <= 12 && digits >= 1 && hasUpper && hasLower) return true;
    if (t.length >= 6 && t.length <= 12 && hasUpper && hasLower && digits >= 1) return true;
    if (t.length >= 7 && t.length <= 11 && hasUpper && hasLower && !/[aeiou]/i.test(lettersOnly)) return true;
    if (t.length >= 6 && t.length <= 12 && digits >= 2 && /[A-Z]/.test(t) && /[a-z]/.test(t)) return true;
    return false;
  }

  function isJunkAutoTagToken(raw) {
    const primary = String(raw || "")
      .trim()
      .replace(/^#+/u, "");
    if (!primary || primary.length < 2) return true;
    const low = primary.toLowerCase();
    if (SHORT_OK.has(low)) return false;
    if (STOPWORDS.has(low)) return true;
    if (looksLikeRandomCdnSlug(primary)) return true;
    const compact = primary.replace(/[\s_\-]/g, "");
    if (/^0x[0-9a-f]+$/i.test(compact)) return true;
    if (compact.length <= 2 && /^[0-9a-f]+$/i.test(compact)) return true;
    if (compact.length >= 8 && /^[0-9a-f]+$/i.test(compact)) return true;
    const alnum = primary.replace(/[^a-z0-9]/gi, "");
    if (!alnum) return true;
    if (/^[0-9]{10,}$/.test(alnum)) return true;
    if (alnum.length >= 12) {
      if (hexishRatio(alnum) >= 0.82) return true;
      if (!/[aeiou]/i.test(alnum)) return true;
    }
    if (alnum.length >= 8 && alnum.length <= 11 && !/[aeiou]/i.test(alnum) && hexishRatio(alnum) >= 0.65) return true;
    if (/^[A-Z][a-z]+[A-Z][a-z]+/.test(primary) && /page$/i.test(low)) return true;
    return false;
  }

  function isCdnOrMediaAssetUrl(u) {
    try {
      const url = u instanceof URL ? u : new URL(String(u || ""));
      const host = (url.hostname || "").toLowerCase();
      const path = (url.pathname || "").toLowerCase();
      if (/\.(jpe?g|png|gif|webp|bmp|mp4|webm|mov|m4v|mkv|m3u8|mpd)(\?|$)/i.test(path)) return true;
      if (/^(cdn\.|media\.|static\.|img\.|thumbs?\.|images\.|files\.)/i.test(host)) return true;
      if (/cloudfront\.net|akamaized\.net|fastly\.net|b-cdn\.net/i.test(host)) return true;
      if (host.includes("onlyfans") && (path.includes("/files/") || path.includes("/thumb"))) return true;
      if (path.includes("/content/") && path.split("/").some((p) => looksLikeRandomCdnSlug(p))) return true;
    } catch (_) {}
    return false;
  }

  function extractSemanticTagsFromUrl(rawUrl) {
    const tags = [];
    try {
      const u = new URL(String(rawUrl || "").trim().split("#")[0]);
      if (isCdnOrMediaAssetUrl(u)) return tags;
      const host = (u.hostname || "").toLowerCase().replace(/^www\./, "");
      const path = (u.pathname || "").replace(/\/+$/, "");
      const parts = path.split("/").filter(Boolean);

      if (host.includes("onlyfans.com")) {
        tags.push("onlyfans");
        const p = parts.join("/");
        let creator = "";
        if (parts[0] === "u" && parts[1]) creator = parts[1];
        else if (parts[0] && !/^(posts|media|my|api|files)$/i.test(parts[0])) creator = parts[0];
        if (creator && creator.length >= 3 && !isJunkAutoTagToken(creator)) tags.push(creator);
        if (/\/posts\//i.test(path) || parts.includes("posts")) tags.push("post");
        else if (creator) tags.push("profile");
      } else if (host.includes("erome.com")) {
        tags.push("erome");
        if (parts[0] === "a" && parts[1]) tags.push("album");
      } else if (host.includes("reddit.com")) {
        tags.push("reddit");
        const i = parts.indexOf("r");
        if (i >= 0 && parts[i + 1] && !isJunkAutoTagToken(parts[i + 1])) tags.push(parts[i + 1]);
      } else if (host.includes("redgifs.com")) {
        tags.push("redgifs");
      }

      const hostSite = host.split(".")[0];
      if (hostSite && hostSite.length >= 4 && !isJunkAutoTagToken(hostSite) && !tags.includes(hostSite)) {
        if (!/^(cdn|media|static|www)$/.test(hostSite)) tags.push(hostSite);
      }
    } catch (_) {}
    const out = [];
    const seen = Object.create(null);
    for (const t of tags) {
      const s = String(t || "").trim();
      if (!s || isJunkAutoTagToken(s)) continue;
      const k = s.toLowerCase();
      if (seen[k]) continue;
      seen[k] = 1;
      out.push(s);
    }
    return out;
  }

  function normalizeAutoTagCandidate(raw) {
    const s = String(raw || "")
      .trim()
      .replace(/^#+/u, "")
      .replace(/[_\-]+/g, " ")
      .replace(/\s+/g, " ")
      .trim();
    if (!s || s.length < 2 || s.length > 64) return "";
    if (STOPWORDS.has(s.toLowerCase())) return "";
    if (/^\d+$/u.test(s)) return "";
    if (isJunkAutoTagToken(s)) return "";
    return s;
  }

  function filterReadableTagHints(hints) {
    return (hints || []).filter((h) => {
      const n = normalizeAutoTagCandidate(h);
      return n && !isJunkAutoTagToken(n);
    });
  }

  root.TbccAutoTagUtils = {
    SHORT_OK,
    STOPWORDS,
    isJunkAutoTagToken,
    looksLikeRandomCdnSlug,
    isCdnOrMediaAssetUrl,
    extractSemanticTagsFromUrl,
    normalizeAutoTagCandidate,
    filterReadableTagHints,
  };
})(typeof globalThis !== "undefined" ? globalThis : self);
