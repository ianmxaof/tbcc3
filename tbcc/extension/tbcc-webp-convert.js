/**
 * WebP → JPEG conversion for TBCC (sidebar downloads, imports, Saved Messages, ZIP).
 * Browser canvas decode — no ImageMagick required in the extension.
 *
 * Enable via Gallery ⚙ → Format → "Convert to JPG" (tbcc_gallery_settings.format === "jpeg").
 *
 * Critical: many CDNs label WebP as .jpg / image/jpeg. Always sniff magic bytes before
 * renaming to .jpg — otherwise Windows Photos reports "unsupported file format".
 */
(function (root) {
  const STORAGE_SETTINGS = "tbcc_gallery_settings";
  const DEFAULT_QUALITY = 0.92;
  const MAX_EDGE = 16384;

  let _jpegModeCache = null;

  function tbccResetWebpSettingsCache() {
    _jpegModeCache = null;
  }

  if (typeof chrome !== "undefined" && chrome.storage && chrome.storage.onChanged) {
    chrome.storage.onChanged.addListener((changes, area) => {
      if (area === "local" && changes[STORAGE_SETTINGS]) tbccResetWebpSettingsCache();
    });
  }

  async function tbccWebpToJpgEnabled() {
    if (_jpegModeCache !== null) return _jpegModeCache;
    try {
      const o = await chrome.storage.local.get(STORAGE_SETTINGS);
      const s = o[STORAGE_SETTINGS] && typeof o[STORAGE_SETTINGS] === "object" ? o[STORAGE_SETTINGS] : {};
      _jpegModeCache = s.format === "jpeg";
    } catch (_) {
      _jpegModeCache = true;
    }
    return _jpegModeCache;
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
    // JPEG
    if (u8[0] === 0xff && u8[1] === 0xd8 && u8[2] === 0xff) return "jpeg";
    // PNG
    if (u8[0] === 0x89 && u8[1] === 0x50 && u8[2] === 0x4e && u8[3] === 0x47) return "png";
    // GIF
    if (u8[0] === 0x47 && u8[1] === 0x49 && u8[2] === 0x46) return "gif";
    // WEBP: RIFF....WEBP
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
    // AVIF / HEIF: ftyp....avif|avis|heic
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

  /**
   * Align filename extension with real bytes. Never claim .jpg for WebP payload.
   */
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

  async function tbccCanvasToJpegBlob(canvas, quality) {
    const q = typeof quality === "number" ? quality : DEFAULT_QUALITY;
    if (canvas.convertToBlob) {
      return canvas.convertToBlob({ type: "image/jpeg", quality: q });
    }
    return new Promise((resolve, reject) => {
      canvas.toBlob(
        (b) => (b ? resolve(b) : reject(new Error("WebP→JPEG encode failed"))),
        "image/jpeg",
        q
      );
    });
  }

  async function tbccConvertWebpBlobToJpeg(blob, quality) {
    if (!blob || !blob.size) throw new Error("Empty image blob");
    const bmp = await createImageBitmap(blob);
    try {
      const w = bmp.width;
      const h = bmp.height;
      if (!w || !h || w > MAX_EDGE || h > MAX_EDGE) {
        throw new Error("Image dimensions out of range");
      }
      const canvas = tbccCreateCanvas(w, h);
      if (!canvas) throw new Error("Canvas not available");
      const ctx = canvas.getContext("2d");
      if (!ctx) throw new Error("Canvas 2d context unavailable");
      ctx.drawImage(bmp, 0, 0, w, h);
      return await tbccCanvasToJpegBlob(canvas, quality);
    } finally {
      bmp.close();
    }
  }

  /**
   * When "Convert to JPG" is on and input is WebP/AVIF (by magic or hint), return JPEG blob + .jpg name.
   * On failure: keep original bytes and an extension that matches those bytes (never fake .jpg).
   */
  async function tbccEnsureJpegBlob(blob, opts) {
    const url = opts && opts.url;
    let name = (opts && opts.name) || "media.webp";
    const force = opts && opts.force;
    const sniffed = await tbccSniffImageKind(blob);
    const wantJpeg = force || (await tbccWebpToJpgEnabled());

    // Already real JPEG
    if (sniffed === "jpeg") {
      return { blob, name: tbccReplaceExtToJpg(name), converted: false, kind: "jpeg" };
    }

    const needsConvert = tbccBlobLooksLikeWebp(blob, url, name, sniffed);
    if (!wantJpeg || !needsConvert) {
      const aligned = await tbccAlignFilenameToBlob(blob, name);
      return { blob, name: aligned, converted: false, kind: sniffed };
    }

    try {
      const jpg = await tbccConvertWebpBlobToJpeg(blob, opts && opts.quality);
      const kind2 = await tbccSniffImageKind(jpg);
      if (kind2 !== "jpeg") {
        throw new Error("JPEG encode produced non-JPEG bytes");
      }
      return {
        blob: new Blob([await jpg.arrayBuffer()], { type: "image/jpeg" }),
        name: tbccReplaceExtToJpg(name),
        converted: true,
        kind: "jpeg",
      };
    } catch (e) {
      console.warn("[TBCC] WebP→JPEG failed, keeping original bytes + real extension:", e);
      const aligned = await tbccAlignFilenameToBlob(blob, name);
      return { blob, name: aligned, converted: false, kind: sniffed };
    }
  }

  async function tbccEnsureJpegArrayBuffer(arrayBuffer, url, name) {
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
    const r = await tbccEnsureJpegBlob(blob, { url, name });
    if (!r.converted) return { buffer: arrayBuffer, name: r.name, converted: false };
    return { buffer: await r.blob.arrayBuffer(), name: r.name, converted: true };
  }

  const api = {
    tbccWebpToJpgEnabled,
    tbccUrlLooksLikeWebp,
    tbccBlobLooksLikeWebp,
    tbccReplaceExtToJpg,
    tbccReplaceExt,
    tbccSniffImageKind,
    tbccSniffImageKindFromBytes,
    tbccAlignFilenameToBlob,
    tbccExtForKind,
    tbccConvertWebpBlobToJpeg,
    tbccEnsureJpegBlob,
    tbccEnsureJpegArrayBuffer,
    tbccResetWebpSettingsCache,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  } else {
    root.TbccWebp = api;
  }
})(typeof globalThis !== "undefined" ? globalThis : typeof self !== "undefined" ? self : this);
