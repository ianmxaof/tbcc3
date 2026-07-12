/**
 * Calm severity chrome — mirrors dashboard schedulerHealthChipColors + severityToastColors.
 * Neutral surface + severity border accent (Carbon low-contrast pattern).
 */
(function (global) {
  const HUE_STOPS = [6, 8, 12, 18, 24, 32, 40, 48, 58, 72, 88, 102, 118, 142];
  const SAT_STOPS = [44, 46, 48, 50, 52, 50, 48, 46, 44, 42, 40, 38, 38, 36];
  const LIGHT_STOPS = [22, 24, 26, 28, 30, 32, 33, 34, 34, 33, 32, 32, 33, 34];

  function lerp(a, b, t) {
    return a + (b - a) * t;
  }

  function sampleStop(stops, ratio) {
    const clamped = Math.max(0, Math.min(1, ratio));
    const maxIdx = stops.length - 1;
    const pos = clamped * maxIdx;
    const lo = Math.floor(pos);
    const hi = Math.min(maxIdx, lo + 1);
    const t = pos - lo;
    return lerp(stops[lo], stops[hi], t);
  }

  function schedulerHealthChipStyle(ratio) {
    const h = sampleStop(HUE_STOPS, ratio);
    const s = sampleStop(SAT_STOPS, ratio);
    const l = sampleStop(LIGHT_STOPS, ratio);
    return {
      borderColor: `hsla(${h}, ${s}%, ${l + 14}%, 0.58)`,
      backgroundColor: `hsla(${h}, ${s}%, ${l}%, 0.38)`,
      color: `hsl(${h}, ${Math.max(28, s - 6)}%, ${Math.min(86, l + 44)}%)`,
    };
  }

  function severityHealthRatio(kind) {
    switch (kind) {
      case "payment":
      case "success":
        return 0.92;
      case "info":
        return 0.72;
      case "pending":
        return 0.48;
      case "warning":
        return 0.38;
      case "error":
        return 0.22;
      case "critical":
        return 0.1;
      default:
        return 0.5;
    }
  }

  function severityGradeEmoji(ratio) {
    const r = Math.max(0, Math.min(1, ratio));
    if (r >= 0.75) return "🟢";
    if (r >= 0.5) return "🟡";
    if (r >= 0.25) return "🟠";
    return "🟤";
  }

  function calmToastStyle(kind) {
    const ratio = severityHealthRatio(kind);
    const base = schedulerHealthChipStyle(ratio);
    return {
      borderColor: base.borderColor,
      accentBorder: base.borderColor,
      backgroundColor: "",
      color: "",
      emoji: severityGradeEmoji(ratio),
      ratio,
    };
  }

  function classifyOpsAlertKind(alert) {
    const priority = String((alert && (alert.priority || alert.kind)) || "").toLowerCase();
    const code = String((alert && alert.code) || "").toLowerCase();
    if (priority === "payment" || code === "payment") return "payment";
    if (code === "invoice" || String((alert && alert.title) || "").toLowerCase().includes("pending")) {
      return "pending";
    }
    const sev = String((alert && alert.severity) || "warning").toLowerCase();
    if (sev === "critical") return "critical";
    if (sev === "info") return "info";
    if (sev === "error") return "error";
    return "warning";
  }

  function toastKindFromType(type, opts) {
    const t = String(type || "info");
    if (opts && opts.kind) return opts.kind;
    if (t === "success") return "success";
    if (t === "error") return opts && opts.critical ? "critical" : "error";
    return "info";
  }

  global.TBCC_SEVERITY_TOAST = {
    schedulerHealthChipStyle,
    severityHealthRatio,
    severityGradeEmoji,
    calmToastStyle,
    classifyOpsAlertKind,
    toastKindFromType,
  };
})(typeof window !== "undefined" ? window : self);
