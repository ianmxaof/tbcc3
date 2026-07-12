import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import {
  channelHref,
  filterScrapeSources,
  formatViewers,
  loadScrapeColPrefs,
  runProgressLabel,
  runProgressPct,
  saveScrapeColPrefs,
  scrapePhaseStyle,
  SCRAPE_COL_DEFS,
  sortScrapeSources,
  type ScrapeColId,
  type ScrapeSortDir,
  type ScrapeSortKey,
  type ScrapeStatusFilter,
  type ScrapeTransportCounts,
  type ScrapeTransportSource,
} from "../utils/scrapeTransportStatus";

type Props = {
  pools: Array<{ id: number; name?: string }>;
  onNotice?: (msg: string) => void;
};

function chipBase(active: boolean): string {
  return `inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-medium tabular-nums border transition-colors ${
    active ? "ring-1 ring-cyan-400/60 border-cyan-500/50" : "border-transparent hover:border-slate-500/50"
  }`;
}

function SortTh({
  label,
  col,
  sortKey,
  sortDir,
  onSort,
}: {
  label: string;
  col: ScrapeSortKey;
  sortKey: ScrapeSortKey;
  sortDir: ScrapeSortDir;
  onSort: (k: ScrapeSortKey) => void;
}) {
  const active = sortKey === col;
  return (
    <th className="px-1.5 py-1 text-left font-medium text-slate-500 whitespace-nowrap">
      <button
        type="button"
        className={`hover:text-slate-300 ${active ? "text-cyan-400" : ""}`}
        onClick={() => onSort(col)}
      >
        {label}
        {active ? (sortDir === "asc" ? " ↑" : " ↓") : ""}
      </button>
    </th>
  );
}

export function ScrapeTransportBar({ pools, onNotice }: Props) {
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState<ScrapeStatusFilter>("all");
  const [addName, setAddName] = useState("");
  const [addIdent, setAddIdent] = useState("");
  const [addPoolId, setAddPoolId] = useState<number>(pools[0]?.id ?? 1);
  const [addSchedule, setAddSchedule] = useState(true);
  const [selected, setSelected] = useState<Set<number>>(() => new Set());
  const [colPrefs, setColPrefs] = useState(loadScrapeColPrefs);
  const [colsOpen, setColsOpen] = useState(false);
  const [sortKey, setSortKey] = useState<ScrapeSortKey>("status");
  const [sortDir, setSortDir] = useState<ScrapeSortDir>("asc");

  useEffect(() => {
    saveScrapeColPrefs(colPrefs);
  }, [colPrefs]);

  const { data, isPending, isError, error, refetch } = useQuery({
    queryKey: ["scrape-transport"],
    queryFn: () => api.jobs.scrapeTransport(),
    refetchInterval: (q) => {
      const counts = (q.state.data as { counts?: ScrapeTransportCounts } | undefined)?.counts;
      const busy = (counts?.running || 0) + (counts?.queued || 0) + (counts?.stalled || 0) > 0;
      return busy ? 2500 : 10000;
    },
  });

  const counts: ScrapeTransportCounts = data?.counts || {
    total: 0,
    running: 0,
    queued: 0,
    stalled: 0,
    error: 0,
    paused: 0,
    idle: 0,
    autonomous: 0,
  };

  const sources = useMemo(() => {
    const filtered = filterScrapeSources((data?.sources || []) as ScrapeTransportSource[], filter);
    return sortScrapeSources(filtered, sortKey, sortDir);
  }, [data?.sources, filter, sortKey, sortDir]);

  const selectedRows = useMemo(
    () => sources.filter((s) => selected.has(s.source_id)),
    [sources, selected]
  );

  const allVisibleSelected = sources.length > 0 && sources.every((s) => selected.has(s.source_id));

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["scrape-transport"] });
    queryClient.invalidateQueries({ queryKey: ["scrape-runs-latest"] });
    queryClient.invalidateQueries({ queryKey: ["sources"] });
  };

  const play = useMutation({
    mutationFn: async (row: ScrapeTransportSource) => {
      if (!row.active) {
        await api.sources.update(row.source_id, { active: true });
      }
      return api.jobs.triggerScrape(row.source_id);
    },
    onSuccess: (res) => {
      onNotice?.(`Scrape queued (run #${res.run_id}).`);
      invalidate();
    },
    onError: (e: Error) => onNotice?.(e.message),
  });

  const pause = useMutation({
    mutationFn: (row: ScrapeTransportSource) =>
      api.sources.update(row.source_id, { active: false, schedule_enabled: false }),
    onSuccess: () => {
      onNotice?.("Source paused (active + schedule off).");
      invalidate();
    },
    onError: (e: Error) => onNotice?.(e.message),
  });

  const resumeAuto = useMutation({
    mutationFn: (row: ScrapeTransportSource) =>
      api.sources.update(row.source_id, { active: true, schedule_enabled: true }),
    onSuccess: () => {
      onNotice?.("Autonomous schedule resumed.");
      invalidate();
    },
    onError: (e: Error) => onNotice?.(e.message),
  });

  const skip = useMutation({
    mutationFn: () => api.jobs.skipScrape(true),
    onSuccess: (res) => {
      const next = res.queued_next;
      onNotice?.(
        next
          ? `Skipped. Next: ${next.source_name || next.source_id} (run #${next.run_id}).`
          : "Skipped current scrape."
      );
      invalidate();
    },
    onError: (e: Error) => onNotice?.(e.message),
  });

  const cancelRun = useMutation({
    mutationFn: (runId: number) => api.jobs.cancelScrapeRun(runId),
    onSuccess: () => {
      onNotice?.("Scrape cancelled.");
      invalidate();
    },
    onError: (e: Error) => onNotice?.(e.message),
  });

  const bulkPlay = useMutation({
    mutationFn: async (rows: ScrapeTransportSource[]) => {
      const results: number[] = [];
      for (const row of rows) {
        if (!row.active) await api.sources.update(row.source_id, { active: true });
        const res = await api.jobs.triggerScrape(row.source_id);
        results.push(res.run_id);
      }
      return results;
    },
    onSuccess: (ids) => {
      onNotice?.(`Queued ${ids.length} scrape(s).`);
      invalidate();
    },
    onError: (e: Error) => onNotice?.(e.message),
  });

  const bulkPause = useMutation({
    mutationFn: async (rows: ScrapeTransportSource[]) => {
      for (const row of rows) {
        await api.sources.update(row.source_id, { active: false, schedule_enabled: false });
      }
    },
    onSuccess: () => {
      onNotice?.(`Paused ${selectedRows.length} source(s).`);
      invalidate();
    },
    onError: (e: Error) => onNotice?.(e.message),
  });

  const bulkCancel = useMutation({
    mutationFn: async (rows: ScrapeTransportSource[]) => {
      let n = 0;
      for (const row of rows) {
        const run = row.latest_run;
        const runId = run?.id != null ? Number(run.id) : null;
        const st = run?.status != null ? String(run.status) : "";
        if (runId != null && (st === "queued" || st === "running")) {
          await api.jobs.cancelScrapeRun(runId);
          n += 1;
        }
      }
      return n;
    },
    onSuccess: (n) => {
      onNotice?.(n ? `Cancelled ${n} run(s).` : "No active runs in selection.");
      invalidate();
    },
    onError: (e: Error) => onNotice?.(e.message),
  });

  const addSource = useMutation({
    mutationFn: () =>
      api.sources.create({
        name: addName.trim() || addIdent.trim() || "New source",
        source_type: "telegram_channel",
        identifier: addIdent.trim(),
        pool_id: addPoolId,
        active: true,
        schedule_enabled: addSchedule,
        schedule_cron: addSchedule ? "0 */6 * * *" : null,
        max_messages_per_run: 50,
      }),
    onSuccess: () => {
      setAddName("");
      setAddIdent("");
      onNotice?.("Source added to transport.");
      invalidate();
    },
    onError: (e: Error) => onNotice?.(e.message),
  });

  const busy =
    play.isPending ||
    pause.isPending ||
    resumeAuto.isPending ||
    skip.isPending ||
    cancelRun.isPending ||
    bulkPlay.isPending ||
    bulkPause.isPending ||
    bulkCancel.isPending;

  const colOn = (id: ScrapeColId) => colPrefs[id] !== false;

  const toggleSort = (k: ScrapeSortKey) => {
    if (sortKey === k) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setSortKey(k);
      setSortDir(k === "name" || k === "channel" || k === "pool" || k === "status" ? "asc" : "desc");
    }
  };

  const toggleSelect = (id: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (allVisibleSelected) setSelected(new Set());
    else setSelected(new Set(sources.map((s) => s.source_id)));
  };

  const masterActive = selectedRows.length > 0;

  return (
    <div className="mb-4 rounded border border-slate-600/80 bg-slate-900/60 px-2.5 py-2 text-[11px] leading-tight">
      {/* Status chips */}
      <div className="flex flex-wrap items-center gap-1.5 mb-1.5">
        <span className="text-[9px] uppercase tracking-wide text-slate-500 font-semibold mr-1">Scrape transport</span>
        <button
          type="button"
          className={`${chipBase(filter === "all")} text-emerald-300 bg-emerald-950/40`}
          onClick={() => setFilter("all")}
        >
          On track{" "}
          <span className="text-emerald-400">
            {Math.max(0, counts.total - counts.stalled - counts.error)}/{counts.total}
          </span>
        </button>
        {counts.running > 0 ? (
          <button
            type="button"
            className={`${chipBase(filter === "running")} text-emerald-300 bg-emerald-950/30`}
            onClick={() => setFilter(filter === "running" ? "all" : "running")}
          >
            Running <span className="text-emerald-400">{counts.running}</span>
          </button>
        ) : null}
        {counts.queued > 0 ? (
          <button
            type="button"
            className={`${chipBase(filter === "queued")} text-cyan-300 bg-cyan-950/30`}
            onClick={() => setFilter(filter === "queued" ? "all" : "queued")}
          >
            Queued <span className="text-cyan-400">{counts.queued}</span>
          </button>
        ) : null}
        {counts.stalled > 0 ? (
          <button
            type="button"
            className={`${chipBase(filter === "stalled")} text-yellow-300 bg-yellow-950/30`}
            onClick={() => setFilter(filter === "stalled" ? "all" : "stalled")}
          >
            Stalled <span className="text-yellow-400">{counts.stalled}</span>
          </button>
        ) : null}
        {counts.error > 0 ? (
          <button
            type="button"
            className={`${chipBase(filter === "error")} text-rose-300 bg-rose-950/30`}
            onClick={() => setFilter(filter === "error" ? "all" : "error")}
          >
            Error <span className="text-rose-400">{counts.error}</span>
          </button>
        ) : null}
        {counts.paused > 0 ? (
          <button
            type="button"
            className={`${chipBase(filter === "paused")} text-slate-300 bg-slate-800/50`}
            onClick={() => setFilter(filter === "paused" ? "all" : "paused")}
          >
            Paused <span className="text-slate-400">{counts.paused}</span>
          </button>
        ) : null}
        <span className="text-slate-600 mx-0.5">|</span>
        <span className="text-slate-500" title="Sources with Active + schedule enabled">
          Auto {counts.autonomous}/{counts.total}
        </span>
        {(data as { scrape_mode_note?: string } | undefined)?.scrape_mode_note ? (
          <span
            className="text-slate-600 truncate max-w-[18rem]"
            title={(data as { scrape_mode_note?: string }).scrape_mode_note}
          >
            sequential lock
          </span>
        ) : null}
        <div className="relative ml-auto flex items-center gap-1">
          <button
            type="button"
            onClick={() => setColsOpen((o) => !o)}
            className="px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-600/50 hover:text-slate-200"
            title="Show / hide columns"
          >
            Columns
          </button>
          {colsOpen ? (
            <div className="absolute right-0 top-full z-20 mt-1 w-40 rounded border border-slate-600 bg-slate-900 p-2 shadow-lg">
              {SCRAPE_COL_DEFS.map((c) => (
                <label key={c.id} className="flex items-center gap-1.5 py-0.5 text-slate-300 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={colOn(c.id)}
                    onChange={() =>
                      setColPrefs((p) => ({
                        ...p,
                        [c.id]: !colOn(c.id),
                      }))
                    }
                  />
                  {c.label}
                </label>
              ))}
            </div>
          ) : null}
          <button
            type="button"
            onClick={() => void refetch()}
            className="px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-600/50 hover:text-slate-200"
          >
            Refresh
          </button>
        </div>
      </div>

      {/* Master bar — activates when rows selected (JD-style) */}
      <div
        className={`mb-1.5 flex flex-wrap items-center gap-1.5 rounded border px-2 py-1 ${
          masterActive
            ? "border-cyan-600/50 bg-cyan-950/30"
            : "border-slate-700/40 bg-slate-950/40 opacity-60"
        }`}
      >
        <span className="text-[9px] uppercase tracking-wide text-slate-500">
          {masterActive ? `${selectedRows.length} selected` : "Select rows → master"}
        </span>
        <button
          type="button"
          disabled={busy || !masterActive}
          title="Play selected — enable + queue each"
          onClick={() => bulkPlay.mutate(selectedRows)}
          className="px-1.5 py-0.5 rounded bg-emerald-900/50 text-emerald-200 border border-emerald-700/40 hover:bg-emerald-800/60 disabled:opacity-40"
        >
          ▶
        </button>
        <button
          type="button"
          disabled={busy || !masterActive}
          title="Pause selected"
          onClick={() => bulkPause.mutate(selectedRows)}
          className="px-1.5 py-0.5 rounded bg-slate-700 text-slate-200 border border-slate-500/50 hover:bg-slate-600 disabled:opacity-40"
        >
          ⏸
        </button>
        <button
          type="button"
          disabled={busy || !masterActive}
          title="Cancel active runs in selection"
          onClick={() => bulkCancel.mutate(selectedRows)}
          className="px-1.5 py-0.5 rounded bg-rose-950/50 text-rose-200 border border-rose-800/40 hover:bg-rose-900/60 disabled:opacity-40"
        >
          ■
        </button>
        <button
          type="button"
          disabled={busy || (counts.running === 0 && counts.queued === 0 && counts.stalled === 0)}
          onClick={() => skip.mutate()}
          className="px-1.5 py-0.5 rounded bg-amber-900/50 text-amber-200 border border-amber-700/40 hover:bg-amber-800/60 disabled:opacity-40"
          title="Cancel current scrape and queue the next scheduled source"
        >
          Skip → next
        </button>
        {masterActive ? (
          <button
            type="button"
            onClick={() => setSelected(new Set())}
            className="ml-auto px-1.5 py-0.5 text-slate-500 hover:text-slate-300"
          >
            Clear
          </button>
        ) : null}
      </div>

      {isError ? <p className="text-rose-400 mb-1">{String((error as Error)?.message || error)}</p> : null}
      {isPending && !data ? <p className="text-slate-500 mb-1">Loading transport…</p> : null}

      <div className="max-h-72 overflow-auto rounded border border-slate-700/60">
        <table className="w-full border-collapse text-[11px]">
          <thead className="sticky top-0 bg-slate-900/95 border-b border-slate-700/80 z-10">
            <tr>
              <th className="px-1.5 py-1 w-6">
                <input
                  type="checkbox"
                  checked={allVisibleSelected}
                  onChange={toggleSelectAll}
                  title="Select all visible"
                />
              </th>
              {colOn("status") ? (
                <SortTh label="Status" col="status" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} />
              ) : null}
              {colOn("name") ? (
                <SortTh label="Name" col="name" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} />
              ) : null}
              {colOn("channel") ? (
                <SortTh label="Channel" col="channel" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} />
              ) : null}
              {colOn("pool") ? (
                <SortTh label="Pool" col="pool" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} />
              ) : null}
              {colOn("views") ? (
                <SortTh label="Views" col="views" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} />
              ) : null}
              {colOn("members") ? (
                <SortTh label="Members" col="members" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} />
              ) : null}
              {colOn("ppd") ? (
                <SortTh label="Posts/day" col="ppd" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} />
              ) : null}
              {colOn("ppw") ? (
                <SortTh label="Posts/wk" col="ppw" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} />
              ) : null}
              {colOn("progress") ? (
                <SortTh label="Progress" col="progress" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} />
              ) : null}
              {colOn("schedule") ? (
                <SortTh label="Sched" col="schedule" sortKey={sortKey} sortDir={sortDir} onSort={toggleSort} />
              ) : null}
              <th className="px-1.5 py-1 text-right text-slate-500 font-medium">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/80">
            {sources.length === 0 && !isPending ? (
              <tr>
                <td colSpan={12} className="px-2 py-2 text-slate-500">
                  No telegram sources yet — add one below.
                </td>
              </tr>
            ) : null}
            {sources.map((row) => {
              const style = scrapePhaseStyle(row.phase);
              const run = row.latest_run || null;
              const runId = run?.id != null ? Number(run.id) : null;
              const runStatus = run?.status != null ? String(run.status) : "";
              const activeJob = runStatus === "queued" || runStatus === "running";
              const progress = runProgressLabel(run);
              const pct = runProgressPct(row);
              const href = channelHref(row);
              const isSel = selected.has(row.source_id);
              const ppw =
                row.posts_per_week != null
                  ? Number(row.posts_per_week)
                  : row.posts_per_day != null
                    ? Number(row.posts_per_day) * 7
                    : null;
              return (
                <tr
                  key={row.source_id}
                  className={`hover:bg-slate-800/40 ${isSel ? "bg-cyan-950/20" : ""}`}
                  onClick={(e) => {
                    if ((e.target as HTMLElement).closest("a,button,input")) return;
                    toggleSelect(row.source_id);
                  }}
                >
                  <td className="px-1.5 py-1" onClick={(e) => e.stopPropagation()}>
                    <input
                      type="checkbox"
                      checked={isSel}
                      onChange={() => toggleSelect(row.source_id)}
                    />
                  </td>
                  {colOn("status") ? (
                    <td className="px-1.5 py-1 whitespace-nowrap">
                      <span className={`inline-flex items-center gap-1 rounded border px-1 py-0.5 ${style.chip}`}>
                        <span className={`w-1.5 h-1.5 rounded-full ${style.dot}`} />
                        {style.label}
                      </span>
                    </td>
                  ) : null}
                  {colOn("name") ? (
                    <td className="px-1.5 py-1 font-medium text-slate-100 truncate max-w-[9rem]" title={row.name}>
                      {row.name || `SRC ${row.source_id}`}
                    </td>
                  ) : null}
                  {colOn("channel") ? (
                    <td className="px-1.5 py-1">
                      {href ? (
                        <a
                          href={href}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="font-mono text-[10px] text-cyan-400 hover:text-cyan-300 underline truncate max-w-[8rem] inline-block"
                          title={href}
                          onClick={(e) => e.stopPropagation()}
                        >
                          {row.identifier}
                        </a>
                      ) : (
                        <span className="font-mono text-[10px] text-cyan-400/90 truncate max-w-[8rem] inline-block">
                          {row.identifier}
                        </span>
                      )}
                    </td>
                  ) : null}
                  {colOn("pool") ? (
                    <td className="px-1.5 py-1 text-slate-500 truncate max-w-[7rem]" title={row.pool_name}>
                      {row.folder_label || row.pool_name || `pool ${row.pool_id}`}
                      {row.suggested_pool_keys ? (
                        <span className="text-amber-400/80 ml-1" title={`Suggested: ${row.suggested_pool_keys}`}>
                          →{row.suggested_pool_keys}
                        </span>
                      ) : null}
                    </td>
                  ) : null}
                  {colOn("views") ? (
                    <td className="px-1.5 py-1 text-violet-300/90 tabular-nums" title="Avg views sample">
                      {formatViewers(row.avg_views_sample)}
                    </td>
                  ) : null}
                  {colOn("members") ? (
                    <td className="px-1.5 py-1 text-slate-400 tabular-nums">
                      {formatViewers(row.participants_count)}
                    </td>
                  ) : null}
                  {colOn("ppd") ? (
                    <td className="px-1.5 py-1 text-slate-500 tabular-nums">
                      {row.posts_per_day != null ? Number(row.posts_per_day).toFixed(1) : "—"}
                    </td>
                  ) : null}
                  {colOn("ppw") ? (
                    <td className="px-1.5 py-1 text-slate-500 tabular-nums">
                      {ppw != null ? ppw.toFixed(1) : "—"}
                    </td>
                  ) : null}
                  {colOn("progress") ? (
                    <td className="px-1.5 py-1 min-w-[5.5rem]" title={progress || undefined}>
                      {pct != null ? (
                        <div className="flex items-center gap-1">
                          <div className="flex-1 h-1.5 rounded bg-slate-800 overflow-hidden min-w-[2.5rem]">
                            <div
                              className={`h-full ${
                                row.phase === "error"
                                  ? "bg-rose-500"
                                  : row.phase === "running"
                                    ? "bg-emerald-500"
                                    : "bg-cyan-600"
                              }`}
                              style={{ width: `${pct}%` }}
                            />
                          </div>
                          <span className="tabular-nums text-slate-500 w-7 text-right">{pct}%</span>
                        </div>
                      ) : (
                        <span className="text-slate-600">—</span>
                      )}
                    </td>
                  ) : null}
                  {colOn("schedule") ? (
                    <td className="px-1.5 py-1">
                      {row.schedule_enabled ? (
                        <span className="text-emerald-500/80" title={row.schedule_cron || ""}>
                          auto
                        </span>
                      ) : (
                        <span className="text-slate-600">manual</span>
                      )}
                    </td>
                  ) : null}
                  <td className="px-1.5 py-1" onClick={(e) => e.stopPropagation()}>
                    <span className="flex items-center justify-end gap-0.5">
                      <button
                        type="button"
                        disabled={busy}
                        title="Play — enable + queue scrape now"
                        onClick={() => play.mutate(row)}
                        className="px-1 py-0.5 rounded bg-emerald-900/50 text-emerald-200 border border-emerald-700/40 hover:bg-emerald-800/60 disabled:opacity-40"
                      >
                        ▶
                      </button>
                      <button
                        type="button"
                        disabled={busy}
                        title="Pause"
                        onClick={() => pause.mutate(row)}
                        className="px-1 py-0.5 rounded bg-slate-700 text-slate-200 border border-slate-500/50 hover:bg-slate-600 disabled:opacity-40"
                      >
                        ⏸
                      </button>
                      <button
                        type="button"
                        disabled={busy || !activeJob || runId == null}
                        title="Cancel this run"
                        onClick={() => runId != null && cancelRun.mutate(runId)}
                        className="px-1 py-0.5 rounded bg-rose-950/50 text-rose-200 border border-rose-800/40 hover:bg-rose-900/60 disabled:opacity-40"
                      >
                        ■
                      </button>
                      <button
                        type="button"
                        disabled={busy || !row.active}
                        title="Resume autonomous"
                        onClick={() => resumeAuto.mutate(row)}
                        className="px-1 py-0.5 rounded bg-cyan-950/40 text-cyan-200 border border-cyan-800/40 hover:bg-cyan-900/50 disabled:opacity-40"
                      >
                        ↻
                      </button>
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="mt-2 flex flex-wrap items-end gap-1.5 border-t border-slate-700/60 pt-2">
        <label className="flex flex-col gap-0.5 text-slate-500">
          Name
          <input
            value={addName}
            onChange={(e) => setAddName(e.target.value)}
            placeholder="MEGAS"
            className="w-28 bg-slate-800 border border-slate-600 rounded px-1.5 py-0.5 text-[11px] text-slate-200"
          />
        </label>
        <label className="flex flex-col gap-0.5 text-slate-500 flex-1 min-w-[10rem]">
          Channel (-100… / @user / t.me/…)
          <input
            value={addIdent}
            onChange={(e) => setAddIdent(e.target.value)}
            placeholder="-100332… or t.me/+invite"
            className="w-full bg-slate-800 border border-slate-600 rounded px-1.5 py-0.5 text-[11px] text-slate-200 font-mono"
          />
        </label>
        <label className="flex flex-col gap-0.5 text-slate-500">
          Pool
          <select
            value={addPoolId}
            onChange={(e) => setAddPoolId(Number(e.target.value))}
            className="bg-slate-800 border border-slate-600 rounded px-1.5 py-0.5 text-[11px] text-slate-200 max-w-[9rem]"
          >
            {pools.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name || `Pool ${p.id}`}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-1 text-slate-400 pb-0.5">
          <input type="checkbox" checked={addSchedule} onChange={(e) => setAddSchedule(e.target.checked)} />
          auto
        </label>
        <button
          type="button"
          disabled={addSource.isPending || !addIdent.trim()}
          onClick={() => addSource.mutate()}
          className="px-2 py-0.5 rounded bg-cyan-700 text-white hover:bg-cyan-600 disabled:opacity-40"
        >
          Add
        </button>
      </div>
    </div>
  );
}
