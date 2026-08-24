/**
 * Raster export for TBCC (sidebar downloads, imports, Saved Messages, ZIP).
 * Browser canvas decode/encode — no ImageMagick in the extension.
 *
 * Gallery ⚙ → Options → Format + export size controls (tbcc_gallery_settings).
 *
 * Critical: many CDNs label WebP as .jpg / image/jpeg. Always sniff magic bytes before
 * renaming — otherwise Windows Photos reports "unsupported file format".
 */
(function (root) {
  const STORAGE_SETTINGS = "tbcc_gallery_settings";
  const DEFAULT_QUALITY = 0.92;
  const MAX_EDGE = 16384;
  const VALID_FORMATS = ["original", "jpeg", "jpeg_all", "png", "webp"];
  const RASTER_KINDS = new Set(["jpeg", "png", "gif", "webp", "avif"]);

  let _settingsCache = null;

  function tbccResetWebpSettingsCache() {
    _settingsCache = null;
  }

  if (typeof chrome !== "undefined" && chrome.storage && chrome.storage.onChanged) {
    chrome.storage.onChanged.addListener((changes, area) => {
      if (area === "local" && changes[STORAGE_SETTINGS]) tbccResetWebpSettingsCache();
    });
  }

  function tbccNormalizeMaxEdge(v) {
    const n = parseInt(String(v || 0), 10);
    if (!Number.isFinite(n) || n <= 0) return 0;
    return Math.max(64, Math.min(MAX_EDGE, n));
  }

  function tbccNormalizeQuality(v) {
    const n = typeof v === "number" ? v : parseFloat(String(v || DEFAULT_QUALITY));
    if (!Number.isFinite(n)) return DEFAULT_QUALITY;
    return Math.max(0.5, Math.min(0.98, n));
  }

  function tbccNormalizeMaxBytes(v) {
    const n = parseInt(String(v || 0), 10);
    if (!Number.isFinite(n) || n <= 0) return 0;
    return Math.max(1024, n);
  }

  async function tbccLoadExportSettings() {
    if (_settingsCache !== null) return _settingsCache;
    try {
      const o = await chrome.storage.local.get(STORAGE_SETTINGS);
      const s = o[STORAGE_SETTINGS] && typeof o[STORAGE_SETTINGS] === "object" ? o[STORAGE_SETTINGS] : {};
      _settingsCache = {
        format: VALID_FORMATS.includes(s.format) ? s.format : "jpeg",
        exportMaxEdge: tbccNormalizeMaxEdge(s.exportMaxEdge),
        jpegQuality: tbccNormalizeQuality(s.jpegQuality),
        exportMaxBytes: tbccNormalizeMaxBytes(s.exportMaxBytes),
      };
    } catch (_) {
      _settingsCache = {
        format: "jpeg",
        exportMaxEdge: 0,
        jpegQuality: DEFAULT_QUALITY,
        exportMaxBytes: 0,
      };
    }
    return _settingsCache;
  }

  async function tbccWebpToJpgEnabled() {
    const s = await tbccLoadExportSettings();
    return s.format === "jpeg" || s.format === "jpeg_all";
  }

  function tbccTargetKindFromFormat(format) {
    if (format === "jpeg" || format === "jpeg_all") return "jpeg";
    if (format === "png") return "png";
    if (format === "webp") return "webp";
    return null;
  }

  function tbccMimeForKind(kind) {
    if (kind === "jpeg") return "image/jpeg";
    if (kind === "png") return "image/png";
    if (kind === "webp") return "image/webp";
    if (kind === "gif") return "image/gif";
    return "application/octet-stream";
  }

  function tbccUrlLooksLikeWebp(url) {
    const u = String(url || "").toLowerCase();
    if (!u) return false;
    if (/\.webp(\?|#|$)/i.test(u)) return true;
    try {
      const p = new URL(u).pathname.toLowerCase();
      if (p.endsWith(".webp")) return true;
      if (/-webp\.\d+\/?$/i.test(p)) return true;
    } catch (_) {}
    return false;
  }

  /**
   * Sniff container from the first bytes (ignores wrong Content-Type / .jpg names).
   * @returns {"jpeg"|"png"|"gif"|"webp"|"avif"|"unknown"}
   */
  function tbccSniffImageKindFromBytes(u8) {
    if (!u8 || u8.length < 12) return "unknown";
    if (u8[0] === 0xff && u8[1] === 0xd8 && u8[2] === 0xff) return "jpeg";
    if (u8[0] === 0x89 && u8[1] === 0x50 && u8[2] === 0x4e && u8[3] === 0x47) return "png";
    if (u8[0] === 0x47 && u8[1] === 0x49 && u8[2] === 0x46) return "gif";
    if (
      u8[0] === 0x52 &&
      u8[1] === 0x49 &&
      u8[2] === 0x46 &&
      u8[3] === 0x46 &&
      u8[8] === 0x57 &&
      u8[9] === 0x45 &&
      u8[10] === 0x42 &&
      u8[11] === 0x50
    ) {
      return "webp";
    }
    if (u8[4] === 0x66 && u8[5] === 0x74 && u8[6] === 0x79 && u8[7] === 0x70) {
      const brand = String.fromCharCode(u8[8], u8[9], u8[10], u8[11]).toLowerCase();
      if (brand === "avif" || brand === "avis" || brand === "mif1" || brand === "heic" || brand === "heix") {
        return "avif";
      }
    }
    return "unknown";
  }

  async function tbccSniffImageKind(blob) {
    if (!blob || !blob.size) return "unknown";
    try {
      const buf = await blob.slice(0, 16).arrayBuffer();
      return tbccSniffImageKindFromBytes(new Uint8Array(buf));
    } catch (_) {
      return "unknown";
    }
  }

  function tbccExtForKind(kind) {
    if (kind === "jpeg") return ".jpg";
    if (kind === "png") return ".png";
    if (kind === "gif") return ".gif";
    if (kind === "webp") return ".webp";
    if (kind === "avif") return ".avif";
    return "";
  }

  function tbccBlobLooksLikeWebp(blob, url, name, sniffed) {
    if (sniffed === "webp" || sniffed === "avif") return true;
    if (!blob) return false;
    const mime = String(blob.type || "").toLowerCase();
    if (mime === "image/webp" || mime === "image/avif") return true;
    const n = String(name || "").toLowerCase();
    if (/\.webp$/i.test(n) || /\.avif$/i.test(n)) return true;
    return tbccUrlLooksLikeWebp(url);
  }

  function tbccReplaceExtToJpg(filename) {
    const n = String(filename || "media").trim() || "media";
    if (/\.jpe?g$/i.test(n)) return n;
    const base = n.replace(/\.[^.\\/]+$/, "") || "media";
    return base + ".jpg";
  }

  function tbccReplaceExt(filename, extWithDot) {
    const n = String(filename || "media").trim() || "media";
    const ext = extWithDot.startsWith(".") ? extWithDot : "." + extWithDot;
    const base = n.replace(/\.[^.\\/]+$/, "") || "media";
    return base + ext;
  }

  function tbccFilenameForKind(filename, kind) {
    if (kind === "jpeg") return tbccReplaceExtToJpg(filename);
    const ext = tbccExtForKind(kind);
    return ext ? tbccReplaceExt(filename, ext) : String(filename || "media.bin");
  }

  async function tbccAlignFilenameToBlob(blob, filename) {
    const kind = await tbccSniffImageKind(blob);
    const ext = tbccExtForKind(kind);
    if (!ext) return String(filename || "media.bin");
    return tbccReplaceExt(filename || "media", ext);
  }

  function tbccCreateCanvas(w, h) {
    if (typeof OffscreenCanvas !== "undefined") {
      return new OffscreenCanvas(w, h);
    }
    if (typeof document !== "undefined") {
      const c = document.createElement("canvas");
      c.width = w;
      c.height = h;
      return c;
    }
    return null;
  }

  function tbccFitInside(w, h, maxEdge) {
    if (!maxEdge || maxEdge <= 0) return { w, h };
    const mw = Math.max(1, maxEdge);
    if (w <= mw && h <= mw) return { w, h };
    const scale = Math.min(mw / w, mw / h);
    return {
      w: Math.max(1, Math.round(w * scale)),
      h: Math.max(1, Math.round(h * scale)),
    };
  }

  async function tbccCanvasToBlob(canvas, mimeType, quality) {
    const q = typeof quality === "number" ? quality : DEFAULT_QUALITY;
    const opts = { type: mimeType };
    if (mimeType === "image/jpeg" || mimeType === "image/webp") opts.quality = q;
    if (canvas.convertToBlob) {
      return canvas.convertToBlob(opts);
    }
    return new Promise((resolve, reject) => {
      canvas.toBlob(
        (b) => (b ? resolve(b) : reject(new Error("Canvas encode failed"))),
        mimeType,
        mimeType === "image/jpeg" || mimeType === "image/webp" ? q : undefined
      );
    });
  }

  async function tbccRasterBlobViaCanvas(blob, { targetKind, maxEdge, quality, srcW, srcH }) {
    if (!blob || !blob.size) throw new Error("Empty image blob");
    const bmp = await createImageBitmap(blob);
    try {
      const sw = srcW || bmp.width;
      const sh = srcH || bmp.height;
      if (!sw || !sh || sw > MAX_EDGE || sh > MAX_EDGE) {
        throw new Error("Image dimensions out of range");
      }
      const fitted = tbccFitInside(sw, sh, maxEdge);
      const canvas = tbccCreateCanvas(fitted.w, fitted.h);
      if (!canvas) throw new Error("Canvas not available");
      const ctx = canvas.getContext("2d");
      if (!ctx) throw new Error("Canvas 2d context unavailable");
      ctx.drawImage(bmp, 0, 0, sw, sh, 0, 0, fitted.w, fitted.h);
      const mime = tbccMimeForKind(targetKind);
      const out = await tbccCanvasToBlob(canvas, mime, quality);
      const kind2 = await tbccSniffImageKind(out);
      if (kind2 !== targetKind) {
        throw new Error("Encode produced unexpected format");
      }
      return out;
    } finally {
      bmp.close();
    }
  }

  async function tbccEnforceMaxBytes(sourceBlob, targetKind, maxBytes, quality, maxEdge) {
    if (!maxBytes || !sourceBlob || sourceBlob.size <= maxBytes) return sourceBlob;

    let q = quality;
    let edge = maxEdge || 0;
    let kind = targetKind;
    let last = sourceBlob;

    for (let attempt = 0; attempt < 14; attempt++) {
      try {
        const bmp = await createImageBitmap(sourceBlob);
        const sw = bmp.width;
        const sh = bmp.height;
        bmp.close();
        if (!edge && (sw > 2048 || sh > 2048)) {
          edge = 2048;
        } else if (edge > 64) {
          edge = Math.max(64, Math.floor(edge * 0.88));
        } else if (kind === "png") {
          kind = "jpeg";
          q = Math.min(q, 0.88);
          edge = edge || 2048;
        } else {
          q = Math.max(0.45, q - 0.06);
        }
        last = await tbccRasterBlobViaCanvas(sourceBlob, {
          targetKind: kind,
          maxEdge: edge,
          quality: q,
          srcW: sw,
          srcH: sh,
        });
        if (last.size <= maxBytes) return last;
        if (kind === "jpeg" || kind === "webp") {
          q = Math.max(0.45, q - 0.07);
        }
      } catch (e) {
        console.warn("[TBCC] export max-bytes pass failed:", e);
        break;
      }
    }
    return last;
  }

  function tbccFormatNeedsFormatChange(format, sniffed, blob, url, name) {
    if (!format || format === "original") return false;
    if (!RASTER_KINDS.has(sniffed)) return false;
    if (format === "jpeg") {
      return tbccBlobLooksLikeWebp(blob, url, name, sniffed);
    }
    const target = tbccTargetKindFromFormat(format);
    if (!target) return false;
    return sniffed !== target;
  }

  function tbccNeedsCanvasExport(format, sniffed, blob, url, name, maxEdge, maxBytes) {
    if (!RASTER_KINDS.has(sniffed)) return false;
    if (tbccFormatNeedsFormatChange(format, sniffed, blob, url, name)) return true;
    if (maxEdge > 0) return true;
    if (maxBytes > 0 && blob && blob.size > maxBytes) return true;
    if (format === "jpeg_all" || format === "png" || format === "webp") {
      const target = tbccTargetKindFromFormat(format);
      if (target && sniffed === target && (maxEdge > 0 || (maxBytes > 0 && blob.size > maxBytes))) {
        return true;
      }
      if (format === "jpeg_all" && sniffed === "jpeg" && (maxEdge > 0 || maxBytes > 0)) return true;
    }
    return false;
  }

  /** True when bulk/all-raster export modes or size caps require buffered fetch. */
  async function tbccRasterExportEnabled() {
    const s = await tbccLoadExportSettings();
    if (s.format === "jpeg_all" || s.format === "png" || s.format === "webp") return true;
    if (s.exportMaxEdge > 0 || s.exportMaxBytes > 0) return true;
    return false;
  }

  async function tbccLegacyWebpJpegOnly() {
    const s = await tbccLoadExportSettings();
    return s.format === "jpeg";
  }

  async function tbccConvertWebpBlobToJpeg(blob, quality) {
    return tbccRasterBlobViaCanvas(blob, { targetKind: "jpeg", maxEdge: 0, quality });
  }

  /**
   * Export raster blob per gallery settings (format, max edge, JPEG quality, max bytes).
   * opts.forceFormat overrides stored format; opts.force skips settings read for format only.
   */
  async function tbccEnsureExportBlob(blob, opts) {
    const url = opts && opts.url;
    let name = (opts && opts.name) || "media.webp";
    const stored = await tbccLoadExportSettings();
    const format = (opts && opts.forceFormat) || (opts && opts.force === true ? "jpeg" : stored.format);
    const maxEdge = opts && opts.maxEdge != null ? tbccNormalizeMaxEdge(opts.maxEdge) : stored.exportMaxEdge;
    const maxBytes = opts && opts.maxBytes != null ? tbccNormalizeMaxBytes(opts.maxBytes) : stored.exportMaxBytes;
    let quality =
      opts && opts.quality != null ? tbccNormalizeQuality(opts.quality) : stored.jpegQuality;

    const sniffed = await tbccSniffImageKind(blob);

    if (sniffed === "jpeg" && format === "jpeg" && !maxEdge && !maxBytes) {
      return { blob, name: tbccReplaceExtToJpg(name), converted: false, kind: "jpeg" };
    }

    if (!tbccNeedsCanvasExport(format, sniffed, blob, url, name, maxEdge, maxBytes)) {
      const aligned = await tbccAlignFilenameToBlob(blob, name);
      return { blob, name: aligned, converted: false, kind: sniffed };
    }

    let targetKind = tbccTargetKindFromFormat(format);
    if (format === "jpeg") {
      targetKind = "jpeg";
    } else if (format === "original") {
      targetKind = RASTER_KINDS.has(sniffed) ? sniffed : "jpeg";
      if (targetKind === "gif") targetKind = "png";
      if (targetKind === "avif") targetKind = "jpeg";
    }
    if (!targetKind || !RASTER_KINDS.has(sniffed)) {
      const aligned = await tbccAlignFilenameToBlob(blob, name);
      return { blob, name: aligned, converted: false, kind: sniffed };
    }
    if (sniffed === "unknown") {
      const aligned = await tbccAlignFilenameToBlob(blob, name);
      return { blob, name: aligned, converted: false, kind: sniffed };
    }

    try {
      let out = await tbccRasterBlobViaCanvas(blob, { targetKind, maxEdge, quality });
      if (maxBytes > 0 && out.size > maxBytes) {
        out = await tbccEnforceMaxBytes(out, targetKind, maxBytes, quality, maxEdge);
        const k2 = await tbccSniffImageKind(out);
        targetKind = k2 !== "unknown" ? k2 : targetKind;
      }
      const kind2 = await tbccSniffImageKind(out);
      if (kind2 === "unknown") throw new Error("Export encode failed sniff");
      return {
        blob: new Blob([await out.arrayBuffer()], { type: tbccMimeForKind(kind2) }),
        name: tbccFilenameForKind(name, kind2),
        converted: true,
        kind: kind2,
      };
    } catch (e) {
      console.warn("[TBCC] Export convert failed, keeping original bytes + real extension:", e);
      const aligned = await tbccAlignFilenameToBlob(blob, name);
      return { blob, name: aligned, converted: false, kind: sniffed };
    }
  }

  /**
   * Legacy WebP→JPEG entry (delegates to tbccEnsureExportBlob; force=true uses jpeg path).
   */
  async function tbccEnsureJpegBlob(blob, opts) {
    const url = opts && opts.url;
    const name = (opts && opts.name) || "media.webp";
    const force = opts && opts.force;
    if (force) {
      return tbccEnsureExportBlob(blob, { ...opts, forceFormat: "jpeg" });
    }
    const stored = await tbccLoadExportSettings();
    if (stored.format === "jpeg") {
      const sniffed = await tbccSniffImageKind(blob);
      if (sniffed === "jpeg") {
        return { blob, name: tbccReplaceExtToJpg(name), converted: false, kind: "jpeg" };
      }
      const needs = tbccBlobLooksLikeWebp(blob, url, name, sniffed);
      if (!needs && !stored.exportMaxEdge && !stored.exportMaxBytes) {
        const aligned = await tbccAlignFilenameToBlob(blob, name);
        return { blob, name: aligned, converted: false, kind: sniffed };
      }
    }
    return tbccEnsureExportBlob(blob, opts);
  }

  async function tbccEnsureExportArrayBuffer(arrayBuffer, url, name) {
    const sniff = tbccSniffImageKindFromBytes(new Uint8Array(arrayBuffer.slice(0, 16)));
    const type =
      sniff === "webp"
        ? "image/webp"
        : sniff === "jpeg"
          ? "image/jpeg"
          : sniff === "png"
            ? "image/png"
            : "application/octet-stream";
    const blob = new Blob([arrayBuffer], { type });
    const r = await tbccEnsureExportBlob(blob, { url, name });
    if (!r.converted) return { buffer: arrayBuffer, name: r.name, converted: false, type };
    return {
      buffer: await r.blob.arrayBuffer(),
      name: r.name,
      converted: true,
      type: r.blob.type || type,
    };
  }

  async function tbccEnsureJpegArrayBuffer(arrayBuffer, url, name) {
    const r = await tbccEnsureExportArrayBuffer(arrayBuffer, url, name);
    return { buffer: r.buffer, name: r.name, converted: r.converted };
  }

  const api = {
    tbccWebpToJpgEnabled,
    tbccLoadExportSettings,
    tbccRasterExportEnabled,
    tbccLegacyWebpJpegOnly,
    tbccTargetKindFromFormat,
    tbccUrlLooksLikeWebp,
    tbccBlobLooksLikeWebp,
    tbccReplaceExtToJpg,
    tbccReplaceExt,
    tbccFilenameForKind,
    tbccSniffImageKind,
    tbccSniffImageKindFromBytes,
    tbccAlignFilenameToBlob,
    tbccExtForKind,
    tbccConvertWebpBlobToJpeg,
    tbccEnsureExportBlob,
    tbccEnsureExportArrayBuffer,
    tbccEnsureJpegBlob,
    tbccEnsureJpegArrayBuffer,
    tbccResetWebpSettingsCache,
    tbccNormalizeMaxEdge,
    tbccNormalizeQuality,
    tbccNormalizeMaxBytes,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  } else {
    root.TbccWebp = api;
  }
})(typeof globalThis !== "undefined" ? globalThis : typeof self !== "undefined" ? self : this);
