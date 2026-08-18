import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Link } from "react-router-dom";
import { api } from "../api";
import { QueryErrorBanner } from "../components/QueryErrorBanner";
import { InfoDisclosure } from "../components/InfoDisclosure";
import { CategoryDemandCrosswalk } from "../components/CategoryDemandCrosswalk";

export function Analytics() {
  const rangeDays = 30;
  const qc = useQueryClient();

  const subQ = useQuery({
    queryKey: ["analytics", "subscriptions"],
    queryFn: () => api.analytics.subscriptions(),
    refetchInterval: 120_000,
  });

  const summaryQ = useQuery({
    queryKey: ["analytics", "post-events-summary", rangeDays],
    queryFn: () => api.analytics.postEventsSummary(rangeDays),
    refetchInterval: 120_000,
  });

  const eventsQ = useQuery({
    queryKey: ["analytics", "post-events", 40],
    queryFn: () => api.analytics.postEvents({ limit: 40, offset: 0 }),
    refetchInterval: 120_000,
  });

  const eromeGovQ = useQuery({
    queryKey: ["analytics", "erome-upload-governance"],
    queryFn: () => api.analytics.eromeUploadGovernance(),
    refetchInterval: 60_000,
  });

  const gateFunnelQ = useQuery({
    queryKey: ["analytics", "gate-funnel", rangeDays],
    queryFn: () => api.analytics.gateFunnel(rangeDays),
    refetchInterval: 120_000,
  });

  const signalsStatusQ = useQuery({
    queryKey: ["analytics", "signals-status"],
    queryFn: () => api.analytics.signalsStatus(),
    refetchInterval: 120_000,
  });

  const signalsEligQ = useQuery({
    queryKey: ["analytics", "signals-eligibility"],
    queryFn: () => api.analytics.signalsEligibility(),
    refetchInterval: 120_000,
  });

  const signalsQ = useQuery({
    queryKey: ["analytics", "signals", 14],
    queryFn: () => api.analytics.signals(14),
    refetchInterval: 120_000,
  });

  const directionQ = useQuery({
    queryKey: ["analytics", "direction", rangeDays],
    queryFn: () => api.analytics.direction({ days: rangeDays }),
    refetchInterval: 300_000,
  });

  const sponsorPulseQ = useQuery({
    queryKey: ["analytics", "sponsor-pulse", rangeDays],
    queryFn: () => api.analytics.sponsorPulse(rangeDays),
    refetchInterval: 120_000,
  });

  const tickMut = useMutation({
    mutationFn: () => api.analytics.signalsTick({ refreshViews: true, pushInbox: false }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["analytics", "signals"] });
      void qc.invalidateQueries({ queryKey: ["analytics", "signals-status"] });
      void qc.invalidateQueries({ queryKey: ["analytics", "signals-eligibility"] });
    },
  });

  const markApproved = useMutation({
    mutationFn: (albumUrl: string) =>
      api.analytics.eromeGovernanceMark({ album_url: albumUrl, status: "approved_public" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["analytics", "erome-upload-governance"] }),
  });

  const chartData = summaryQ.data?.by_day ?? [];
  const lastTickUnix = signalsStatusQ.data?.last_tick_unix ?? null;
  const lastTickLabel = lastTickUnix
    ? new Date(lastTickUnix * 1000).toLocaleString()
    : "never";
  const viewsN = signalsEligQ.data?.footprint?.deliveries_with_views ?? 0;
  const tickFresh =
    lastTickUnix != null && Date.now() / 1000 - lastTickUnix < 24 * 3600;
  const signalsTone = lastTickUnix == null ? "text-red-400" : tickFresh ? "text-emerald-400" : "text-amber-400";

  return (
    <div className="max-w-5xl space-y-10">
      <div className="flex items-start justify-between gap-3">
        <h1 className="text-xl font-semibold text-slate-100">Analytics</h1>
        <Link to="/income" className="text-sm text-cyan-400 hover:text-cyan-300 shrink-0">
          Income Hub →
        </Link>
        <InfoDisclosure className="shrink-0">
          Step 1: subscription totals and an append-only outbound Telegram log (scheduled sends + pool albums). Step 2:
          AI tag/caption suggestions remain under Media Library (human review before apply). Deeper engagement metrics
          can layer in later.
        </InfoDisclosure>
      </div>

      <section className="bg-slate-800/60 rounded-lg border border-slate-700 p-4 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-medium text-slate-300 uppercase tracking-wide">Growth signals</h2>
          <span className={`text-xs ${signalsTone}`}>last tick: {lastTickLabel}</span>
        </div>
        <p className="text-slate-500 text-xs">
          Deliveries with views: {viewsN}
          {signalsEligQ.data?.footprint?.refreshable_deliveries != null
            ? ` · refreshable ${signalsEligQ.data.footprint.refreshable_deliveries}`
            : ""}
          {signalsEligQ.data?.footprint?.attribution_events != null
            ? ` · attribution events ${signalsEligQ.data.footprint.attribution_events}`
            : ""}
        </p>
        {(signalsQ.data?.signals ?? []).length > 0 ? (
          <ul className="text-sm text-slate-300 space-y-1">
            {(signalsQ.data?.signals ?? []).slice(0, 5).map((s, i) => (
              <li key={`${s.signal_type}-${i}`}>
                <span className="text-slate-500">[{s.confidence}]</span> {s.recommendation}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-slate-500 text-sm">
            No ranked signals yet — usually means views were never refreshed (tick never ran).
          </p>
        )}
        <button
          type="button"
          disabled={tickMut.isPending}
          onClick={() => {
            if (
              window.confirm(
                "Run growth signals tick? Refreshes Telethon views (costly). Inbox push is OFF for this button."
              )
            ) {
              tickMut.mutate();
            }
          }}
          className="px-3 py-1.5 rounded border border-slate-600 text-sm text-slate-300 hover:border-slate-500 disabled:opacity-50"
        >
          {tickMut.isPending ? "Ticking…" : "Run signals tick (no inbox)"}
        </button>
        {tickMut.isError && (
          <p className="text-red-400 text-sm">{String((tickMut.error as Error).message)}</p>
        )}
      </section>

      <section className="bg-slate-800/60 rounded-lg border border-slate-700 p-4 space-y-3">
        <h2 className="text-sm font-medium text-slate-300 uppercase tracking-wide">
          Direction (Top 5 · {rangeDays}d)
        </h2>
        {directionQ.isPending ? (
          <p className="text-slate-500 text-sm">Loading…</p>
        ) : (directionQ.data?.directions ?? []).length > 0 ? (
          <ol className="list-decimal list-inside text-sm text-slate-300 space-y-2">
            {(directionQ.data?.directions ?? []).slice(0, 5).map((d, i) => (
              <li key={i}>
                <span className="text-cyan-400/90">[{d.horizon ?? "?"}]</span> {d.title || d.rationale}
                {d.mcp_followup ? (
                  <span className="block text-xs text-slate-500 ml-5">→ {d.mcp_followup}</span>
                ) : null}
              </li>
            ))}
          </ol>
        ) : (
          <p className="text-slate-500 text-sm whitespace-pre-wrap">
            {(directionQ.data?.markdown || "").slice(0, 800) || "No direction payload."}
          </p>
        )}
      </section>

      <section className="bg-slate-800/60 rounded-lg border border-slate-700 p-4 space-y-3">
        <h2 className="text-sm font-medium text-slate-300 uppercase tracking-wide">
          Sponsor packs pulse ({rangeDays}d)
        </h2>
        {sponsorPulseQ.isPending ? (
          <p className="text-slate-500 text-sm">Loading…</p>
        ) : (
          <div className="space-y-4">
            {(sponsorPulseQ.data?.packs ?? []).map((pack) => (
              <div key={pack.id}>
                <p className="text-slate-200 text-sm font-medium">
                  {pack.title}{" "}
                  <span className="text-slate-500 font-normal">
                    · {pack.clicks} clicks · ${pack.attributed_usd.toFixed(2)}
                  </span>
                </p>
                <div className="overflow-x-auto mt-1">
                  <table className="min-w-full text-xs text-left">
                    <thead className="text-slate-500">
                      <tr>
                        <th className="pr-3 py-1">#</th>
                        <th className="pr-3 py-1">Label</th>
                        <th className="pr-3 py-1">Role</th>
                        <th className="pr-3 py-1">Clicks</th>
                        <th className="pr-3 py-1">$</th>
                      </tr>
                    </thead>
                    <tbody className="text-slate-300">
                      {pack.slots.map((s) => (
                        <tr key={`${pack.id}-${s.index}-${s.label}`}>
                          <td className="pr-3 py-0.5">{s.index}</td>
                          <td className="pr-3 py-0.5">{s.label}</td>
                          <td className="pr-3 py-0.5 text-slate-500">{s.role}</td>
                          <td className="pr-3 py-0.5">{s.clicks}</td>
                          <td className="pr-3 py-0.5">${s.attributed_usd.toFixed(2)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {subQ.isError && (
        <QueryErrorBanner
          title="Could not load subscriptions"
          message={String((subQ.error as Error)?.message ?? subQ.error)}
          onRetry={() => void subQ.refetch()}
        />
      )}
      {summaryQ.isError && (
        <QueryErrorBanner
          title="Could not load post summary"
          message={String((summaryQ.error as Error)?.message ?? summaryQ.error)}
          onRetry={() => void summaryQ.refetch()}
        />
      )}
      {eventsQ.isError && (
        <QueryErrorBanner
          title="Could not load recent events"
          message={String((eventsQ.error as Error)?.message ?? eventsQ.error)}
          onRetry={() => void eventsQ.refetch()}
        />
      )}

      <section>
        <h2 className="text-sm font-medium text-slate-300 uppercase tracking-wide mb-3">Subscriptions</h2>
        {subQ.isPending ? (
          <p className="text-slate-500 text-sm">Loading…</p>
        ) : subQ.data ? (
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
            <StatCard label="Total" value={subQ.data.total_subscriptions} />
            <StatCard label="Active" value={subQ.data.active} />
            <StatCard label="Expired" value={subQ.data.expired} />
            <StatCard label="Cancelled" value={subQ.data.cancelled} />
            <StatCard label="Revenue (Stars)" value={subQ.data.revenue_stars} />
          </div>
        ) : null}
      </section>

      <section>
        <h2 className="text-sm font-medium text-slate-300 uppercase tracking-wide mb-3">
          Gate funnel (Linkvertise beacons, last {rangeDays} days)
        </h2>
        <p className="text-slate-500 text-sm mb-3">
          Clicks on <code className="text-slate-400">api.powercore.app/r/…</code> beacons → loot-bot touch → revenue
          joined on <code className="text-slate-400">source_ref</code>. Paste beacons into LV — see{" "}
          <code className="text-slate-400">docs/WK31_BEACON_PASTE.md</code>.
        </p>
        {gateFunnelQ.isError && (
          <QueryErrorBanner
            title="Could not load gate funnel"
            message={String((gateFunnelQ.error as Error)?.message ?? gateFunnelQ.error)}
            onRetry={() => void gateFunnelQ.refetch()}
          />
        )}
        {gateFunnelQ.isPending ? (
          <p className="text-slate-500 text-sm">Loading…</p>
        ) : gateFunnelQ.data ? (
          <>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
              <StatCard label="Human clicks" value={gateFunnelQ.data.totals.clicks} />
              <StatCard label="Touches" value={gateFunnelQ.data.totals.touches} />
              <StatCard
                label="Click→touch %"
                value={
                  gateFunnelQ.data.totals.click_to_touch_pct != null
                    ? `${gateFunnelQ.data.totals.click_to_touch_pct}%`
                    : "—"
                }
              />
              <StatCard label="Beaconed refs" value={gateFunnelQ.data.totals.beaconed_source_refs} />
            </div>
            {gateFunnelQ.data.unbeaconed_earning_refs.length > 0 && (
              <p className="text-amber-400/90 text-sm mb-3">
                Unbeaconed revenue refs: {gateFunnelQ.data.unbeaconed_earning_refs.join(", ")}
              </p>
            )}
            {gateFunnelQ.data.gate_funnel.length > 0 ? (
              <div className="overflow-x-auto border border-slate-700 rounded-lg">
                <table className="min-w-full text-sm text-left">
                  <thead className="bg-slate-900/60 text-slate-400 uppercase text-xs">
                    <tr>
                      <th className="px-3 py-2">source_ref</th>
                      <th className="px-3 py-2">clicks</th>
                      <th className="px-3 py-2">touches</th>
                      <th className="px-3 py-2">$</th>
                      <th className="px-3 py-2">click→touch</th>
                      <th className="px-3 py-2">top geo</th>
                    </tr>
                  </thead>
                  <tbody className="text-slate-300 divide-y divide-slate-800">
                    {gateFunnelQ.data.gate_funnel.slice(0, 24).map((row) => (
                      <tr key={row.source_ref} className="hover:bg-slate-900/40">
                        <td className="px-3 py-2 font-mono text-xs">{row.source_ref}</td>
                        <td className="px-3 py-2">{row.clicks}</td>
                        <td className="px-3 py-2">{row.touches}</td>
                        <td className="px-3 py-2">${row.revenue_usd.toFixed(2)}</td>
                        <td className="px-3 py-2">
                          {row.click_to_touch_pct != null ? `${row.click_to_touch_pct}%` : "—"}
                        </td>
                        <td className="px-3 py-2 text-xs text-slate-500">
                          {row.top_countries.map((c) => `${c.country}:${c.clicks}`).join(" ") || "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text-slate-500 text-sm">No beacon traffic yet — paste wk31 URLs into Linkvertise.</p>
            )}
          </>
        ) : null}
      </section>

      <WebHubScoreboard
        rows={gateFunnelQ.data?.gate_funnel ?? []}
        isPending={gateFunnelQ.isPending}
        rangeDays={rangeDays}
      />

      <section>
        <h2 className="text-sm font-medium text-slate-300 uppercase tracking-wide mb-3">
          Outbound posts (last {rangeDays} days)
        </h2>
        {summaryQ.isPending ? (
          <p className="text-slate-500 text-sm">Loading…</p>
        ) : summaryQ.data ? (
          <>
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mb-6">
              <StatCard label="Scheduled sends" value={summaryQ.data.totals.scheduled_post_sent} />
              <StatCard label="Pool albums" value={summaryQ.data.totals.pool_album_posted} />
              <StatCard label="All events" value={summaryQ.data.totals.all} />
              <StatCard label="Succeeded" value={summaryQ.data.totals.ok} />
              <StatCard label="Failed" value={summaryQ.data.totals.failed} />
            </div>

            {chartData.length > 0 ? (
              <div className="grid grid-cols-1 xl:grid-cols-4 gap-4 items-stretch">
                <div className="xl:col-span-3 h-72 w-full min-w-0 bg-slate-900/50 border border-slate-700 rounded-lg p-3">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                      <XAxis dataKey="date" tick={{ fill: "#94a3b8", fontSize: 11 }} stroke="#475569" />
                      <YAxis allowDecimals={false} tick={{ fill: "#94a3b8", fontSize: 11 }} stroke="#475569" />
                      <Tooltip
                        contentStyle={{ backgroundColor: "#1e293b", border: "1px solid #334155", borderRadius: 8 }}
                        labelStyle={{ color: "#e2e8f0" }}
                      />
                      <Legend />
                      <Bar dataKey="scheduled_post_sent" name="Scheduled" stackId="a" fill="#22d3ee" />
                      <Bar dataKey="pool_album_posted" name="Pool album" stackId="a" fill="#a78bfa" />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                <div className="xl:col-span-1 bg-slate-900/40 border border-slate-700 rounded-lg p-3">
                  <h3 className="text-xs font-medium text-slate-400 uppercase tracking-wide mb-2">By channel</h3>
                  {summaryQ.data.by_channel.length > 0 ? (
                    <ul className="text-sm text-slate-300 space-y-1 max-h-64 overflow-y-auto pr-1">
                      {summaryQ.data.by_channel.map((c) => (
                        <li key={c.channel_id}>
                          <span className="text-slate-100">{c.channel_name}</span>
                          <span className="text-slate-500"> — {c.count}</span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-slate-500 text-sm">No channel totals yet.</p>
                  )}
                </div>
              </div>
            ) : (
              <p className="text-slate-500 text-sm">
                No outbound post events in this window yet. Events are recorded when Celery sends scheduled posts or
                pool interval albums.
              </p>
            )}
          </>
        ) : null}
      </section>

      <CategoryDemandCrosswalk />

      <section>
        <h2 className="text-sm font-medium text-slate-300 uppercase tracking-wide mb-3">Recent post events</h2>
        {eventsQ.isPending ? (
          <p className="text-slate-500 text-sm">Loading…</p>
        ) : eventsQ.data && eventsQ.data.items.length > 0 ? (
          <div className="overflow-x-auto border border-slate-700 rounded-lg">
            <table className="w-full text-sm text-left">
              <thead className="bg-slate-800/80 text-slate-400">
                <tr>
                  <th className="px-3 py-2 font-medium">Time (UTC)</th>
                  <th className="px-3 py-2 font-medium">Type</th>
                  <th className="px-3 py-2 font-medium">Channel</th>
                  <th className="px-3 py-2 font-medium">Ref</th>
                  <th className="px-3 py-2 font-medium">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700">
                {eventsQ.data.items.map((row) => (
                  <tr key={row.id} className="hover:bg-slate-800/40">
                    <td className="px-3 py-2 text-slate-300 whitespace-nowrap">
                      {row.created_at ? row.created_at.replace("Z", "") : "—"}
                    </td>
                    <td className="px-3 py-2 text-slate-200">{row.event_type}</td>
                    <td className="px-3 py-2 text-slate-400">{row.channel_name ?? row.channel_id ?? "—"}</td>
                    <td className="px-3 py-2 text-slate-500">
                      {row.scheduled_post_id != null ? `post #${row.scheduled_post_id}` : ""}
                      {row.pool_id != null ? `pool #${row.pool_id}` : ""}
                      {row.scheduled_post_id == null && row.pool_id == null ? "—" : ""}
                    </td>
                    <td className="px-3 py-2">
                      {row.ok ? (
                        <span className="text-emerald-400">ok</span>
                      ) : (
                        <span className="text-red-400" title={row.error_message || ""}>
                          failed
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-slate-500 text-sm">No events logged yet.</p>
        )}
      </section>

      <section>
        <h2 className="text-sm font-medium text-slate-300 uppercase tracking-wide mb-3">
          Erome private staging
        </h2>
        {eromeGovQ.isError && (
          <QueryErrorBanner
            title="Could not load Erome governance"
            message={String((eromeGovQ.error as Error)?.message ?? eromeGovQ.error)}
            onRetry={() => void eromeGovQ.refetch()}
          />
        )}
        {eromeGovQ.isPending ? (
          <p className="text-slate-500 text-sm">Loading…</p>
        ) : eromeGovQ.data ? (
          <div className="space-y-3">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <StatCard label="Pending review" value={eromeGovQ.data.pending_review} />
              <StatCard label="Private" value={eromeGovQ.data.private_count} />
              <StatCard label="Public" value={eromeGovQ.data.public_count} />
              <div className="rounded-lg border border-slate-700 bg-slate-800/40 px-3 py-2">
                <div className="text-slate-500 text-xs uppercase tracking-wide">Default</div>
                <div className="text-lg font-semibold text-slate-100">{eromeGovQ.data.default_visibility}</div>
              </div>
            </div>
            {(eromeGovQ.data.pending || []).length === 0 ? (
              <p className="text-slate-500 text-sm">No private albums awaiting governance.</p>
            ) : (
              <ul className="space-y-2 text-sm">
                {eromeGovQ.data.pending.map((row) => (
                  <li
                    key={row.album_url || row.title}
                    className="flex flex-wrap items-center justify-between gap-2 rounded border border-slate-700 bg-slate-800/30 px-3 py-2"
                  >
                    <div className="min-w-0">
                      <div className="text-slate-200 truncate">{row.title || "Untitled"}</div>
                      <a
                        className="text-cyan-400 hover:text-cyan-300 text-xs break-all"
                        href={row.album_url}
                        target="_blank"
                        rel="noreferrer"
                      >
                        {row.album_url}
                      </a>
                    </div>
                    <button
                      type="button"
                      className="shrink-0 rounded bg-emerald-700/80 px-2 py-1 text-xs text-white hover:bg-emerald-600 disabled:opacity-50"
                      disabled={!row.album_url || markApproved.isPending}
                      onClick={() => row.album_url && markApproved.mutate(row.album_url)}
                      title="Marks ledger approved — still flip Public on Erome (or use --promote-public)"
                    >
                      Mark approved
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        ) : null}
      </section>
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border border-slate-700 bg-slate-800/40 px-3 py-2">
      <div className="text-slate-500 text-xs uppercase tracking-wide">{label}</div>
      <div className="text-lg font-semibold text-slate-100 tabular-nums">{value}</div>
    </div>
  );
}

/**
 * P10 — client-filters the same gate-funnel payload already fetched above
 * (no new backend endpoint). See docs/handoffs/2026-08-10_aof-hub-p9-p10_report.md
 * "P10 design" for why expects_touch exists and must be respected here:
 * without it, web-vpapi-/web-live- rows (affiliate links) AND web-vip/web-spicy
 * (bare bot links with no ?start= payload) all read as a broken 0% funnel when
 * zero touches is the correct, expected outcome for both shapes.
 */
function WebHubScoreboard({
  rows,
  isPending,
  rangeDays,
}: {
  rows: Array<{
    source_ref: string;
    slugs: string[];
    clicks: number;
    touches: number;
    revenue_usd: number;
    click_to_touch_pct: number | null;
    expects_touch: boolean;
  }>;
  isPending: boolean;
  rangeDays: number;
}) {
  const webRows = rows
    .filter((r) => r.source_ref.startsWith("src_web_"))
    .sort((a, b) => b.revenue_usd - a.revenue_usd || b.clicks - a.clicks);

  const totals = webRows.reduce(
    (acc, r) => ({
      clicks: acc.clicks + r.clicks,
      touches: acc.touches + r.touches,
      revenue: acc.revenue + r.revenue_usd,
    }),
    { clicks: 0, touches: 0, revenue: 0 }
  );

  return (
    <section>
      <h2 className="text-sm font-medium text-slate-300 uppercase tracking-wide mb-3">
        Web hub scoreboard (aof-forum, last {rangeDays} days)
      </h2>
      <p className="text-slate-500 text-sm mb-3">
        <code className="text-slate-400">src_web_*</code> rows from the gate funnel above — hub CTAs, VPAPI labels,
        and live-embed outbound clicks. Rows marked <span className="text-amber-400/90">no touch expected</span>{" "}
        either point off Telegram (affiliate links) or are a bare bot link with no <code>?start=</code> payload;
        zero touches there is expected, not broken.
      </p>
      {isPending ? (
        <p className="text-slate-500 text-sm">Loading…</p>
      ) : webRows.length === 0 ? (
        <p className="text-slate-500 text-sm">No web hub beacon traffic yet.</p>
      ) : (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mb-4">
            <StatCard label="Web clicks" value={totals.clicks} />
            <StatCard label="Web touches" value={totals.touches} />
            <StatCard label="Web revenue ($)" value={Math.round(totals.revenue)} />
          </div>
          <div className="overflow-x-auto border border-slate-700 rounded-lg">
            <table className="min-w-full text-sm text-left">
              <thead className="bg-slate-900/60 text-slate-400 uppercase text-xs">
                <tr>
                  <th className="px-3 py-2">source_ref</th>
                  <th className="px-3 py-2">clicks</th>
                  <th className="px-3 py-2">touches</th>
                  <th className="px-3 py-2">$</th>
                  <th className="px-3 py-2">click→touch</th>
                </tr>
              </thead>
              <tbody className="text-slate-300 divide-y divide-slate-800">
                {webRows.map((row) => (
                  <tr key={row.source_ref} className="hover:bg-slate-900/40">
                    <td className="px-3 py-2 font-mono text-xs">{row.source_ref}</td>
                    <td className="px-3 py-2">{row.clicks}</td>
                    <td className="px-3 py-2">
                      {!row.expects_touch ? (
                        <span
                          className="text-amber-400/90"
                          title="No ?start= payload reaches Telegram here (affiliate link, or a bare bot link) — touches aren't possible by design"
                        >
                          no touch expected
                        </span>
                      ) : (
                        row.touches
                      )}
                    </td>
                    <td className="px-3 py-2">${row.revenue_usd.toFixed(2)}</td>
                    <td className="px-3 py-2">
                      {!row.expects_touch
                        ? "—"
                        : row.click_to_touch_pct != null
                          ? `${row.click_to_touch_pct}%`
                          : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}
