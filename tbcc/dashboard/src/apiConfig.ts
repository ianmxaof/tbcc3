/** Which TBCC backend the dashboard talks to (Vite dev proxies inject the internal key). */
export type ApiTarget = "local" | "island";

const STORAGE_KEY = "tbcc:dashboardApiTarget";

export const API_TARGET_META: Record<
  ApiTarget,
  { label: string; shortLabel: string; hint: string }
> = {
  local: {
    label: "Local (home :8000)",
    shortLabel: "Local",
    hint: "Home tray / Docker API on 127.0.0.1:8000 — separate DB from production.",
  },
  island: {
    label: "Island (production VM)",
    shortLabel: "Island",
    hint: "Live revenue island via api.powercore.app — scheduler, pools, and commerce DB.",
  },
};

let currentTarget: ApiTarget = readInitialTarget();
const listeners = new Set<() => void>();

function readInitialTarget(): ApiTarget {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === "local" || stored === "island") return stored;
  } catch {
    /* private mode */
  }
  const envDefault = import.meta.env.VITE_DEFAULT_API_TARGET;
  if (envDefault === "island" || envDefault === "local") return envDefault;
  return "local";
}

/** Static build override — when set, target switcher is ignored for fetch URLs. */
export function getStaticApiBaseOverride(): string | undefined {
  const raw = import.meta.env.VITE_API_BASE as string | undefined;
  return raw?.replace(/\/$/, "") || undefined;
}

export function apiBaseForTarget(target: ApiTarget): string {
  const override = getStaticApiBaseOverride();
  if (override) return override;
  return target === "island" ? "/island-api" : "/api";
}

export function getApiTarget(): ApiTarget {
  return currentTarget;
}

export function getApiBase(): string {
  return apiBaseForTarget(currentTarget);
}

export function setApiTarget(target: ApiTarget): void {
  if (getStaticApiBaseOverride()) return;
  if (target === currentTarget) return;
  currentTarget = target;
  try {
    localStorage.setItem(STORAGE_KEY, target);
  } catch {
    /* ignore */
  }
  for (const fn of listeners) fn();
}

export function subscribeApiTarget(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function canSwitchApiTarget(): boolean {
  return !getStaticApiBaseOverride();
}
