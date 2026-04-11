import { useMemo } from "react";

type ScheduledPost = {
  id: number;
  name?: string | null;
  scheduled_at?: string | null;
  interval_minutes?: number | null;
  channel_name?: string | null;
};

/** Buckets scheduled one-time posts into the next 7 local-midnight day columns. */
export function SchedulerWeek({ posts }: { posts: ScheduledPost[] }) {
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
    return out;
  }, [posts]);

  return (
    <div className="mb-6 border border-slate-600 rounded-lg p-3 bg-slate-800/50">
      <h3 className="text-sm font-medium text-slate-200 mb-2">Next 7 days (one-time schedules)</h3>
      <div className="grid grid-cols-7 gap-1 text-xs min-h-[72px]">
        {days.map((d) => (
          <div key={d.iso} className="border border-slate-600 rounded p-1 bg-slate-900/40">
            <div className="text-slate-400 font-medium mb-1 truncate" title={d.iso}>
              {d.label}
            </div>
            <ul className="space-y-1 text-slate-300">
              {d.items.map((p) => (
                <li key={p.id} className="truncate" title={p.name || `#${p.id}`}>
                  {p.channel_name ? <span className="text-slate-500">{p.channel_name}: </span> : null}
                  {p.name || `Job #${p.id}`}
                </li>
              ))}
              {d.items.length === 0 && <li className="text-slate-600">—</li>}
            </ul>
          </div>
        ))}
      </div>
    </div>
  );
}
