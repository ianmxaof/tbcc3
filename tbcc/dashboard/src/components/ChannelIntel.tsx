import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { api } from "../api";
import { QueryErrorBanner } from "./QueryErrorBanner";

type ChannelIntelRow = {
  id?: number;
  chat_id?: number;
  source_id?: number | null;
  title?: string | null;
  username?: string | null;
  identifier?: string | null;
  forward_enabled?: boolean | null;
  skip_reason?: string | null;
  pool_key?: string | null;
  pool_name?: string | null;
  category?: string | null;
  folder_label?: string | null;
  tags_sample?: string | null;
  posts_per_day?: number | null;
  posts_per_week?: number | null;
  posts_per_month?: number | null;
  messages_sampled?: number;
  last_post_at?: string | null;
  cadence_span_days?: number | null;
  cadence?: { by_month?: Record<string, number>; by_weekday?: Record<string, number> };
  updated_at?: string | null;
};

function fmtNum(n: unknown, digits = 2): string {
  if (n == null || Number.isNaN(Number(n))) return "—";
  return Number(n).toFixed(digits);
}

function fmtDt(raw: unknown): string {
  if (!raw) return "—";
  const d = new Date(String(raw));
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString();
}

function forwardBadge(row: ChannelIntelRow): { label: string; className: string } {
  if (row.forward_enabled === true) return { label: "Yes", className: "text-emerald-400" };
  if (row.forward_enabled === false) return { label: "No", className: "text-rose-400" };
  return { label: "?", className: "text-slate-400" };
}

export function ChannelIntel() {
  const [poolFilter, setPoolFilter] = useState("");
  const [forwardFilter, setForwardFilter] = useState<"" | "yes" | "no" | "unknown">("");

  const forwardParam =
    forwardFilter === "yes" ? true : forwardFilter === "no" ? false : undefined;

  const {
    data: rows = [],
    isPending,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ["channel-intel", poolFilter, forwardFilter],
    queryFn: () =>
      api.sources.listChannelIntel({
        pool_key: poolFilter || undefined,
        forward_enabled: forwardParam,
        limit: 500,
      }),
    refetchInterval: 30_000,
  });

  const typed = rows as ChannelIntelRow[];
  const filtered = useMemo(() => {
    if (forwardFilter === "unknown") {
      return typed.filter((r) => r.forward_enabled == null);
    }
    return typed;
  }, [typed, forwardFilter]);
  const poolKeys = useMemo(() => {
    const s = new Set<string>();
    for (const r of typed) {
      if (r.pool_key) s.add(String(r.pool_key));
    }
    return [...s].sort();
  }, [typed]);

  const summary = useMemo(() => {
    let fwdYes = 0;
    let fwdNo = 0;
    let unknown = 0;
    for (const r of filtered) {
      if (r.forward_enabled === true) fwdYes += 1;
      else if (r.forward_enabled === false) fwdNo += 1;
      else unknown += 1;
    }
    return { total: filtered.length, fwdYes, fwdNo, unknown };
  }, [filtered]);

  return (
    <div className="bg-slate-800 rounded-lg p-4 mb-6">
      <div className="flex flex-wrap items-start justify-between gap-3 mb-3">
        <div>
          <h2 className="text-lg font-medium text-slate-100">Channel intel backlog</h2>
          <p className="text-slate-500 text-xs mt-1 max-w-3xl">
            Competition analytics from inbound scrapes: forward policy, AOF lane, hashtags, posting cadence
            (daily / weekly / monthly buckets from message timestamps). Forward-disabled channels are auto-skipped.
          </p>
        </div>
        <div className="text-xs text-slate-400 font-mono">
          {summary.total} tracked · {summary.fwdYes} forward OK · {summary.fwdNo} blocked · {summary.unknown} unknown
        </div>
      </div>

      {isError ? (
        <QueryErrorBanner
          title="Could not load channel intel"
          message={String((error as Error)?.message ?? error)}
          onRetry={() => void refetch()}
        />
      ) : null}

      <div className="flex flex-wrap gap-2 mb-3">
        <select
          value={poolFilter}
          onChange={(e) => setPoolFilter(e.target.value)}
          className="bg-slate-700 border border-slate-600 rounded px-2 py-1 text-sm text-slate-200"
        >
          <option value="">All pools</option>
          {poolKeys.map((k) => (
            <option key={k} value={k}>
              {k}
            </option>
          ))}
        </select>
        <select
          value={forwardFilter}
          onChange={(e) => setForwardFilter(e.target.value as typeof forwardFilter)}
          className="bg-slate-700 border border-slate-600 rounded px-2 py-1 text-sm text-slate-200"
        >
          <option value="">All forward states</option>
          <option value="yes">Forward enabled</option>
          <option value="no">Forward disabled</option>
          <option value="unknown">Not probed yet</option>
        </select>
        <button
          type="button"
          onClick={() => void refetch()}
          className="px-2 py-1 text-sm bg-slate-700 border border-slate-600 rounded text-slate-200 hover:bg-slate-600"
        >
          Refresh
        </button>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full border border-slate-600 rounded-lg overflow-hidden text-xs">
          <thead className="bg-slate-700">
            <tr>
              <th className="text-left p-2">Channel</th>
              <th className="text-left p-2">Pool</th>
              <th className="text-left p-2">Folder</th>
              <th className="text-left p-2">Forward</th>
              <th className="text-left p-2">Posts/day</th>
              <th className="text-left p-2">Posts/wk</th>
              <th className="text-left p-2">Posts/mo</th>
              <th className="text-left p-2">Last post</th>
              <th className="text-left p-2">Tags</th>
              <th className="text-left p-2">Cadence</th>
            </tr>
          </thead>
          <tbody>
            {isPending && !filtered.length ? (
              <tr>
                <td colSpan={10} className="p-3 text-slate-500">
                  Loading channel intel…
                </td>
              </tr>
            ) : null}
            {!isPending && !filtered.length ? (
              <tr>
                <td colSpan={10} className="p-3 text-slate-500">
                  No channel profiles yet — run a batch scrape to populate intel.
                </td>
              </tr>
            ) : null}
            {filtered.map((r) => {
              const fb = forwardBadge(r);
              const monthKeys = r.cadence?.by_month ? Object.keys(r.cadence.by_month).slice(-3).join(", ") : "";
              return (
                <tr key={String(r.id ?? r.chat_id)} className="border-t border-slate-600 hover:bg-slate-900/40">
                  <td className="p-2">
                    <div className="font-medium text-slate-100 truncate max-w-[160px]" title={r.title ?? ""}>
                      {r.title || r.username || r.identifier || r.chat_id}
                    </div>
                    {r.skip_reason ? (
                      <div className="text-rose-400/80 truncate max-w-[160px]" title={r.skip_reason}>
                        {r.skip_reason}
                      </div>
                    ) : null}
                  </td>
                  <td className="p-2 font-mono text-cyan-300">{r.pool_key || "—"}</td>
                  <td className="p-2 text-slate-400 truncate max-w-[100px]" title={r.folder_label ?? ""}>
                    {r.folder_label || "—"}
                  </td>
                  <td className={`p-2 ${fb.className}`}>{fb.label}</td>
                  <td className="p-2 font-mono">{fmtNum(r.posts_per_day, 2)}</td>
                  <td className="p-2 font-mono">{fmtNum(r.posts_per_week, 1)}</td>
                  <td className="p-2 font-mono">{fmtNum(r.posts_per_month, 1)}</td>
                  <td className="p-2 whitespace-nowrap text-slate-400">{fmtDt(r.last_post_at)}</td>
                  <td className="p-2 text-slate-400 truncate max-w-[140px]" title={r.tags_sample ?? ""}>
                    {r.tags_sample || "—"}
                  </td>
                  <td className="p-2 text-slate-500 truncate max-w-[120px]" title={monthKeys}>
                    {r.messages_sampled ? `${r.messages_sampled} msgs` : "—"}
                    {monthKeys ? ` · ${monthKeys}` : ""}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
