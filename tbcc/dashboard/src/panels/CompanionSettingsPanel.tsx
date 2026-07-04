import { useCallback, useEffect, useState } from "react";
import { api } from "../api";

type Ops = Awaited<ReturnType<typeof api.companion.ops>>;

export function CompanionSettingsPanel() {
  const [ops, setOps] = useState<Ops | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      setOps(await api.companion.ops());
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return (
    <div className="max-w-3xl space-y-4">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-slate-100">Companion bot (@aof_spicybot_bot)</h2>
          <p className="text-sm text-slate-400 mt-1">
            LLM chat + undress webhooks. Restart via tray: TBCC-CompanionBot.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void refresh()}
          className="px-3 py-1.5 text-sm rounded bg-slate-700 hover:bg-slate-600 text-slate-200"
        >
          Refresh
        </button>
      </div>

      {loading && !ops ? <p className="text-slate-400">Loading…</p> : null}
      {err ? <p className="text-red-400 text-sm">{err}</p> : null}

      {ops ? (
        <div className="grid gap-3 sm:grid-cols-2">
          <Stat label="LLM model" value={ops.llm_model} ok={ops.llm_configured} />
          <Stat label="Provider" value={ops.llm_provider} />
          <Stat label="Undress balance" value={ops.undress_balance ?? "—"} />
          <Stat label="Pending jobs" value={String(ops.pending_jobs)} />
          <Stat label="Webhook" value={ops.webhook_ok ? "reachable" : "down"} ok={ops.webhook_ok} />
          <Stat label="Image provider" value={ops.image_provider} />
          <Stat label="Free trial / user" value={String(ops.free_trial_photos)} />
          <Stat label="Stars / photo" value={ops.stars_enabled ? `${ops.stars_per_photo}⭐` : "off"} />
          <Stat label="Gate" value={ops.gate_enabled ? "on" : "off"} />
          <Stat label="Bot token" value={ops.token_configured ? "set" : "missing"} ok={ops.token_configured} />
        </div>
      ) : null}

      {ops && !ops.webhook_ok ? (
        <p className="text-amber-300 text-sm border border-amber-700/50 rounded-lg p-3 bg-amber-950/20">
          Webhook unreachable — photo results will not DM back. Check ngrok + TBCC_PUBLIC_API_BASE_URL.
          <br />
          <span className="text-slate-400">{ops.webhook_detail}</span>
        </p>
      ) : null}
    </div>
  );
}

function Stat({ label, value, ok }: { label: string; value: string; ok?: boolean }) {
  const color =
    ok === undefined ? "text-slate-100" : ok ? "text-emerald-400" : "text-amber-400";
  return (
    <div className="rounded-lg border border-slate-700 bg-slate-800/50 p-3">
      <div className="text-xs text-slate-500 uppercase tracking-wide">{label}</div>
      <div className={`text-sm font-medium mt-1 break-all ${color}`}>{value}</div>
    </div>
  );
}
