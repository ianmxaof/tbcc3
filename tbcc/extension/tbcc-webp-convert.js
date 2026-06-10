/**
 * WebP → JPEG conversion for TBCC (sidebar downloads, imports, Saved Messages, ZIP).
 * Browser canvas decode — no ImageMagick required in the extension.
 *
 * Enable via Gallery ⚙ → Format → "Convert to JPG" (tbcc_gallery_settings.format === "jpeg").
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
      const s = (o[STORAGE_SETTINGS] && typeof o[STORAGE_SETTINGS] === "object") ? o[STORAGE_SETTINGS] : {};
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

  function tbccBlobLooksLikeWebp(blob, url, name) {
    if (!blob) return false;
    const mime = String(blob.type || "").toLowerCase();
    if (mime === "image/webp") return true;
    const n = String(name || "").toLowerCase();
    if (/\.webp$/i.test(n)) return true;
    return tbccUrlLooksLikeWebp(url);
  }

  function tbccReplaceExtToJpg(filename) {
    const n = String(filename || "media").trim() || "media";
    if (/\.jpe?g$/i.test(n)) return n;
    const base = n.replace(/\.[^.\\/]+$/, "") || "media";
    return base + ".jpg";
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

  /**
   * Decode WebP (or any image blob) and re-encode as JPEG.
   * @returns {Promise<Blob>}
   */
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
   * When "Convert to JPG" is on and input is WebP, return JPEG blob + .jpg filename.
   * @returns {Promise<{ blob: Blob, name: string, converted: boolean }>}
   */
  async function tbccEnsureJpegBlob(blob, opts) {
    const url = opts && opts.url;
    const name = (opts && opts.name) || "media.webp";
    const force = opts && opts.force;
    if (!force && !(await tbccWebpToJpgEnabled())) {
      return { blob, name, converted: false };
    }
    if (!tbccBlobLooksLikeWebp(blob, url, name)) {
      return { blob, name, converted: false };
    }
    try {
      const jpg = await tbccConvertWebpBlobToJpeg(blob, opts && opts.quality);
      return { blob: jpg, name: tbccReplaceExtToJpg(name), converted: true };
    } catch (e) {
      console.warn("[TBCC] WebP→JPEG failed, using original:", e);
      return { blob, name, converted: false };
    }
  }

  async function tbccEnsureJpegArrayBuffer(arrayBuffer, url, name) {
    const blob = new Blob([arrayBuffer], { type: "image/webp" });
    const r = await tbccEnsureJpegBlob(blob, { url, name });
    if (!r.converted) return { buffer: arrayBuffer, name: r.name, converted: false };
    return { buffer: await r.blob.arrayBuffer(), name: r.name, converted: true };
  }

  const api = {
    tbccWebpToJpgEnabled,
    tbccUrlLooksLikeWebp,
    tbccBlobLooksLikeWebp,
    tbccReplaceExtToJpg,
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
