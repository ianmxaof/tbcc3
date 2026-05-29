import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Scheduler } from "./Scheduler";
import { Sources } from "./Sources";

type AutomationTab = "publish" | "ingest";

function tabFromPath(pathname: string): AutomationTab {
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
    navigate(next === "ingest" ? "/scheduler/ingest" : "/scheduler", { replace: true });
  }

  return (
    <div>
      <h1 className="text-2xl font-semibold mb-2">Automation</h1>
      <p className="text-slate-400 mb-4 max-w-3xl text-sm">
        <strong className="text-slate-300">Publish</strong> sends approved pool media to your channels on a schedule.{" "}
        <strong className="text-slate-300">Ingest</strong> pulls media from Telegram channels into pools. Log in once,
        add one source per channel, set schedules, then use Scrape now or Celery Beat.
      </p>

      <div className="flex gap-1 mb-6 border-b border-slate-700 flex-wrap">
        <button
          type="button"
          onClick={() => selectTab("publish")}
          className={`px-4 py-2 text-sm font-medium rounded-t-lg border-b-2 -mb-px transition-colors ${
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
          className={`px-4 py-2 text-sm font-medium rounded-t-lg border-b-2 -mb-px transition-colors ${
            tab === "ingest"
              ? "border-cyan-500 text-cyan-400 bg-slate-800/80"
              : "border-transparent text-slate-400 hover:text-slate-200"
          }`}
        >
          Ingest from channels
        </button>
      </div>

      {tab === "publish" ? <Scheduler embedded /> : <Sources embedded />}
    </div>
  );
}
