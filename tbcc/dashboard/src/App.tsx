import { BrowserRouter, Routes, Route, NavLink, Navigate } from "react-router-dom";
import { MediaLibrary } from "./panels/MediaLibrary";
import { PoolCurateGallery } from "./panels/PoolCurateGallery";
import { AutomationPanel } from "./panels/AutomationPanel";
import { Subscriptions } from "./panels/Subscriptions";
import { BotsPanel } from "./panels/BotsPanel";
import { TagsPanel } from "./panels/TagsPanel";
import { Analytics } from "./panels/Analytics";
import { IncomePanel } from "./panels/IncomePanel";
import { MiscPanel } from "./panels/MiscPanel";
import { MasterArchivePanel } from "./panels/MasterArchivePanel";
import { DashboardSettingsPanel } from "./panels/DashboardSettingsPanel";
import { DashboardHeaderToolbar } from "./components/DashboardHeaderToolbar";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { SystemHealthBanner } from "./components/SystemHealthBanner";
import { OpsAlertsPoller } from "./components/OpsAlertsPoller";
import { ScrapeRunBanner } from "./components/ScrapeRunBanner";
import { TbccClipboardInit } from "./components/TbccClipboardInit";
import { ApprovalQueueCounter } from "./components/ApprovalQueueCounter";

const nav = [
  { to: "/", label: "Media", showQueue: true },
  { to: "/curate", label: "Curate", showQueue: true },
  { to: "/scheduler", label: "Automation", showQueue: false },
  { to: "/subscriptions", label: "Commerce", showQueue: false },
  { to: "/income", label: "Income", showQueue: false },
  { to: "/analytics", label: "Analytics", showQueue: false },
  { to: "/bots", label: "System", showQueue: false },
  { to: "/misc", label: "Misc", showQueue: false },
  { to: "/archive", label: "Archive", showQueue: false },
];

function AppShell() {
  return (
    <BrowserRouter>
      <TbccClipboardInit />
      <div className="min-h-screen flex flex-col">
        <SystemHealthBanner />
        <OpsAlertsPoller />
        <ScrapeRunBanner />
        <nav className="bg-slate-800 border-b border-slate-700 px-4 py-3 flex gap-4">
          <span className="font-bold text-slate-200 mr-4 flex items-center gap-2">
            <img src="/favicon-32x32.png" alt="" width={22} height={22} className="rounded-sm" />
            TBCC
          </span>
          {nav.map(({ to, label, showQueue }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              className={({ isActive }) =>
                `inline-flex items-center gap-1.5 ${isActive ? "text-cyan-400 font-medium" : "text-slate-400 hover:text-slate-200"}`
              }
            >
              {label}
              {showQueue ? <ApprovalQueueCounter variant="compact" /> : null}
            </NavLink>
          ))}
          <DashboardHeaderToolbar />
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
              path="/curate"
              element={
                <ErrorBoundary name="PoolCurateGallery">
                  <PoolCurateGallery />
                </ErrorBoundary>
              }
            />
            <Route
              path="/income"
              element={
                <ErrorBoundary name="Income">
                  <IncomePanel />
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
              path="/scheduler/bots"
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
            <Route
              path="/settings/*"
              element={
                <ErrorBoundary name="Settings">
                  <DashboardSettingsPanel />
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

function App() {
  return <AppShell />;
}

export default App;
