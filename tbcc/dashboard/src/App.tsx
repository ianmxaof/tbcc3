import { BrowserRouter, Routes, Route, NavLink, Navigate } from "react-router-dom";
import { useEffect, useState } from "react";
import { MediaLibrary } from "./panels/MediaLibrary";
import { AutomationPanel } from "./panels/AutomationPanel";
import { Subscriptions } from "./panels/Subscriptions";
import { BotsPanel } from "./panels/BotsPanel";
import { TagsPanel } from "./panels/TagsPanel";
import { Analytics } from "./panels/Analytics";
import { MiscPanel } from "./panels/MiscPanel";
import { MasterArchivePanel } from "./panels/MasterArchivePanel";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { SystemHealthBanner } from "./components/SystemHealthBanner";
import { ScrapeRunBanner } from "./components/ScrapeRunBanner";
import { TbccClipboardInit } from "./components/TbccClipboardInit";

const nav = [
  { to: "/", label: "Media" },
  { to: "/scheduler", label: "Automation" },
  { to: "/subscriptions", label: "Commerce" },
  { to: "/analytics", label: "Analytics" },
  { to: "/bots", label: "System" },
  { to: "/misc", label: "Misc" },
  { to: "/archive", label: "Archive" },
];

const DASHBOARD_THEME_KEY = "tbccDashboardThemePreset";
type DashboardTheme = "dark" | "chatgpt" | "github" | "obsidian" | "cursor";

function normalizeDashboardTheme(value: unknown): DashboardTheme {
  const v = String(value || "").trim().toLowerCase();
  if (v === "chatgpt" || v === "github" || v === "obsidian" || v === "cursor") return v;
  return "dark";
}

function App() {
  const [themePreset, setThemePreset] = useState<DashboardTheme>(() => {
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

  return (
    <BrowserRouter>
      <TbccClipboardInit />
      <div className="min-h-screen flex flex-col">
        <SystemHealthBanner />
        <ScrapeRunBanner />
        <nav className="bg-slate-800 border-b border-slate-700 px-4 py-3 flex gap-4">
          <span className="font-bold text-slate-200 mr-4">TBCC</span>
          {nav.map(({ to, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              className={({ isActive }) =>
                isActive ? "text-cyan-400 font-medium" : "text-slate-400 hover:text-slate-200"
              }
            >
              {label}
            </NavLink>
          ))}
          <label className="ml-auto flex items-center gap-2 text-xs text-slate-300">
            Theme
            <select
              value={themePreset}
              onChange={(e) => setThemePreset(normalizeDashboardTheme(e.target.value))}
              className="bg-slate-700 border border-slate-600 rounded px-2 py-1 text-slate-100"
              title="Dashboard color preset"
            >
              <option value="dark">Dark</option>
              <option value="chatgpt">ChatGPT</option>
              <option value="github">GitHub</option>
              <option value="obsidian">Obsidian</option>
              <option value="cursor">Cursor</option>
            </select>
          </label>
        </nav>
        <main className="flex-1 min-w-0 p-6">
          <Routes>
            <Route
              path="/"
              element={
                <ErrorBoundary name="Media">
                  <MediaLibrary />
                </ErrorBoundary>
              }
            />
            <Route
              path="/analytics"
              element={
                <ErrorBoundary name="Analytics">
                  <Analytics />
                </ErrorBoundary>
              }
            />
            <Route
              path="/tags"
              element={
                <ErrorBoundary name="Tags">
                  <TagsPanel />
                </ErrorBoundary>
              }
            />
            <Route path="/pools" element={<Navigate to="/" replace />} />
            <Route path="/sources" element={<Navigate to="/scheduler/ingest" replace />} />
            <Route
              path="/scheduler"
              element={
                <ErrorBoundary name="Automation">
                  <AutomationPanel />
                </ErrorBoundary>
              }
            />
            <Route
              path="/scheduler/ingest"
              element={
                <ErrorBoundary name="Automation">
                  <AutomationPanel />
                </ErrorBoundary>
              }
            />
            <Route
              path="/subscriptions"
              element={
                <ErrorBoundary name="Subscriptions">
                  <Subscriptions />
                </ErrorBoundary>
              }
            />
            <Route path="/growth" element={<Navigate to="/bots" replace />} />
            <Route
              path="/bots"
              element={
                <ErrorBoundary name="Bots">
                  <BotsPanel />
                </ErrorBoundary>
              }
            />
            <Route path="/emoji-factory" element={<Navigate to="/misc/emoji" replace />} />
            <Route path="/emoji-factory/*" element={<Navigate to="/misc/emoji" replace />} />
            <Route
              path="/misc"
              element={
                <ErrorBoundary name="Misc">
                  <MiscPanel />
                </ErrorBoundary>
              }
            />
            <Route
              path="/misc/emoji"
              element={
                <ErrorBoundary name="Misc">
                  <MiscPanel initialTab="emoji" />
                </ErrorBoundary>
              }
            />
            <Route
              path="/archive"
              element={
                <ErrorBoundary name="Archive">
                  <MasterArchivePanel />
                </ErrorBoundary>
              }
            />
            <Route path="*" element={<p className="text-slate-400">No route matches this URL.</p>} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}

export default App;
