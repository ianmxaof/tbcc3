import { useQuery } from "@tanstack/react-query";
import { api, type ListeningRelayPostLogItem } from "../api";
import { QueryErrorBanner } from "./QueryErrorBanner";

function formatRelayTime(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function triggerLabel(trigger: string): string {
  if (trigger === "lastfm") return "Last.fm";
  if (trigger === "webhook") return "Webhook";
  if (trigger === "test") return "Test";
  return trigger;
}

function triggerTone(trigger: string): string {
  if (trigger === "lastfm") return "bg-cyan-900/60 text-cyan-200 border-cyan-700/50";
  if (trigger === "webhook") return "bg-amber-900/50 text-amber-200 border-amber-700/50";
  if (trigger === "test") return "bg-slate-700/80 text-slate-300 border-slate-600";
  return "bg-slate-800 text-slate-300 border-slate-600";
}

function statusTone(status: string): string {
  if (status === "sent") return "text-emerald-400";
  if (status === "failed") return "text-rose-400";
  return "text-amber-300";
}

function destinationLine(item: ListeningRelayPostLogItem): string {
  const d = item.destination;
  const parts: string[] = [];
  if (d.channel_name) parts.push(d.channel_name);
  else if (d.kind === "random") parts.push("Random AOF lane");
  if (d.kind === "topic" && d.label) parts.push(d.label);
  else if (d.kind === "main" && !d.channel_name) parts.push("Main chat");
  if (d.lane === "vip") parts.push("VIP");
  if (item.destination.kind === "random") parts.push("(random)");
  return parts.filter(Boolean).join(" · ") || "—";
}

function RelayPostHistoryCard({ item }: { item: ListeningRelayPostLogItem }) {
  const meta: string[] = [];
  if (item.source_label || item.source) meta.push(item.source_label || item.source || "");
  if (item.template_slot != null && item.template_slots_total) {
    meta.push(`slot ${item.template_slot + 1}/${item.template_slots_total}`);
  }
  if (item.copy_followups_count > 0) meta.push(`${item.copy_followups_count} copy panel(s)`);
  if (item.ascii_beat) meta.push("ASCII beat");
  if (item.tryptych) meta.push("tryptych");
  if (item.send_silent) meta.push("silent");
  const fanout: string[] = [];
  if (item.buffer_sent) fanout.push("Buffer");
  if (item.discord_sent) fanout.push("Discord");
  if (item.telegram_message_id) fanout.push(`TG #${item.telegram_message_id}`);

  return (
    <article className="rounded-lg border border-slate-700/80 bg-slate-950/40 p-3 space-y-2">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2 mb-1">
            <span className={`text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded border ${triggerTone(item.trigger)}`}>
              {triggerLabel(item.trigger)}
            </span>
            <span className={`text-[10px] font-medium ${statusTone(item.status)}`}>{item.status}</span>
            <time className="text-[10px] text-slate-500">{formatRelayTime(item.created_at)}</time>
          </div>
          <p className="text-sm text-slate-100 font-medium truncate" title={item.headline || undefined}>
            {item.headline || item.main_html_preview || "(no title)"}
          </p>
          {item.album ? <p className="text-xs text-slate-500 truncate">{item.album}</p> : null}
        </div>
      </div>

      <dl className="grid gap-1 text-[11px] sm:grid-cols-2">
        <div>
          <dt className="text-slate-500">Destination</dt>
          <dd className="text-slate-300">{destinationLine(item)}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Fan-out</dt>
          <dd className="text-slate-300">{fanout.length ? fanout.join(" · ") : "Telegram only"}</dd>
        </div>
      </dl>

      {meta.length ? (
        <p className="text-[10px] text-slate-500">{meta.join(" · ")}</p>
      ) : null}

      {item.url ? (
        <a
          href={item.url}
          target="_blank"
          rel="noreferrer"
          className="block text-[11px] text-cyan-400/90 hover:underline truncate"
        >
          {item.url}
        </a>
      ) : null}

      {item.telegram_message_url ? (
        <a
          href={item.telegram_message_url}
          target="_blank"
          rel="noreferrer"
          className="inline-flex text-[11px] text-violet-300 hover:underline"
        >
          Open in Telegram{item.telegram_message_id ? ` (#${item.telegram_message_id})` : ""}
        </a>
      ) : null}

      {item.main_html_preview ? (
        <details className="text-[11px]">
          <summary className="cursor-pointer text-slate-500 hover:text-slate-300 select-none">Posted preview</summary>
          <pre className="mt-1 whitespace-pre-wrap font-mono text-slate-400 bg-slate-900/80 rounded p-2 border border-slate-800 max-h-28 overflow-auto">
            {item.main_html_preview}
          </pre>
        </details>
      ) : null}

      {item.error_message ? (
        <p className="text-[11px] text-rose-400/90">{item.error_message}</p>
      ) : null}
    </article>
  );
}

export function RelayPostHistory({ pollMs = 30_000 }: { pollMs?: number }) {
  const q = useQuery({
    queryKey: ["listeningRelayHistory"],
    queryFn: () => api.listeningRelay.history({ limit: 25 }),
    refetchInterval: pollMs,
  });

  const items = q.data?.items ?? [];

  return (
    <section className="rounded-lg border border-slate-600/80 bg-slate-950/30 p-4 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-sm font-medium text-slate-200">Recent relay posts</h3>
          <p className="text-xs text-slate-500 mt-0.5">
            Last.fm scrobbles, webhooks, and test sends — destination, copy, and fan-out metadata.
          </p>
        </div>
        <button
          type="button"
          className="text-xs px-2.5 py-1 rounded border border-slate-600 text-slate-400 hover:text-slate-200 hover:border-slate-500"
          onClick={() => void q.refetch()}
          disabled={q.isFetching}
        >
          {q.isFetching ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      {q.isError ? (
        <QueryErrorBanner
          title="Could not load relay history"
          message={String(q.error instanceof Error ? q.error.message : q.error ?? "Unknown error")}
          onRetry={() => void q.refetch()}
        />
      ) : null}

      {q.isLoading && !items.length ? (
        <p className="text-xs text-slate-500 py-4 text-center">Loading history…</p>
      ) : null}

      {!q.isLoading && !items.length ? (
        <p className="text-xs text-slate-500 py-6 text-center border border-dashed border-slate-700 rounded-lg">
          No relay posts logged yet. History fills in after the next Last.fm scrobble, webhook event, or test post.
        </p>
      ) : null}

      <div className="grid gap-2 max-h-[28rem] overflow-y-auto pr-1">
        {items.map((item) => (
          <RelayPostHistoryCard key={item.id} item={item} />
        ))}
      </div>
    </section>
  );
}
