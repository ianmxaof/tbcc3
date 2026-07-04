import { useState } from "react";
import { countdownStatusLabel } from "../utils/schedulerIntervalCountdown";
import type { SchedulingStackHealth } from "../utils/schedulerIntervalCountdown";
import { computeSchedulerCountdown } from "../utils/schedulerIntervalCountdown";
import {
  classifySchedulerPost,
  formatDurationHms,
  type SchedulerPostRecord,
} from "../utils/schedulerPostStatus";
import { formatPtForDashboard } from "../utils/formatUtc";

type Props = {
  post: SchedulerPostRecord;
  scheduling?: SchedulingStackHealth | null;
  nowMs: number;
  showTroubleDetail?: boolean;
};

export function SchedulerPostStatusCell({ post, scheduling, nowMs, showTroubleDetail }: Props) {
  const [expanded, setExpanded] = useState(false);
  const classified = classifySchedulerPost(post, scheduling, nowMs);
  const snapshot = computeSchedulerCountdown({
    lastPostedAt: post.last_posted_at,
    intervalMinutes: post.interval_minutes,
    scheduledAt: post.scheduled_at,
    sentAt: post.sent_at,
    autoPausedAt: post.posting_auto_paused_at,
    nowMs,
  });
  const statusUi = snapshot ? countdownStatusLabel(snapshot, scheduling) : null;

  const isTrouble =
    classified.phase === "stalled" || classified.phase === "paused" || showTroubleDetail;
  const durationMs =
    classified.phase === "paused"
      ? classified.pausedSinceMs
      : classified.phase === "stalled"
        ? classified.stalledSinceMs
        : null;

  const labelWithDuration =
    durationMs != null && isTrouble
      ? `${statusUi?.label || classified.phase} ${formatDurationHms(durationMs)}`
      : statusUi?.label;

  const streak = post.send_failure_streak != null ? Number(post.send_failure_streak) : 0;

  return (
    <div className="min-w-[5.5rem]" onClick={(e) => e.stopPropagation()}>
      {statusUi ? (
        <button
          type="button"
          className={`text-left text-[10px] font-medium ${statusUi.className} ${
            isTrouble && (classified.errorText || streak > 0) ? "underline decoration-dotted cursor-pointer" : ""
          }`}
          title={classified.errorText || statusUi.title}
          onClick={() => {
            if (isTrouble && (classified.errorText || streak > 0)) setExpanded((v) => !v);
          }}
        >
          {labelWithDuration}
          {isTrouble && (classified.errorText || streak > 0) ? (
            <span className="ml-0.5 text-slate-500">{expanded ? "▴" : "▾"}</span>
          ) : null}
        </button>
      ) : (
        <span className="text-slate-500 text-[10px]">—</span>
      )}
      {expanded && isTrouble ? (
        <div className="mt-1 rounded border border-slate-600/80 bg-slate-900/90 p-1.5 text-[10px] text-slate-300 space-y-1 max-w-[14rem]">
          {classified.errorText ? <p className="text-rose-200/90 break-words">{classified.errorText}</p> : null}
          {streak > 0 ? <p className="text-slate-400">Send failure streak: {streak}</p> : null}
          {post.last_posted_at ? (
            <p className="text-slate-500">Last post {formatPtForDashboard(String(post.last_posted_at))} PT</p>
          ) : null}
          {snapshot?.nextRunMs != null ? (
            <p className="text-slate-500">
              Expected {formatPtForDashboard(new Date(snapshot.nextRunMs).toISOString())} PT
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
