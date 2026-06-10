/** TBCC operational alert toasts (breaking conflicts, error hub). */

export type AlertToastSeverity = "critical" | "warning" | "info";

export type OpsAlert = {
  id: string;
  kind?: string;
  code?: string;
  severity?: string;
  title?: string;
  message?: string;
};

const DEFAULT_MS = 12000;
const CRITICAL_MS = 18000;

function injectStyles(): void {
  if (typeof document === "undefined") return;
  if (document.getElementById("tbcc-alert-toast-styles")) return;
  const style = document.createElement("style");
  style.id = "tbcc-alert-toast-styles";
  style.textContent = `
    .tbcc-alert-toast-host {
      position: fixed;
      right: 12px;
      bottom: 12px;
      z-index: 100000;
      display: flex;
      flex-direction: column;
      gap: 8px;
      max-width: min(420px, calc(100vw - 24px));
      pointer-events: none;
    }
    .tbcc-alert-toast {
      padding: 10px 12px;
      font: 500 12px/1.4 system-ui, -apple-system, sans-serif;
      border-radius: 8px;
      box-shadow: 0 6px 20px rgba(0, 0, 0, 0.4);
      pointer-events: auto;
      animation: tbcc-alert-pop 0.22s ease;
    }
    .tbcc-alert-toast--critical {
      color: #fecaca;
      background: rgba(127, 29, 29, 0.95);
      border: 1px solid rgba(248, 113, 113, 0.55);
    }
    .tbcc-alert-toast--warning {
      color: #fde68a;
      background: rgba(120, 53, 15, 0.94);
      border: 1px solid rgba(251, 191, 36, 0.5);
    }
    .tbcc-alert-toast__title {
      font-weight: 600;
      margin-bottom: 4px;
    }
    @keyframes tbcc-alert-pop {
      from { opacity: 0; transform: translateY(8px); }
      to { opacity: 1; transform: translateY(0); }
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

export function showAlertToast(alert: OpsAlert): void {
  const host = ensureHost();
  const sev = (alert.severity || "warning").toLowerCase();
  const isCritical = sev === "critical";
  const el = document.createElement("div");
  el.className = `tbcc-alert-toast ${isCritical ? "tbcc-alert-toast--critical" : "tbcc-alert-toast--warning"}`;
  const title = document.createElement("div");
  title.className = "tbcc-alert-toast__title";
  title.textContent = alert.title || "TBCC alert";
  const body = document.createElement("div");
  body.textContent = alert.message || "";
  el.appendChild(title);
  el.appendChild(body);
  host.appendChild(el);
  window.setTimeout(() => {
    try {
      el.remove();
    } catch {
      /* ignore */
    }
  }, isCritical ? CRITICAL_MS : DEFAULT_MS);
}
