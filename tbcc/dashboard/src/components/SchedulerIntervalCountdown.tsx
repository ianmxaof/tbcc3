import { useEffect, useMemo, useState } from "react";
import {
  computeSchedulerCountdown,
  countdownTimerClass,
  effectiveCountdownPhase,
  formatCountdownHms,
  formatPacificClock24FromMs,
  schedulingStackHealthy,
  type SchedulingStackHealth,
} from "../utils/schedulerIntervalCountdown";
import { formatPtForDashboard, formatUtcForDashboard } from "../utils/formatUtc";

function useNowTicker(intervalMs = 1000): number {
  const [nowMs, setNowMs] = useState(() => Date.now());
  useEffect(() => {
    setNowMs(Date.now());
    const id = window.setInterval(() => setNowMs(Date.now()), intervalMs);
    return () => window.clearInterval(id);
  }, [intervalMs]);
  return nowMs;
}

/** Single 1 Hz clock for all scheduler rows (Pacific wall + countdowns). */
export function useSchedulerClock(): number {
  return useNowTicker(1000);
}

type Props = {
  lastPostedAt?: unknown;
  intervalMinutes?: unknown;
  scheduledAt?: unknown;
  sentAt?: unknown;
  autoPausedAt?: unknown;
  scheduling?: SchedulingStackHealth | null;
  nowMs: number;
};

export function SchedulerIntervalCountdown({
  lastPostedAt,
  intervalMinutes,
  scheduledAt,
  sentAt,
  autoPausedAt,
  scheduling,
  nowMs,
}: Props) {
  const snapshotBase = useMemo(
    () =>
      computeSchedulerCountdown({
        lastPostedAt,
        intervalMinutes,
        scheduledAt,
        sentAt,
        autoPausedAt,
        nowMs,
      }),
    [lastPostedAt, intervalMinutes, scheduledAt, sentAt, autoPausedAt, nowMs]
  );

  const snapshot = snapshotBase;

  if (!snapshot) {
    return <span className="text-slate-600 text-[10px]">—</span>;
  }

  const phase = effectiveCountdownPhase(snapshot, scheduling);
  const timerClass = countdownTimerClass(phase);
  const stackOk = schedulingStackHealthy(scheduling);
  const displayMs = (() => {
    if (phase === "idle") return snapshot.intervalMs;
    if (phase === "sent") return 0;
    if (phase === "stalled" || phase === "paused") return 0;
    return snapshot.remainingMs;
  })();

  const pacificNow = formatPacificClock24FromMs(nowMs);
  const nextPt =
    snapshot.nextRunMs != null ? formatPacificClock24FromMs(snapshot.nextRunMs) : null;
  const nextPtLong =
    snapshot.nextRunMs != null
      ? formatPtForDashboard(new Date(snapshot.nextRunMs).toISOString())
      : null;

  const intervalLabel =
    snapshot.mode === "recurring" && snapshot.intervalMs > 0
      ? `Every ${Math.round(snapshot.intervalMs / 60_000)} min`
      : null;

  const subLine = (() => {
    if (phase === "idle") return "Post now to start";
    if (phase === "sent") return "Completed";
    if (phase === "paused") return "Auto-paused";
    if (phase === "stalled" && !stackOk && snapshot.mode === "recurring") {
      return "Beat / Celery-Post offline";
    }
    if (phase === "stalled") {
      return nextPtLong ? `Overdue · was ${nextPtLong} PT` : "Overdue";
    }
    if (nextPt) return `Next ${nextPt} PT`;
    return null;
  })();

  const title = [
    `Pacific now ${pacificNow}`,
    intervalLabel,
    subLine,
    snapshot.nextRunMs != null
      ? `Next UTC ${formatUtcForDashboard(new Date(snapshot.nextRunMs).toISOString())}`
      : null,
    !stackOk ? "TBCC-Beat or TBCC-Celery-Post not running" : null,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <div className="leading-tight" title={title}>
      <div className={`font-mono text-[13px] font-semibold tabular-nums tracking-tight ${timerClass}`}>
        {formatCountdownHms(displayMs)}
      </div>
      <div className="text-[9px] text-slate-500 tabular-nums mt-px">{pacificNow} PT</div>
      {subLine ? (
        <div
          className={`text-[9px] mt-0.5 truncate max-w-[7.5rem] ${
            phase === "running" ? "text-cyan-300/80" : phase === "stalled" ? "text-yellow-400/85" : "text-slate-500"
          }`}
        >
          {subLine}
        </div>
      ) : null}
      {intervalLabel ? (
        <div className="text-[9px] text-slate-600 mt-0.5">{intervalLabel}</div>
      ) : null}
    </div>
  );
}
