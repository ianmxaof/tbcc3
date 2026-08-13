/**
 * AOF / PowerRename-style ZIP entry names for harvest & overlay ZIP export.
 * Default entry: AOF_{name}_{index:5}_telegram.me_aofmainhub.{ext}
 * Bundle archive: TBCC Bundle · {name} · telegram.me_aofmainhub · allmylinks.comaof69.zip
 */
(function (root) {
  const DEFAULT_TEMPLATE = "AOF_{name}_{index:5}_telegram.me_aofmainhub";
  const DEFAULT_BUNDLE_TEMPLATE =
    "TBCC Bundle · {name} · telegram.me_aofmainhub · allmylinks.comaof69";
  const BRAND_HANDLE = "telegram.me_aofmainhub";
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

  function hostSiteLabel(hostname) {
    const h = String(hostname || "")
      .toLowerCase()
      .replace(/^www\./, "");
    if (!h) return "";
    if (h.includes("onlyfans")) return "onlyfans";
    if (h.includes("erome")) return "erome";
    if (h.includes("motherless")) return "motherless";
    if (h.includes("fapello")) return "fapello";
    if (h === "x.com" || h.includes("twitter")) return "x";
    if (h.includes("reddit")) return "reddit";
    if (h.includes("redgifs")) return "redgifs";
    const base = h.split(".")[0];
    return sanitizeSegment(base) || "";
  }

  function cleanPageTitle(raw) {
    let t = String(raw || "").trim();
    if (!t) return "";
    t = t.replace(/\s*[-|·•]\s*(OnlyFans|EROME|Erome|Porn|Pornhub|Motherless|Fapello|Reddit).*$/i, "");
    t = t.replace(/\s*\|.*$/, "");
    t = t.replace(/\s+on\s+OnlyFans$/i, "");
    t = t.replace(/\s+\(@[A-Za-z0-9_]+\)\s*$/i, "");
    return sanitizeBundleToken(t);
  }

  function onlyfansCreatorFromUrl(url) {
    try {
      const u = new URL(String(url || ""));
      const parts = (u.pathname || "").replace(/\/+$/, "").split("/").filter(Boolean);
      if (parts[0] === "u" && parts[1]) return sanitizeBundleToken(parts[1]);
      if (parts[0] && !/^(posts|media|my|api|files)$/i.test(parts[0])) return sanitizeBundleToken(parts[0]);
    } catch (_) {}
    return "";
  }

  function eromeAlbumFromUrl(url) {
    try {
      const u = new URL(String(url || ""));
      const m = (u.pathname || "").match(/\/a\/([^/?#]+)/i);
      if (m && m[1]) return sanitizeBundleToken(m[1]);
    } catch (_) {}
    return "";
  }

  function motherlessGalleryFromUrl(url) {
    try {
      const u = new URL(String(url || ""));
      const m = (u.pathname || "").match(/\/(G[A-Za-z0-9]{4,})(?:\/|$)/i);
      if (m && m[1]) return sanitizeBundleToken(m[1].toUpperCase());
    } catch (_) {}
    return "";
  }

  function fapelloSlugFromUrl(url) {
    try {
      const u = new URL(String(url || ""));
      const path = u.pathname || "";
      const cdn = path.match(/\/content\/m\/r\/([^/]+)/i);
      if (cdn && cdn[1]) return sanitizeBundleToken(cdn[1]);
      const parts = path.replace(/\/+$/, "").split("/").filter(Boolean);
      if (parts.length === 1 && parts[0] && !/^(content|search|tags)$/i.test(parts[0])) {
        return sanitizeBundleToken(parts[0]);
      }
    } catch (_) {}
    return "";
  }

  function redditSubFromUrl(url) {
    try {
      const u = new URL(String(url || ""));
      const parts = (u.pathname || "").split("/").filter(Boolean);
      const i = parts.indexOf("r");
      if (i >= 0 && parts[i + 1]) return sanitizeBundleToken(parts[i + 1]);
    } catch (_) {}
    return "";
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

  /**
   * Infer human-readable zip tokens from page URL, title, and per-item hints.
   * @returns {{ name: string, site: string, gallery: string, title: string, profileName: string }}
   */
  function inferZipContext(input) {
    const ctx = input && typeof input === "object" ? input : {};
    const sourceUrl = String(ctx.sourceUrl || ctx.url || "").trim();
    const pageTitle = String(ctx.pageTitle || ctx.title || "").trim();
    const hints = ctx.itemHints && typeof ctx.itemHints === "object" ? ctx.itemHints : {};
    let site = "";
    let gallery = "";
    let title = cleanPageTitle(pageTitle);
    let profileName = sanitizeBundleToken(hints.profileName || hints.tbccZipProfileName || "");

    try {
      const u = new URL(sourceUrl.split("#")[0]);
      const host = u.hostname || "";
      site = hostSiteLabel(host);
      if (host.includes("onlyfans")) {
        const creator = onlyfansCreatorFromUrl(sourceUrl);
        if (creator) profileName = profileName || creator;
      } else if (host.includes("erome")) {
        gallery = eromeAlbumFromUrl(sourceUrl);
        if (!title && gallery) title = gallery;
      } else if (host.includes("motherless")) {
        gallery = motherlessGalleryFromUrl(sourceUrl);
        if (gallery) profileName = profileName || gallery;
      } else if (host.includes("fapello")) {
        const slug = fapelloSlugFromUrl(sourceUrl);
        if (slug) profileName = profileName || slug;
      } else if (host.includes("reddit")) {
        const sub = redditSubFromUrl(sourceUrl);
        if (sub) profileName = profileName || sub;
      } else if (host.includes("twitter") || host === "x.com") {
        const handle = profileNameFromSourceUrl(sourceUrl);
        if (handle) profileName = profileName || handle;
      }
    } catch (_) {}

    if (!profileName && title) profileName = title;
    if (!profileName && gallery) profileName = gallery;
    if (!profileName && site) profileName = site;
    if (!profileName || /^media$/i.test(profileName)) profileName = randomFiveId();

    return {
      name: profileName,
      site: site || "web",
      gallery: gallery || "",
      title: title || profileName,
      profileName,
      sourceUrl,
    };
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

  function expandBundleTemplate(template, ctx) {
    const tpl = String(template || DEFAULT_BUNDLE_TEMPLATE).trim() || DEFAULT_BUNDLE_TEMPLATE;
    const zip = inferZipContext(ctx);
    const name = sanitizeBundleToken((ctx && (ctx.name || ctx.profileName)) || zip.name) || zip.name;
    const site = sanitizeBundleToken((ctx && ctx.site) || zip.site) || zip.site;
    const gallery = sanitizeBundleToken((ctx && ctx.gallery) || zip.gallery) || "";
    const title = sanitizeBundleToken((ctx && ctx.seoTitle) || (ctx && ctx.title) || zip.title) || name;
    const date = new Date().toISOString().slice(0, 10).replace(/-/g, "");
    let out = tpl
      .replace(/\{name\}/gi, name)
      .replace(/\{profile\}/gi, name)
      .replace(/\{site\}/gi, site)
      .replace(/\{gallery\}/gi, gallery || name)
      .replace(/\{title\}/gi, title)
      .replace(/\{date\}/gi, date);
    if (!/\.\w{2,5}$/i.test(out)) out = out + ".zip";
    return out.replace(/[<>:"/\\|?*\x00-\x1f]+/g, "_").slice(0, 180);
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
   * Prefer model/gallery/site from inferZipContext; template tokens: {name} {site} {gallery} {title} {date}.
   */
  function buildBundleArchiveFilename(ctx) {
    const custom = ctx && ctx.bundleTemplate && String(ctx.bundleTemplate).trim();
    if (custom) return expandBundleTemplate(custom, ctx);
    const zip = inferZipContext(ctx);
    let token = sanitizeBundleToken((ctx && (ctx.name || ctx.profileName)) || zip.name);
    if (!token || /^media$/i.test(token)) token = zip.name;
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

  /**
   * Destination-aware archive / object names for the zip flywheel.
   * @param {"downloads_promo"|"host_gated"|"loot_modifier"|"shop_bundle"|"video_title"|"archive_uuid"} dest
   * @param {{ name?: string, profileName?: string, sourceUrl?: string, seoTitle?: string, ext?: string, bundleTemplate?: string }} ctx
   */
  function buildDestinationFilename(dest, ctx) {
    const d = String(dest || "downloads_promo").trim().toLowerCase();
    const ext =
      String((ctx && ctx.ext) || "zip")
        .replace(/^\./, "")
        .toLowerCase() || "zip";
    const zip = inferZipContext(ctx);
    const token =
      sanitizeBundleToken((ctx && (ctx.name || ctx.profileName)) || "") || zip.name || randomFiveId();

    if (d === "downloads_promo") {
      return downloadPathForBundle(ctx);
    }
    if (d === "video_title") {
      const seo = sanitizeBundleToken((ctx && ctx.seoTitle) || zip.title || token) || token;
      return `${seo} · ${BRAND_HANDLE}.${ext}`.replace(/[<>:"/\\|?*\x00-\x1f]+/g, "_").slice(0, 180);
    }
    if (d === "archive_uuid") {
      const ts = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
      const id = randomFiveId() + randomFiveId().slice(0, 3);
      return `aof_${ts}_${id}.${ext}`;
    }
    if (d === "host_gated" || d === "loot_modifier" || d === "shop_bundle") {
      const id = randomFiveId();
      const leaf = sanitizeSegment(token).slice(0, 40) || "pack";
      return `${leaf}_${id}.${ext}`;
    }
    return downloadPathForBundle(ctx);
  }

  /** v1 flywheel destinations (skip inbox/watch). */
  const FLYWHEEL_DESTINATIONS = {
    downloads_promo: "downloads_promo",
    host_gated: "host_gated",
    loot_modifier: "loot_modifier",
    shop_bundle: "shop_bundle",
  };

  function buildExportFilename(input) {
    const ctx = input && typeof input === "object" ? input : {};
    const index1 = Math.max(1, ctx.index != null ? Number(ctx.index) : 1);
    const baseName = String(ctx.baseName || "media").trim() || "media";
    const heuristic = ctx.heuristicNaming !== false;
    const tpl = String(ctx.template || DEFAULT_TEMPLATE).trim() || DEFAULT_TEMPLATE;
    if (!heuristic) {
      const pad = String(index1).padStart(3, "0");
      const ext = extFromContext(ctx);
      const safe = sanitizeSegment(baseName) || "media";
      const hasExt = /\.\w{2,5}$/i.test(safe);
      const leaf = hasExt ? safe : safe + "." + ext;
      return (pad + "_" + leaf).replace(/[^\w.\-]+/g, "_").slice(0, 180);
    }
    const zip = inferZipContext({
      sourceUrl: ctx.sourceUrl || "",
      pageTitle: ctx.pageTitle || "",
      itemHints: { profileName: ctx.profileHint || ctx.profileName || "" },
    });
    const name =
      sanitizeSegment(ctx.profileHint || ctx.profileName || zip.name) || zip.name || "media";
    return buildZipFilename(tpl, {
      name,
      index: index1,
      baseName,
      ext: ctx.ext,
      mime: ctx.mime,
    });
  }

  /** Prefix Downloads/tbcc/ for gallery + context-menu exports. */
  function tbccDownloadFolderPath(leaf) {
    const clean = String(leaf || "media")
      .replace(/[<>:"/\\|?*\x00-\x1f]+/g, "_")
      .replace(/^\/+/, "")
      .replace(/^tbcc\//i, "");
    return "tbcc/" + clean;
  }

  const api = {
    DEFAULT_TEMPLATE,
    DEFAULT_BUNDLE_TEMPLATE,
    BRAND_HANDLE,
    ALLMYLINKS_SLOT,
    BUNDLE_PREFIX,
    FLYWHEEL_DESTINATIONS,
    profileNameFromSourceUrl,
    inferZipContext,
    buildZipFilename,
    buildBundleArchiveFilename,
    expandBundleTemplate,
    downloadPathForBundle,
    buildDestinationFilename,
    buildExportFilename,
    tbccDownloadFolderPath,
    sanitizeSegment,
    sanitizeBundleToken,
    randomFiveId,
    hostSiteLabel,
    cleanPageTitle,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = { TbccZipNaming: api };
  } else {
    root.TbccZipNaming = api;
  }
})(typeof globalThis !== "undefined" ? globalThis : typeof self !== "undefined" ? self : this);
