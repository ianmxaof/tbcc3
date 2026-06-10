import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Scheduler } from "./Scheduler";
import { Sources } from "./Sources";
import { AutomationBotsPanel } from "./AutomationBotsPanel";

type AutomationTab = "publish" | "ingest" | "bots";

function tabFromPath(pathname: string): AutomationTab {
  if (pathname.includes("/bots")) return "bots";
  if (pathname.includes("/ingest") || pathname === "/sources") return "ingest";
  return "publish";
}

/**
 * Outbound posting (Scheduler) + inbound channel scrapers (Sources) in one nav item.
 * Backend APIs stay separate; this is presentation only.
 */
export function AutomationPanel() {
  const location = useLocation();
  const navigate = useNavigate();
  const [tab, setTab] = useState<AutomationTab>(() => tabFromPath(location.pathname));

  useEffect(() => {
    setTab(tabFromPath(location.pathname));
  }, [location.pathname]);

  function selectTab(next: AutomationTab) {
    setTab(next);
    const path =
      next === "ingest" ? "/scheduler/ingest" : next === "bots" ? "/scheduler/bots" : "/scheduler";
    navigate(path, { replace: true });
  }

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
        <h1 className="text-base font-semibold tracking-tight text-slate-100">Automation</h1>
        <p className="text-[10px] leading-snug text-slate-500">
          <strong className="text-slate-400">Publish</strong> · schedule out
          <span className="mx-1 text-slate-600">|</span>
          <strong className="text-slate-400">Ingest</strong> · scrape in
          <span className="mx-1 text-slate-600">|</span>
          <strong className="text-slate-400">Bots</strong> · workers
        </p>
      </div>

      <div className="mb-3 flex flex-wrap gap-0.5 border-b border-slate-700">
        <button
          type="button"
          onClick={() => selectTab("publish")}
          className={`px-3 py-1.5 text-xs font-medium rounded-t-md border-b-2 -mb-px transition-colors ${
            tab === "publish"
              ? "border-cyan-500 text-cyan-400 bg-slate-800/80"
              : "border-transparent text-slate-400 hover:text-slate-200"
          }`}
        >
          Publish to channels
        </button>
        <button
          type="button"
          onClick={() => selectTab("ingest")}
          className={`px-3 py-1.5 text-xs font-medium rounded-t-md border-b-2 -mb-px transition-colors ${
            tab === "ingest"
              ? "border-cyan-500 text-cyan-400 bg-slate-800/80"
              : "border-transparent text-slate-400 hover:text-slate-200"
          }`}
        >
          Ingest from channels
        </button>
        <button
          type="button"
          onClick={() => selectTab("bots")}
          className={`px-3 py-1.5 text-xs font-medium rounded-t-md border-b-2 -mb-px transition-colors ${
            tab === "bots"
              ? "border-cyan-500 text-cyan-400 bg-slate-800/80"
              : "border-transparent text-slate-400 hover:text-slate-200"
          }`}
        >
          Bots &amp; workers
        </button>
      </div>

      {tab === "publish" ? <Scheduler embedded /> : tab === "ingest" ? <Sources embedded /> : <AutomationBotsPanel />}
    </div>
  );
}
