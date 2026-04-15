import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import { useState } from "react";
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from "recharts";
import { Link } from "react-router-dom";
import { QueryErrorBanner } from "../components/QueryErrorBanner";
import { InfoDisclosure } from "../components/InfoDisclosure";

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

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4 mb-6 items-stretch">
        {analyticsData && (
          <div className="bg-slate-800 rounded-lg p-4 border border-slate-700 xl:col-span-1">
            <div className="grid grid-cols-3 gap-3">
              <div>
                <span className="text-slate-400 text-sm">Total</span>
                <p className="text-xl font-medium">{analyticsData.total_subscriptions}</p>
              </div>
              <div>
                <span className="text-slate-400 text-sm">Active</span>
                <p className="text-xl font-medium text-green-400">{analyticsData.active}</p>
              </div>
              <div>
                <span className="text-slate-400 text-sm">Revenue</span>
                <p className="text-xl font-medium text-cyan-400">{analyticsData.revenue_stars} ⭐</p>
              </div>
            </div>
          </div>
        )}

        {pieData.length > 0 && (
          <div className="bg-slate-800 rounded-lg p-4 border border-slate-700 xl:col-span-1">
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

        <div className="bg-slate-800 rounded-lg p-4 border border-slate-700 xl:col-span-1">
          <div className="flex items-center justify-between gap-2 mb-2">
            <h2 className="text-lg font-medium">Shop &amp; products</h2>
            <InfoDisclosure title="Navigation help">
              Create/edit products under{" "}
              <Link to="/bots" className="text-cyan-400 hover:underline font-medium">
                Bots → Shop products
              </Link>
              . Referrals and growth settings:{" "}
              <Link to="/bots" className="text-cyan-400 hover:underline font-medium">
                System → Referrals & growth
              </Link>
              .
            </InfoDisclosure>
          </div>
          <p className="text-slate-400 text-sm">
            The payment bot reads catalog changes on each <code className="text-slate-300">/subscribe</code>; no redeploy needed.
          </p>
        </div>
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
