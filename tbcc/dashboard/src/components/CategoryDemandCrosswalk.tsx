import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api";
import { QueryErrorBanner } from "./QueryErrorBanner";

export function CategoryDemandCrosswalk() {
  const qc = useQueryClient();
  const [feedback, setFeedback] = useState<string | null>(null);

  const demandQ = useQuery({
    queryKey: ["analytics", "category-demand"],
    queryFn: () => api.analytics.categoryDemand({ limit: 30 }),
    retry: 1,
  });

  const ga4Q = useQuery({
    queryKey: ["analytics", "ga4-device-country"],
    queryFn: () => api.analytics.ga4HubDeviceCountry(7),
    retry: 1,
  });

  const seed = useMutation({
    mutationFn: () => api.analytics.seedIndustryIntelligence(),
    onSuccess: (r) => {
      setFeedback(
        `Seeded ${r.benchmarks.upserted ?? 0} benchmarks + ${r.iui_corpus.chunks ?? 0} IIU RAG chunks`
      );
      void qc.invalidateQueries({ queryKey: ["analytics", "category-demand"] });
    },
    onError: (e: Error) => setFeedback(e.message),
  });

  const rows = demandQ.data?.rows ?? [];
  const gaps = demandQ.data?.gaps ?? [];
  const needsSeed = demandQ.data && !demandQ.data.seeded;

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-medium text-slate-300 uppercase tracking-wide">
            Industry intelligence
          </h2>
          <p className="text-slate-500 text-sm mt-1 max-w-2xl">
            IIU-style demand priors crosswalked against tagged media supply. Gap score = demand index minus
            supply share of library.
          </p>
        </div>
        <button
          type="button"
          onClick={() => seed.mutate()}
          disabled={seed.isPending}
          className="px-3 py-1.5 text-sm rounded-md bg-cyan-700/80 hover:bg-cyan-600 text-white disabled:opacity-50"
        >
          {seed.isPending ? "Seeding…" : "Seed benchmarks + IIU RAG"}
        </button>
      </div>

      {feedback && <p className="text-sm text-cyan-300">{feedback}</p>}

      {demandQ.isError && (
        <QueryErrorBanner
          title="Category demand crosswalk failed"
          message={String((demandQ.error as Error)?.message ?? demandQ.error)}
          onRetry={() => void demandQ.refetch()}
        />
      )}

      {needsSeed && (
        <p className="text-amber-300/90 text-sm border border-amber-700/50 rounded-lg px-3 py-2 bg-amber-950/20">
          Benchmarks not seeded yet — click &quot;Seed benchmarks + IIU RAG&quot; to load IIU priors and
          Secretary knowledge chunks.
        </p>
      )}

      {demandQ.data?.seeded && (
        <p className="text-slate-500 text-xs">
          Library: {demandQ.data.total_media} media · {demandQ.data.benchmark_count} category benchmarks ·
          gap threshold {demandQ.data.gap_threshold}
        </p>
      )}

      {gaps.length > 0 && (
        <div>
          <h3 className="text-xs font-medium text-slate-400 uppercase tracking-wide mb-2">
            Top opportunity gaps
          </h3>
          <ul className="flex flex-wrap gap-2">
            {gaps.slice(0, 6).map((g) => (
              <li
                key={g.slug}
                className="text-sm px-2.5 py-1 rounded-full border border-amber-700/60 bg-amber-950/30 text-amber-100"
              >
                {g.title}{" "}
                <span className="text-amber-400/80 tabular-nums">+{g.gap_score.toFixed(0)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {rows.length > 0 ? (
        <div className="overflow-x-auto border border-slate-700 rounded-lg">
          <table className="w-full text-sm text-left">
            <thead className="bg-slate-800/80 text-slate-400">
              <tr>
                <th className="px-3 py-2 font-medium">Category</th>
                <th className="px-3 py-2 font-medium">Demand</th>
                <th className="px-3 py-2 font-medium">Supply</th>
                <th className="px-3 py-2 font-medium">Gap</th>
                <th className="px-3 py-2 font-medium">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-700">
              {rows.map((row) => (
                <tr key={row.slug} className="hover:bg-slate-800/40">
                  <td className="px-3 py-2 text-slate-200">
                    {row.title}
                    {!row.in_clip_catalog && (
                      <span className="ml-1 text-slate-500 text-xs">(ext)</span>
                    )}
                  </td>
                  <td className="px-3 py-2 tabular-nums text-slate-300">{row.demand_index}</td>
                  <td className="px-3 py-2 tabular-nums text-slate-400">
                    {row.supply_count}{" "}
                    <span className="text-slate-600">({row.supply_pct}%)</span>
                  </td>
                  <td className="px-3 py-2 tabular-nums text-slate-300">{row.gap_score}</td>
                  <td className="px-3 py-2">
                    <StatusBadge status={row.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : demandQ.isPending ? (
        <p className="text-slate-500 text-sm">Loading crosswalk…</p>
      ) : null}

      {ga4Q.data?.configured && (ga4Q.data.rows?.length ?? 0) > 0 && (
        <div className="border border-slate-700 rounded-lg p-3 bg-slate-900/40">
          <h3 className="text-xs font-medium text-slate-400 uppercase tracking-wide mb-2">
            GA4 hub — device × country ({ga4Q.data.lookback_days}d)
          </h3>
          <ul className="text-sm text-slate-300 space-y-1 max-h-40 overflow-y-auto">
            {ga4Q.data.rows.slice(0, 12).map((r, i) => (
              <li key={`${r.device_category}-${r.country}-${i}`}>
                {r.device_category} · {r.country} — {r.sessions} sessions
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

function StatusBadge({ status }: { status: string }) {
  if (status === "under_supplied") {
    return <span className="text-amber-400">under-supplied</span>;
  }
  if (status === "over_supplied") {
    return <span className="text-violet-400">over-supplied</span>;
  }
  return <span className="text-slate-500">balanced</span>;
}
