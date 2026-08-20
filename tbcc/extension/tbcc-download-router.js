/**
 * Download-routing "circuit board": ordered rules that route ANY browser
 * download (not just TBCC's own) into a Downloads subfolder by file
 * extension, source domain, MIME prefix, or URL pattern.
 *
 * chrome.downloads.onDeterminingFilename only accepts a filename relative to
 * the default Downloads directory — no absolute paths, no "..". Routing is
 * therefore always a subfolder under Downloads, never an arbitrary disk path.
 */
(function (root) {
  function sanitizeSegment(s) {
    return String(s || "")
      .trim()
      .replace(/[<>:"|?*\x00-\x1f]+/g, "_")
      .replace(/\.\.+/g, ".")
      .replace(/^[\\/]+|[\\/]+$/g, "")
      .slice(0, 80);
  }

  function extOf(filename) {
    const base = String(filename || "").split(/[\\/]/).pop() || "";
    const dot = base.lastIndexOf(".");
    return dot > 0 && dot < base.length - 1 ? base.slice(dot + 1).toLowerCase() : "";
  }

  function hostnameOf(url) {
    try {
      return new URL(String(url || "")).hostname.toLowerCase().replace(/^www\./, "");
    } catch (_) {
      return "";
    }
  }

  function pad2(n) {
    return String(n).padStart(2, "0");
  }

  function matchesDomain(host, matchValue) {
    const want = String(matchValue || "").trim().toLowerCase().replace(/^www\./, "");
    if (!want || !host) return false;
    return host === want || host.endsWith("." + want);
  }

  /**
   * @param {import("./tbcc-download-router").Route} route
   * @param {{ url?: string, referrer?: string, mime?: string, filename?: string }} item
   */
  function routeMatches(route, item) {
    if (!route || route.enabled === false) return false;
    const type = String(route.matchType || "").trim();
    const value = route.matchValue;
    if (type === "extension") {
      const ext = extOf(item && item.filename);
      const list = String(value || "")
        .split(",")
        .map((s) => s.trim().toLowerCase().replace(/^\./, ""))
        .filter(Boolean);
      return !!ext && list.includes(ext);
    }
    if (type === "domain") {
      const host = hostnameOf((item && item.url) || "") || hostnameOf((item && item.referrer) || "");
      return matchesDomain(host, value);
    }
    if (type === "mimePrefix") {
      const mime = String((item && item.mime) || "").toLowerCase();
      const want = String(value || "").toLowerCase();
      return !!want && mime.startsWith(want);
    }
    if (type === "urlRegex") {
      try {
        const re = new RegExp(String(value || ""), "i");
        return re.test((item && (item.finalUrl || item.url)) || "");
      } catch (_) {
        return false;
      }
    }
    return false;
  }

  /**
   * First enabled route (in list order) whose match condition is satisfied.
   * @param {Route[]} routes
   * @param {object} item
   * @returns Route|null
   */
  function matchRoute(routes, item) {
    for (const r of Array.isArray(routes) ? routes : []) {
      if (routeMatches(r, item)) return r;
    }
    return null;
  }

  /** Expand {ext} {domain} {YYYY} {MM} {DD} {filename} tokens in a route's folder template. */
  function expandFolderTemplate(template, item) {
    const now = new Date();
    const ext = extOf(item && item.filename);
    const host = hostnameOf((item && item.url) || "") || hostnameOf((item && item.referrer) || "");
    const baseNoExt = (() => {
      const base = String((item && item.filename) || "").split(/[\\/]/).pop() || "";
      const dot = base.lastIndexOf(".");
      return dot > 0 ? base.slice(0, dot) : base;
    })();
    return String(template || "")
      .replace(/\{ext\}/gi, ext || "misc")
      .replace(/\{domain\}/gi, host || "unknown")
      .replace(/\{YYYY\}/g, String(now.getFullYear()))
      .replace(/\{MM\}/g, pad2(now.getMonth() + 1))
      .replace(/\{DD\}/g, pad2(now.getDate()))
      .replace(/\{filename\}/gi, baseNoExt || "file");
  }

  /**
   * Build the routed relative filename for chrome.downloads suggest().
   * @param {Route} route
   * @param {object} item
   * @returns {string|null} relative path, or null if the route has no folder to apply
   */
  function buildRoutedFilename(route, item) {
    const base = String((item && item.filename) || "file").split(/[\\/]/).pop() || "file";
    const folderTpl = String((route && route.folder) || "").trim();
    if (!folderTpl) return null;
    const expanded = expandFolderTemplate(folderTpl, item);
    const segments = expanded
      .split("/")
      .map(sanitizeSegment)
      .filter(Boolean);
    if (!segments.length) return null;
    return segments.join("/") + "/" + base;
  }

  const api = {
    extOf,
    hostnameOf,
    matchesDomain,
    routeMatches,
    matchRoute,
    expandFolderTemplate,
    buildRoutedFilename,
    sanitizeSegment,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = { TbccDownloadRouter: api };
  } else {
    root.TbccDownloadRouter = api;
  }
})(typeof globalThis !== "undefined" ? globalThis : typeof self !== "undefined" ? self : this);
