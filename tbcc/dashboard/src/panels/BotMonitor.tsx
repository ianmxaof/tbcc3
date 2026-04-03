import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import { QueryErrorBanner } from "../components/QueryErrorBanner";

export function BotMonitor() {
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

  return (
    <div>
      <h1 className="text-2xl font-semibold mb-4">Bot Monitor</h1>
      <p className="text-slate-400 mb-6">
        Bot status and last seen. Restart controls can be wired to your process manager (e.g. systemd, Docker).
      </p>
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
