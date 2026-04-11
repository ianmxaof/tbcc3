import { BrowserRouter, Routes, Route, NavLink } from "react-router-dom";
import { MediaLibrary } from "./panels/MediaLibrary";
import { ContentPools } from "./panels/ContentPools";
import { Sources } from "./panels/Sources";
import { Scheduler } from "./panels/Scheduler";
import { Subscriptions } from "./panels/Subscriptions";
import { BotsPanel } from "./panels/BotsPanel";
import { Growth } from "./panels/Growth";
import { TagsPanel } from "./panels/TagsPanel";
import { Analytics } from "./panels/Analytics";
import { ErrorBoundary } from "./components/ErrorBoundary";

const nav = [
  { to: "/", label: "Media" },
  { to: "/analytics", label: "Analytics" },
  { to: "/tags", label: "Tags" },
  { to: "/pools", label: "Pools" },
  { to: "/sources", label: "Sources" },
  { to: "/scheduler", label: "Scheduler" },
  { to: "/subscriptions", label: "Subscriptions" },
  { to: "/growth", label: "Growth" },
  { to: "/bots", label: "Bots" },
];

function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen flex flex-col">
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
        </nav>
        {/* min-w-0 prevents flex children from collapsing to 0 width (blank main content) */}
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
            <Route
              path="/pools"
              element={
                <ErrorBoundary name="Pools">
                  <ContentPools />
                </ErrorBoundary>
              }
            />
            <Route
              path="/sources"
              element={
                <ErrorBoundary name="Sources">
                  <Sources />
                </ErrorBoundary>
              }
            />
            <Route
              path="/scheduler"
              element={
                <ErrorBoundary name="Scheduler">
                  <Scheduler />
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
            <Route
              path="/growth"
              element={
                <ErrorBoundary name="Growth">
                  <Growth />
                </ErrorBoundary>
              }
            />
            <Route
              path="/bots"
              element={
                <ErrorBoundary name="Bots">
                  <BotsPanel />
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
