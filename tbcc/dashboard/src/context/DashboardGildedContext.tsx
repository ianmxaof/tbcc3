import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  applyGildedSettings,
  readGildedSettings,
  saveGildedSettings,
  type DashboardGildedSettings,
} from "../utils/dashboardGildedSettings";

type DashboardGildedContextValue = {
  settings: DashboardGildedSettings;
  updateSettings: (patch: Partial<DashboardGildedSettings>) => void;
  replaceSettings: (next: DashboardGildedSettings) => void;
};

const DashboardGildedContext = createContext<DashboardGildedContextValue | null>(null);

export function DashboardGildedProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState<DashboardGildedSettings>(() => readGildedSettings());

  const replaceSettings = useCallback((next: DashboardGildedSettings) => {
    setSettings(next);
    saveGildedSettings(next);
    applyGildedSettings(next);
  }, []);

  const updateSettings = useCallback((patch: Partial<DashboardGildedSettings>) => {
    setSettings((prev) => {
      const next = { ...prev, ...patch };
      saveGildedSettings(next);
      applyGildedSettings(next);
      return next;
    });
  }, []);

  useEffect(() => {
    applyGildedSettings(settings);
  }, [settings]);

  const value = useMemo(
    () => ({ settings, updateSettings, replaceSettings }),
    [settings, updateSettings, replaceSettings]
  );

  return <DashboardGildedContext.Provider value={value}>{children}</DashboardGildedContext.Provider>;
}

export function useDashboardGilded(): DashboardGildedContextValue {
  const ctx = useContext(DashboardGildedContext);
  if (!ctx) {
    throw new Error("useDashboardGilded must be used within DashboardGildedProvider");
  }
  return ctx;
}
