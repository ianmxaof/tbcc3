import { useQuery } from "@tanstack/react-query";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "../api";
import { QueryErrorBanner } from "../components/QueryErrorBanner";
import { InfoDisclosure } from "../components/InfoDisclosure";

export function Analytics() {
  const rangeDays = 30;

  const subQ = useQuery({
    queryKey: ["analytics", "subscriptions"],
    queryFn: () => api.analytics.subscriptions(),
  });

  const summaryQ = useQuery({
    queryKey: ["analytics", "post-events-summary", rangeDays],
    queryFn: () => api.analytics.postEventsSummary(rangeDays),
  });

  const eventsQ = useQuery({
    queryKey: ["analytics", "post-events", 40],
    queryFn: () => api.analytics.postEvents({ limit: 40, offset: 0 }),
  });

  const chartData = summaryQ.data?.by_day ?? [];

  return (
    <div className="max-w-5xl space-y-10">
      <div className="flex items-start justify-between gap-3">
        <h1 className="text-xl font-semibold text-slate-100">Analytics</h1>
        <InfoDisclosure className="shrink-0">
          Step 1: subscription totals and an append-only outbound Telegram log (scheduled sends + pool albums). Step 2:
          AI tag/caption suggestions remain under Media Library (human review before apply). Deeper engagement metrics
          can layer in later.
        </InfoDisclosure>
      </div>

      {subQ.isError && (
        <QueryErrorBanner
          title="Could not load subscriptions"
          message={String((subQ.error as Error)?.message ?? subQ.error)}
          onRetry={() => void subQ.refetch()}
        />
      )}
      {summaryQ.isError && (
        <QueryErrorBanner
          title="Could not load post summary"
          message={String((summaryQ.error as Error)?.message ?? summaryQ.error)}
          onRetry={() => void summaryQ.refetch()}
        />
      )}
      {eventsQ.isError && (
        <QueryErrorBanner
          title="Could not load recent events"
          message={String((eventsQ.error as Error)?.message ?? eventsQ.error)}
          onRetry={() => void eventsQ.refetch()}
        />
      )}

      <section>
        <h2 className="text-sm font-medium text-slate-300 uppercase tracking-wide mb-3">Subscriptions</h2>
        {subQ.isPending ? (
          <p className="text-slate-500 text-sm">Loading…</p>
        ) : subQ.data ? (
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
            <StatCard label="Total" value={subQ.data.total_subscriptions} />
            <StatCard label="Active" value={subQ.data.active} />
            <StatCard label="Expired" value={subQ.data.expired} />
            <StatCard label="Cancelled" value={subQ.data.cancelled} />
            <StatCard label="Revenue (Stars)" value={subQ.data.revenue_stars} />
          </div>
        ) : null}
      </section>

      <section>
        <h2 className="text-sm font-medium text-slate-300 uppercase tracking-wide mb-3">
          Outbound posts (last {rangeDays} days)
        </h2>
        {summaryQ.isPending ? (
          <p className="text-slate-500 text-sm">Loading…</p>
        ) : summaryQ.data ? (
          <>
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mb-6">
              <StatCard label="Scheduled sends" value={summaryQ.data.totals.scheduled_post_sent} />
              <StatCard label="Pool albums" value={summaryQ.data.totals.pool_album_posted} />
              <StatCard label="All events" value={summaryQ.data.totals.all} />
              <StatCard label="Succeeded" value={summaryQ.data.totals.ok} />
              <StatCard label="Failed" value={summaryQ.data.totals.failed} />
            </div>

            {chartData.length > 0 ? (
              <div className="grid grid-cols-1 xl:grid-cols-4 gap-4 items-stretch">
                <div className="xl:col-span-3 h-72 w-full min-w-0 bg-slate-900/50 border border-slate-700 rounded-lg p-3">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                      <XAxis dataKey="date" tick={{ fill: "#94a3b8", fontSize: 11 }} stroke="#475569" />
                      <YAxis allowDecimals={false} tick={{ fill: "#94a3b8", fontSize: 11 }} stroke="#475569" />
                      <Tooltip
                        contentStyle={{ backgroundColor: "#1e293b", border: "1px solid #334155", borderRadius: 8 }}
                        labelStyle={{ color: "#e2e8f0" }}
                      />
                      <Legend />
                      <Bar dataKey="scheduled_post_sent" name="Scheduled" stackId="a" fill="#22d3ee" />
                      <Bar dataKey="pool_album_posted" name="Pool album" stackId="a" fill="#a78bfa" />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                <div className="xl:col-span-1 bg-slate-900/40 border border-slate-700 rounded-lg p-3">
                  <h3 className="text-xs font-medium text-slate-400 uppercase tracking-wide mb-2">By channel</h3>
                  {summaryQ.data.by_channel.length > 0 ? (
                    <ul className="text-sm text-slate-300 space-y-1 max-h-64 overflow-y-auto pr-1">
                      {summaryQ.data.by_channel.map((c) => (
                        <li key={c.channel_id}>
                          <span className="text-slate-100">{c.channel_name}</span>
                          <span className="text-slate-500"> — {c.count}</span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-slate-500 text-sm">No channel totals yet.</p>
                  )}
                </div>
              </div>
            ) : (
              <p className="text-slate-500 text-sm">
                No outbound post events in this window yet. Events are recorded when Celery sends scheduled posts or
                pool interval albums.
              </p>
            )}
          </>
        ) : null}
      </section>

      <section>
        <h2 className="text-sm font-medium text-slate-300 uppercase tracking-wide mb-3">Recent post events</h2>
        {eventsQ.isPending ? (
          <p className="text-slate-500 text-sm">Loading…</p>
        ) : eventsQ.data && eventsQ.data.items.length > 0 ? (
          <div className="overflow-x-auto border border-slate-700 rounded-lg">
            <table className="w-full text-sm text-left">
              <thead className="bg-slate-800/80 text-slate-400">
                <tr>
                  <th className="px-3 py-2 font-medium">Time (UTC)</th>
                  <th className="px-3 py-2 font-medium">Type</th>
                  <th className="px-3 py-2 font-medium">Channel</th>
                  <th className="px-3 py-2 font-medium">Ref</th>
                  <th className="px-3 py-2 font-medium">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700">
                {eventsQ.data.items.map((row) => (
                  <tr key={row.id} className="hover:bg-slate-800/40">
                    <td className="px-3 py-2 text-slate-300 whitespace-nowrap">
                      {row.created_at ? row.created_at.replace("Z", "") : "—"}
                    </td>
                    <td className="px-3 py-2 text-slate-200">{row.event_type}</td>
                    <td className="px-3 py-2 text-slate-400">{row.channel_name ?? row.channel_id ?? "—"}</td>
                    <td className="px-3 py-2 text-slate-500">
                      {row.scheduled_post_id != null ? `post #${row.scheduled_post_id}` : ""}
                      {row.pool_id != null ? `pool #${row.pool_id}` : ""}
                      {row.scheduled_post_id == null && row.pool_id == null ? "—" : ""}
                    </td>
                    <td className="px-3 py-2">
                      {row.ok ? (
                        <span className="text-emerald-400">ok</span>
                      ) : (
                        <span className="text-red-400" title={row.error_message || ""}>
                          failed
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-slate-500 text-sm">No events logged yet.</p>
        )}
      </section>
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border border-slate-700 bg-slate-800/40 px-3 py-2">
      <div className="text-slate-500 text-xs uppercase tracking-wide">{label}</div>
      <div className="text-lg font-semibold text-slate-100 tabular-nums">{value}</div>
    </div>
  );
}
