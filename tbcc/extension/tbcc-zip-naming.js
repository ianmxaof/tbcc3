/**
 * AOF / PowerRename-style ZIP entry names for harvest & overlay ZIP export.
 * Default entry: AOF_{name}_{index:5}_t.me_aofmainhub.{ext}
 * Bundle archive: TBCC Bundle · {name} · TG@AOFMAINHUB · allmylinks.comaof69.zip
 */
(function (root) {
  const DEFAULT_TEMPLATE = "AOF_{name}_{index:5}_t.me_aofmainhub";
  const BRAND_HANDLE = "TG@AOFMAINHUB";
  const ALLMYLINKS_SLOT = "allmylinks.comaof69";
  const BUNDLE_PREFIX = "TBCC Bundle";

  function sanitizeSegment(s) {
    return String(s || "")
      .trim()
      .replace(/[^\w.\-]+/g, "_")
      .replace(/^_+|_+$/g, "")
      .slice(0, 64);
  }

  /** Soft sanitize for brand bundle names — keep readable handle, strip path-illegal chars. */
  function sanitizeBundleToken(s) {
    return String(s || "")
      .trim()
      .replace(/^@+/, "")
      .replace(/[<>:"/\\|?*\x00-\x1f]+/g, "")
      .replace(/\s+/g, " ")
      .slice(0, 64)
      .trim();
  }

  function randomFiveId() {
    const n = Math.floor(10000 + Math.random() * 90000);
    return String(n);
  }

  /** X / Twitter profile handle from a page URL. */
  function profileNameFromSourceUrl(url) {
    const s = String(url || "");
    const m = s.match(/(?:twitter\.com|x\.com)\/([^/?#]+)/i);
    if (!m) return "";
    const h = m[1].toLowerCase();
    if (["home", "search", "i", "intent", "share", "explore", "notifications", "messages"].includes(h)) {
      return "";
    }
    return sanitizeSegment(h) || "";
  }

  function formatCounter(index1, padding, increment, start) {
    const inc = Math.max(1, increment || 1);
    const st = start != null && !isNaN(start) ? Number(start) : 1;
    const pad = Math.min(12, Math.max(1, padding || 5));
    const n = st + (Math.max(1, index1) - 1) * inc;
    return String(n).padStart(pad, "0");
  }

  function expandPowerRenameCounters(template, index1) {
    return String(template || "").replace(
      /\$\{padding=(\d+)(?:;increment=(\d+))?(?:;start=(\d+))?\}/gi,
      function (_m, p, inc, st) {
        return formatCounter(index1, parseInt(p, 10), inc ? parseInt(inc, 10) : 1, st ? parseInt(st, 10) : 1);
      }
    );
  }

  function extFromContext(ctx) {
    if (ctx && ctx.ext) {
      const e = String(ctx.ext).replace(/^\./, "").toLowerCase();
      if (e) return e;
    }
    const base = ctx && ctx.baseName ? String(ctx.baseName) : "";
    const dot = base.lastIndexOf(".");
    if (dot > 0 && dot < base.length - 1) {
      const e = base.slice(dot + 1).toLowerCase();
      if (/^[a-z0-9]{2,5}$/.test(e)) return e;
    }
    const mime = ctx && ctx.mime ? String(ctx.mime).toLowerCase() : "";
    if (mime === "image/jpeg" || mime === "image/jpg") return "jpg";
    if (mime === "image/png") return "png";
    if (mime === "image/webp") return "webp";
    if (mime === "image/gif") return "gif";
    if (mime.startsWith("video/")) return "mp4";
    return "jpg";
  }

  /**
   * @param {string} template
   * @param {{ name?: string, index?: number, ext?: string, baseName?: string, mime?: string }} ctx
   */
  function buildZipFilename(template, ctx) {
    const tpl = String(template || DEFAULT_TEMPLATE).trim() || DEFAULT_TEMPLATE;
    const index1 = Math.max(1, ctx && ctx.index != null ? Number(ctx.index) : 1);
    const name = sanitizeSegment((ctx && ctx.name) || "media") || "media";
    const ext = extFromContext(ctx);
    let out = expandPowerRenameCounters(tpl, index1);
    out = out.replace(/\{name\}/gi, name);
    out = out.replace(/\{profile\}/gi, name);
    out = out.replace(/\{index:(\d+)\}/gi, function (_m, p) {
      return formatCounter(index1, parseInt(p, 10), 1, 1);
    });
    out = out.replace(/\{index\}/gi, formatCounter(index1, 5, 1, 1));
    out = out.replace(/\{ext\}/gi, ext);
    if (!/\{ext\}/i.test(tpl) && !/\.\w{2,5}$/i.test(out)) {
      out = out + "." + ext;
    }
    return out.replace(/[^\w.\-]+/g, "_").replace(/_+\./g, ".").slice(0, 180);
  }

  /**
   * Final Downloads/tbcc/ archive name for overlay / gallery ZIP export.
   * Prefer X profile handle; else 5-digit id.
   * Example: TBCC Bundle · Damon43095616 · TG@AOFMAINHUB · allmylinks.comaof69.zip
   */
  function buildBundleArchiveFilename(ctx) {
    let token = sanitizeBundleToken((ctx && (ctx.name || ctx.profileName)) || "");
    if (!token || /^media$/i.test(token)) {
      const fromUrl = profileNameFromSourceUrl((ctx && ctx.sourceUrl) || "");
      token = sanitizeBundleToken(fromUrl);
    }
    if (!token || /^media$/i.test(token)) token = randomFiveId();
    const ext =
      String((ctx && ctx.ext) || "zip")
        .replace(/^\./, "")
        .toLowerCase() || "zip";
    const base = `${BUNDLE_PREFIX} · ${token} · ${BRAND_HANDLE} · ${ALLMYLINKS_SLOT}.${ext}`;
    return base.replace(/[<>:"/\\|?*\x00-\x1f]+/g, "_").slice(0, 180);
  }

  function downloadPathForBundle(ctx) {
    const name = buildBundleArchiveFilename(ctx);
    return name.indexOf("tbcc/") === 0 ? name : "tbcc/" + name;
  }

  root.TbccZipNaming = {
    DEFAULT_TEMPLATE,
    BRAND_HANDLE,
    ALLMYLINKS_SLOT,
    BUNDLE_PREFIX,
    profileNameFromSourceUrl,
    buildZipFilename,
    buildBundleArchiveFilename,
    downloadPathForBundle,
    sanitizeSegment,
    sanitizeBundleToken,
    randomFiveId,
  };
})(typeof self !== "undefined" ? self : globalThis);
