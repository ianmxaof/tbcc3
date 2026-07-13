/** TBCC priority alert toasts — calm chip-palette borders on neutral surfaces. */

import {
  calmToastStyle,
  classifyOpsAlertKind,
  type ToastSeverityKind,
} from "./severityToastColors";

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
      bottom: 16px;
      top: auto;
      z-index: 100000;
      display: flex;
      flex-direction: column;
      gap: 10px;
      max-width: min(420px, calc(100vw - 32px));
      pointer-events: none;
    }
    .tbcc-alert-toast {
      padding: 12px 14px;
      font: 500 13px/1.45 system-ui, -apple-system, sans-serif;
      border-radius: 10px;
      background: rgba(30, 30, 46, 0.96);
      color: #cdd6f4;
      border: 1px solid rgba(69, 71, 90, 0.9);
      box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35);
      pointer-events: auto;
      animation: tbcc-alert-pop 0.22s ease;
      box-sizing: border-box;
    }
    .tbcc-alert-toast__title {
      font-weight: 650;
      font-size: 13px;
      margin-bottom: 4px;
      letter-spacing: 0.01em;
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .tbcc-alert-toast__body {
      font-weight: 450;
      font-size: 12.5px;
      line-height: 1.5;
      white-space: pre-wrap;
      opacity: 0.94;
    }
    .tbcc-alert-toast__badge {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      opacity: 0.85;
      flex-shrink: 0;
    }
    .tbcc-alert-toast__action {
      margin-top: 8px;
      font-weight: 550;
      font-size: 12px;
      opacity: 0.88;
    }
    @keyframes tbcc-alert-pop {
      from { opacity: 0; transform: translateY(8px) scale(0.98); }
      to { opacity: 1; transform: translateY(0) scale(1); }
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
    host.setAttribute("aria-live", "polite");
    document.body.appendChild(host);
  }
  return host;
}

function toastDuration(kind: ToastSeverityKind): number {
  if (kind === "payment") return PAYMENT_MS;
  if (kind === "pending" || kind === "critical") return CRITICAL_MS;
  return DEFAULT_MS;
}

function toastBadgeLabel(alert: OpsAlert, kind: ToastSeverityKind): string {
  const code = (alert.code || "").toLowerCase();
  if (code === "payment") return "Sale";
  if (code === "invoice") return "Checkout";
  if (code === "loot") return "Loot";
  if (kind === "critical") return "Urgent";
  if (kind === "pending") return "Pending";
  return "Alert";
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
  const kind = classifyOpsAlertKind(alert);
  const calm = calmToastStyle(kind);
  const el = document.createElement("div");
  el.className = "tbcc-alert-toast";
  el.style.borderColor = calm.accentBorder;
  el.style.boxShadow = `inset 3px 0 0 0 ${calm.accentBorder}, 0 8px 24px rgba(0, 0, 0, 0.35)`;

  const title = document.createElement("div");
  title.className = "tbcc-alert-toast__title";
  const badge = document.createElement("span");
  badge.className = "tbcc-alert-toast__badge";
  badge.textContent = `${calm.emoji} ${toastBadgeLabel(alert, kind)}`;
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
  }, toastDuration(kind));
}
