import { useMemo } from "react";

type ScheduledPost = {
  id: number;
  name?: string | null;
  scheduled_at?: string | null;
  interval_minutes?: number | null;
  channel_name?: string | null;
  campaign_group_id?: string | null;
};

function dedupeCampaignsOneTimeDay(items: ScheduledPost[]): ScheduledPost[] {
  const byCg = new Map<string, ScheduledPost[]>();
  const singles: ScheduledPost[] = [];
  for (const p of items) {
    const cg = p.campaign_group_id;
    if (cg && typeof cg === "string") {
      const arr = byCg.get(cg) ?? [];
      arr.push(p);
      byCg.set(cg, arr);
    } else {
      singles.push(p);
    }
  }
  const merged: ScheduledPost[] = [...singles];
  for (const arr of byCg.values()) {
    const sorted = [...arr].sort((a, b) => a.id - b.id);
    const leader = sorted[0];
    const names = sorted.map((p) => p.channel_name).filter(Boolean) as string[];
    const unique = [...new Set(names)];
    merged.push({
      ...leader,
      channel_name: unique.length ? unique.join(", ") : leader.channel_name,
    });
  }
  merged.sort((a, b) => a.id - b.id);
  return merged;
}

/** Buckets scheduled one-time posts into the next 7 local-midnight day columns. */
export function SchedulerWeek({
  posts,
  onDayClick,
  compact = false,
}: {
  posts: ScheduledPost[];
  /** When set, each day cell is clickable to open scheduling UI for that date (YYYY-MM-DD). */
  onDayClick?: (isoDate: string) => void;
  /** Fits in overview band beside pool chart + pools panel. */
  compact?: boolean;
}) {
  const days = useMemo(() => {
    const start = new Date();
    start.setHours(0, 0, 0, 0);
    const out: { label: string; iso: string; items: ScheduledPost[] }[] = [];
    for (let d = 0; d < 7; d++) {
      const dt = new Date(start);
      dt.setDate(start.getDate() + d);
      const iso = dt.toISOString().slice(0, 10);
      out.push({
        label: compact
          ? dt.toLocaleDateString(undefined, { weekday: "short", day: "numeric" })
          : dt.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" }),
        iso,
        items: [],
      });
    }
    for (const p of posts) {
      if (!p.scheduled_at || p.interval_minutes) continue;
      const day = String(p.scheduled_at).slice(0, 10);
      const col = out.find((x) => x.iso === day);
      if (col) col.items.push(p);
    }
    for (const col of out) {
      col.items = dedupeCampaignsOneTimeDay(col.items);
    }
    return out;
  }, [posts, compact]);

  const cellMinH = compact ? "min-h-[3.25rem]" : "min-h-[72px]";
  const wrapClass = compact
    ? "flex flex-col h-full min-h-0"
    : "mb-6 border border-slate-600 rounded-lg p-3 bg-slate-800/50";

  return (
    <div className={wrapClass}>
      <div className={`shrink-0 ${compact ? "px-2 py-1 border-b border-slate-600/70" : "mb-2"}`}>
        <h3 className={compact ? "text-[10px] font-semibold uppercase tracking-wider text-slate-500" : "text-sm font-medium text-slate-200"}>
          {compact ? "Week" : "Next 7 days (one-time schedules)"}
        </h3>
        {!compact && onDayClick ? (
          <p className="text-slate-500 text-[11px] mt-1">
            Click a day to open the schedule form for that date (one-time or recurring interval).
          </p>
        ) : null}
      </div>
      <div
        className={`grid grid-cols-7 gap-0.5 flex-1 min-h-0 ${compact ? "p-1.5 text-[10px]" : "text-xs min-h-[72px]"}`}
      >
        {days.map((d) => {
          const inner = (
            <>
              <div
                className={`text-slate-400 font-medium truncate ${compact ? "mb-0.5 leading-tight" : "mb-1"}`}
                title={d.iso}
              >
                {d.label}
              </div>
              <ul className={`text-slate-300 pointer-events-none ${compact ? "space-y-px leading-tight" : "space-y-1"}`}>
                {d.items.slice(0, compact ? 2 : 20).map((p) => (
                  <li key={p.id} className="truncate" title={p.name || `#${p.id}`}>
                    {!compact && p.channel_name ? <span className="text-slate-500">{p.channel_name}: </span> : null}
                    {p.name || `#${p.id}`}
                  </li>
                ))}
                {d.items.length > (compact ? 2 : 0) && compact ? (
                  <li className="text-slate-500">+{d.items.length - 2}</li>
                ) : null}
                {d.items.length === 0 && <li className="text-slate-600">—</li>}
              </ul>
            </>
          );
          if (onDayClick) {
            return (
              <button
                key={d.iso}
                type="button"
                onClick={() => onDayClick(d.iso)}
                className={`border border-slate-600/80 rounded-sm bg-slate-900/50 text-left w-full ${cellMinH} hover:bg-slate-800/90 hover:border-cyan-600/50 focus:outline-none focus:ring-1 focus:ring-cyan-500 transition-colors ${compact ? "p-0.5" : "p-1"}`}
                aria-label={`Open schedule for ${d.label}`}
                title={compact ? "Click to schedule" : undefined}
              >
                {inner}
              </button>
            );
          }
          return (
            <div key={d.iso} className={`border border-slate-600 rounded-sm bg-slate-900/40 ${compact ? "p-0.5" : "p-1"} ${cellMinH}`}>
              {inner}
            </div>
          );
        })}
      </div>
    </div>
  );
}
