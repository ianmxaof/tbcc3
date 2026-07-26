/**
 * Parse compact view/like counts from site UI ("4.7M", "4,7M", "12.3K").
 *
 * Critical: with K/M/B suffix, comma is a *decimal* separator (EU locales / CDN copy),
 * not a thousands separator. Stripping commas first turns "4,7M" into "47M" (10× inflate).
 */
(function (root) {
  function tbccParseAbbrevNumber(text) {
    if (text == null) return 0;
    const t = String(text).replace(/\s+/g, " ").trim();
    if (!t) return 0;
    const m = t.match(/(\d[\d.,]*)(\s*[KMB])?/i);
    if (!m) return 0;
    let raw = m[1];
    const unit = (m[2] || "").trim().toUpperCase();
    if (unit) {
      // Abbreviated: normalize decimal comma → dot; keep a single decimal point.
      raw = raw.replace(/,/g, ".");
      const parts = raw.split(".");
      if (parts.length > 2) {
        raw = parts[0] + "." + parts.slice(1).join("");
      }
    } else {
      // Full integer: commas are thousands; dotted thousands (1.234.567) → strip dots.
      raw = raw.replace(/,/g, "");
      if (/^\d{1,3}(\.\d{3})+$/.test(raw)) {
        raw = raw.replace(/\./g, "");
      } else {
        raw = raw.replace(/\.(?=.*\.)/g, "");
      }
    }
    const num = parseFloat(raw);
    if (!Number.isFinite(num)) return 0;
    if (unit === "K") return Math.round(num * 1e3);
    if (unit === "M") return Math.round(num * 1e6);
    if (unit === "B") return Math.round(num * 1e9);
    return Math.round(num);
  }

  /** Compact display for live intel feeds (2400000 → "2.4M"). */
  function tbccFormatAbbrevNumber(n) {
    const v = Number(n);
    if (!Number.isFinite(v) || v < 0) return "0";
    if (v >= 1e9) return `${(v / 1e9).toFixed(v >= 1e10 ? 0 : 1).replace(/\.0$/, "")}B`;
    if (v >= 1e6) return `${(v / 1e6).toFixed(v >= 1e7 ? 0 : 1).replace(/\.0$/, "")}M`;
    if (v >= 1e3) return `${(v / 1e3).toFixed(v >= 1e4 ? 0 : 1).replace(/\.0$/, "")}K`;
    return String(Math.round(v));
  }

  const api = { tbccParseAbbrevNumber, tbccFormatAbbrevNumber };
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
  if (root) {
    root.tbccParseAbbrevNumber = tbccParseAbbrevNumber;
    root.tbccFormatAbbrevNumber = tbccFormatAbbrevNumber;
  }
})(typeof globalThis !== "undefined" ? globalThis : typeof window !== "undefined" ? window : this);
