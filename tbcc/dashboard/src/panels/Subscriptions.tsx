import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import { useState } from "react";
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from "recharts";
import { Link } from "react-router-dom";
import { ScheduledPostsList } from "../components/ScheduledPostsList";
import { QueryErrorBanner } from "../components/QueryErrorBanner";

export function Subscriptions() {
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined);
  const {
    data: subs = [],
    isPending: subsPending,
    isError: subsError,
    error: subsErr,
    refetch: refetchSubs,
  } = useQuery({
    queryKey: ["subscriptions", statusFilter],
    queryFn: () => api.subscriptions.list(statusFilter),
  });
  const { data: plans = [] } = useQuery({
    queryKey: ["subscriptionPlans"],
    queryFn: () => api.subscriptionPlans.list(),
  });
  const { data: analyticsData } = useQuery({
    queryKey: ["analytics", "subscriptions"],
    queryFn: () => api.analytics.subscriptions(),
  });

  const statusCounts = (subs as Array<Record<string, unknown>>).reduce<Record<string, number>>((acc, s) => {
    const st = String(s.status || "unknown");
    acc[st] = (acc[st] ?? 0) + 1;
    return acc;
  }, {});
  const pieData = Object.entries(statusCounts).map(([name, value]) => ({ name, value }));
  const COLORS = ["#22c55e", "#eab308", "#ef4444", "#64748b"];

  return (
    <div>
      <h1 className="text-2xl font-semibold mb-4">Subscriptions</h1>
      {subsError && (
        <QueryErrorBanner
          title="Could not load subscriptions"
          message={String((subsErr as Error)?.message ?? subsErr)}
          onRetry={() => void refetchSubs()}
        />
      )}

      {analyticsData && (
        <div className="bg-slate-800 rounded-lg p-4 mb-6 max-w-md flex flex-wrap gap-4">
          <div>
            <span className="text-slate-400 text-sm">Total</span>
            <p className="text-xl font-medium">{analyticsData.total_subscriptions}</p>
          </div>
          <div>
            <span className="text-slate-400 text-sm">Active</span>
            <p className="text-xl font-medium text-green-400">{analyticsData.active}</p>
          </div>
          <div>
            <span className="text-slate-400 text-sm">Revenue (Stars)</span>
            <p className="text-xl font-medium text-cyan-400">{analyticsData.revenue_stars} ⭐</p>
          </div>
        </div>
      )}

      <div className="bg-slate-800 rounded-lg p-4 mb-6 max-w-lg border border-slate-700">
        <h2 className="text-lg font-medium mb-2">Shop &amp; subscription products</h2>
        <p className="text-slate-400 text-sm mb-3">
          Create and edit products (AOF access, Stars pricing, captions) under{" "}
          <Link to="/bots" className="text-cyan-400 hover:underline font-medium">
            Bots → Shop products
          </Link>
          . The payment bot loads the catalog from the API on each <code className="text-slate-300">/subscribe</code> — no
          redeploy needed. Referrals, landing bulletin, and milestone chat targets:{" "}
          <Link to="/growth" className="text-cyan-400 hover:underline font-medium">
            Growth
          </Link>
          .
        </p>
      </div>

      <div className="mb-8">
        <h2 className="text-lg font-medium mb-2">Active posting (cron)</h2>
        <p className="text-slate-400 text-sm mb-4">
          Recurring channel posts (interval-based jobs). Click a row to edit caption, how often it runs, and — when a
          content pool is linked — album size and random vs queue order (same fields as the Pools tab). Full scheduler
          UI (including one-time posts) is on the{" "}
          <Link to="/scheduler" className="text-cyan-400 hover:underline">
            Scheduler
          </Link>{" "}
          tab.
        </p>
        <ScheduledPostsList compactRecurringOnly />
      </div>

      <div className="flex gap-2 mb-4">
        <button
          onClick={() => setStatusFilter(undefined)}
          className={`px-3 py-1 rounded ${!statusFilter ? "bg-cyan-600 text-white" : "bg-slate-700 text-slate-300"}`}
        >
          All
        </button>
        {["active", "expired", "cancelled"].map((s) => (
          <button
            key={s}
            onClick={() => setStatusFilter(s)}
            className={`px-3 py-1 rounded ${statusFilter === s ? "bg-cyan-600 text-white" : "bg-slate-700 text-slate-300"}`}
          >
            {s}
          </button>
        ))}
      </div>
      {pieData.length > 0 && (
        <div className="bg-slate-800 rounded-lg p-4 mb-6 max-w-sm">
          <h2 className="text-lg font-medium mb-3">By status</h2>
          <ResponsiveContainer width="100%" height={200}>
            <PieChart>
              <Pie
                data={pieData}
                dataKey="value"
                nameKey="name"
                cx="50%"
                cy="50%"
                outerRadius={70}
                label={({ name, value }) => `${name}: ${value}`}
              >
                {pieData.map((_, i) => (
                  <Cell key={i} fill={COLORS[i % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{ backgroundColor: "#1e293b", border: "1px solid #475569" }}
              />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        </div>
      )}
      <div className="overflow-x-auto">
        <table className="w-full border border-slate-600 rounded-lg overflow-hidden">
          <thead className="bg-slate-700">
            <tr>
              <th className="text-left p-3">ID</th>
              <th className="text-left p-3">User ID</th>
              <th className="text-left p-3">Plan</th>
              <th className="text-left p-3">Status</th>
              <th className="text-left p-3">Expires</th>
              <th className="text-left p-3">Payment</th>
            </tr>
          </thead>
          <tbody>
            {subsPending && !subs.length && !subsError ? (
              <tr>
                <td colSpan={6} className="p-4 text-slate-500">
                  Loading subscriptions…
                </td>
              </tr>
            ) : null}
            {subs.map((s: Record<string, unknown>) => (
              <tr key={String(s.id)} className="border-t border-slate-600 hover:bg-slate-800/50">
                <td className="p-3">{String(s.id)}</td>
                <td className="p-3 font-mono text-sm">{String(s.telegram_user_id)}</td>
                <td className="p-3">
                  {String(
                    s.plan_id != null
                      ? (plans as Array<Record<string, unknown>>).find((p) => p.id === s.plan_id)?.name ?? `#${s.plan_id}`
                      : s.plan ?? "—"
                  )}
                </td>
                <td className="p-3">
                  <span
                    className={`px-2 py-0.5 rounded text-sm ${
                      s.status === "active"
                        ? "bg-green-900/50 text-green-300"
                        : s.status === "expired"
                          ? "bg-slate-600 text-slate-300"
                          : "bg-red-900/50 text-red-300"
                    }`}
                  >
                    {String(s.status)}
                  </span>
                </td>
                <td className="p-3 text-slate-400 text-sm">
                  {s.expires_at ? String(s.expires_at).slice(0, 19) : "—"}
                </td>
                <td className="p-3 text-slate-400">{String(s.payment_method ?? "—")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {subs.length === 0 && !subsPending && !subsError && (
        <p className="text-slate-500 mt-4">No subscriptions.</p>
      )}
    </div>
  );
}
