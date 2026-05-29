import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import { useState } from "react";
import { QueryErrorBanner } from "../components/QueryErrorBanner";
import { CronScheduleBuilder } from "../components/CronScheduleBuilder";
import { ScraperTelegramAuth } from "../components/ScraperTelegramAuth";
import { SourceEditorModal, type SourceRow } from "../components/SourceEditorModal";
import { buildCronFromState, defaultScheduleState, describeCron } from "../utils/cronSchedule";

function formatMediaTypes(raw: unknown): string {
  const s = String(raw ?? "both").toLowerCase();
  if (s === "photos") return "Photos";
  if (s === "videos") return "Videos";
  return "Both";
}

function formatSchedule(s: Record<string, unknown>): string {
  if (s.schedule_enabled && s.schedule_cron) return describeCron(String(s.schedule_cron));
  return "Manual";
}

function formatLastScraped(raw: unknown): string {
  if (!raw) return "—";
  const d = new Date(String(raw));
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString();
}

export function Sources({ embedded = false }: { embedded?: boolean }) {
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
  const [addExpanded, setAddExpanded] = useState(false);
  const [addScheduleCron, setAddScheduleCron] = useState(buildCronFromState(defaultScheduleState()));
  const [addScheduleEnabled, setAddScheduleEnabled] = useState(false);
  const [addMaxMessages, setAddMaxMessages] = useState(50);
  const [editingSource, setEditingSource] = useState<SourceRow | null>(null);
  const [scrapeNotice, setScrapeNotice] = useState<string | null>(null);

  const createSource = useMutation({
    mutationFn: () =>
      api.sources.create({
        name: name || "New source",
        source_type: "telegram_channel",
        identifier: identifier || "",
        pool_id: poolId,
        active,
        schedule_cron: addScheduleEnabled ? addScheduleCron : null,
        schedule_enabled: addScheduleEnabled,
        max_messages_per_run: addMaxMessages,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sources"] });
      setName("");
      setIdentifier("");
    },
  });

  const triggerScrape = useMutation({
    mutationFn: (sourceId: number) => api.jobs.triggerScrape(sourceId),
    onSuccess: (data) => {
      setScrapeNotice(`Scrape queued (run #${data.run_id}). Watch the banner above for progress and results.`);
      queryClient.invalidateQueries({ queryKey: ["sources"] });
      queryClient.invalidateQueries({ queryKey: ["scrape-runs-latest"] });
    },
    onError: (e: Error) => setScrapeNotice(e.message),
  });

  const poolList = pools as Array<{ id: number; name?: string }>;
  const colCount = 10;

  return (
    <div>
      {!embedded ? (
        <>
          <h1 className="text-2xl font-semibold mb-2">Sources</h1>
          <p className="text-slate-400 text-sm mb-4 max-w-2xl">
            One <strong>source</strong> = one Telegram channel → one <strong>pool</strong>. Log in once below, then add
            each channel with <strong>Add source</strong> and its own schedule. Beat runs scrapes one at a time.
          </p>
        </>
      ) : null}
      {sourcesError && (
        <QueryErrorBanner
          title="Could not load sources"
          message={String((sourcesErr as Error)?.message ?? sourcesErr)}
          onRetry={() => void refetchSources()}
        />
      )}
      {scrapeNotice ? (
        <p
          className={`text-sm mb-4 max-w-2xl ${scrapeNotice.includes("queued") ? "text-emerald-300" : "text-amber-300"}`}
        >
          {scrapeNotice}
        </p>
      ) : null}
      {poolsError && (
        <QueryErrorBanner
          title="Could not load pools"
          message={String((poolsErr as Error)?.message ?? poolsErr)}
          onRetry={() => void refetchPools()}
        />
      )}

      <div className="mb-6 max-w-2xl">
        <ScraperTelegramAuth />
      </div>

      <div className="bg-slate-800 rounded-lg p-4 mb-6 max-w-2xl">
        <h2 className="text-lg font-medium mb-1">Add source</h2>
        <p className="text-slate-500 text-xs mb-3">
          Each new channel is a new row (same Telegram login). Stagger schedules (e.g. 06:00, 06:15, 06:30 UTC) for a
          daily chain.
        </p>
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
              poolList.map((p) => (
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
            type="button"
            onClick={() => setAddExpanded((v) => !v)}
            className="text-cyan-400 text-sm hover:text-cyan-300"
          >
            {addExpanded ? "Hide schedule & limits" : "Schedule & limits…"}
          </button>
          {addExpanded ? (
            <div className="rounded border border-slate-600/80 bg-slate-900/40 p-3 space-y-3">
              <label className="block text-slate-400 text-xs">
                Messages per run
                <div className="flex items-center gap-2 mt-1">
                  <button
                    type="button"
                    onClick={() => setAddMaxMessages((n) => Math.max(1, n - 5))}
                    className="h-8 w-8 rounded bg-slate-700 border border-slate-600 text-slate-200"
                  >
                    −
                  </button>
                  <span className="text-slate-200 font-mono min-w-[3rem] text-center">{addMaxMessages}</span>
                  <button
                    type="button"
                    onClick={() => setAddMaxMessages((n) => Math.min(500, n + 5))}
                    className="h-8 w-8 rounded bg-slate-700 border border-slate-600 text-slate-200"
                  >
                    +
                  </button>
                </div>
              </label>
              <CronScheduleBuilder
                cron={addScheduleCron}
                enabled={addScheduleEnabled}
                onCronChange={setAddScheduleCron}
                onEnabledChange={setAddScheduleEnabled}
              />
            </div>
          ) : null}
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
        <table className="w-full border border-slate-600 rounded-lg overflow-hidden text-sm">
          <thead className="bg-slate-700">
            <tr>
              <th className="text-left p-3">ID</th>
              <th className="text-left p-3">Name</th>
              <th className="text-left p-3">Channel</th>
              <th className="text-left p-3">Pool</th>
              <th className="text-left p-3">Media</th>
              <th className="text-left p-3">Limit</th>
              <th className="text-left p-3">Schedule</th>
              <th className="text-left p-3">Last scrape</th>
              <th className="text-left p-3">Active</th>
              <th className="text-left p-3">Actions</th>
            </tr>
          </thead>
          <tbody>
            {sourcesPending && !sources.length ? (
              <tr>
                <td colSpan={colCount} className="p-4 text-slate-500">
                  Loading sources…
                </td>
              </tr>
            ) : null}
            {!sourcesPending && !sourcesError && !sources.length ? (
              <tr>
                <td colSpan={colCount} className="p-4 text-slate-500">
                  No sources yet.
                </td>
              </tr>
            ) : null}
            {sources.map((s: Record<string, unknown>) => {
              const row: SourceRow = {
                id: Number(s.id),
                name: s.name != null ? String(s.name) : undefined,
                identifier: s.identifier != null ? String(s.identifier) : undefined,
                source_type: s.source_type != null ? String(s.source_type) : undefined,
                pool_id: s.pool_id != null ? Number(s.pool_id) : undefined,
                active: s.active !== false,
                schedule_cron: s.schedule_cron != null ? String(s.schedule_cron) : null,
                schedule_enabled: Boolean(s.schedule_enabled),
                media_types: s.media_types != null ? String(s.media_types) : undefined,
                max_messages_per_run:
                  s.max_messages_per_run != null ? Number(s.max_messages_per_run) : undefined,
                last_scraped_at: s.last_scraped_at != null ? String(s.last_scraped_at) : null,
              };
              return (
                <tr
                  key={String(s.id)}
                  className="border-t border-slate-600 hover:bg-slate-800/50 cursor-pointer"
                  onClick={() => setEditingSource(row)}
                  title="Click to edit or delete"
                >
                  <td className="p-3">{String(s.id)}</td>
                  <td className="p-3 font-medium text-slate-100">{String(s.name)}</td>
                  <td className="p-3 font-mono text-xs text-cyan-300 max-w-[140px] truncate" title={String(s.identifier)}>
                    {String(s.identifier)}
                  </td>
                  <td className="p-3">{String(s.pool_id)}</td>
                  <td className="p-3 text-slate-300">{formatMediaTypes(s.media_types)}</td>
                  <td className="p-3 text-slate-300">{String(s.max_messages_per_run ?? 50)}</td>
                  <td className="p-3 font-mono text-xs text-slate-400 max-w-[120px] truncate" title={formatSchedule(s)}>
                    {formatSchedule(s)}
                  </td>
                  <td className="p-3 text-slate-400 text-xs whitespace-nowrap">{formatLastScraped(s.last_scraped_at)}</td>
                  <td className="p-3">{s.active ? "✓" : "—"}</td>
                  <td className="p-3" onClick={(e) => e.stopPropagation()}>
                    <button
                      onClick={() => triggerScrape.mutate(Number(s.id))}
                      disabled={triggerScrape.isPending || !s.active}
                      title={s.active ? "Queue Celery scrape for this source" : "Enable Active in editor to scrape"}
                      className="px-2 py-1 bg-slate-600 text-slate-200 rounded text-sm hover:bg-slate-500 disabled:opacity-40 whitespace-nowrap"
                    >
                      Scrape now
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <SourceEditorModal source={editingSource} pools={poolList} onClose={() => setEditingSource(null)} />
    </div>
  );
}
