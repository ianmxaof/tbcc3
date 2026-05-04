import { useCallback, useEffect, useState } from "react";
import { api, type WatchFolderStatus } from "../api";
import { QueryErrorBanner } from "../components/QueryErrorBanner";

function isConfigured(s: WatchFolderStatus): s is Extract<WatchFolderStatus, { configured: true }> {
  return "configured" in s && s.configured === true;
}

export function WatchFolder() {
  const [data, setData] = useState<WatchFolderStatus | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setErr(null);
    setLoading(true);
    try {
      setData(await api.watchFolder.status());
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="max-w-4xl">
      <div className="flex items-center gap-3 mb-4">
        <h2 className="text-lg font-semibold text-slate-100">Watch folder</h2>
        <button
          type="button"
          onClick={() => void load()}
          disabled={loading}
          className="text-sm px-3 py-1 rounded border border-slate-600 text-slate-200 hover:bg-slate-700 disabled:opacity-50"
        >
          Refresh
        </button>
      </div>

      <p className="text-slate-400 text-sm mb-4">
        Drop finished downloads into the <strong className="text-slate-300">inbox</strong> folder; the organizer script moves them into the{" "}
        <strong className="text-slate-300">library</strong> by type (Images, Videos, …). This page only reads{" "}
        <code className="text-cyan-400/90">TBCC_WATCH_*</code> from the same <code className="text-cyan-400/90">.env</code> as the API — it does not start the watcher.
      </p>

      {err ? (
        <QueryErrorBanner title="Could not load watch folder status" message={err} onRetry={() => void load()} />
      ) : null}

      {loading && !data ? <p className="text-slate-500">Loading…</p> : null}

      {data && !isConfigured(data) ? (
        <div className="rounded-lg border border-amber-700/60 bg-amber-950/30 px-4 py-3 text-amber-100/90 text-sm">
          <p className="font-medium text-amber-100 mb-1">Not configured</p>
          <p>{data.hint}</p>
          <p className="mt-2 text-slate-400">
            Uncomment <code className="text-slate-300">TBCC_WATCH_INBOX</code> (and optionally <code className="text-slate-300">TBCC_WATCH_LIBRARY</code>,{" "}
            <code className="text-slate-300">TBCC_WATCH_LOG</code>) in <code className="text-slate-300">tbcc/.env</code>, restart uvicorn, then refresh here.
          </p>
        </div>
      ) : null}

      {data && isConfigured(data) ? (
        <div className="space-y-6">
          <section className="rounded-lg border border-slate-700 bg-slate-900/40 p-4">
            <h3 className="text-sm font-medium text-slate-300 mb-2">Paths</h3>
            <dl className="grid gap-2 text-sm">
              <div>
                <dt className="text-slate-500">Inbox</dt>
                <dd className="font-mono text-cyan-300/90 break-all">{data.inbox.path}</dd>
                <dd className="text-slate-500 mt-0.5">
                  {data.inbox.is_dir ? (
                    <>
                      <span className="text-emerald-400/90">ready</span>
                      {data.inbox.file_count != null ? ` · ${data.inbox.file_count} file(s) at top level` : null}
                    </>
                  ) : data.inbox.exists ? (
                    <span className="text-amber-400/90">exists but is not a directory</span>
                  ) : (
                    <span className="text-amber-400/90">missing — create this folder or fix .env</span>
                  )}
                </dd>
              </div>
              <div>
                <dt className="text-slate-500">Library</dt>
                <dd className="font-mono text-cyan-300/90 break-all">{data.library.path}</dd>
                <dd className="text-slate-500 mt-0.5">
                  {data.library.is_dir ? <span className="text-emerald-400/90">present</span> : <span className="text-slate-500">will be created when the organizer runs</span>}
                </dd>
              </div>
              <div>
                <dt className="text-slate-500">Debounce</dt>
                <dd className="text-slate-300">{data.debounce_s}s before moving a new file</dd>
              </div>
            </dl>
          </section>

          <section className="rounded-lg border border-slate-700 bg-slate-900/40 p-4">
            <h3 className="text-sm font-medium text-slate-300 mb-2">Library counts (files per category folder)</h3>
            <ul className="grid grid-cols-2 sm:grid-cols-3 gap-2 text-sm">
              {Object.entries(data.library.files_per_category).map(([k, v]) => (
                <li key={k} className="flex justify-between gap-2 border border-slate-700/80 rounded px-2 py-1.5">
                  <span className="text-slate-400">{k}</span>
                  <span className="text-slate-100 font-mono">{v ?? "—"}</span>
                </li>
              ))}
            </ul>
          </section>

          <section className="rounded-lg border border-slate-700 bg-slate-900/40 p-4">
            <h3 className="text-sm font-medium text-slate-300 mb-2">Run the organizer</h3>
            <p className="text-slate-500 text-sm mb-2">From a terminal (same machine as this API / .env):</p>
            <pre className="text-xs text-slate-300 bg-slate-950/80 border border-slate-700 rounded p-3 overflow-x-auto whitespace-pre-wrap">
              {data.runbook.watch}
              {"\n"}
              {data.runbook.once}
              {"\n"}
              {data.runbook.dry_run}
            </pre>
          </section>

          <section className="rounded-lg border border-slate-700 bg-slate-900/40 p-4">
            <h3 className="text-sm font-medium text-slate-300 mb-2">Recent log (JSONL)</h3>
            {data.log.path ? (
              <p className="text-xs text-slate-500 mb-2 font-mono break-all">{data.log.path}</p>
            ) : (
              <p className="text-sm text-slate-500 mb-2">Set TBCC_WATCH_LOG in .env to record moves.</p>
            )}
            {data.log.path && !data.log.exists ? <p className="text-sm text-slate-500">File does not exist yet.</p> : null}
            {data.log.recent.length === 0 && data.log.exists ? <p className="text-sm text-slate-500">Log is empty.</p> : null}
            {data.log.recent.length > 0 ? (
              <ul className="space-y-2 max-h-72 overflow-y-auto text-xs font-mono">
                {data.log.recent.map((row, i) => (
                  <li key={i} className="border border-slate-700/60 rounded p-2 text-slate-300 break-all">
                    {JSON.stringify(row)}
                  </li>
                ))}
              </ul>
            ) : null}
          </section>
        </div>
      ) : null}
    </div>
  );
}
