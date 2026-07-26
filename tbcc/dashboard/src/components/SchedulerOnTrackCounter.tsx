import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import { useApiTarget } from "../context/ApiTargetContext";
import { useSchedulerClock } from "./SchedulerIntervalCountdown";
import { computeTransportStats } from "../utils/schedulerPostStatus";
import {
  schedulerHealthChipStyle,
  schedulerHealthRatio,
} from "../utils/schedulerHealthChipColors";

export function useSchedulerOnTrackSummary() {
  const { target } = useApiTarget();
  const schedulerNowMs = useSchedulerClock();
  const { data: schedulingHealth } = useQuery({
    queryKey: ["health", "scheduling", target],
    queryFn: () => api.healthScheduling(),
    refetchInterval: 15_000,
    staleTime: 10_000,
  });
  const { data: scheduledPosts = [], isLoading, isError } = useQuery({
    queryKey: ["scheduledPosts", target],
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
