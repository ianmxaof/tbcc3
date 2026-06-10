import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, type SecretarySettingsEffective } from "../api";
import { QueryErrorBanner } from "../components/QueryErrorBanner";
import { ScraperTelegramAuth } from "../components/ScraperTelegramAuth";

type BotRuntime = {
  label: string;
  module: string;
  username?: string;
  status: string;
  pid?: number | null;
  adapter?: string;
  message?: string;
};

function RuntimeCard({
  botKey,
  info,
  settingsLink,
  settingsLabel,
}: {
  botKey: string;
  info: BotRuntime;
  settingsLink?: string;
  settingsLabel?: string;
}) {
  const qc = useQueryClient();
  const rtQ = useQuery({
    queryKey: ["bot-runtime", botKey],
    queryFn: () => api.bots.runtime(botKey),
    refetchInterval: 8000,
  });
  const control = useMutation({
    mutationFn: (action: "start" | "stop" | "restart" | "reload") => api.bots.control(botKey, action),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["bot-runtime", botKey] });
      qc.invalidateQueries({ queryKey: ["automationOverview"] });
    },
  });
  const status = rtQ.data?.status ?? info.status ?? "unknown";
  const running = status === "running";

  return (
    <div className="rounded-lg border border-slate-700 bg-slate-900/40 p-4">
      <div className="flex flex-wrap items-start justify-between gap-2 mb-2">
        <div>
          <h3 className="text-sm font-semibold text-slate-100">{info.label}</h3>
          <p className="text-xs text-slate-500 font-mono">{info.module}</p>
          {info.username ? (
            <p className="text-xs text-cyan-400/90 mt-0.5">
              @{info.username}
            </p>
          ) : null}
        </div>
        <span
          className={`px-2 py-0.5 rounded text-xs ${
            running ? "bg-emerald-900/50 text-emerald-300" : "bg-slate-700 text-slate-400"
          }`}
        >
          {status}
          {rtQ.data?.pid ? ` · PID ${rtQ.data.pid}` : ""}
        </span>
      </div>
      <div className="flex flex-wrap gap-2 mb-2">
        {(["start", "stop", "restart", "reload"] as const).map((act) => (
          <button
            key={act}
            type="button"
            disabled={control.isPending}
            onClick={() => control.mutate(act)}
            className="px-2.5 py-1 text-xs rounded bg-slate-700 hover:bg-slate-600 disabled:opacity-50 capitalize"
          >
            {act}
          </button>
        ))}
        {settingsLink ? (
          <Link
            to={settingsLink}
            className="px-2.5 py-1 text-xs rounded border border-cyan-800 text-cyan-400 hover:bg-cyan-950/40"
          >
            {settingsLabel ?? "Settings"}
          </Link>
        ) : null}
      </div>
      {rtQ.data?.message ? <p className="text-xs text-slate-500">{rtQ.data.message}</p> : null}
      {control.isError ? <p className="text-xs text-red-300 mt-1">{(control.error as Error).message}</p> : null}
    </div>
  );
}

export function AutomationBotsPanel() {
  const { data, isPending, isError, error, refetch } = useQuery({
    queryKey: ["automationOverview"],
    queryFn: () => api.automation.overview(),
    refetchInterval: 15_000,
  });

  const fe = data?.format_engine;
  const secSettings = fe?.settings as SecretarySettingsEffective | undefined;

  return (
    <div className="space-y-8 max-w-5xl">
      <section>
        <h2 className="text-lg font-semibold text-slate-100 mb-1">Publish scheduler</h2>
        <p className="text-sm text-slate-400 mb-3">
          TBCC-Beat ticks every few minutes and enqueues pool interval posts plus scheduled/recurring jobs. Requires{" "}
          <strong>TBCC-Beat</strong> and <strong>TBCC-Celery</strong> (post queue). Configure in{" "}
          <strong>Publish to channels</strong>.
        </p>
        <div className="flex flex-wrap gap-4 text-sm">
          <div className="rounded border border-slate-700 px-4 py-3 bg-slate-900/30">
            <span className="text-slate-500">Scheduled jobs</span>
            <p className="text-xl font-semibold text-slate-100">{data?.scheduler?.total_posts ?? "—"}</p>
          </div>
          <div className="rounded border border-slate-700 px-4 py-3 bg-slate-900/30">
            <span className="text-slate-500">Recurring</span>
            <p className="text-xl font-semibold text-slate-100">{data?.scheduler?.recurring_posts ?? "—"}</p>
          </div>
          <div className="rounded border border-slate-700 px-4 py-3 bg-slate-900/30">
            <span className="text-slate-500">TBCC-Beat</span>
            <p
              className={`text-sm font-semibold ${
                data?.scheduler?.beat_running ? "text-emerald-400" : "text-amber-400"
              }`}
            >
              {data?.scheduler?.beat_running ? "Running" : "Not detected"}
              {data?.scheduler?.scheduling_paused_by_focus ? " · paused (focus)" : ""}
            </p>
          </div>
          <div className="rounded border border-slate-700 px-4 py-3 bg-slate-900/30">
            <span className="text-slate-500">TBCC-Celery</span>
            <p
              className={`text-sm font-semibold ${
                data?.scheduler?.celery_worker_running ? "text-emerald-400" : "text-amber-400"
              }`}
            >
              {data?.scheduler?.celery_worker_running ? "Running" : "Not detected"}
            </p>
          </div>
          <div className="rounded border border-slate-700 px-4 py-3 bg-slate-900/30">
            <span className="text-slate-500">TBCC-Celery-Post</span>
            <p
              className={`text-sm font-semibold ${
                data?.scheduler?.celery_post_worker_running ? "text-emerald-400" : "text-amber-400"
              }`}
            >
              {data?.scheduler?.celery_post_worker_running ? "Running" : "Not detected"}
            </p>
          </div>
        </div>
        {data?.scheduler?.queues && (
          <p className="text-xs text-slate-500 mt-2">
            Queue depth: post={Number((data.scheduler.queues as Record<string, { length?: number }>).post?.length ?? 0)}{" "}
            · celery=
            {Number((data.scheduler.queues as Record<string, { length?: number }>).celery?.length ?? 0)}
            {Number((data.scheduler.queues as Record<string, { length?: number }>).post?.length ?? 0) >= 50 ||
            Number((data.scheduler.queues as Record<string, { length?: number }>).celery?.length ?? 0) >= 200 ? (
              <span className="text-rose-400"> — backlog; use System health → Purge stale Celery queues</span>
            ) : null}
          </p>
        )}
      </section>

      <section>
        <h2 className="text-lg font-semibold text-slate-100 mb-1">Ingest scraper (Telethon)</h2>
        <p className="text-sm text-slate-400 mb-3">
          Userbot session for pulling media from source channels. Full source list is under{" "}
          <strong>Ingest from channels</strong>.
        </p>
        <ScraperTelegramAuth compact />
        {data?.scraper?.authorized ? (
          <p className="text-xs text-emerald-400 mt-2">
            Session OK
            {data.scraper.user?.username ? ` · @${data.scraper.user.username}` : ""}
          </p>
        ) : (
          <p className="text-xs text-amber-400/90 mt-2">Scraper not authorized — ingest jobs cannot run.</p>
        )}
      </section>

      <section>
        <h2 className="text-lg font-semibold text-slate-100 mb-2">Telegram bots</h2>
        <p className="text-sm text-slate-400 mb-4">
          Long-lived bot processes. Payment and loot settings live under <Link to="/bots" className="text-cyan-400 hover:underline">System → Bots</Link>.
          Secretary / Format Engine is configured there too — or use the link on each card below.
        </p>
        {isError && <QueryErrorBanner title="Automation overview" message={String(error)} onRetry={() => void refetch()} />}
        {isPending && !data && <p className="text-sm text-slate-500">Loading bot status…</p>}
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
          {data?.bots?.payment_bot && (
            <RuntimeCard
              botKey="payment_bot"
              info={data.bots.payment_bot as BotRuntime}
              settingsLink="/bots"
              settingsLabel="Shop & payment settings"
            />
          )}
          {data?.bots?.loot_bot && (
            <RuntimeCard
              botKey="loot_bot"
              info={data.bots.loot_bot as BotRuntime}
              settingsLink="/bots"
              settingsLabel="Loot overseer"
            />
          )}
          {data?.bots?.secretary_bot && (
            <RuntimeCard
              botKey="secretary_bot"
              info={data.bots.secretary_bot as BotRuntime}
              settingsLink="/bots"
              settingsLabel="Secretary / Format Engine"
            />
          )}
        </div>
      </section>

      {fe && (
        <section className="rounded-lg border border-cyan-900/50 bg-cyan-950/20 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
            <h2 className="text-lg font-semibold text-cyan-100">Format Engine (secretary)</h2>
            <Link
              to="/bots"
              className="text-sm text-cyan-400 hover:underline"
              onClick={() => {
                try {
                  sessionStorage.setItem("tbccBotsTab", "secretary");
                } catch {
                  /* ignore */
                }
              }}
            >
              Open full panel →
            </Link>
          </div>
          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3 text-sm mb-4">
            <div className="rounded bg-slate-900/60 px-3 py-2 border border-slate-700">
              <span className="text-slate-500 text-xs">User contexts</span>
              <p className="text-lg font-medium text-slate-100">{fe.user_contexts_total}</p>
            </div>
            <div className="rounded bg-slate-900/60 px-3 py-2 border border-slate-700">
              <span className="text-slate-500 text-xs">FAQ chunks (RAG)</span>
              <p className="text-lg font-medium text-slate-100">{fe.knowledge_chunks_active}</p>
            </div>
            <div className="rounded bg-slate-900/60 px-3 py-2 border border-slate-700">
              <span className="text-slate-500 text-xs">Format Engine</span>
              <p className="text-slate-200">{secSettings?.format_engine_enabled ? "On" : "Off"}</p>
            </div>
            <div className="rounded bg-slate-900/60 px-3 py-2 border border-slate-700">
              <span className="text-slate-500 text-xs">RAG / LLM refine</span>
              <p className="text-slate-200">
                {secSettings?.rag_enabled ? "RAG on" : "RAG off"}
                {secSettings?.llm_refine_on_phase_change ? " · refine on" : ""}
              </p>
            </div>
          </div>
          {fe.phases && Object.keys(fe.phases).length > 0 ? (
            <div>
              <p className="text-xs text-slate-400 mb-2">Users by interaction phase</p>
              <div className="flex flex-wrap gap-2">
                {Object.entries(fe.phases).map(([phase, count]) => (
                  <span key={phase} className="px-2 py-1 rounded bg-slate-800 text-xs text-slate-300">
                    {phase}: {count}
                  </span>
                ))}
              </div>
            </div>
          ) : (
            <p className="text-xs text-slate-500">No secretary conversations stored yet — users appear after first DM.</p>
          )}
        </section>
      )}
    </div>
  );
}
