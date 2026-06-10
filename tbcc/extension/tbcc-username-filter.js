/* global globalThis */
/**
 * Strict username intake for master archive + model search.
 * Only plausible handles on cam/fan platforms — blocks code-page garbage.
 */
(function (global) {
  const RESERVED = new Set(
    [
      "a", "an", "the", "and", "or", "to", "of", "in", "on", "at", "by", "for", "from", "with",
      "application", "install", "enhanced", "hyperrealistic", "below", "endpoint", "obfuscation",
      "powershell", "prepend", "replace", "script", "undress", "name", "make", "image", "https",
      "http", "here", "nvidia", "gravatar", "gorillamail", "linkvertise", "sharklasers", "proton",
      "bot", "message", "handler", "function", "return", "const", "class", "import", "export",
      "undefined", "null", "true", "false", "var", "let", "async", "await", "static", "public",
      "private", "void", "int", "string", "object", "array", "type", "interface", "extends",
      "implements", "module", "package", "require", "default", "switch", "case", "break",
      "continue", "while", "foreach", "self", "this", "super", "new", "delete", "typeof",
      "instanceof", "try", "catch", "finally", "throw", "yield", "get", "set", "enum",
      "username", "user", "users", "profile", "profiles", "search", "models", "model", "video",
      "videos", "photo", "photos", "media", "login", "signup", "register", "settings", "admin",
      "www", "en", "com", "org", "net", "html", "body", "head", "title", "meta", "link", "div",
      "span", "input", "button", "form", "table", "style", "href", "src", "alt", "width", "height",
      "hii", "rthi", "seaside", "cloud", "data", "index", "home", "about", "contact", "privacy",
      "terms", "cookie", "cookies", "cdn", "api", "assets", "static", "content", "page", "pages",
    ].map((s) => s.toLowerCase())
  );

  /** Host must match for passive context/copy username capture. */
  const SOURCE_HOST =
    /(?:^|\.)((?:chaturbate|stripchat|onlyfans|fansly|loyalfans|myfreecams|bongacams|cam4|camsoda|livejasmin|manyvids|fanvue|fancentro|admireme|alua|justfor)\.(?:com|tv|fans|site|vip|me|io|net|org)|(?:coomer|kemono)\.(?:st|party|su)|(?:fapello|leakedzone)\.com)(?:$|:)/i;

  function normalizeUsernameCandidate(raw) {
    if (!raw) return "";
    let s = String(raw).trim();
    s = s.replace(/^@+/, "");
    s = s.replace(/^[^\w]+|[^\w.:-]+$/g, "");
    if (!s) return "";
    if (!/^[a-zA-Z0-9._-]{2,64}$/.test(s)) return "";
    const low = s.toLowerCase();
    if (RESERVED.has(low)) return "";
    if (/^\d+$/.test(s)) return "";
    if (!/[a-zA-Z]/.test(s)) return "";
    if (s.length <= 2 && !/[a-zA-Z]{2,}/.test(s)) return "";
    if (/^(user|u|id|uid|name|test|demo|null|none|admin|root|guest)\d*$/i.test(s)) return "";
    return s;
  }

  function isAllowedUsernameSourceUrl(rawUrl) {
    if (!rawUrl) return false;
    try {
      const h = new URL(String(rawUrl)).hostname.toLowerCase();
      return SOURCE_HOST.test(h + (h.includes(":") ? "" : ""));
    } catch (_) {
      return false;
    }
  }

  /**
   * Accept username for master archive when:
   * - handle passes normalize, AND
   * - page/ref URL is a cam/fan platform OR source is explicit model_search / user_action
   */
  function acceptUsernameForArchive(username, opts) {
    const clean = normalizeUsernameCandidate(username);
    if (!clean) return "";
    const source = opts && opts.source ? String(opts.source).toLowerCase() : "";
    const ref = (opts && opts.ref) || (opts && opts.pageUrl) || "";
    if (source === "model_search" || source === "username_search" || source === "user_pick") {
      return clean;
    }
    if (isAllowedUsernameSourceUrl(ref)) return clean;
    return "";
  }

  global.TbccUsernameFilter = {
    normalizeUsernameCandidate,
    isAllowedUsernameSourceUrl,
    acceptUsernameForArchive,
    RESERVED,
  };
})(typeof globalThis !== "undefined" ? globalThis : self);
