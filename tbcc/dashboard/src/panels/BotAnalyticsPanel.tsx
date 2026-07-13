import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api";
import { QueryErrorBanner } from "../components/QueryErrorBanner";

const EVENT_LABELS: Record<string, string> = {
  loot_roll: "Loot rolls (paid/preview)",
  loot_free_pull: "Loot free pulls",
  subscription_created: "Subscriptions",
  referral_recorded: "Referrals",
  erome_album_published: "Erome publishes",
};

export function BotAnalyticsPanel() {
  const [days, setDays] = useState(30);
  const { data, isPending, isError, error, refetch } = useQuery({
    queryKey: ["bots-funnel", days],
    queryFn: () => api.analytics.botsFunnel(days),
  });

  const byType = data?.attribution?.totals_by_type ?? {};
  const loot = data?.loot_players;
  const links = data?.deep_links;

  return (
    <div className="space-y-6 max-w-4xl">
      <div className="flex flex-wrap items-center gap-3">
        <label className="text-sm text-slate-400">
          Range
          <select
            className="ml-2 bg-slate-800 border border-slate-600 rounded px-2 py-1 text-slate-200"
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
          >
            <option value={7}>7 days</option>
            <option value={30}>30 days</option>
            <option value={90}>90 days</option>
          </select>
        </label>
        <button
          type="button"
          onClick={() => void refetch()}
          className="text-sm px-3 py-1 rounded border border-slate-600 text-slate-300 hover:bg-slate-800"
        >
          Refresh
        </button>
      </div>

      {isError ? <QueryErrorBanner error={error} onRetry={() => void refetch()} /> : null}

      {isPending ? (
        <p className="text-slate-400 text-sm">Loading bot funnel…</p>
      ) : (
        <>
          <section className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <StatCard label="Loot players (all time)" value={loot?.unique_players ?? 0} />
            <StatCard label="Total rolls" value={loot?.total_rolls ?? 0} />
            <StatCard label="Free pulls used" value={loot?.free_pulls_used ?? 0} />
            <StatCard label="Active players (7d)" value={loot?.active_players_7d ?? 0} />
          </section>

          <section className="rounded-lg border border-slate-700 bg-slate-900/50 p-4">
            <h2 className="text-sm font-medium text-slate-200 mb-3">Attribution events ({days}d)</h2>
            <div className="space-y-2">
              {Object.keys(byType).length === 0 ? (
                <p className="text-slate-500 text-sm">No events in range — rolls/subs record when loot bot + payment bot are up.</p>
              ) : (
                Object.entries(byType).map(([k, v]) => (
                  <div key={k} className="flex justify-between text-sm">
                    <span className="text-slate-400">{EVENT_LABELS[k] ?? k}</span>
                    <span className="text-cyan-400 font-mono">{v}</span>
                  </div>
                ))
              )}
            </div>
            {data?.attribution?.subscription_stars_total != null && data.attribution.subscription_stars_total > 0 ? (
              <p className="text-xs text-slate-500 mt-3">
                Subscription Stars attributed: {data.attribution.subscription_stars_total}
              </p>
            ) : null}
          </section>

          {links ? (
            <section className="rounded-lg border border-slate-700 bg-slate-900/50 p-4">
              <h2 className="text-sm font-medium text-slate-200 mb-3">Monetization deep links (copy for X / promos)</h2>
              <DeepLink label="Paid Loot Room checkout" url={links.loot_paid_checkout} />
              <DeepLink label="Payment bot menu_loot" url={links.payment_bot_menu_loot} />
              <DeepLink label="Free pull (loot overseer)" url={links.loot_free_pull} />
            </section>
          ) : null}
        </>
      )}
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border border-slate-700 bg-slate-900/60 p-3">
      <div className="text-2xl font-semibold text-cyan-400">{value}</div>
      <div className="text-xs text-slate-500 mt-1">{label}</div>
    </div>
  );
}

function DeepLink({ label, url }: { label: string; url: string }) {
  return (
    <div className="mb-2">
      <div className="text-xs text-slate-500 mb-1">{label}</div>
      <code className="text-xs text-slate-300 break-all block bg-slate-950/80 px-2 py-1 rounded border border-slate-800">
        {url}
      </code>
    </div>
  );
}
