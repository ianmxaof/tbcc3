import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api";
import { QueryErrorBanner } from "./QueryErrorBanner";

const DEPOSIT_LIMITS = [8, 12, 20, 50, 100] as const;

type Props = {
  className?: string;
};

export function SchedulerGrowthHub({ className = "" }: Props) {
  const qc = useQueryClient();
  const [depositLimit, setDepositLimit] = useState<number>(8);
  const [feedback, setFeedback] = useState<string | null>(null);

  const { data, isPending, isError, error, refetch } = useQuery({
    queryKey: ["growth-hub-status"],
    queryFn: () => api.growthHub.status(),
    refetchInterval: 60_000,
  });

  const { data: liveness } = useQuery({
    queryKey: ["growth-hub-liveness"],
    queryFn: () => api.growthHub.livenessStatus(),
    refetchInterval: 60_000,
  });

  const applyLiveness = useMutation({
    mutationFn: () => api.growthHub.applyLiveness(),
    onSuccess: (r) => {
      setFeedback(
        `Liveness installed — thin lanes ${r.intervals?.thin_min ?? "?"}m · heartbeat ${r.intervals?.heartbeat_min ?? "?"}m · ${r.subscriber_count_real ?? 0} real subs`
      );
      void qc.invalidateQueries({ queryKey: ["growth-hub-liveness"] });
      void qc.invalidateQueries({ queryKey: ["scheduledPosts"] });
    },
    onError: (e: Error) => setFeedback(e.message),
  });

  const sync = useMutation({
    mutationFn: () => api.growthHub.syncSchedulers(),
    onSuccess: (r) => {
      setFeedback(
        `Synced ${r.channels?.length ?? 0} channel schedulers · PACKS=${r.bulletin_has_packs ? "yes" : "no"} · GOON=${r.bulletin_has_goon ? "yes" : "no"}`
      );
      void qc.invalidateQueries({ queryKey: ["growth-hub-status"] });
      void qc.invalidateQueries({ queryKey: ["scheduledPosts"] });
    },
    onError: (e: Error) => setFeedback(e.message),
  });

  const syncAffiliates = useMutation({
    mutationFn: () => api.growthHub.syncAffiliateRotation(),
    onSuccess: (r) => {
      const n = r.affiliate?.active_rows ?? 0;
      setFeedback(
        `Affiliate rotation synced — ${n} active sponsors · partners in bulletin=${r.bulletin_has_partners ? "yes" : "no"}`
      );
      void qc.invalidateQueries({ queryKey: ["growth-hub-status"] });
      void qc.invalidateQueries({ queryKey: ["scheduledPosts"] });
      void qc.invalidateQueries({ queryKey: ["promoAffiliateStats"] });
    },
    onError: (e: Error) => setFeedback(e.message),
  });

  const broadcast = useMutation({
    mutationFn: () => api.growthHub.broadcastBulletin(),
    onSuccess: (r) => {
      setFeedback(`Queued links hub bulletin to ${r.count ?? 0} channels (Celery poster). Check Telegram in ~1 min.`);
      void qc.invalidateQueries({ queryKey: ["growth-hub-status"] });
    },
    onError: (e: Error) => setFeedback(e.message),
  });

  const conversionSprint = useMutation({
    mutationFn: () => api.growthHub.conversionSprint(),
    onSuccess: (r) => {
      const pool = r.stars_bait?.outreach_pool ?? "?";
      const sched = r.album_checkout?.schedulers_updated ?? "?";
      const blast = r.broadcast?.count ?? 0;
      setFeedback(
        `Conversion sprint queued — stars-bait pool ${pool} · ${sched} schedulers checkout-synced · bulletin to ${blast} channels`
      );
      void qc.invalidateQueries({ queryKey: ["growth-hub-status"] });
      void qc.invalidateQueries({ queryKey: ["scheduledPosts"] });
    },
    onError: (e: Error) => setFeedback(e.message),
  });

  const deposit = useMutation({
    mutationFn: () => api.growthHub.storageDeposit({ limit: depositLimit, media_types: "both" }),
    onSuccess: (r) => {
      if (r.error) {
        setFeedback(r.error);
        return;
      }
      const mirror = (r as { topic_mirror?: { matched_count?: number } }).topic_mirror;
      setFeedback(
        `Queued ${r.matched_count} pool imports (${depositLimit}/topic)` +
          (mirror?.matched_count != null ? ` + ${mirror.matched_count} topic mirrors` : "")
      );
    },
    onError: (e: Error) => setFeedback(e.message),
  });

  const topicMirror = useMutation({
    mutationFn: () => api.growthHub.topicMirror({ limit_per_pair: 8 }),
    onSuccess: (r) => {
      setFeedback(`Topic mirror queued for ${r.matched_count ?? 0} lane pairs (deduped).`);
    },
    onError: (e: Error) => setFeedback(e.message),
  });

  const schedOk = data?.schedulers?.filter((s) => s.ok).length ?? 0;
  const schedTotal = data?.schedulers?.length ?? 0;

  return (
    <div
      className={`tbcc-panel flex max-w-full flex-col rounded-md border border-emerald-800/50 bg-slate-900/80 p-3 ${className}`}
    >
      <div className="mb-2 flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <h2 className="text-sm font-semibold text-emerald-100">Growth hub</h2>
        <span className="text-[10px] text-slate-500">AOF network ops — not OpenClaw</span>
      </div>

      <p className="mb-3 text-xs leading-relaxed text-slate-400">
        Keeps every AOF channel scheduler carrying the same <strong className="text-slate-300">links hub bulletin</strong>{" "}
        (PACKS · GOON · BOP · ABG cross-links), rotates <strong className="text-slate-300">sponsor footers</strong> from
        your affiliate DB, and can <strong className="text-slate-300">import Storage Hub</strong> media into lane pools.
        All buttons call TBCC FastAPI + Celery directly — OpenClaw is a separate ops agent and does not run these actions.
      </p>

      {isError && (
        <QueryErrorBanner
          title="Growth hub unavailable"
          message={String((error as Error)?.message ?? error)}
          onRetry={() => void refetch()}
        />
      )}

      {isPending && !data && <p className="text-xs text-slate-500">Loading growth hub…</p>}

      {data && (
        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto">
          <section className="rounded border border-amber-700/40 bg-amber-950/20 p-2">
            <p className="mb-1 text-[10px] uppercase tracking-wide text-amber-400">Conversion sprint</p>
            <p className="mb-2 text-xs leading-relaxed text-slate-400">
              One click: seed <strong className="text-slate-300">stars-bait</strong> copy + DM pacing, force{" "}
              <strong className="text-slate-300">Stars checkout</strong> on every scheduler, refresh bulletin slots, and
              blast the links hub to all channels. Run weekly or after any poster/session incident.
            </p>
            <button
              type="button"
              className="rounded bg-amber-600 px-3 py-1.5 text-xs font-semibold text-slate-950 hover:bg-amber-500 disabled:opacity-50"
              disabled={conversionSprint.isPending}
              title="POST /growth-hub/conversion-sprint — stars-bait → album checkout → sync schedulers → broadcast"
              onClick={() => conversionSprint.mutate()}
            >
              {conversionSprint.isPending ? "Running sprint…" : "Run conversion sprint"}
            </button>
          </section>

          <section>
            <p className="mb-1 text-[10px] uppercase tracking-wide text-slate-500">Links bulletin</p>
            <p className="mb-2 text-xs text-slate-400">
              Channel schedulers with bulletin slot:{" "}
              <strong className={schedOk === schedTotal ? "text-emerald-400" : "text-amber-400"}>
                {schedOk}/{schedTotal}
              </strong>
              {data.pinned_bulletin_id != null && (
                <>
                  {" "}
                  · pinned main job <code className="text-slate-300">#{data.pinned_bulletin_id}</code>
                </>
              )}
            </p>

            <details className="mb-2 text-xs text-slate-400">
              <summary className="cursor-pointer text-slate-300">Preview bulletin HTML</summary>
              <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap rounded border border-slate-700 bg-slate-950/80 p-2 text-[10px] text-slate-300">
                {data.bulletin_preview}
              </pre>
            </details>

            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                className="rounded bg-slate-700 px-3 py-1.5 text-xs font-medium text-slate-100 hover:bg-slate-600 disabled:opacity-50"
                disabled={sync.isPending}
                title="Rebuild bulletin + per-channel promo variations on every AOF * SCHEDULER row"
                onClick={() => sync.mutate()}
              >
                {sync.isPending ? "Syncing…" : "Sync schedulers"}
              </button>
              <button
                type="button"
                className="rounded bg-cyan-800 px-3 py-1.5 text-xs font-medium text-white hover:bg-cyan-700 disabled:opacity-50"
                disabled={syncAffiliates.isPending}
                title="Read promo_affiliate_links table → inject sponsor footers + partners block into schedulers"
                onClick={() => syncAffiliates.mutate()}
              >
                {syncAffiliates.isPending ? "Syncing…" : "Sync affiliate rotation"}
              </button>
              <button
                type="button"
                className="rounded bg-emerald-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-600 disabled:opacity-50"
                disabled={broadcast.isPending}
                title="Post bulletin variation 0 to every network channel now (staggered Celery sends)"
                onClick={() => broadcast.mutate()}
              >
                {broadcast.isPending ? "Queuing…" : "Post bulletin to all channels"}
              </button>
            </div>
            <p className="mt-2 text-[10px] text-slate-500">
              New sponsor URL? Misc → <strong className="text-slate-400">Promo affiliate links</strong> (bulk JSON or
              picker), then run <strong className="text-slate-400">Sync affiliate rotation</strong> here.
            </p>
          </section>

          <section className="border-t border-slate-700/80 pt-3">
            <p className="mb-1 text-[10px] uppercase tracking-wide text-slate-500">Network liveness</p>
            <p className="mb-2 text-xs leading-relaxed text-slate-400">
              Optional “looks alive” layer: faster intervals on thin lanes (GOON/BOP/ABG), heartbeat + drop-ticker posts
              on main group, and drop-signal copy on quiet channels. Pure TBCC schedulers — no OpenClaw.
              {liveness && (
                <>
                  {" "}
                  <strong className="text-emerald-400">{liveness.subscriber_count_real}</strong> real Stars subs.
                </>
              )}
            </p>
            <div className="mb-2 flex flex-wrap gap-2">
              <button
                type="button"
                className="rounded bg-amber-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-amber-600 disabled:opacity-50"
                disabled={applyLiveness.isPending}
                title="Create/update liveness scheduler rows + tune intervals + enable pool backup posts"
                onClick={() => applyLiveness.mutate()}
              >
                {applyLiveness.isPending ? "Applying…" : "Enable liveness automation"}
              </button>
              <button
                type="button"
                className="rounded bg-violet-800 px-3 py-1.5 text-xs font-medium text-white hover:bg-violet-700 disabled:opacity-50"
                disabled={topicMirror.isPending}
                title="Copy deduped Storage Hub topic media into matching main supergroup forum topics"
                onClick={() => topicMirror.mutate()}
              >
                {topicMirror.isPending ? "Mirroring…" : "Mirror storage → main topics"}
              </button>
            </div>
            {liveness?.main_pulses?.length ? (
              <ul className="text-[10px] text-slate-500">
                {liveness.main_pulses.map((p) => (
                  <li key={p.name}>
                    {p.installed === false ? (
                      <span className="text-amber-400">{p.name}: not installed — run Enable liveness</span>
                    ) : (
                      <>
                        {p.name.split("—").pop()?.trim()} every {p.interval_minutes}m
                        {p.variations != null ? ` · ${p.variations} variations` : ""}
                      </>
                    )}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-[10px] text-slate-500">Liveness pulses not installed yet.</p>
            )}
          </section>

          <section className="border-t border-slate-700/80 pt-3">
            <p className="mb-1 text-[10px] uppercase tracking-wide text-slate-500">Storage hub → pools</p>
            <p className="mb-2 text-xs text-slate-400">
              Import new media from Storage Hub forum topics into matching AOF lane pools (pending import jobs — existing
              pool media untouched).
            </p>
            <div className="flex flex-wrap items-center gap-2">
              <select
                className="rounded border border-slate-600 bg-slate-800 px-2 py-1 text-xs text-slate-200"
                value={depositLimit}
                onChange={(e) => setDepositLimit(Number(e.target.value))}
              >
                {DEPOSIT_LIMITS.map((n) => (
                  <option key={n} value={n}>
                    {n} items / topic
                  </option>
                ))}
              </select>
              <button
                type="button"
                className="rounded bg-indigo-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-600 disabled:opacity-50"
                disabled={deposit.isPending}
                onClick={() => deposit.mutate()}
              >
                {deposit.isPending ? "Queuing…" : "Deposit all matched topics"}
              </button>
              <span className="text-[10px] text-slate-500">
                {data.storage_hub.identifier} · topic title → pool
              </span>
            </div>
          </section>

          {data.schedulers.some((s) => !s.ok) && (
            <ul className="text-[10px] text-amber-400/90">
              {data.schedulers
                .filter((s) => !s.ok)
                .map((s) => (
                  <li key={s.key}>
                    {s.key}: {s.reason ?? "missing bulletin variation"} — run Sync schedulers
                  </li>
                ))}
            </ul>
          )}
        </div>
      )}

      {feedback && (
        <p className="mt-2 shrink-0 text-xs text-emerald-300/90" role="status">
          {feedback}
        </p>
      )}
    </div>
  );
}
