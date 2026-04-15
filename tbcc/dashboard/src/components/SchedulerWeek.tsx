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
}: {
  posts: ScheduledPost[];
  /** When set, each day cell is clickable to open scheduling UI for that date (YYYY-MM-DD). */
  onDayClick?: (isoDate: string) => void;
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
        label: dt.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" }),
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
  }, [posts]);

  return (
    <div className="mb-6 border border-slate-600 rounded-lg p-3 bg-slate-800/50">
      <h3 className="text-sm font-medium text-slate-200 mb-2">Next 7 days (one-time schedules)</h3>
      {onDayClick ? (
        <p className="text-slate-500 text-[11px] mb-2">
          Click a day to open the schedule form for that date (one-time or recurring interval).
        </p>
      ) : null}
      <div className="grid grid-cols-7 gap-1 text-xs min-h-[72px]">
        {days.map((d) => {
          const inner = (
            <>
              <div className="text-slate-400 font-medium mb-1 truncate" title={d.iso}>
                {d.label}
              </div>
              <ul className="space-y-1 text-slate-300 pointer-events-none">
                {d.items.map((p) => (
                  <li key={p.id} className="truncate" title={p.name || `#${p.id}`}>
                    {p.channel_name ? <span className="text-slate-500">{p.channel_name}: </span> : null}
                    {p.name || `Job #${p.id}`}
                  </li>
                ))}
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
                className="border border-slate-600 rounded p-1 bg-slate-900/40 text-left w-full min-h-[72px] hover:bg-slate-800/90 hover:border-cyan-600/50 focus:outline-none focus:ring-2 focus:ring-cyan-500 transition-colors"
                aria-label={`Open schedule for ${d.label}`}
              >
                {inner}
              </button>
            );
          }
          return (
            <div key={d.iso} className="border border-slate-600 rounded p-1 bg-slate-900/40">
              {inner}
            </div>
          );
        })}
      </div>
    </div>
  );
}
