/**
 * Calm severity chrome for toasts / banners — same 14-stop palette as scheduler chips.
 * Visual pattern (Carbon/Twilio “low contrast”): neutral surface + severity border accent.
 * ratio 1 = healthy green, 0 = warm dark red.
 */
import {
  schedulerHealthChipStyle,
  type SchedulerHealthChipStyle,
} from "./schedulerHealthChipColors";

export type ToastSeverityKind =
  | "success"
  | "info"
  | "warning"
  | "error"
  | "critical"
  | "payment"
  | "pending";

/** Maps message kind → chip health ratio (higher = calmer / greener). */
export function severityHealthRatio(kind: ToastSeverityKind): number {
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

export type CalmToastStyle = SchedulerHealthChipStyle & {
  /** Soft left/inner border for severity without flooding the fill. */
  accentBorder: string;
  emoji: string;
};

export function calmToastStyle(kind: ToastSeverityKind): CalmToastStyle {
  const ratio = severityHealthRatio(kind);
  const base = schedulerHealthChipStyle(ratio);
  return {
    ...base,
    // Neutral fill — severity lives on the border (calmer than filled red/amber panels).
    backgroundColor: "var(--tbcc-bg-surface, rgba(30, 30, 46, 0.96))",
    color: "var(--tbcc-text-primary, #cdd6f4)",
    accentBorder: base.borderColor,
    borderColor: base.borderColor,
    emoji: severityGradeEmoji(ratio),
  };
}

/** Approximate chip grade as a soft emoji for OS / tray notifications (no color API). */
export function severityGradeEmoji(ratio: number): string {
  const r = Math.max(0, Math.min(1, ratio));
  if (r >= 0.75) return "🟢";
  if (r >= 0.5) return "🟡";
  if (r >= 0.25) return "🟠";
  return "🟤";
}

export function classifyOpsAlertKind(alert: {
  severity?: string;
  priority?: string;
  kind?: string;
  code?: string;
  title?: string;
}): ToastSeverityKind {
  const priority = (alert.priority || alert.kind || "").toLowerCase();
  const code = (alert.code || "").toLowerCase();
  if (priority === "payment" || code === "payment") return "payment";
  if (code === "invoice" || (alert.title || "").toLowerCase().includes("pending")) return "pending";
  const sev = (alert.severity || "warning").toLowerCase();
  if (sev === "critical") return "critical";
  if (sev === "info") return "info";
  if (sev === "error") return "error";
  return "warning";
}
