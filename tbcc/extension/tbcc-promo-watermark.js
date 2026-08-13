/**
 * Promo text watermark — shared settings + local canvas burn-in (images).
 * Filename naming uses tbcc-zip-naming.js (same gallery settings).
 */
(function (root) {
  const POSITIONS = [
    "bottom_right",
    "upper_right",
    "upper_left",
    "bottom_left",
    "center_diagonal",
  ];

  const DEFAULT_PROMO_WATERMARK = {
    enabled: true,
    text: "telegram.me/aofmainhub",
    textSecondary: "",
    textTertiary: "",
    opacity: 0.58,
    color: "#ffffff",
    position: "bottom_right",
    mode: "rotate",
    sizeRatio: 0.045,
    stripPrevious: false,
  };

  let _rotateIndex = 0;

  function clamp(n, lo, hi) {
    return Math.max(lo, Math.min(hi, n));
  }

  function normalizePromoWatermark(raw) {
    const src = raw && typeof raw === "object" ? raw : {};
    const opacity = Number(src.opacity);
    const sizeRatio = Number(src.sizeRatio != null ? src.sizeRatio : src.size_ratio);
    const position = String(src.position || DEFAULT_PROMO_WATERMARK.position).toLowerCase();
    const mode = String(src.mode || DEFAULT_PROMO_WATERMARK.mode).toLowerCase();
    return {
      enabled: src.enabled !== false,
      text: String(src.text || src.text_primary || DEFAULT_PROMO_WATERMARK.text).trim(),
      textSecondary: String(src.textSecondary || src.text_secondary || "").trim(),
      textTertiary: String(src.textTertiary || src.text_tertiary || "").trim(),
      opacity: Number.isFinite(opacity) ? clamp(opacity, 0.15, 1) : DEFAULT_PROMO_WATERMARK.opacity,
      color: String(src.color || DEFAULT_PROMO_WATERMARK.color).trim() || DEFAULT_PROMO_WATERMARK.color,
      position: POSITIONS.includes(position) ? position : DEFAULT_PROMO_WATERMARK.position,
      mode: mode === "fixed" ? "fixed" : "rotate",
      sizeRatio: Number.isFinite(sizeRatio)
        ? clamp(sizeRatio, 0.012, 0.08)
        : DEFAULT_PROMO_WATERMARK.sizeRatio,
      stripPrevious: !!src.stripPrevious || !!src.strip_previous,
    };
  }

  function promoWatermarkFromGallerySettings(settings) {
    const cfg = normalizePromoWatermark((settings && settings.promoWatermark) || {});
    if (settings && settings.skipPromoWatermark === true) {
      return { ...cfg, enabled: false };
    }
    return cfg;
  }

  function textsFromConfig(cfg) {
    const c = normalizePromoWatermark(cfg);
    return [c.text, c.textSecondary, c.textTertiary].filter(Boolean);
  }

  function parseColorHex(raw) {
    let s = String(raw || "#ffffff").trim();
    if (!s.startsWith("#")) s = "#" + s;
    const m = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(s);
    if (!m) return { r: 255, g: 255, b: 255 };
    let hex = m[1];
    if (hex.length === 3) hex = hex.split("").map((ch) => ch + ch).join("");
    return {
      r: parseInt(hex.slice(0, 2), 16),
      g: parseInt(hex.slice(2, 4), 16),
      b: parseInt(hex.slice(4, 6), 16),
    };
  }

  function fontSizeFor(w, h, sizeRatio) {
    const ratio = Number(sizeRatio) || DEFAULT_PROMO_WATERMARK.sizeRatio;
    return clamp(Math.round(Math.min(w, h) * ratio), 9, 28);
  }

  function marginPx(w, h) {
    return clamp(Math.round(Math.min(w, h) * 0.012), 4, 80);
  }

  function positionsForTexts(cfg, count) {
    const c = normalizePromoWatermark(cfg);
    if (count <= 0) return [];
    if (c.mode === "fixed") {
      const slots = [c.position, "bottom_left", "upper_left", "upper_right", "bottom_right"];
      return Array.from({ length: count }, (_, i) => slots[i % slots.length]);
    }
    const out = [];
    for (let i = 0; i < count; i++) {
      out.push(POSITIONS[(_rotateIndex + i) % POSITIONS.length]);
    }
    _rotateIndex += count;
    return out;
  }

  function anchorXY(position, w, h, tw, th, m) {
    if (position === "upper_left") return [m, m];
    if (position === "upper_right") return [w - tw - m, m];
    if (position === "bottom_left") return [m, h - th - m];
    if (position === "center_diagonal") return [(w - tw) / 2, (h - th) / 2];
    return [w - tw - m, h - th - m];
  }

  function drawTextWithShadow(ctx, x, y, text, fontSize, rgba) {
    ctx.font = `700 ${fontSize}px system-ui,Segoe UI,sans-serif`;
    ctx.textBaseline = "top";
    ctx.lineWidth = Math.max(2, Math.round(fontSize / 8));
    ctx.strokeStyle = `rgba(0,0,0,${Math.min(0.85, rgba.a + 0.15)})`;
    ctx.fillStyle = `rgba(${rgba.r},${rgba.g},${rgba.b},${rgba.a})`;
    ctx.strokeText(text, x, y);
    ctx.fillText(text, x, y);
  }

  function drawWatermarkOnCanvas(ctx, w, h, cfg) {
    const c = normalizePromoWatermark(cfg);
    const texts = textsFromConfig(c);
    if (!c.enabled || !texts.length) return;
    const rgb = parseColorHex(c.color);
    const a = clamp(Number(c.opacity) || 0.58, 0.15, 1);
    const rgba = { r: rgb.r, g: rgb.g, b: rgb.b, a };
    const fs = fontSizeFor(w, h, c.sizeRatio);
    const m = marginPx(w, h);
    const posList = positionsForTexts(c, texts.length);
    ctx.save();
    for (let i = 0; i < texts.length; i++) {
      const text = texts[i];
      const position = posList[i] || c.position;
      ctx.font = `700 ${fs}px system-ui,Segoe UI,sans-serif`;
      const tw = ctx.measureText(text).width;
      const th = fs * 1.15;
      if (position === "center_diagonal") {
        ctx.save();
        ctx.translate(w / 2, h / 2);
        ctx.rotate((-32 * Math.PI) / 180);
        drawTextWithShadow(ctx, -tw / 2, -th / 2, text, fs, rgba);
        ctx.restore();
      } else {
        const [x, y] = anchorXY(position, w, h, tw, th, m);
        drawTextWithShadow(ctx, x, y, text, fs, rgba);
      }
    }
    ctx.restore();
  }

  async function applyPromoWatermarkBlob(blob, mediaTypeHint, cfg) {
    const c = normalizePromoWatermark(cfg);
    if (!c.enabled || !textsFromConfig(c).length) return blob;
    const kind = String(mediaTypeHint || "photo").toLowerCase();
    if (kind === "video") return blob;
    if (typeof createImageBitmap !== "function" || typeof OffscreenCanvas === "undefined") {
      return blob;
    }
    const mime = String((blob && blob.type) || "image/jpeg").split(";")[0] || "image/jpeg";
    const bmp = await createImageBitmap(blob);
    try {
      const w = bmp.width || 1;
      const h = bmp.height || 1;
      const canvas = new OffscreenCanvas(w, h);
      const ctx = canvas.getContext("2d");
      if (!ctx) return blob;
      ctx.drawImage(bmp, 0, 0);
      drawWatermarkOnCanvas(ctx, w, h, c);
      const outType = mime.includes("png") ? "image/png" : "image/jpeg";
      const outBlob = await canvas.convertToBlob(
        outType === "image/png" ? { type: outType } : { type: "image/jpeg", quality: 0.92 }
      );
      return outBlob;
    } finally {
      try {
        bmp.close();
      } catch (_) {}
    }
  }

  function configToApiPayload(cfg) {
    const c = normalizePromoWatermark(cfg);
    return {
      enabled: c.enabled,
      text: c.text || null,
      text_secondary: c.textSecondary || null,
      text_tertiary: c.textTertiary || null,
      opacity: c.opacity,
      color: c.color,
      strip_previous: c.stripPrevious,
      position: c.position,
      mode: c.mode,
      size_ratio: c.sizeRatio,
    };
  }

  function appendWatermarkConfigToForm(form, cfg) {
    if (!form || !form.append) return;
    form.append("watermark_config", JSON.stringify(configToApiPayload(cfg)));
  }

  function effectiveFromApiResponse(data) {
    const eff = (data && data.effective) || data || {};
    return normalizePromoWatermark({
      enabled: eff.enabled !== false,
      text: eff.text,
      textSecondary: eff.text_secondary,
      textTertiary: eff.text_tertiary,
      opacity: eff.opacity,
      color: eff.color,
      position: eff.position,
      mode: eff.mode,
      sizeRatio: eff.size_ratio,
      stripPrevious: eff.strip_previous,
    });
  }

  const api = {
    POSITIONS,
    DEFAULT_PROMO_WATERMARK,
    normalizePromoWatermark,
    promoWatermarkFromGallerySettings,
    textsFromConfig,
    configToApiPayload,
    appendWatermarkConfigToForm,
    effectiveFromApiResponse,
    applyPromoWatermarkBlob,
    drawWatermarkOnCanvas,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = { TbccPromoWatermark: api };
  } else {
    root.TbccPromoWatermark = api;
  }
})(typeof globalThis !== "undefined" ? globalThis : typeof self !== "undefined" ? self : this);
