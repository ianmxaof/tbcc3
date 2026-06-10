export const DASHBOARD_GILDED_LEGACY_KEY = "tbccDashboardGildedPanels";
export const DASHBOARD_GILDED_SETTINGS_KEY = "tbccDashboardGildedSettings";

export type DashboardGildedSettings = {
  enabled: boolean;
  showHeaderToggle: boolean;
  color: string;
  opacity: number;
  thickness: number;
};

export const DEFAULT_GILDED_SETTINGS: DashboardGildedSettings = {
  enabled: true,
  showHeaderToggle: true,
  color: "#fbbf24",
  opacity: 0.31,
  thickness: 1,
};

function clamp(n: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, n));
}

function normalizeHexColor(value: unknown): string {
  const raw = String(value || "").trim();
  if (/^#[0-9a-fA-F]{6}$/.test(raw)) return raw.toLowerCase();
  if (/^#[0-9a-fA-F]{3}$/.test(raw)) {
    const h = raw.slice(1);
    return `#${h[0]}${h[0]}${h[1]}${h[1]}${h[2]}${h[2]}`.toLowerCase();
  }
  return DEFAULT_GILDED_SETTINGS.color;
}

export function hexToRgba(hex: string, alpha: number): string {
  const h = normalizeHexColor(hex).slice(1);
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${clamp(alpha, 0, 1)})`;
}

function readLegacyEnabled(): boolean | null {
  try {
    const raw = window.localStorage.getItem(DASHBOARD_GILDED_LEGACY_KEY);
    if (raw === "0" || raw === "false") return false;
    if (raw === "1" || raw === "true") return true;
  } catch {
    /* ignore */
  }
  return null;
}

function normalizeSettings(raw: unknown): DashboardGildedSettings {
  const base = { ...DEFAULT_GILDED_SETTINGS };
  if (!raw || typeof raw !== "object") return base;
  const o = raw as Partial<DashboardGildedSettings>;
  return {
    enabled: o.enabled !== false,
    showHeaderToggle: o.showHeaderToggle !== false,
    color: normalizeHexColor(o.color),
    opacity: clamp(Number(o.opacity ?? base.opacity), 0.05, 1),
    thickness: clamp(Number(o.thickness ?? base.thickness), 1, 4),
  };
}

export function readGildedSettings(): DashboardGildedSettings {
  try {
    const raw = window.localStorage.getItem(DASHBOARD_GILDED_SETTINGS_KEY);
    if (raw) {
      return normalizeSettings(JSON.parse(raw));
    }
  } catch {
    /* ignore */
  }
  const legacy = readLegacyEnabled();
  if (legacy !== null) {
    return { ...DEFAULT_GILDED_SETTINGS, enabled: legacy };
  }
  return { ...DEFAULT_GILDED_SETTINGS };
}

export function saveGildedSettings(settings: DashboardGildedSettings): void {
  const normalized = normalizeSettings(settings);
  try {
    window.localStorage.setItem(DASHBOARD_GILDED_SETTINGS_KEY, JSON.stringify(normalized));
    window.localStorage.setItem(DASHBOARD_GILDED_LEGACY_KEY, normalized.enabled ? "1" : "0");
  } catch {
    /* ignore */
  }
}

export function applyGildedSettings(settings: DashboardGildedSettings): void {
  const s = normalizeSettings(settings);
  const root = document.documentElement;
  root.setAttribute("data-dashboard-gilded", s.enabled ? "1" : "0");
  root.style.setProperty("--tbcc-gilded-border", hexToRgba(s.color, s.opacity));
  root.style.setProperty(
    "--tbcc-gilded-border-strong",
    hexToRgba(s.color, clamp(s.opacity + 0.11, 0, 1))
  );
  root.style.setProperty("--tbcc-gilded-border-width", `${s.thickness}px`);
}
