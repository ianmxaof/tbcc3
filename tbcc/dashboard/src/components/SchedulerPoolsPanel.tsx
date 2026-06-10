import { useMemo } from "react";
import { formatUtcForDashboard } from "../utils/formatUtc";

/** Fixed-size pool chip grid — sits beside pool-intervals chart (not a full-width strip). */
export function SchedulerPoolsPanel({
  scheduledPosts,
  poolMap,
}: {
  scheduledPosts: Array<Record<string, unknown>>;
  poolMap: Record<string, Record<string, unknown>>;
}) {
  const chips = useMemo(() => {
    const seen = new Set<number>();
    const out: Array<Record<string, unknown>> = [];
    for (const row of scheduledPosts) {
      const pid = Number(row.pool_id);
      if (!Number.isFinite(pid) || pid <= 0 || seen.has(pid)) continue;
      const rec = poolMap[String(pid)];
      if (!rec) continue;
      seen.add(pid);
      out.push(rec);
    }
    return out.sort((a, b) => String(a.name || "").localeCompare(String(b.name || "")));
  }, [scheduledPosts, poolMap]);

  const totalApproved = chips.reduce((n, p) => n + Number(p.approved_count ?? 0), 0);

  return (
    <div className="tbcc-panel flex flex-col h-full min-h-0 w-full rounded-md border border-slate-600/90 bg-slate-900/55 overflow-hidden">
      <div className="shrink-0 px-2 py-1 border-b border-slate-600/70 flex flex-wrap items-baseline gap-x-1.5 gap-y-0">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">Pools</span>
        <span className="text-[10px] text-slate-500 tabular-nums">
          {chips.length} linked · {totalApproved} approved
        </span>
      </div>
      <div className="flex-1 min-h-0 overflow-y-auto overflow-x-hidden p-1.5">
        {chips.length === 0 ? (
          <p className="text-[10px] text-slate-500 px-0.5">No pools linked to jobs.</p>
        ) : (
          <div className="grid grid-cols-2 gap-1 content-start">
            {chips.map((p) => {
              const approved = Number(p.approved_count ?? 0);
              const album = Number(p.album_size ?? 5);
              const last = p.last_posted ? formatUtcForDashboard(String(p.last_posted)) : "never";
              return (
                <span
                  key={String(p.id)}
                  title={`${String(p.name)} · ${approved}/${album} approved · interval ${p.interval_minutes}m · last pool run ${last}`}
                  className="inline-flex items-center gap-1 rounded border border-slate-600/90 bg-slate-800/80 px-1.5 py-0.5 text-[10px] leading-tight min-w-0"
                >
                  <span className="truncate text-slate-300">{String(p.name || `Pool ${p.id}`)}</span>
                  <span className={`tabular-nums shrink-0 ${approved > 0 ? "text-cyan-400" : "text-slate-500"}`}>
                    {approved}/{album}
                  </span>
                </span>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
