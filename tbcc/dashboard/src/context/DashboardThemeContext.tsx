import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

export const DASHBOARD_THEME_KEY = "tbccDashboardThemePreset";

export type DashboardTheme = "dark" | "chatgpt" | "github" | "obsidian" | "cursor";

export const DASHBOARD_THEME_LABELS: Record<DashboardTheme, string> = {
  dark: "Dark",
  chatgpt: "ChatGPT",
  github: "GitHub",
  obsidian: "Obsidian",
  cursor: "Cursor",
};

export function normalizeDashboardTheme(value: unknown): DashboardTheme {
  const v = String(value || "").trim().toLowerCase();
  if (v === "chatgpt" || v === "github" || v === "obsidian" || v === "cursor") return v;
  return "dark";
}

type DashboardThemeContextValue = {
  themePreset: DashboardTheme;
  setThemePreset: (next: DashboardTheme) => void;
};

const DashboardThemeContext = createContext<DashboardThemeContextValue | null>(null);

export function DashboardThemeProvider({ children }: { children: ReactNode }) {
  const [themePreset, setThemePresetState] = useState<DashboardTheme>(() => {
    try {
      return normalizeDashboardTheme(window.localStorage.getItem(DASHBOARD_THEME_KEY));
    } catch {
      return "dark";
    }
  });

  useEffect(() => {
    document.documentElement.setAttribute("data-dashboard-theme", themePreset);
    try {
      window.localStorage.setItem(DASHBOARD_THEME_KEY, themePreset);
    } catch {
      // Ignore storage write errors.
    }
  }, [themePreset]);

  const setThemePreset = (next: DashboardTheme) => {
    setThemePresetState(normalizeDashboardTheme(next));
  };

  const value = useMemo(() => ({ themePreset, setThemePreset }), [themePreset]);

  return <DashboardThemeContext.Provider value={value}>{children}</DashboardThemeContext.Provider>;
}

export function useDashboardTheme(): DashboardThemeContextValue {
  const ctx = useContext(DashboardThemeContext);
  if (!ctx) {
    throw new Error("useDashboardTheme must be used within DashboardThemeProvider");
  }
  return ctx;
}
