import { useState, type ReactNode } from "react";
import type { TransportStats } from "../utils/schedulerPostStatus";
import { computeTransportStats } from "../utils/schedulerPostStatus";
import type { SchedulingStackHealth } from "../utils/schedulerIntervalCountdown";
import type { SchedulerPostRecord } from "../utils/schedulerPostStatus";

type Props = {
  title: string;
  posts: SchedulerPostRecord[];
  defaultExpanded: boolean;
  scheduling?: SchedulingStackHealth | null;
  nowMs: number;
  children: ReactNode;
};

export function SchedulerGroupSection({
  title,
  posts,
  defaultExpanded,
  scheduling,
  nowMs,
  children,
}: Props) {
  const [open, setOpen] = useState(defaultExpanded);
  const stats: TransportStats = computeTransportStats(posts, scheduling, nowMs);
  const trouble = stats.stalled + stats.autoPaused;

  return (
    <>
      <tr className="bg-slate-800/80 border-t border-slate-600/80">
        <td colSpan={9} className="px-2 py-1.5">
          <button
            type="button"
            className="flex w-full items-center gap-2 text-left text-[11px] font-semibold text-slate-200 hover:text-white"
            onClick={() => setOpen((v) => !v)}
          >
            <span className="text-slate-500 w-4">{open ? "▾" : "▸"}</span>
            <span>{title}</span>
            <span className="text-slate-500 font-normal">({posts.length})</span>
            {stats.total > 0 ? (
              <span className="ml-auto tabular-nums text-[10px] font-medium text-emerald-400/90">
                {stats.healthyPrimary}/{stats.total}
                {trouble > 0 ? (
                  <span className="text-yellow-400/90 ml-1">
                    · {stats.stalled} stalled
                    {stats.autoPaused > 0 ? ` · ${stats.autoPaused} paused` : ""}
                  </span>
                ) : null}
              </span>
            ) : null}
          </button>
        </td>
      </tr>
      {open ? children : null}
    </>
  );
}
