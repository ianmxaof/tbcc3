import { useCallback, useEffect, useState } from "react";
import { Link, Navigate, NavLink, Route, Routes, useLocation } from "react-router-dom";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../api";
import { useDashboardGilded } from "../context/DashboardGildedContext";
import { QueryErrorBanner } from "../components/QueryErrorBanner";
import {
  DEFAULT_GILDED_SETTINGS,
  hexToRgba,
  type DashboardGildedSettings,
} from "../utils/dashboardGildedSettings";
import {
  DASHBOARD_THEME_LABELS,
  normalizeDashboardTheme,
  type DashboardTheme,
  useDashboardTheme,
} from "../context/DashboardThemeContext";

declare global {
  interface Window {
    EyeDropper?: new () => { open: () => Promise<{ sRGBHex: string }> };
    chrome?: {
      runtime?: {
        sendMessage?: (msg: unknown, cb?: (r: unknown) => void) => void;
        openOptionsPage?: () => void;
      };
    };
  }
}

const PAGE_MENU_ORDER = [
  "save-archive",
  "save-archive-all",
  "save-pool",
  "save-saved",
  "download-url",
  "download-frame",
  "toggle-select",
  "copy-url",
  "open-url",
  "reverse-image",
  "lookup-username",
] as const;

const EXTENSION_OPTION_SECTIONS = [
  { id: "capture-settings", label: "Capture (side panel gallery)" },
  { id: "local-stack", label: "Local stack & launch daemon" },
  { id: "adapter-lab", label: "Adapter lab" },
  { id: "model", label: "Model search" },
  { id: "saved-videos", label: "Saved videos" },
  { id: "master-archive", label: "Master archive" },
  { id: "reverse", label: "Reverse image" },
] as const;

const SETTINGS_NAV = [
  { to: "/settings/dashboard", label: "Dashboard" },
  { to: "/settings/extension", label: "Extension" },
  { to: "/settings/supervisor", label: "Supervisor" },
] as const;

function gildedEqual(a: DashboardGildedSettings, b: DashboardGildedSettings): boolean {
  return (
    a.enabled === b.enabled &&
    a.showHeaderToggle === b.showHeaderToggle &&
    a.color === b.color &&
    a.opacity === b.opacity &&
    a.thickness === b.thickness
  );
}

function trySyncExtensionContextMenu(): Promise<boolean> {
  return new Promise((resolve) => {
    try {
      const send = window.chrome?.runtime?.sendMessage;
      if (!send) {
        resolve(false);
        return;
      }
      send({ action: "tbcc-sync-context-menu-settings" }, (r) => {
        resolve(!!(r && typeof r === "object" && (r as { ok?: boolean }).ok));
      });
    } catch {
      resolve(false);
    }
  });
}

function tryOpenExtensionOptions(): boolean {
  try {
    if (window.chrome?.runtime?.openOptionsPage) {
      window.chrome.runtime.openOptionsPage();
      return true;
    }
  } catch {
    // ignore
  }
  return false;
}

function SettingsSectionNav() {
  return (
    <nav className="flex flex-wrap gap-1 border-b border-slate-700 pb-3 mb-6">
      {SETTINGS_NAV.map(({ to, label }) => (
        <NavLink
          key={to}
          to={to}
          className={({ isActive }) =>
            [
              "px-3 py-1.5 rounded text-sm transition-colors",
              isActive
                ? "bg-slate-700 text-cyan-400 font-medium"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/80",
            ].join(" ")
          }
        >
          {label}
        </NavLink>
      ))}
    </nav>
  );
}

function DashboardAppearanceSection() {
  const { settings, replaceSettings } = useDashboardGilded();
  const { themePreset, setThemePreset } = useDashboardTheme();
  const [gildedDraft, setGildedDraft] = useState<DashboardGildedSettings>(() => ({ ...settings }));
  const [gildedSavedAt, setGildedSavedAt] = useState<number | null>(null);
  const gildedDirty = !gildedEqual(gildedDraft, settings);

  useEffect(() => {
    if (gildedDirty) return;
    setGildedDraft({ ...settings });
  }, [settings, gildedDirty]);

  const pickScreenColor = useCallback(async () => {
    if (!window.EyeDropper) {
      window.alert("Screen eyedropper needs Chromium (Chrome/Edge). Use the color input instead.");
      return;
    }
    try {
      const dropper = new window.EyeDropper();
      const result = await dropper.open();
      if (result?.sRGBHex) setGildedDraft((prev) => ({ ...prev, color: result.sRGBHex }));
    } catch {
      /* user cancelled */
    }
  }, []);

  const previewBorder = hexToRgba(gildedDraft.color, gildedDraft.opacity);

  const saveGilded = () => {
    replaceSettings(gildedDraft);
    setGildedSavedAt(Date.now());
  };

  return (
    <div className="space-y-8 max-w-2xl">
      <section className="tbcc-panel rounded-lg border border-slate-600 bg-slate-800/80 p-5 space-y-4">
        <h2 className="text-lg font-medium text-slate-100">Color theme</h2>
        <p className="text-sm text-slate-400">
          Dashboard color preset. Stored in this browser only; the extension gallery uses the same presets in its own
          options.
        </p>
        <label className="flex flex-wrap items-center gap-3 text-slate-300 text-sm">
          <span>Theme preset</span>
          <select
            value={themePreset}
            onChange={(e) => setThemePreset(normalizeDashboardTheme(e.target.value))}
            className="bg-slate-900 border border-slate-600 rounded px-2 py-1.5 text-slate-100 outline-none focus:ring-1 focus:ring-amber-500/50"
          >
            {(Object.keys(DASHBOARD_THEME_LABELS) as DashboardTheme[]).map((key) => (
              <option key={key} value={key}>
                {DASHBOARD_THEME_LABELS[key]}
              </option>
            ))}
          </select>
        </label>
      </section>

      <section className="tbcc-panel rounded-lg border border-slate-600 bg-slate-800/80 p-5 space-y-4">
        <h2 className="text-lg font-medium text-slate-100">Gilded panel borders</h2>
        <p className="text-sm text-slate-400">
          Warm accent borders on dashboard panels. Changes apply only after you press{" "}
          <strong className="text-slate-300">Save appearance</strong>.
        </p>

        <label className="flex items-center gap-2 text-slate-300">
          <input
            type="checkbox"
            checked={gildedDraft.enabled}
            onChange={(e) => setGildedDraft((prev) => ({ ...prev, enabled: e.target.checked }))}
          />
          <span>Gilded borders enabled</span>
        </label>

        <label className="flex items-center gap-2 text-slate-300">
          <input
            type="checkbox"
            checked={gildedDraft.showHeaderToggle}
            onChange={(e) => setGildedDraft((prev) => ({ ...prev, showHeaderToggle: e.target.checked }))}
          />
          <span>Show quick &ldquo;Gilded&rdquo; toggle in the top navigation bar</span>
        </label>

        <div className="flex flex-wrap items-end gap-4">
          <label className="block text-slate-400">
            Border color
            <div className="mt-1 flex items-center gap-2">
              <input
                type="color"
                value={gildedDraft.color}
                onChange={(e) => setGildedDraft((prev) => ({ ...prev, color: e.target.value }))}
                className="h-9 w-11 cursor-pointer bg-transparent border-0 p-0"
                title="Pick color"
              />
              <span
                className="inline-block h-9 w-9 rounded border border-slate-500 shrink-0"
                style={{ backgroundColor: gildedDraft.color }}
                title={gildedDraft.color}
              />
              <input
                className="w-28 bg-slate-900 border border-slate-600 rounded px-2 py-1 text-slate-100 font-mono text-xs"
                value={gildedDraft.color}
                onChange={(e) => setGildedDraft((prev) => ({ ...prev, color: e.target.value }))}
              />
              <button
                type="button"
                onClick={() => void pickScreenColor()}
                className="px-2 py-1 rounded bg-slate-700 text-slate-100 text-xs hover:bg-slate-600"
                title="Pick color from anywhere on screen (Chromium)"
              >
                Eyedropper
              </button>
            </div>
          </label>

          <label className="block text-slate-400 min-w-[10rem]">
            Opacity {gildedDraft.opacity.toFixed(2)}
            <input
              type="range"
              min={0.05}
              max={1}
              step={0.01}
              value={gildedDraft.opacity}
              onChange={(e) => setGildedDraft((prev) => ({ ...prev, opacity: Number(e.target.value) }))}
              className="mt-1 block w-full"
            />
          </label>

          <label className="block text-slate-400 min-w-[10rem]">
            Thickness {gildedDraft.thickness}px
            <input
              type="range"
              min={1}
              max={4}
              step={1}
              value={gildedDraft.thickness}
              onChange={(e) => setGildedDraft((prev) => ({ ...prev, thickness: Number(e.target.value) }))}
              className="mt-1 block w-full"
            />
          </label>
        </div>

        <div className="pt-2">
          <p className="text-xs text-slate-500 mb-2">Preview</p>
          <div
            className="rounded-md bg-slate-900/60 px-4 py-6 text-sm text-slate-400"
            style={{
              borderStyle: "solid",
              borderWidth: gildedDraft.thickness,
              borderColor: previewBorder,
            }}
          >
            Sample panel border with current color, opacity, and thickness.
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3 pt-1">
          <button
            type="button"
            disabled={!gildedDirty}
            onClick={saveGilded}
            className="px-3 py-1.5 rounded bg-sky-700 text-slate-100 text-sm hover:bg-sky-600 disabled:opacity-50"
          >
            Save appearance
          </button>
          {gildedSavedAt && !gildedDirty ? (
            <span className="text-xs text-emerald-400">Appearance saved to this browser.</span>
          ) : null}
          <button
            type="button"
            onClick={() => setGildedDraft({ ...DEFAULT_GILDED_SETTINGS })}
            className="text-xs text-slate-400 hover:text-slate-200 underline"
          >
            Reset gilded defaults
          </button>
        </div>
      </section>
    </div>
  );
}

function ExtensionSettingsSection() {
  const qc = useQueryClient();
  const ctxQ = useQuery({ queryKey: ["extensionContextMenu"], queryFn: () => api.extensionContextMenu.get() });
  const [pageMenu, setPageMenu] = useState<Record<string, boolean>>({});
  const [ctxEdited, setCtxEdited] = useState(false);
  const [ctxSavedAt, setCtxSavedAt] = useState<number | null>(null);
  const [ctxSyncNote, setCtxSyncNote] = useState<string | null>(null);
  const [optionsOpened, setOptionsOpened] = useState<boolean | null>(null);

  useEffect(() => {
    if (!ctxQ.data?.pageMenu || ctxEdited) return;
    setPageMenu({ ...ctxQ.data.pageMenu });
  }, [ctxQ.data, ctxEdited]);

  const saveCtxMenu = useMutation({
    mutationFn: async () => {
      const result = await api.extensionContextMenu.patch(pageMenu);
      const synced = await trySyncExtensionContextMenu();
      return { result, synced };
    },
    onSuccess: ({ synced }) => {
      setCtxEdited(false);
      setCtxSavedAt(Date.now());
      setCtxSyncNote(
        synced
          ? "Saved to server and pushed to the TBCC extension."
          : "Saved to server (tbcc/data/extension-context-menu.json). Reload hostile-site tabs or wait ~3 min for extension sync."
      );
      qc.invalidateQueries({ queryKey: ["extensionContextMenu"] });
    },
  });

  const openExtensionOptions = () => {
    const ok = tryOpenExtensionOptions();
    setOptionsOpened(ok);
  };

  return (
    <div className="space-y-8 max-w-3xl">
      <section className="tbcc-panel rounded-lg border border-slate-600 bg-slate-800/80 p-5 space-y-4">
        <h2 className="text-lg font-medium text-slate-100">Extension options (browser)</h2>
        <p className="text-sm text-slate-400">
          Capture, model search, adapter lab, reverse image, local stack launch, and other gallery-side settings live
          in the extension options page today. This dashboard section will host all of them over time; until then, open
          the full options page from the TBCC toolbar or gallery gear.
        </p>
        <ul className="grid gap-1 sm:grid-cols-2 text-sm text-slate-300">
          {EXTENSION_OPTION_SECTIONS.map(({ id, label }) => (
            <li key={id} className="flex items-center gap-2">
              <span className="text-slate-500">·</span>
              <span>{label}</span>
            </li>
          ))}
        </ul>
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={openExtensionOptions}
            className="px-3 py-1.5 rounded bg-slate-700 text-slate-100 text-sm hover:bg-slate-600"
          >
            Open extension options
          </button>
          {optionsOpened === true ? (
            <span className="text-xs text-emerald-400">Opened in a new tab.</span>
          ) : optionsOpened === false ? (
            <span className="text-xs text-slate-500">
              Use the TBCC extension toolbar → Extension options, or gallery ⚙ Capture options.
            </span>
          ) : null}
        </div>
      </section>

      <section className="tbcc-panel rounded-lg border border-slate-600 bg-slate-800/80 p-5 space-y-4">
        <h2 className="text-lg font-medium text-slate-100">In-page context menus</h2>
        <p className="text-sm text-slate-400">
          Toggle items in the TBCC in-page media menu (hostile sites like Erome/RedGIFs, or{" "}
          <strong className="text-slate-300">Alt + right-click</strong> elsewhere). Press{" "}
          <strong className="text-slate-300">Save &amp; sync extension</strong> to persist on the server and push to the
          extension when it is running.
        </p>
        {ctxQ.isError ? (
          <QueryErrorBanner
            title="Could not load context menu settings"
            message={ctxQ.error instanceof Error ? ctxQ.error.message : "Request failed"}
            onRetry={() => void ctxQ.refetch()}
          />
        ) : null}
        <div className="grid gap-2 sm:grid-cols-2">
          {PAGE_MENU_ORDER.map((key) => {
            const labels = ctxQ.data?.labels ?? {};
            const label = labels[key] || key;
            return (
              <label key={key} className="flex items-center gap-2 text-slate-300 text-sm">
                <input
                  type="checkbox"
                  checked={pageMenu[key] !== false}
                  disabled={ctxQ.isLoading || saveCtxMenu.isPending}
                  onChange={(e) => {
                    setCtxEdited(true);
                    setCtxSavedAt(null);
                    setCtxSyncNote(null);
                    setPageMenu((prev) => ({ ...prev, [key]: e.target.checked }));
                  }}
                />
                <span>{label}</span>
              </label>
            );
          })}
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            disabled={!ctxEdited || saveCtxMenu.isPending}
            onClick={() => saveCtxMenu.mutate()}
            className="px-3 py-1.5 rounded bg-sky-700 text-slate-100 text-sm hover:bg-sky-600 disabled:opacity-50"
          >
            {saveCtxMenu.isPending ? "Saving…" : "Save & sync extension"}
          </button>
          {ctxSavedAt && !ctxEdited && ctxSyncNote ? (
            <span className="text-xs text-emerald-400">{ctxSyncNote}</span>
          ) : null}
          {saveCtxMenu.isError ? (
            <span className="text-xs text-rose-400">Save failed — is the TBCC API running?</span>
          ) : null}
        </div>
      </section>
    </div>
  );
}

function SupervisorSettingsSection() {
  return (
    <div className="space-y-8 max-w-2xl">
      <section className="tbcc-panel rounded-lg border border-slate-600 bg-slate-800/80 p-5 space-y-4">
        <h2 className="text-lg font-medium text-slate-100">Tray supervisor &amp; local stack</h2>
        <p className="text-sm text-slate-400">
          Process control (start/stop API, Celery, Redis, focus profiles) is coordinated through the Windows tray
          supervisor and the extension Tools panel. Supervisor-specific settings will live here as they migrate off
          extension options and PowerShell menus.
        </p>
        <p className="text-sm text-slate-400">
          The <strong className="text-slate-200">Supervisor panel</strong> is a dense HWiNFO-style desktop window:
          stack health, host CPU/RAM sparklines, per-service LEDs, error hub tail (double-click a line to jump to it in
          Notepad), and conflicts. Open it from the tray menu or double-click the tray icon. Use{" "}
          <strong className="text-slate-200">Mini mode</strong> or{" "}
          <strong className="text-slate-200">Open supervisor mini</strong> for a compact always-on-top monitor.
        </p>
        <ul className="text-sm text-slate-300 space-y-2 list-disc pl-5">
          <li>
            Launch daemon: <code className="text-slate-400">cd tbcc\tools</code> then{" "}
            <code className="text-slate-400">.\tbcc-launch-daemon.ps1</code>
          </li>
          <li>Tray menu: service up/down, Telegram session tools, focus profile apply</li>
          <li>
            Extension → Tools: <strong className="text-slate-200">Start tray supervisor</strong>,{" "}
            <strong className="text-slate-200">Launch full stack (cold)</strong>
          </li>
          <li>
            Optional <code className="text-slate-400">TBCC_INTERNAL_API_KEY</code> for API launch fallback — set in
            Extension options → Local stack until migrated here
          </li>
        </ul>
        <p className="text-sm text-slate-400">
          Focus profiles (batch import / reduced background load) are shown in the{" "}
          <Link to="/" className="text-cyan-400 hover:underline">
            system health banner
          </Link>{" "}
          when active. See <code className="text-slate-400">tbcc/docs/TBCC_FOCUS_PROFILES.md</code>.
        </p>
      </section>
    </div>
  );
}

export function DashboardSettingsPanel() {
  const location = useLocation();

  return (
    <div>
      <h1 className="text-2xl font-semibold mb-2">TBCC settings</h1>
      <p className="text-slate-400 mb-4 max-w-3xl">
        Comprehensive settings for the dashboard, browser extension, and tray supervisor. More extension and supervisor
        controls will move here over time; the gear in the upper-right opens this page (eventually under your account
        menu when OAuth sign-in is added).
      </p>

      <SettingsSectionNav />

      <Routes>
        <Route index element={<Navigate to="dashboard" replace state={{ from: location }} />} />
        <Route path="dashboard" element={<DashboardAppearanceSection />} />
        <Route path="extension" element={<ExtensionSettingsSection />} />
        <Route path="supervisor" element={<SupervisorSettingsSection />} />
        <Route path="*" element={<Navigate to="dashboard" replace />} />
      </Routes>
    </div>
  );
}
