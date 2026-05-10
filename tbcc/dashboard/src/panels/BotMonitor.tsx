import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import { QueryErrorBanner } from "../components/QueryErrorBanner";

export function BotMonitor() {
  const qc = useQueryClient();
  const {
    data: bots = [],
    isPending,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ["bots"],
    queryFn: () => api.bots.list(),
  });
  const runtimeQ = useQuery({
    queryKey: ["bot-runtime", "payment_bot"],
    queryFn: () => api.bots.runtime("payment_bot"),
    refetchInterval: 8000,
  });
  const lootRuntimeQ = useQuery({
    queryKey: ["bot-runtime", "loot_bot"],
    queryFn: () => api.bots.runtime("loot_bot"),
    refetchInterval: 8000,
  });
  const control = useMutation({
    mutationFn: (action: "start" | "stop" | "restart" | "reload") => api.bots.control("payment_bot", action),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["bots"] });
      qc.invalidateQueries({ queryKey: ["bot-runtime", "payment_bot"] });
    },
  });
  const lootControl = useMutation({
    mutationFn: (action: "start" | "stop" | "restart" | "reload") => api.bots.control("loot_bot", action),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["bots"] });
      qc.invalidateQueries({ queryKey: ["bot-runtime", "loot_bot"] });
    },
  });

  return (
    <div>
      <h1 className="text-2xl font-semibold mb-4">Bot Monitor</h1>
      <p className="text-slate-400 mb-6">
        Bot status and last seen. Restart controls can be wired to your process manager (e.g. systemd, Docker).
      </p>
      <div className="mb-5 border border-slate-700 rounded-lg p-4 bg-slate-900/30">
        <h2 className="text-sm font-semibold text-slate-200 mb-2">Payment bot runtime control</h2>
        <p className="text-xs text-slate-400 mb-3">
          Step 2 control plane: local API-managed runtime for `payment_bot` (start/stop/restart, plus config reload hint).
        </p>
        <div className="flex flex-wrap items-center gap-2 mb-2">
          <button
            type="button"
            onClick={() => control.mutate("start")}
            disabled={control.isPending}
            className="px-3 py-1.5 text-sm rounded bg-emerald-700/80 text-emerald-50 hover:bg-emerald-600 disabled:opacity-50"
          >
            Start
          </button>
          <button
            type="button"
            onClick={() => control.mutate("stop")}
            disabled={control.isPending}
            className="px-3 py-1.5 text-sm rounded bg-red-800/70 text-red-50 hover:bg-red-700 disabled:opacity-50"
          >
            Stop
          </button>
          <button
            type="button"
            onClick={() => control.mutate("restart")}
            disabled={control.isPending}
            className="px-3 py-1.5 text-sm rounded bg-cyan-700/80 text-cyan-50 hover:bg-cyan-600 disabled:opacity-50"
          >
            Restart
          </button>
          <button
            type="button"
            onClick={() => control.mutate("reload")}
            disabled={control.isPending}
            className="px-3 py-1.5 text-sm rounded bg-slate-700 text-slate-100 hover:bg-slate-600 disabled:opacity-50"
          >
            Reload config
          </button>
        </div>
        <p className="text-xs text-slate-400">
          Runtime:{" "}
          <span className={runtimeQ.data?.status === "running" ? "text-emerald-300" : "text-slate-300"}>
            {runtimeQ.data?.status ?? "unknown"}
          </span>
          {runtimeQ.data?.pid ? ` · PID ${runtimeQ.data.pid}` : ""}
          {runtimeQ.data && (runtimeQ.data as Record<string, unknown>).adapter
            ? ` · adapter ${String((runtimeQ.data as Record<string, unknown>).adapter)}`
            : ""}
        </p>
        {runtimeQ.data && (runtimeQ.data as Record<string, unknown>).message ? (
          <p className="text-xs text-slate-500 mt-1">{String((runtimeQ.data as Record<string, unknown>).message)}</p>
        ) : null}
        {control.isError ? <p className="text-xs text-red-300 mt-2">{(control.error as Error).message}</p> : null}
        {control.isSuccess && control.data?.message ? (
          <p className="text-xs text-cyan-200 mt-2">{control.data.message}</p>
        ) : null}
      </div>

      <div className="mb-5 border border-slate-700 rounded-lg p-4 bg-slate-900/30">
        <h2 className="text-sm font-semibold text-slate-200 mb-2">Loot overseer runtime (`loot_bot`)</h2>
        <p className="text-xs text-slate-400 mb-3">
          Runs <code className="text-slate-300">python -m bots.loot_bot</code> (@aof_lootgod_bot). Configure token,
          invite link, and Docker commands under Bots → <strong>Loot overseer</strong>.
        </p>
        <div className="flex flex-wrap items-center gap-2 mb-2">
          <button
            type="button"
            onClick={() => lootControl.mutate("start")}
            disabled={lootControl.isPending}
            className="px-3 py-1.5 text-sm rounded bg-emerald-700/80 text-emerald-50 hover:bg-emerald-600 disabled:opacity-50"
          >
            Start
          </button>
          <button
            type="button"
            onClick={() => lootControl.mutate("stop")}
            disabled={lootControl.isPending}
            className="px-3 py-1.5 text-sm rounded bg-red-800/70 text-red-50 hover:bg-red-700 disabled:opacity-50"
          >
            Stop
          </button>
          <button
            type="button"
            onClick={() => lootControl.mutate("restart")}
            disabled={lootControl.isPending}
            className="px-3 py-1.5 text-sm rounded bg-cyan-700/80 text-cyan-50 hover:bg-cyan-600 disabled:opacity-50"
          >
            Restart
          </button>
          <button
            type="button"
            onClick={() => lootControl.mutate("reload")}
            disabled={lootControl.isPending}
            className="px-3 py-1.5 text-sm rounded bg-slate-700 text-slate-100 hover:bg-slate-600 disabled:opacity-50"
          >
            Reload config
          </button>
        </div>
        <p className="text-xs text-slate-400">
          Runtime:{" "}
          <span className={lootRuntimeQ.data?.status === "running" ? "text-emerald-300" : "text-slate-300"}>
            {lootRuntimeQ.data?.status ?? "unknown"}
          </span>
          {lootRuntimeQ.data?.pid ? ` · PID ${lootRuntimeQ.data.pid}` : ""}
          {lootRuntimeQ.data && (lootRuntimeQ.data as Record<string, unknown>).adapter
            ? ` · adapter ${String((lootRuntimeQ.data as Record<string, unknown>).adapter)}`
            : ""}
        </p>
        {lootRuntimeQ.data && (lootRuntimeQ.data as Record<string, unknown>).message ? (
          <p className="text-xs text-slate-500 mt-1">{String((lootRuntimeQ.data as Record<string, unknown>).message)}</p>
        ) : null}
        {lootControl.isError ? <p className="text-xs text-red-300 mt-2">{(lootControl.error as Error).message}</p> : null}
        {lootControl.isSuccess && lootControl.data?.message ? (
          <p className="text-xs text-cyan-200 mt-2">{lootControl.data.message}</p>
        ) : null}
      </div>

      {isError && (
        <QueryErrorBanner
          title="Could not load bots"
          message={String((error as Error)?.message ?? error)}
          onRetry={() => void refetch()}
        />
      )}
      <div className="overflow-x-auto">
        <table className="w-full border border-slate-600 rounded-lg overflow-hidden">
          <thead className="bg-slate-700">
            <tr>
              <th className="text-left p-3">ID</th>
              <th className="text-left p-3">Name</th>
              <th className="text-left p-3">Role</th>
              <th className="text-left p-3">Status</th>
              <th className="text-left p-3">Last seen</th>
            </tr>
          </thead>
          <tbody>
            {isPending && !bots.length && !isError ? (
              <tr>
                <td colSpan={5} className="p-4 text-slate-500">
                  Loading…
                </td>
              </tr>
            ) : null}
            {!isPending && !isError && !bots.length ? (
              <tr>
                <td colSpan={5} className="p-4 text-slate-500">
                  No bots registered.
                </td>
              </tr>
            ) : null}
            {bots.map((b: Record<string, unknown>) => (
              <tr key={String(b.id)} className="border-t border-slate-600 hover:bg-slate-800/50">
                <td className="p-3">{String(b.id)}</td>
                <td className="p-3">{String(b.name)}</td>
                <td className="p-3">
                  <span className="px-2 py-0.5 rounded bg-slate-600 text-slate-300 text-sm">
                    {String(b.role)}
                  </span>
                </td>
                <td className="p-3">
                  <span
                    className={`px-2 py-0.5 rounded text-sm ${
                      b.status === "running" ? "bg-green-900/50 text-green-300" : "bg-slate-600 text-slate-400"
                    }`}
                  >
                    {String(b.status)}
                  </span>
                </td>
                <td className="p-3 text-slate-400 text-sm">
                  {b.last_seen ? String(b.last_seen).slice(0, 19) : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {bots.length === 0 && (
        <p className="text-slate-500 mt-4">No bots registered. Add bots via the API or database.</p>
      )}
    </div>
  );
}
