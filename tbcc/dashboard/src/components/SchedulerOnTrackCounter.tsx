import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import { useSchedulerClock } from "./SchedulerIntervalCountdown";
import type { SchedulingStackHealth } from "../utils/schedulerIntervalCountdown";
import { computeTransportStats } from "../utils/schedulerPostStatus";
import {
  schedulerHealthChipStyle,
  schedulerHealthRatio,
} from "../utils/schedulerHealthChipColors";

const API = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

async function fetchSchedulingHealth(): Promise<SchedulingStackHealth> {
  try {
    const r = await fetch(`${API}/health/system`, { cache: "no-store" });
    const data = (await r.json()) as { scheduling?: Record<string, unknown> };
    const s = data.scheduling || {};
    return {
      beatRunning: Boolean(s.beat_running),
      celeryPostRunning: Boolean(s.celery_post_worker_running),
      celeryPostSchedulerRunning: Boolean(
        s.celery_post_scheduler_worker_running ?? s.celery_post_worker_running
      ),
      schedulingPaused: Boolean(s.scheduling_paused_by_focus),
      focusProfile: typeof s.focus_profile === "string" ? s.focus_profile : undefined,
    };
  } catch {
    return {
      beatRunning: false,
      celeryPostRunning: false,
      celeryPostSchedulerRunning: false,
      schedulingPaused: false,
    };
  }
}

export function useSchedulerOnTrackSummary() {
  const schedulerNowMs = useSchedulerClock();
  const { data: schedulingHealth } = useQuery({
    queryKey: ["health", "scheduling"],
    queryFn: fetchSchedulingHealth,
    refetchInterval: 15_000,
    staleTime: 10_000,
  });
  const { data: scheduledPosts = [], isLoading, isError } = useQuery({
    queryKey: ["scheduledPosts"],
    queryFn: () => api.scheduledPosts.list(),
    refetchInterval: 15_000,
    staleTime: 10_000,
  });

  const stats = useMemo(
    () =>
      computeTransportStats(
        scheduledPosts as Array<Record<string, unknown>>,
        schedulingHealth,
        schedulerNowMs
      ),
    [scheduledPosts, schedulingHealth, schedulerNowMs]
  );

  return { stats, isLoading, isError };
}

type Props = {
  variant?: "compact";
  className?: string;
};

export function SchedulerOnTrackCounter({ variant = "compact", className = "" }: Props) {
  const { stats, isLoading, isError } = useSchedulerOnTrackSummary();
  const { healthyPrimary, total } = stats;
  const ratio = schedulerHealthRatio(healthyPrimary, total);
  const chipStyle = schedulerHealthChipStyle(ratio);
  const label = `${healthyPrimary} / ${total}`;

  const title =
    "Recurring schedulers on track (running countdown, idle, or focus-paused) vs total recurring jobs. " +
    "Stalled and auto-paused jobs lower the ratio.";

  if (variant !== "compact") return null;

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium tabular-nums ${className}`}
      style={isLoading || isError ? undefined : chipStyle}
      title={title}
    >
      {isLoading ? (
        "…"
      ) : isError ? (
        <span className="text-slate-400">sched ?</span>
      ) : (
        label
      )}
    </span>
  );
}
