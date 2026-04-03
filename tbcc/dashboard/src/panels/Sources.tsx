import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import { useState } from "react";
import { QueryErrorBanner } from "../components/QueryErrorBanner";

export function Sources() {
  const queryClient = useQueryClient();
  const {
    data: sources = [],
    isPending: sourcesPending,
    isError: sourcesError,
    error: sourcesErr,
    refetch: refetchSources,
  } = useQuery({
    queryKey: ["sources"],
    queryFn: () => api.sources.list(),
  });
  const {
    data: pools = [],
    isPending: poolsPending,
    isError: poolsError,
    error: poolsErr,
    refetch: refetchPools,
  } = useQuery({
    queryKey: ["pools"],
    queryFn: () => api.pools.list(),
  });
  const [name, setName] = useState("");
  const [identifier, setIdentifier] = useState("");
  const [poolId, setPoolId] = useState<number>(1);
  const [active, setActive] = useState(true);

  const createSource = useMutation({
    mutationFn: () =>
      api.sources.create({
        name: name || "New source",
        source_type: "telegram_channel",
        identifier: identifier || "",
        pool_id: poolId,
        active,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sources"] });
      setName("");
      setIdentifier("");
    },
  });

  const triggerScrape = useMutation({
    mutationFn: (sourceId: number) => api.jobs.triggerScrape(sourceId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["sources"] }),
  });

  return (
    <div>
      <h1 className="text-2xl font-semibold mb-2">Sources</h1>
      <p className="text-slate-400 text-sm mb-4 max-w-2xl">
        Telegram channels only (Telethon). After <strong>Scrape now</strong>, open{" "}
        <strong>Media</strong> with status <strong>pending</strong> — rows show the <strong>Pool</strong> column (not the
        Pools tab). First scraper run may need login in a terminal:{" "}
        <code className="text-slate-300">python scripts/run_scrape_once.py &lt;source_id&gt;</code>
      </p>
      {sourcesError && (
        <QueryErrorBanner
          title="Could not load sources"
          message={String((sourcesErr as Error)?.message ?? sourcesErr)}
          onRetry={() => void refetchSources()}
        />
      )}
      {poolsError && (
        <QueryErrorBanner
          title="Could not load pools"
          message={String((poolsErr as Error)?.message ?? poolsErr)}
          onRetry={() => void refetchPools()}
        />
      )}
      <div className="bg-slate-800 rounded-lg p-4 mb-6 max-w-md">
        <h2 className="text-lg font-medium mb-3">Add source</h2>
        <div className="space-y-2">
          <input
            type="text"
            placeholder="Name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200"
          />
          <input
            type="text"
            placeholder="Channel username or URL"
            value={identifier}
            onChange={(e) => setIdentifier(e.target.value)}
            className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200"
          />
          <select
            value={poolId}
            onChange={(e) => setPoolId(Number(e.target.value))}
            className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200"
            disabled={poolsPending && !pools.length}
          >
            {poolsPending && !pools.length ? (
              <option value={1}>Loading pools…</option>
            ) : (
              (pools as Array<{ id: number; name?: string }>).map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name || `Pool ${p.id}`}
                </option>
              ))
            )}
          </select>
          <label className="flex items-center gap-2 text-slate-300">
            <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} />
            Active
          </label>
          <button
            onClick={() => createSource.mutate()}
            disabled={createSource.isPending || !identifier}
            className="px-4 py-2 bg-cyan-600 text-white rounded hover:bg-cyan-500 disabled:opacity-50"
          >
            {createSource.isPending ? "Adding..." : "Add source"}
          </button>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full border border-slate-600 rounded-lg overflow-hidden">
          <thead className="bg-slate-700">
            <tr>
              <th className="text-left p-3">ID</th>
              <th className="text-left p-3">Name</th>
              <th className="text-left p-3">Identifier</th>
              <th className="text-left p-3">Type</th>
              <th className="text-left p-3">Pool ID</th>
              <th className="text-left p-3">Active</th>
              <th className="text-left p-3">Actions</th>
            </tr>
          </thead>
          <tbody>
            {sourcesPending && !sources.length ? (
              <tr>
                <td colSpan={7} className="p-4 text-slate-500">
                  Loading sources…
                </td>
              </tr>
            ) : null}
            {!sourcesPending && !sourcesError && !sources.length ? (
              <tr>
                <td colSpan={7} className="p-4 text-slate-500">
                  No sources yet.
                </td>
              </tr>
            ) : null}
            {sources.map((s: Record<string, unknown>) => (
              <tr key={String(s.id)} className="border-t border-slate-600 hover:bg-slate-800/50">
                <td className="p-3">{String(s.id)}</td>
                <td className="p-3">{String(s.name)}</td>
                <td className="p-3 font-mono text-sm text-cyan-300">{String(s.identifier)}</td>
                <td className="p-3 text-slate-400">{String(s.source_type)}</td>
                <td className="p-3">{String(s.pool_id)}</td>
                <td className="p-3">{s.active ? "✓" : "—"}</td>
                <td className="p-3">
                  <button
                    onClick={() => triggerScrape.mutate(Number(s.id))}
                    disabled={triggerScrape.isPending}
                    className="px-2 py-1 bg-slate-600 text-slate-200 rounded text-sm hover:bg-slate-500"
                  >
                    Scrape now
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
