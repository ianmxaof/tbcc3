import type { SchedulingStackHealth } from "../utils/schedulerIntervalCountdown";
import { schedulingWorkersHealthy } from "../utils/schedulerIntervalCountdown";
import type { SchedulerStatusFilter, TransportStats } from "../utils/schedulerPostStatus";

type Props = {
  stats: TransportStats;
  scheduling?: SchedulingStackHealth | null;
  statusFilter: SchedulerStatusFilter;
  onStatusFilterChange: (f: SchedulerStatusFilter) => void;
};

function chipBase(active: boolean): string {
  return `inline-flex items-center gap-1 rounded px-2 py-1 text-[11px] font-medium tabular-nums border transition-colors ${
    active ? "ring-1 ring-cyan-400/60 border-cyan-500/50" : "border-transparent hover:border-slate-500/50"
  }`;
}

export function SchedulerTransportBar({ stats, scheduling, statusFilter, onStatusFilterChange }: Props) {
  const workersOk = schedulingWorkersHealthy(scheduling);
  const { total, onTrack, idle, stalled, autoPaused, focusPaused, healthyPrimary } = stats;

  const filterLabel =
    statusFilter === "stalled"
      ? `Showing ${stalled} stalled job${stalled === 1 ? "" : "s"}`
      : statusFilter === "auto_paused"
        ? `Showing ${autoPaused} auto-paused job${autoPaused === 1 ? "" : "s"}`
        : statusFilter === "idle"
          ? `Showing ${idle} idle job${idle === 1 ? "" : "s"}`
          : null;

  return (
    <div className="mb-2 rounded-lg border border-slate-600/90 bg-slate-900/50 px-3 py-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[10px] uppercase tracking-wide text-slate-500 font-semibold mr-1">Transport</span>

        <button
          type="button"
          className={`${chipBase(statusFilter === "all")} text-emerald-300 bg-emerald-950/40`}
          title="Recurring jobs on track (running countdown or awaiting first post)"
          onClick={() => onStatusFilterChange("all")}
        >
          On track{" "}
          <span className="text-emerald-400">
            {healthyPrimary}/{total || 0}
          </span>
        </button>

        {stalled > 0 ? (
          <button
            type="button"
            className={`${chipBase(statusFilter === "stalled")} text-yellow-300 bg-yellow-950/30`}
            title="Past due — waiting for Beat enqueue or send"
            onClick={() => onStatusFilterChange(statusFilter === "stalled" ? "all" : "stalled")}
          >
            Stalled{" "}
            <span className="text-yellow-400">
              {stalled}/{total || 0}
            </span>
          </button>
        ) : null}

        {focusPaused > 0 ? (
          <button
            type="button"
            className={`${chipBase(false)} text-cyan-300 bg-cyan-950/30`}
            title="Focus profile paused Beat — workers up, scheduling resumes when focus ends"
          >
            Focus paused{" "}
            <span className="text-cyan-400">
              {focusPaused}/{total || 0}
            </span>
          </button>
        ) : null}

        {autoPaused > 0 ? (
          <button
            type="button"
            className={`${chipBase(statusFilter === "auto_paused")} text-rose-300 bg-rose-950/30`}
            title="Too many send failures — beat will not enqueue until cleared"
            onClick={() => onStatusFilterChange(statusFilter === "auto_paused" ? "all" : "auto_paused")}
          >
            Auto-paused{" "}
            <span className="text-rose-400">
              {autoPaused}/{total || 0}
            </span>
          </button>
        ) : null}

        {idle > 0 ? (
          <button
            type="button"
            className={`${chipBase(statusFilter === "idle")} text-amber-300 bg-amber-950/25`}
            title="Recurring job never posted — use Post now to start interval"
            onClick={() => onStatusFilterChange(statusFilter === "idle" ? "all" : "idle")}
          >
            Idle{" "}
            <span className="text-amber-400">
              {idle}/{total || 0}
            </span>
          </button>
        ) : null}

        <span className="text-slate-600 mx-1">|</span>

        <span
          className={`inline-flex items-center gap-1.5 text-[10px] ${
            workersOk ? (scheduling?.schedulingPaused ? "text-cyan-400/90" : "text-emerald-400/90") : "text-red-400/90"
          }`}
          title={
            scheduling?.schedulingPaused
              ? "Focus profile paused Beat scheduling — Celery-Post may still run"
              : workersOk
                ? "Beat and Celery-Post workers detected"
                : "Start TBCC-Beat and TBCC-Celery-Post for scheduled sends"
          }
        >
          <span
            className={`inline-block w-2 h-2 rounded-full ${
              workersOk ? (scheduling?.schedulingPaused ? "bg-cyan-400" : "bg-emerald-400") : "bg-red-500"
            }`}
          />
          Stack · Beat {scheduling?.beatRunning ? "up" : "down"} · Celery-Post{" "}
          {scheduling?.celeryPostRunning ? "up" : "down"}
          {scheduling?.schedulingPaused ? " · focus pause" : ""}
        </span>

        {onTrack > 0 && stalled === 0 && autoPaused === 0 && focusPaused === 0 ? (
          <span className="text-[10px] text-slate-500 ml-auto hidden sm:inline">
            {onTrack} running · {idle} awaiting first post
          </span>
        ) : null}
      </div>

      {filterLabel ? (
        <div className="mt-1.5 flex items-center gap-2 text-[10px] text-slate-400">
          <span>{filterLabel}</span>
          <button
            type="button"
            className="text-cyan-400 hover:text-cyan-300 underline"
            onClick={() => onStatusFilterChange("all")}
          >
            Clear filter
          </button>
        </div>
      ) : null}
    </div>
  );
}
