import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Link } from "react-router-dom";
import { api } from "../api";
import { QueryErrorBanner } from "../components/QueryErrorBanner";
import { InfoDisclosure } from "../components/InfoDisclosure";

const RANGE_OPTIONS = [
  { label: "All time", value: undefined as number | undefined },
  { label: "30 days", value: 30 },
  { label: "7 days", value: 7 },
];

const MANUAL_SOURCES = [
  { value: "linkvertise", label: "Linkvertise" },
  { value: "admaven", label: "AdMaven" },
  { value: "workink", label: "Work.ink" },
  { value: "bmc", label: "Buy Me a Coffee" },
  { value: "affiliate", label: "Affiliate program" },
  { value: "digital_product", label: "Digital product" },
  { value: "other", label: "Other" },
];

const SYNC_SOURCES = [
  { key: "linkvertise", label: "Linkvertise" },
  { key: "admaven", label: "AdMaven" },
  { key: "workink", label: "Work.ink" },
  { key: "bmc", label: "Buy Me a Coffee" },
];

export function IncomePanel() {
  const qc = useQueryClient();
  const [rangeDays, setRangeDays] = useState<number | undefined>(undefined);
  const [manualSource, setManualSource] = useState("linkvertise");
  const [manualAmount, setManualAmount] = useState("");
  const [manualLabel, setManualLabel] = useState("");
  const [manualPeriod, setManualPeriod] = useState("");
  const [manualNotes, setManualNotes] = useState("");
  const [manualAffiliateId, setManualAffiliateId] = useState("");
  const [syncMsg, setSyncMsg] = useState<string | null>(null);

  const summaryQ = useQuery({
    queryKey: ["analytics", "income", "summary", rangeDays],
    queryFn: () => api.analytics.incomeSummary({ days: rangeDays }),
  });

  const entriesQ = useQuery({
    queryKey: ["analytics", "income", "entries", rangeDays],
    queryFn: () => api.analytics.incomeEntries({ days: rangeDays, limit: 40 }),
  });

  const affiliatesQ = useQuery({
    queryKey: ["analytics", "income", "affiliates"],
    queryFn: () => api.analytics.incomeAffiliates(),
  });

  const manualMut = useMutation({
    mutationFn: () =>
      api.analytics.incomeManual({
        source: manualSource,
        amount_usd: parseFloat(manualAmount),
        source_label: manualLabel.trim() || undefined,
        period_key: manualPeriod.trim() || undefined,
        notes: manualNotes.trim() || undefined,
        promo_affiliate_link_id:
          manualSource === "affiliate" && manualAffiliateId.trim()
            ? parseInt(manualAffiliateId, 10)
            : undefined,
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["analytics", "income"] });
      setManualAmount("");
      setManualNotes("");
    },
  });

  const syncMut = useMutation({
    mutationFn: (sources?: string[]) => api.analytics.incomeSync({ sources }),
    onSuccess: (data) => {
      void qc.invalidateQueries({ queryKey: ["analytics", "income"] });
      const lines = (data.results ?? []).map((r) => {
        if (r.skipped) return `${r.source}: no new earnings`;
        if (r.error) return `${r.source}: ${r.error}`;
        if (r.delta_usd != null) return `${r.source}: +$${r.delta_usd}`;
        return `${r.source}: ok`;
      });
      setSyncMsg(lines.join(" · ") || "Sync complete");
    },
    onError: (e) => setSyncMsg(String((e as Error).message ?? e)),
  });

  const chartData = useMemo(() => {
    return (summaryQ.data?.by_source ?? []).map((row) => ({
      name: row.label.length > 22 ? `${row.label.slice(0, 20)}…` : row.label,
      usd: Math.round(row.usd_cents) / 100,
      fullLabel: row.label,
      category: row.category,
    }));
  }, [summaryQ.data]);

  const totals = summaryQ.data?.totals;

  return (
    <div className="max-w-6xl space-y-8">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-100">Income Hub</h1>
          <p className="text-slate-400 text-sm mt-1">
            Unified rollup across Stars, crypto, gates, affiliates, and donations.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Link to="/subscriptions" className="text-sm text-cyan-400 hover:text-cyan-300">
            Commerce →
          </Link>
          <InfoDisclosure title="Income Hub help">
            Internal sources auto-record from Telegram Stars and NOWPayments. External platforms sync via
            API/scrape or manual weekly entries. Affiliate rows come from{" "}
            <Link to="/misc/tools" className="text-cyan-400">
              Misc → Promo affiliates
            </Link>
            .
          </InfoDisclosure>
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        {RANGE_OPTIONS.map((opt) => (
          <button
            key={opt.label}
            type="button"
            onClick={() => setRangeDays(opt.value)}
            className={`px-3 py-1.5 rounded text-sm border ${
              rangeDays === opt.value
                ? "bg-cyan-900/40 border-cyan-600 text-cyan-300"
                : "border-slate-600 text-slate-400 hover:border-slate-500"
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {summaryQ.isError && (
        <QueryErrorBanner
          title="Could not load income summary"
          message={String((summaryQ.error as Error)?.message ?? summaryQ.error)}
          onRetry={() => void summaryQ.refetch()}
        />
      )}

      {summaryQ.data && totals && (
        <section className="grid grid-cols-2 lg:grid-cols-5 gap-3">
          <StatCard label="Total (USD)" value={`$${totals.usd.toFixed(2)}`} accent />
          <StatCard label="Internal" value={`$${totals.internal_usd.toFixed(2)}`} />
          <StatCard label="External" value={`$${totals.external_usd.toFixed(2)}`} />
          <StatCard label="Stars (XTR)" value={`${totals.stars} ⭐`} />
          <StatCard label="Entries" value={String(totals.entry_count)} />
        </section>
      )}

      {chartData.length > 0 && (
        <section className="bg-slate-800 rounded-lg p-4 border border-slate-700">
          <h2 className="text-sm font-medium text-slate-300 uppercase tracking-wide mb-4">By source</h2>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 48 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="name" tick={{ fill: "#94a3b8", fontSize: 11 }} angle={-28} textAnchor="end" height={70} />
              <YAxis tick={{ fill: "#94a3b8", fontSize: 11 }} tickFormatter={(v) => `$${v}`} />
              <Tooltip
                contentStyle={{ backgroundColor: "#1e293b", border: "1px solid #475569" }}
                formatter={(value: number, _n, item) => [
                  `$${value.toFixed(2)}`,
                  (item.payload as { fullLabel?: string }).fullLabel ?? "USD",
                ]}
              />
              <Bar dataKey="usd" fill="#22d3ee" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </section>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <section className="bg-slate-800 rounded-lg p-4 border border-slate-700 space-y-3">
          <h2 className="text-lg font-medium">Manual entry</h2>
          <p className="text-slate-400 text-sm">
            Paste weekly totals from dashboards that lack API access (Undress USD, BotyNude, etc.).
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <label className="block text-sm">
              <span className="text-slate-400">Source</span>
              <select
                value={manualSource}
                onChange={(e) => setManualSource(e.target.value)}
                className="mt-1 w-full bg-slate-900 border border-slate-600 rounded px-2 py-1.5"
              >
                {MANUAL_SOURCES.map((s) => (
                  <option key={s.value} value={s.value}>
                    {s.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="block text-sm">
              <span className="text-slate-400">Amount (USD)</span>
              <input
                type="number"
                min="0.01"
                step="0.01"
                value={manualAmount}
                onChange={(e) => setManualAmount(e.target.value)}
                className="mt-1 w-full bg-slate-900 border border-slate-600 rounded px-2 py-1.5"
                placeholder="42.50"
              />
            </label>
            <label className="block text-sm sm:col-span-2">
              <span className="text-slate-400">Label (optional)</span>
              <input
                value={manualLabel}
                onChange={(e) => setManualLabel(e.target.value)}
                className="mt-1 w-full bg-slate-900 border border-slate-600 rounded px-2 py-1.5"
                placeholder="Undress referral USD — week 26"
              />
            </label>
            <label className="block text-sm">
              <span className="text-slate-400">Period key (optional)</span>
              <input
                value={manualPeriod}
                onChange={(e) => setManualPeriod(e.target.value)}
                className="mt-1 w-full bg-slate-900 border border-slate-600 rounded px-2 py-1.5"
                placeholder="2026-W26"
              />
            </label>
            {manualSource === "affiliate" && (
              <label className="block text-sm">
                <span className="text-slate-400">Affiliate link ID</span>
                <input
                  value={manualAffiliateId}
                  onChange={(e) => setManualAffiliateId(e.target.value)}
                  className="mt-1 w-full bg-slate-900 border border-slate-600 rounded px-2 py-1.5"
                  placeholder="12"
                />
              </label>
            )}
            <label className="block text-sm sm:col-span-2">
              <span className="text-slate-400">Notes</span>
              <input
                value={manualNotes}
                onChange={(e) => setManualNotes(e.target.value)}
                className="mt-1 w-full bg-slate-900 border border-slate-600 rounded px-2 py-1.5"
              />
            </label>
          </div>
          <button
            type="button"
            disabled={manualMut.isPending || !manualAmount || parseFloat(manualAmount) <= 0}
            onClick={() => manualMut.mutate()}
            className="px-4 py-2 rounded bg-cyan-700 hover:bg-cyan-600 disabled:opacity-50 text-sm font-medium"
          >
            {manualMut.isPending ? "Saving…" : "Add entry"}
          </button>
          {manualMut.isError && (
            <p className="text-red-400 text-sm">{String((manualMut.error as Error).message)}</p>
          )}
        </section>

        <section className="bg-slate-800 rounded-lg p-4 border border-slate-700 space-y-3">
          <h2 className="text-lg font-medium">External sync</h2>
          <p className="text-slate-400 text-sm">
            Pull cumulative balances where configured (.env URLs/tokens). Records only new deltas since last sync.
          </p>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              disabled={syncMut.isPending}
              onClick={() => syncMut.mutate(undefined)}
              className="px-3 py-1.5 rounded bg-slate-700 hover:bg-slate-600 text-sm"
            >
              Sync all
            </button>
            {SYNC_SOURCES.map((s) => (
              <button
                key={s.key}
                type="button"
                disabled={syncMut.isPending}
                onClick={() => syncMut.mutate([s.key])}
                className="px-3 py-1.5 rounded border border-slate-600 hover:border-slate-500 text-sm text-slate-300"
              >
                {s.label}
              </button>
            ))}
          </div>
          {syncMsg && <p className="text-slate-300 text-sm">{syncMsg}</p>}
          <p className="text-slate-500 text-xs">
            Linkvertise: Playwright auth · AdMaven/Work.ink: dashboard URL + cookie · BMC: TBCC_BMC_ACCESS_TOKEN
          </p>
        </section>
      </div>

      <section className="bg-slate-800 rounded-lg p-4 border border-slate-700">
        <h2 className="text-lg font-medium mb-3">Affiliate registry</h2>
        {affiliatesQ.isPending ? (
          <p className="text-slate-500 text-sm">Loading…</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-slate-400 text-left border-b border-slate-700">
                  <th className="py-2 pr-3">ID</th>
                  <th className="py-2 pr-3">Program</th>
                  <th className="py-2 pr-3">Payout</th>
                  <th className="py-2 pr-3">Last recorded</th>
                </tr>
              </thead>
              <tbody>
                {(affiliatesQ.data?.items ?? []).map((row) => (
                  <tr key={row.id} className="border-b border-slate-700/60">
                    <td className="py-2 pr-3 text-slate-400">{row.id}</td>
                    <td className="py-2 pr-3">{row.label}</td>
                    <td className="py-2 pr-3 text-slate-400">{row.payout_kind}</td>
                    <td className="py-2 pr-3">
                      {row.last_usd_cents > 0 ? (
                        <span className="text-cyan-400">${(row.last_usd_cents / 100).toFixed(2)}</span>
                      ) : (
                        <span className="text-slate-500">—</span>
                      )}
                      {row.last_earned_at && (
                        <span className="text-slate-500 text-xs ml-2">{row.last_earned_at.slice(0, 10)}</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="bg-slate-800 rounded-lg p-4 border border-slate-700">
        <h2 className="text-lg font-medium mb-3">Recent ledger entries</h2>
        {entriesQ.isPending ? (
          <p className="text-slate-500 text-sm">Loading…</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-slate-400 text-left border-b border-slate-700">
                  <th className="py-2 pr-3">When</th>
                  <th className="py-2 pr-3">Source</th>
                  <th className="py-2 pr-3">Label</th>
                  <th className="py-2 pr-3">Amount</th>
                  <th className="py-2 pr-3">Kind</th>
                </tr>
              </thead>
              <tbody>
                {(entriesQ.data?.items ?? []).map((row) => (
                  <tr key={row.id} className="border-b border-slate-700/60">
                    <td className="py-2 pr-3 text-slate-400 whitespace-nowrap">
                      {(row.earned_at ?? row.created_at ?? "").slice(0, 10)}
                    </td>
                    <td className="py-2 pr-3 text-slate-300">{row.source}</td>
                    <td className="py-2 pr-3">{row.source_label ?? "—"}</td>
                    <td className="py-2 pr-3 text-cyan-400">
                      {row.currency === "XTR" ? `${row.amount_minor} ⭐` : `$${row.amount_usd.toFixed(2)}`}
                    </td>
                    <td className="py-2 pr-3 text-slate-500">{row.sync_kind}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

function StatCard({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent?: boolean;
}) {
  return (
    <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
      <span className="text-slate-400 text-sm">{label}</span>
      <p className={`text-xl font-medium mt-1 ${accent ? "text-cyan-400" : "text-slate-100"}`}>{value}</p>
    </div>
  );
}
