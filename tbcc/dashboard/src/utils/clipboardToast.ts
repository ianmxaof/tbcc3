/** Global TBCC "Copied!" tooltip + clipboard helper (dashboard). */

export const TBCC_COPIED_MESSAGE = "Copied!";
const DEFAULT_MS = 1600;

function injectStyles(): void {
  if (typeof document === "undefined") return;
  if (document.getElementById("tbcc-copied-toast-styles")) return;
  const style = document.createElement("style");
  style.id = "tbcc-copied-toast-styles";
  style.textContent = `
    .tbcc-copied-toast-host {
      position: fixed;
      inset: 0;
      z-index: 99999;
      pointer-events: none;
    }
    .tbcc-copied-toast {
      position: fixed;
      padding: 4px 10px;
      font: 600 11px/1.35 system-ui, -apple-system, sans-serif;
      color: #ecfdf5;
      background: rgba(16, 185, 129, 0.94);
      border: 1px solid rgba(52, 211, 153, 0.55);
      border-radius: 6px;
      box-shadow: 0 4px 14px rgba(0, 0, 0, 0.35);
      animation: tbcc-copied-pop 0.2s ease;
      pointer-events: none;
      white-space: nowrap;
    }
    @keyframes tbcc-copied-pop {
      from { opacity: 0; transform: scale(0.92) translateY(4px); }
      to { opacity: 1; transform: scale(1) translateY(0); }
    }
  `;
  document.head.appendChild(style);
}

function ensureHost(): HTMLElement {
  injectStyles();
  let host = document.getElementById("tbcc-copied-toast-host");
  if (!host) {
    host = document.createElement("div");
    host.id = "tbcc-copied-toast-host";
    host.className = "tbcc-copied-toast-host";
    host.setAttribute("aria-live", "polite");
    document.body.appendChild(host);
  }
  return host;
}

function copyViaExecCommand(text: string): boolean {
  try {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.cssText = "position:fixed;left:-9999px;top:0;opacity:0";
    document.body.appendChild(ta);
    ta.select();
    ta.setSelectionRange(0, text.length);
    const ok = document.execCommand("copy");
    document.body.removeChild(ta);
    return ok;
  } catch {
    return false;
  }
}

export type CopiedToastOptions = {
  message?: string;
  anchor?: HTMLElement | null;
  durationMs?: number;
};

/** Small tooltip-sized “Copied!” near the click target (or bottom-right). */
export function showCopiedToast(opts?: CopiedToastOptions): void {
  const host = ensureHost();
  const el = document.createElement("div");
  el.className = "tbcc-copied-toast";
  el.textContent = opts?.message?.trim() || TBCC_COPIED_MESSAGE;
  host.appendChild(el);

  const anchor = opts?.anchor;
  if (anchor?.getBoundingClientRect) {
    const r = anchor.getBoundingClientRect();
    const w = el.offsetWidth || 72;
    const left = Math.min(window.innerWidth - w - 8, Math.max(8, r.left + r.width / 2 - w / 2));
    const top = Math.max(8, r.top - 30);
    el.style.left = `${Math.round(left)}px`;
    el.style.top = `${Math.round(top)}px`;
  } else {
    el.style.right = "12px";
    el.style.bottom = "12px";
  }

  window.setTimeout(() => {
    try {
      el.remove();
    } catch {
      /* ignore */
    }
  }, opts?.durationMs ?? DEFAULT_MS);
}

/** Copy text and show the global Copied! toast on success. */
export async function tbccCopyText(
  text: string,
  opts?: CopiedToastOptions
): Promise<boolean> {
  const s = String(text ?? "");
  if (!s.trim()) return false;
  let ok = false;
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(s);
      ok = true;
    }
  } catch {
    ok = false;
  }
  if (!ok) ok = copyViaExecCommand(s);
  if (ok) showCopiedToast(opts);
  return ok;
}

/** Buttons with data-tbcc-copy or data-tbcc-copy-from get automatic Copied! toast. */
export function bindTbccDelegatedCopy(root: Document | HTMLElement = document): void {
  const el = root as Document & { __tbccCopyBound?: boolean };
  if (el.__tbccCopyBound) return;
  el.__tbccCopyBound = true;
  root.addEventListener(
    "click",
    (ev) => {
      const t = ev.target as HTMLElement | null;
      const btn = t?.closest?.("[data-tbcc-copy]") as HTMLElement | null;
      if (!btn || (btn as HTMLButtonElement).disabled) return;
      const raw = btn.getAttribute("data-tbcc-copy");
      const fromId = btn.getAttribute("data-tbcc-copy-from");
      let payload = raw ?? "";
      if (fromId) {
        const src = document.getElementById(fromId);
        if (src) payload = src.textContent || "";
      }
      if (!payload.trim()) return;
      ev.preventDefault();
      ev.stopPropagation();
      void tbccCopyText(payload, { anchor: btn });
    },
    true
  );
}
