/** TBCC priority alert toasts — sales, pending checkout, critical ops (not error-hub noise). */

export type AlertToastSeverity = "critical" | "warning" | "info";

export type OpsAlert = {
  id: string;
  kind?: string;
  code?: string;
  severity?: string;
  priority?: string;
  title?: string;
  message?: string;
};

const DEFAULT_MS = 12000;
const CRITICAL_MS = 22000;
const PAYMENT_MS = 28000;

function injectStyles(): void {
  if (typeof document === "undefined") return;
  if (document.getElementById("tbcc-alert-toast-styles")) return;
  const style = document.createElement("style");
  style.id = "tbcc-alert-toast-styles";
  style.textContent = `
    .tbcc-alert-toast-host {
      position: fixed;
      right: 16px;
      top: 16px;
      z-index: 100000;
      display: flex;
      flex-direction: column;
      gap: 10px;
      max-width: min(440px, calc(100vw - 32px));
      pointer-events: none;
    }
    .tbcc-alert-toast {
      padding: 12px 14px;
      font: 600 13px/1.45 system-ui, -apple-system, sans-serif;
      border-radius: 10px;
      box-shadow: 0 10px 32px rgba(0, 0, 0, 0.55);
      pointer-events: auto;
      animation: tbcc-alert-pop 0.28s ease;
    }
    .tbcc-alert-toast--critical {
      color: #fecaca;
      background: linear-gradient(135deg, rgba(127, 29, 29, 0.98), rgba(91, 20, 20, 0.98));
      border: 2px solid rgba(248, 113, 113, 0.75);
      animation: tbcc-alert-pop 0.28s ease, tbcc-alert-flash-critical 1.1s ease-in-out 3;
    }
    .tbcc-alert-toast--warning {
      color: #fde68a;
      background: rgba(120, 53, 15, 0.96);
      border: 1px solid rgba(251, 191, 36, 0.55);
    }
    .tbcc-alert-toast--payment {
      color: #ecfdf5;
      background: linear-gradient(135deg, rgba(6, 95, 70, 0.98), rgba(4, 120, 87, 0.98));
      border: 2px solid rgba(52, 211, 153, 0.85);
      animation: tbcc-alert-pop 0.28s ease, tbcc-alert-flash-payment 0.85s ease-in-out 6;
    }
    .tbcc-alert-toast--pending {
      color: #fffbeb;
      background: linear-gradient(135deg, rgba(146, 64, 14, 0.98), rgba(180, 83, 9, 0.98));
      border: 2px solid rgba(251, 191, 36, 0.8);
      animation: tbcc-alert-pop 0.28s ease, tbcc-alert-flash-pending 1s ease-in-out 4;
    }
    .tbcc-alert-toast__title {
      font-weight: 700;
      font-size: 14px;
      margin-bottom: 5px;
      letter-spacing: 0.01em;
    }
    .tbcc-alert-toast__body {
      font-weight: 500;
      font-size: 13px;
      line-height: 1.5;
      white-space: pre-wrap;
    }
    .tbcc-alert-toast__badge {
      display: inline-block;
      margin-right: 6px;
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      opacity: 0.9;
    }
    .tbcc-alert-toast__action {
      margin-top: 8px;
      font-weight: 600;
      font-size: 12px;
      opacity: 0.92;
    }
    @keyframes tbcc-alert-pop {
      from { opacity: 0; transform: translateY(-10px) scale(0.97); }
      to { opacity: 1; transform: translateY(0) scale(1); }
    }
    @keyframes tbcc-alert-flash-payment {
      0%, 100% { box-shadow: 0 10px 32px rgba(0, 0, 0, 0.55), 0 0 0 0 rgba(52, 211, 153, 0.5); }
      50% { box-shadow: 0 10px 32px rgba(0, 0, 0, 0.55), 0 0 0 10px rgba(52, 211, 153, 0); }
    }
    @keyframes tbcc-alert-flash-pending {
      0%, 100% { box-shadow: 0 10px 32px rgba(0, 0, 0, 0.55), 0 0 0 0 rgba(251, 191, 36, 0.45); }
      50% { box-shadow: 0 10px 32px rgba(0, 0, 0, 0.55), 0 0 0 8px rgba(251, 191, 36, 0); }
    }
    @keyframes tbcc-alert-flash-critical {
      0%, 100% { box-shadow: 0 10px 32px rgba(0, 0, 0, 0.55), 0 0 0 0 rgba(248, 113, 113, 0.45); }
      50% { box-shadow: 0 10px 32px rgba(0, 0, 0, 0.55), 0 0 0 10px rgba(248, 113, 113, 0); }
    }
  `;
  document.head.appendChild(style);
}

function ensureHost(): HTMLElement {
  injectStyles();
  let host = document.getElementById("tbcc-alert-toast-host");
  if (!host) {
    host = document.createElement("div");
    host.id = "tbcc-alert-toast-host";
    host.className = "tbcc-alert-toast-host";
    host.setAttribute("aria-live", "assertive");
    document.body.appendChild(host);
  }
  return host;
}

function toastClass(alert: OpsAlert): string {
  const priority = (alert.priority || alert.kind || "").toLowerCase();
  const code = (alert.code || "").toLowerCase();
  if (priority === "payment" || code === "payment") {
    return "tbcc-alert-toast--payment";
  }
  if (code === "invoice" || (alert.title || "").toLowerCase().includes("pending")) {
    return "tbcc-alert-toast--pending";
  }
  const sev = (alert.severity || "warning").toLowerCase();
  return sev === "critical" ? "tbcc-alert-toast--critical" : "tbcc-alert-toast--warning";
}

function toastDuration(alert: OpsAlert): number {
  const cls = toastClass(alert);
  if (cls.includes("payment")) return PAYMENT_MS;
  if (cls.includes("pending")) return CRITICAL_MS;
  if (cls.includes("critical")) return CRITICAL_MS;
  return DEFAULT_MS;
}

function toastBadge(alert: OpsAlert): string {
  const code = (alert.code || "").toLowerCase();
  if (code === "payment") return "💰 Sale";
  if (code === "invoice") return "🧾 Checkout";
  if (code === "loot") return "🎮 Loot";
  if ((alert.severity || "").toLowerCase() === "critical") return "🔴 Urgent";
  return "⚠️ Alert";
}

function splitAlertMessage(message: string): { impact: string; action: string | null } {
  const raw = (message || "").trim();
  for (const marker of ["\n\nWhat to do:\n", "\n\nWhat to do: "]) {
    const idx = raw.indexOf(marker);
    if (idx >= 0) {
      return {
        impact: raw.slice(0, idx).trim(),
        action: raw.slice(idx + marker.length).trim() || null,
      };
    }
  }
  return { impact: raw, action: null };
}

export function showAlertToast(alert: OpsAlert): void {
  const host = ensureHost();
  const el = document.createElement("div");
  el.className = `tbcc-alert-toast ${toastClass(alert)}`;
  const title = document.createElement("div");
  title.className = "tbcc-alert-toast__title";
  const badge = document.createElement("span");
  badge.className = "tbcc-alert-toast__badge";
  badge.textContent = toastBadge(alert);
  title.appendChild(badge);
  title.appendChild(document.createTextNode(alert.title || "TBCC alert"));
  const { impact, action } = splitAlertMessage(alert.message || "");
  const body = document.createElement("div");
  body.className = "tbcc-alert-toast__body";
  body.textContent = impact;
  el.appendChild(title);
  el.appendChild(body);
  if (action) {
    const actionEl = document.createElement("div");
    actionEl.className = "tbcc-alert-toast__action";
    actionEl.textContent = `What to do: ${action}`;
    el.appendChild(actionEl);
  }
  host.prepend(el);
  window.setTimeout(() => {
    try {
      el.remove();
    } catch {
      /* ignore */
    }
  }, toastDuration(alert));
}
