import { useQuery } from "@tanstack/react-query";
import { api } from "../api";

export type ApprovalQueueSummary = {
  total_pending: number;
  total_queue: number;
  pools: Array<{
    pool_id: number;
    pool_name: string;
    pending: number;
    queue_total: number;
  }>;
};

export function useApprovalQueueSummary() {
  return useQuery({
    queryKey: ["media-pending-summary"],
    queryFn: () => api.media.pendingSummary(),
    staleTime: 30_000,
    refetchInterval: 60_000,
  });
}

function fmt(n: number) {
  return n.toLocaleString();
}

type ApprovalQueueCounterProps = {
  /** When set, show this pool's counts instead of global totals. */
  poolId?: number;
  poolName?: string;
  /** compact = inline badge; banner = full-width callout */
  variant?: "compact" | "banner";
  className?: string;
};

export function ApprovalQueueCounter({
  poolId,
  poolName,
  variant = "banner",
  className = "",
}: ApprovalQueueCounterProps) {
  const { data, isLoading, isError } = useApprovalQueueSummary();

  const poolRow =
    poolId != null && poolId > 0 ? data?.pools?.find((p) => p.pool_id === poolId) : undefined;
  const pending = poolRow ? poolRow.pending : (data?.total_pending ?? 0);
  const queueTotal = poolRow ? poolRow.queue_total : (data?.total_queue ?? 0);
  const scopeLabel = poolRow
    ? poolName || poolRow.pool_name || `Pool ${poolId}`
    : "all pools";

  const ratio = `${fmt(pending)} / ${fmt(queueTotal)}`;
  const approvedInQueue = Math.max(0, queueTotal - pending);
  const isClear = queueTotal === 0;

  const title =
    "Pending approval / items still in queue. Denominator is pending + approved (not posted). Rejects remove items from both counts.";

  if (variant === "compact") {
    return (
      <span
        className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium tabular-nums ${
          isClear
            ? "border-slate-600/80 bg-slate-800/80 text-slate-400"
            : pending > 0
              ? "border-amber-600/50 bg-amber-950/50 text-amber-200"
              : "border-emerald-800/50 bg-emerald-950/40 text-emerald-200"
        } ${className}`}
        title={title}
      >
        {isLoading ? "…" : isError ? "queue ?" : ratio}
      </span>
    );
  }

  return (
    <div
      className={`rounded-lg border px-3 py-2 text-sm ${
        isClear
          ? "border-slate-700/80 bg-slate-800/50 text-slate-400"
          : pending > 0
            ? "border-amber-800/50 bg-amber-950/35 text-amber-100"
            : "border-emerald-900/40 bg-emerald-950/25 text-emerald-100"
      } ${className}`}
      title={title}
    >
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <span className="text-xs uppercase tracking-wide text-slate-500">Approval queue</span>
        <span className="font-semibold tabular-nums text-lg leading-none">
          {isLoading ? "…" : isError ? "unavailable" : ratio}
        </span>
        {!isLoading && !isError && (
          <span className="text-xs text-slate-400">
            {isClear
              ? "clear — nothing awaiting approval"
              : poolId && poolId > 0
                ? `${scopeLabel}`
                : "across all pools"}
          </span>
        )}
      </div>
      {!isLoading && !isError && !isClear && (
        <p className="mt-1 text-xs text-slate-400/90">
          <strong className="text-slate-300">{fmt(pending)}</strong> pending
          {approvedInQueue > 0 ? (
            <>
              {" "}
              · <strong className="text-slate-300">{fmt(approvedInQueue)}</strong> approved (still in queue)
            </>
          ) : null}
          {pending === queueTotal ? null : (
            <>
              {" "}
              · rejects shrink both numbers; approves move pending → approved
            </>
          )}
        </p>
      )}
    </div>
  );
}
