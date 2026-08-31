import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type AofNetworkStatus } from "../api";
import { QueryErrorBanner } from "../components/QueryErrorBanner";

const POLL_IDLE_MS = 8_000;
const POLL_ACTIVE_MS = 4_000;

function StatusDot({ on }: { on: boolean }) {
  return (
    <span
      className={`inline-block w-2 h-2 rounded-full ${on ? "bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.8)]" : "bg-slate-600"}`}
      aria-hidden
    />
  );
}

function ProgressBar({ value, max, label, tone = "cyan" }: { value: number; max: number; label: string; tone?: "cyan" | "emerald" }) {
  const pct = max > 0 ? Math.min(100, Math.round(((max - value) / max) * 100)) : value === 0 && max > 0 ? 100 : 0;
  const bar = tone === "emerald" ? "from-emerald-700 to-emerald-400" : "from-cyan-600 to-emerald-500";
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs text-slate-400">
        <span>{label}</span>
        <span>
          {value} remaining · {pct}% drained
        </span>
      </div>
      <div className="h-2 rounded-full bg-slate-800 border border-slate-700 overflow-hidden">
        <div className={`h-full bg-gradient-to-r ${bar} transition-all duration-700 ease-out`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function formatActivityRow(row: Record<string, unknown>, kind: "watch" | "hub"): string {
  const action = String(row.action ?? "?");
  if (kind === "watch") {
    const dest = row.dest ?? row.library_subdir ?? "";
    const src = row.src ?? "";
    const name = typeof src === "string" ? src.split(/[/\\]/).pop() : "";
    return `${action} · ${name} → ${dest}`;
  }
  const lane = row.network_key ?? row.topic_title ?? "";
  const src = row.src ?? "";
  const name = typeof src === "string" ? src.split(/[/\\]/).pop() : "";
  const reason = row.reason ? ` (${row.reason})` : "";
  return `${action} · ${lane} · ${name}${reason}`;
}

function StageCard({
  title,
  subtitle,
  running,
  stat,
  statLabel,
}: {
  title: string;
  subtitle: string;
  running: boolean;
  stat: string | number;
  statLabel: string;
}) {
  return (
    <div className="rounded-lg border border-slate-700/80 bg-slate-950/50 p-3 flex-1 min-w-[140px]">
      <div className="flex items-center gap-2 mb-1">
        <StatusDot on={running} />
        <span className="text-sm font-medium text-slate-200">{title}</span>
      </div>
      <p className="text-[11px] text-slate-500 mb-2">{subtitle}</p>
      <p className="font-mono text-2xl text-slate-100">{stat}</p>
      <p className="text-xs text-slate-500">{statLabel}</p>
    </div>
  );
}

export function WatchFolder() {
  const qc = useQueryClient();
  const inboxPeak = useRef<number>(0);
  const hubPeak = useRef<number>(0);

  const statusQ = useQuery({
    queryKey: ["aof-network-status"],
    queryFn: () => api.aofNetwork.status(),
    refetchInterval: (query) => {
      if (query.state.fetchStatus === "fetching") return false;
      const active = query.state.data?.activity.pipeline_active;
      return active ? POLL_ACTIVE_MS : POLL_IDLE_MS;
    },
    staleTime: 2_000,
  });

  const data = statusQ.data;
  const inboxPending = data?.summary.inbox_pending ?? null;
  const hubTotal = data?.summary.hub_uploads_total ?? data?.lane_hub.ledger.total_uploads ?? 0;
  const hubBuffer = data?.summary.hub_buffer_pending ?? 0;
  const hubPending = data?.summary.hub_pending_uploads ?? null;
  const hubQueueTotal = hubPending != null ? hubTotal + hubPending : null;
  const hubDrained = hubPending != null && hubPending === 0;

  useEffect(() => {
    if (inboxPending != null && inboxPending > inboxPeak.current) {
      inboxPeak.current = inboxPending;
    }
  }, [inboxPending]);

  useEffect(() => {
    if (hubTotal > hubPeak.current) {
      hubPeak.current = hubTotal;
    }
  }, [hubTotal]);

  const invalidate = useCallback(() => {
    void qc.invalidateQueries({ queryKey: ["aof-network-status"] });
  }, [qc]);

  const control = useMutation({
    mutationFn: async (action: string) => {
      switch (action) {
        case "start-all":
          return api.aofNetwork.startAll();
        case "stop-all":
          return api.aofNetwork.stopAll();
        case "watch-start":
          return api.aofNetwork.watchStart();
        case "watch-stop":
          return api.aofNetwork.watchStop();
        case "hub-start":
          return api.aofNetwork.laneHubStart();
        case "hub-stop":
          return api.aofNetwork.laneHubStop();
        default:
          throw new Error(`unknown action ${action}`);
      }
    },
    onSuccess: () => invalidate(),
  });

  const maxLaneCount = useMemo(() => {
    if (!data?.lane_hub.lanes.length) return 1;
    return Math.max(1, ...data.lane_hub.lanes.map((l) => l.media_count ?? 0));
  }, [data?.lane_hub.lanes]);

  const pollMs = data?.activity.pipeline_active ? POLL_ACTIVE_MS : POLL_IDLE_MS;
  const busy = control.isPending || statusQ.isFetching;
  const unsortedCount = data?.summary.unsorted_media ?? data?.utilities?.unsorted?.media_count ?? null;

  return (
    <div className="max-w-5xl space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-lg font-semibold text-slate-100">AOF network pipeline</h2>
        <span className="text-xs text-slate-500">polls every {pollMs / 1000}s</span>
        {data?.activity.pipeline_active ? (
          <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-950/60 border border-emerald-700/50 text-emerald-300 animate-pulse">
            transferring
          </span>
        ) : null}
        <button
          type="button"
          onClick={() => void qc.fetchQuery({ queryKey: ["aof-network-status"], queryFn: () => api.aofNetwork.status(true) })}
          disabled={busy}
          className="text-sm px-3 py-1 rounded border border-slate-600 text-slate-200 hover:bg-slate-700 disabled:opacity-50 ml-auto"
        >
          Refresh counts
        </button>
      </div>

      <p className="text-slate-400 text-sm">
        Inbox → lane / Unsorted → Storage Hub topics. Hub upload count (ledger) should climb as files deposit; inbox and buffer should drain.
      </p>

      {statusQ.isError ? (
        <QueryErrorBanner
          title="Could not load AOF network status"
          message={statusQ.error instanceof Error ? statusQ.error.message : String(statusQ.error)}
          onRetry={() => void statusQ.refetch()}
        />
      ) : null}

      {statusQ.isPending && !data ? <p className="text-slate-500">Loading…</p> : null}

      {data?.counts_refreshing ? (
        <p className="text-xs text-amber-400/90 mb-3">Scanning folder counts in background — live logs and ledger update every few seconds.</p>
      ) : null}

      {data?.counters?.last_error ? (
        <p className="text-xs text-red-400/90">Last hub error: {data.counters.last_error}</p>
      ) : null}

      {data ? (
        <>
          <section className="rounded-lg border border-slate-700 bg-slate-900/40 p-4 space-y-4">
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                disabled={busy}
                onClick={() => control.mutate("start-all")}
                className="px-4 py-2 rounded-lg bg-emerald-700/80 hover:bg-emerald-600 text-white text-sm font-medium disabled:opacity-50"
              >
                Start firehose
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={() => control.mutate("stop-all")}
                className="px-3 py-2 rounded-lg border border-slate-600 text-slate-300 text-sm hover:bg-slate-800 disabled:opacity-50"
              >
                Stop all
              </button>
            </div>

            <div className="flex flex-wrap gap-3">
              <StageCard
                title="1 · Inbox"
                subtitle="Watch organizer"
                running={data.watch.running}
                stat={data.summary.inbox_pending ?? "—"}
                statLabel="media pending"
              />
              <StageCard
                title="2 · Lanes"
                subtitle="Local folders + Unsorted"
                running={data.watch.running}
                stat={data.summary.total_lane_media + (unsortedCount ?? 0)}
                statLabel={`on disk (${unsortedCount ?? "?"} unsorted)`}
              />
              <StageCard
                title="3 · Storage Hub"
                subtitle="Telegram topic uploads"
                running={data.lane_hub.running}
                stat={hubQueueTotal != null ? `${hubTotal}/${hubQueueTotal}` : hubTotal}
                statLabel={
                  hubPending != null && hubPending > 0
                    ? `${hubPending} pending`
                    : hubBuffer > 0
                      ? `${hubBuffer} buffered (album)`
                      : "drained"
                }
              />
            </div>

            <div className="grid sm:grid-cols-2 gap-4">
              <DaemonCard
                title="Watch organizer"
                subtitle="Inbox → lane folders / Unsorted"
                running={data.watch.running}
                pids={data.watch.pids}
                onStart={() => control.mutate("watch-start")}
                onStop={() => control.mutate("watch-stop")}
                busy={busy}
              />
              <DaemonCard
                title="Lane hub deposit"
                subtitle="Lanes + Unsorted → Storage Hub"
                running={data.lane_hub.running}
                pids={data.lane_hub.pids}
                onStart={() => control.mutate("hub-start")}
                onStop={() => control.mutate("hub-stop")}
                busy={busy}
                disabled={!data.lane_hub.enabled}
              />
            </div>

            {inboxPending != null && inboxPeak.current > 0 ? (
              <ProgressBar value={inboxPending} max={inboxPeak.current} label="Inbox drain" />
            ) : null}

            {hubQueueTotal != null && hubQueueTotal > 0 ? (
              <div className="space-y-1">
                <div className="flex justify-between text-xs text-slate-400">
                  <span>Storage Hub queue</span>
                  <span>
                    {hubTotal}/{hubQueueTotal} uploaded{hubPending ? ` · ${hubPending} pending` : ""} · +
                    {data.activity.uploads_last_5m ?? 0} last 5m
                  </span>
                </div>
                <div className="h-2 rounded-full bg-slate-800 border border-slate-700 overflow-hidden">
                  <div
                    className={`h-full bg-gradient-to-r transition-all duration-700 ease-out ${
                      hubDrained ? "from-emerald-700 to-emerald-400" : "from-cyan-600 to-amber-400"
                    }`}
                    style={{ width: `${Math.min(100, Math.round((hubTotal / hubQueueTotal) * 100))}%` }}
                  />
                </div>
              </div>
            ) : hubTotal > 0 || (data.counters?.uploads_total ?? 0) > 0 ? (
              <div className="space-y-1">
                <div className="flex justify-between text-xs text-slate-400">
                  <span>Storage Hub uploads (ledger)</span>
                  <span>{hubTotal} total · pending unknown · +{data.activity.uploads_last_5m ?? 0} last 5m</span>
                </div>
                <div className="h-2 rounded-full bg-slate-800 border border-slate-700 overflow-hidden">
                  <div className="h-full bg-gradient-to-r from-cyan-600 to-amber-400 w-full opacity-40" />
                </div>
              </div>
            ) : null}

            <dl className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
              <Stat label="Inbox pending" value={data.summary.inbox_pending ?? "—"} />
              <Stat label="Unsorted on disk" value={unsortedCount ?? "—"} />
              <Stat label="Moves / min" value={data.activity.moves_last_minute} active={data.activity.moves_last_minute > 0} />
              <Stat label="Uploads / min" value={data.activity.uploads_last_minute} active={data.activity.uploads_last_minute > 0} />
              <Stat label="Hub uploads (ledger)" value={hubTotal} active={data.activity.uploads_last_minute > 0} />
              <Stat label="Hub pending" value={hubPending ?? "—"} active={(hubPending ?? 0) > 0} />
              <Stat label="Session moves" value={data.counters?.moves_total ?? "—"} />
              <Stat label="Session uploads" value={data.counters?.uploads_total ?? "—"} />
              <Stat label="Hub errors / min" value={data.activity.errors_last_minute ?? 0} active={(data.activity.errors_last_minute ?? 0) > 0} />
              <Stat
                label="Firehose"
                value={data.summary.firehose_ready ? "ON" : "off"}
                active={data.summary.firehose_ready}
              />
            </dl>
          </section>

          <section className="rounded-lg border border-slate-700 bg-slate-900/40 p-4">
            <h3 className="text-sm font-medium text-slate-300 mb-3">Lane folders → hub topics</h3>
            <div className="space-y-2 max-h-80 overflow-y-auto pr-1">
              {data.lane_hub.lanes.map((lane) => (
                <LaneRow key={lane.network_key} lane={lane} maxCount={maxLaneCount} />
              ))}
            </div>
          </section>

          <section className="grid md:grid-cols-2 gap-4">
            <ActivityFeed title="Watch log (moves)" rows={data.activity.watch_recent} kind="watch" />
            <ActivityFeed title="Hub log (uploads)" rows={data.activity.hub_recent} kind="hub" />
          </section>

          <section className="rounded-lg border border-slate-700 bg-slate-900/40 p-4 text-xs text-slate-500 font-mono break-all space-y-1">
            <div>Inbox: {data.watch.inbox_path}</div>
            <div>Library: {data.watch.library_path}</div>
            <div>Last poll: {data.ts}</div>
          </section>
        </>
      ) : null}
    </div>
  );
}

function Stat({ label, value, active }: { label: string; value: string | number; active?: boolean }) {
  return (
    <div className="rounded border border-slate-700/80 px-2 py-1.5">
      <dt className="text-slate-500 text-xs">{label}</dt>
      <dd className={`font-mono text-base ${active ? "text-emerald-400" : "text-slate-100"}`}>{value}</dd>
    </div>
  );
}

function DaemonCard({
  title,
  subtitle,
  running,
  pids,
  onStart,
  onStop,
  busy,
  disabled,
}: {
  title: string;
  subtitle: string;
  running: boolean;
  pids: number[];
  onStart: () => void;
  onStop: () => void;
  busy: boolean;
  disabled?: boolean;
}) {
  return (
    <div className="rounded-lg border border-slate-700/80 bg-slate-950/40 p-3">
      <div className="flex items-center gap-2 mb-1">
        <StatusDot on={running} />
        <span className="text-sm font-medium text-slate-200">{title}</span>
        <span className={`text-xs ${running ? "text-emerald-400" : "text-slate-500"}`}>{running ? "running" : "stopped"}</span>
      </div>
      <p className="text-xs text-slate-500 mb-2">{subtitle}</p>
      {pids.length > 0 ? <p className="text-xs text-slate-600 mb-2">pid {pids.join(", ")}</p> : null}
      <div className="flex gap-2">
        <button
          type="button"
          disabled={busy || disabled || running}
          onClick={onStart}
          className="text-xs px-2 py-1 rounded border border-emerald-700/60 text-emerald-300 hover:bg-emerald-950/50 disabled:opacity-40"
        >
          Start
        </button>
        <button
          type="button"
          disabled={busy || !running}
          onClick={onStop}
          className="text-xs px-2 py-1 rounded border border-slate-600 text-slate-400 hover:bg-slate-800 disabled:opacity-40"
        >
          Stop
        </button>
      </div>
    </div>
  );
}

function LaneRow({ lane, maxCount }: { lane: AofNetworkStatus["lane_hub"]["lanes"][0]; maxCount: number }) {
  const count = lane.media_count ?? 0;
  const uploaded = lane.ledger_uploads ?? 0;
  const pending = lane.pending_uploads;
  const pct = maxCount > 0 && lane.media_count != null ? Math.round((count / maxCount) * 100) : 0;
  return (
    <div className="flex items-center gap-3 text-sm border border-slate-800 rounded px-2 py-1.5">
      <span className="w-6 text-center shrink-0">{lane.emoji}</span>
      <div className="min-w-0 flex-1">
        <div className="flex justify-between gap-2">
          <span className="text-slate-300 truncate">{lane.folder_name}</span>
          <span className="font-mono text-slate-100 shrink-0">
            {count ?? "…"} disk · {uploaded} hub{pending != null && pending > 0 ? ` · ${pending} pending` : ""}
          </span>
        </div>
        <div className="h-1 mt-1 rounded-full bg-slate-800 overflow-hidden">
          <div
            className={`h-full ${pending != null && pending === 0 ? "bg-emerald-600/70" : "bg-cyan-700/70"}`}
            style={{ width: `${pct}%` }}
          />
        </div>
        <p className="text-[10px] text-slate-600 truncate mt-0.5">→ {lane.topic_title}</p>
      </div>
    </div>
  );
}

function ActivityFeed({
  title,
  rows,
  kind,
}: {
  title: string;
  rows: Array<Record<string, unknown>>;
  kind: "watch" | "hub";
}) {
  return (
    <div className="rounded-lg border border-slate-700 bg-slate-900/40 p-4">
      <h3 className="text-sm font-medium text-slate-300 mb-2">{title}</h3>
      {rows.length === 0 ? <p className="text-sm text-slate-500">No recent activity.</p> : null}
      <ul className="space-y-1 max-h-48 overflow-y-auto text-xs font-mono text-slate-400">
        {rows.map((row, i) => (
          <li key={i} className="border-b border-slate-800/60 pb-1 break-all">
            {formatActivityRow(row, kind)}
          </li>
        ))}
      </ul>
    </div>
  );
}
