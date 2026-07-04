import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";

export type ScrapeRunRow = {
  id: number;
  run_kind?: string;
  source_id?: number;
  source_name?: string;
  pool_id?: number;
  trigger?: string;
  status?: string;
  messages_scanned?: number;
  stored?: number;
  skipped_duplicate?: number;
  skipped_media_type?: number;
  skipped_no_media?: number;
  errors_count?: number;
  error_summary?: string | null;
  fix_hint?: string | null;
  media_library_url?: string;
  started_at?: string | null;
  finished_at?: string | null;
  created_at?: string | null;
};

const DISMISS_KEY = "tbcc:dismissedScrapeRuns";
const FINISHED_TTL_MS = 20 * 60 * 1000;

function readDismissed(): Set<number> {
  try {
    const raw = localStorage.getItem(DISMISS_KEY);
    if (!raw) return new Set();
    const arr = JSON.parse(raw) as unknown;
    if (!Array.isArray(arr)) return new Set();
    return new Set(arr.map((x) => Number(x)).filter((n) => Number.isFinite(n)));
  } catch {
    return new Set();
  }
}

function writeDismissed(ids: Set<number>) {
  try {
    localStorage.setItem(DISMISS_KEY, JSON.stringify([...ids].slice(-80)));
  } catch {
    /* ignore */
  }
}

function parseRun(raw: Record<string, unknown>): ScrapeRunRow {
  return {
    id: Number(raw.id),
    run_kind: raw.run_kind != null ? String(raw.run_kind) : undefined,
    source_id: raw.source_id != null ? Number(raw.source_id) : undefined,
    source_name: raw.source_name != null ? String(raw.source_name) : undefined,
    pool_id: raw.pool_id != null ? Number(raw.pool_id) : undefined,
    trigger: raw.trigger != null ? String(raw.trigger) : undefined,
    status: raw.status != null ? String(raw.status) : undefined,
    messages_scanned: raw.messages_scanned != null ? Number(raw.messages_scanned) : undefined,
    stored: raw.stored != null ? Number(raw.stored) : undefined,
    skipped_duplicate: raw.skipped_duplicate != null ? Number(raw.skipped_duplicate) : undefined,
    skipped_media_type: raw.skipped_media_type != null ? Number(raw.skipped_media_type) : undefined,
    skipped_no_media: raw.skipped_no_media != null ? Number(raw.skipped_no_media) : undefined,
    errors_count: raw.errors_count != null ? Number(raw.errors_count) : undefined,
    error_summary: raw.error_summary != null ? String(raw.error_summary) : null,
    fix_hint: raw.fix_hint != null ? String(raw.fix_hint) : null,
    media_library_url: raw.media_library_url != null ? String(raw.media_library_url) : undefined,
    started_at: raw.started_at != null ? String(raw.started_at) : null,
    finished_at: raw.finished_at != null ? String(raw.finished_at) : null,
    created_at: raw.created_at != null ? String(raw.created_at) : null,
  };
}

function isActive(status: string | undefined) {
  return status === "queued" || status === "running";
}

function isFinished(status: string | undefined) {
  return status === "done" || status === "failed" || status === "skipped";
}

function runEndedAt(run: ScrapeRunRow): number {
  const raw = run.finished_at || run.created_at;
  if (!raw) return 0;
  const t = new Date(raw).getTime();
  return Number.isFinite(t) ? t : 0;
}

function isRecentFinished(run: ScrapeRunRow): boolean {
  const ended = runEndedAt(run);
  if (!ended) return true;
  return Date.now() - ended < FINISHED_TTL_MS;
}

function mediaLink(run: ScrapeRunRow): string {
  if (run.media_library_url) return run.media_library_url;
  const pool = run.pool_id && run.pool_id > 0 ? run.pool_id : 1;
  return `/?status=pending&pool_id=${pool}`;
}

function runSummary(run: ScrapeRunRow): string {
  const isLink = run.run_kind === "link" || (run.source_name || "").startsWith("LINK:");
  const parts: string[] = [];
  if (run.messages_scanned != null) parts.push(`${run.messages_scanned} msgs`);
  if (isLink) {
    if (run.stored != null && run.stored > 0) parts.push(`${run.stored} modifiers`);
    if (run.skipped_no_media != null && run.skipped_no_media > 0) parts.push(`${run.skipped_no_media} failed`);
  } else {
    if (run.stored != null && run.stored > 0) parts.push(`${run.stored} new`);
    if (run.skipped_duplicate != null && run.skipped_duplicate > 0) parts.push(`${run.skipped_duplicate} dupes`);
    if (run.skipped_media_type != null && run.skipped_media_type > 0) parts.push(`${run.skipped_media_type} type skip`);
  }
  return parts.join(" · ") || "No stats yet";
}

export function ScrapeRunBanner() {
  const [dismissed, setDismissed] = useState<Set<number>>(() => readDismissed());

  const { data: runsRaw = [] } = useQuery({
    queryKey: ["scrape-runs-latest"],
    queryFn: () => api.sources.listScrapeRuns(8),
    refetchInterval: (query) => {
      const rows = (query.state.data as Array<Record<string, unknown>> | undefined) ?? [];
      const active = rows.some((r) => isActive(String(r.status ?? "")));
      return active ? 2500 : 12000;
    },
    refetchIntervalInBackground: true,
  });

  const runs = useMemo(() => runsRaw.map((r) => parseRun(r)), [runsRaw]);

  const dismiss = useCallback((runId: number) => {
    setDismissed((prev) => {
      const next = new Set(prev);
      next.add(runId);
      writeDismissed(next);
      return next;
    });
  }, []);

  useEffect(() => {
    writeDismissed(dismissed);
  }, [dismissed]);

  const activeRun = runs.find((r) => isActive(r.status) && !dismissed.has(r.id));
  const finishedRun = runs.find(
    (r) => isFinished(r.status) && !dismissed.has(r.id) && isRecentFinished(r)
  );

  if (!activeRun && !finishedRun) return null;

  const isLinkRun =
    activeRun?.run_kind === "link" ||
    finishedRun?.run_kind === "link" ||
    (finishedRun?.source_name || activeRun?.source_name || "").startsWith("LINK:");

  if (activeRun) {
    const label = activeRun.source_name || `Source ${activeRun.source_id ?? "?"}`;
    return (
      <div className="bg-cyan-950/80 border-b border-cyan-700 px-4 py-2 text-sm text-cyan-100" role="status">
        <div className="flex flex-wrap items-center gap-3">
          <span>
            <strong className="font-medium">{isLinkRun ? "Link scrape in progress" : "Scrape in progress"}</strong> —{" "}
            {label}
            {activeRun.trigger ? ` (${activeRun.trigger})` : ""}
          </span>
          <button
            type="button"
            className="text-xs underline opacity-80 hover:opacity-100 ml-auto"
            onClick={() => dismiss(activeRun.id)}
          >
            Hide
          </button>
        </div>
      </div>
    );
  }

  if (!finishedRun) return null;

  const label = finishedRun.source_name || `Source ${finishedRun.source_id ?? "?"}`;
  const success = finishedRun.status === "done" && !finishedRun.error_summary;
  const skipped = finishedRun.status === "skipped";
  const failed = finishedRun.status === "failed" || Boolean(finishedRun.error_summary);

  return (
    <div
      className={
        success
          ? "bg-emerald-950/85 border-b border-emerald-700 px-4 py-2 text-sm text-emerald-100"
          : skipped
            ? "bg-amber-950/85 border-b border-amber-700 px-4 py-2 text-sm text-amber-100"
            : "bg-red-950/85 border-b border-red-700 px-4 py-2 text-sm text-red-100"
      }
      role="status"
    >
      <div className="flex flex-wrap items-start gap-3">
        <div className="flex-1 min-w-[200px]">
          <strong className="font-medium">
            {success
              ? isLinkRun
                ? "Link scrape finished"
                : "Scrape finished"
              : skipped
                ? "Scrape skipped"
                : "Scrape failed"}{" "}
            — {label}
          </strong>
          <p className="mt-1 opacity-95">{runSummary(finishedRun)}</p>
          {failed && finishedRun.error_summary ? (
            <p className="mt-1 opacity-95">{finishedRun.error_summary}</p>
          ) : null}
          {finishedRun.fix_hint ? (
            <p className="mt-1 text-xs opacity-85">
              <strong>Fix:</strong> {finishedRun.fix_hint}
            </p>
          ) : null}
          {success && (finishedRun.stored ?? 0) > 0 ? (
            <p className="mt-2">
              <Link to={mediaLink(finishedRun)} className="underline font-medium hover:opacity-90">
                {isLinkRun
                  ? "Open Loot modifiers"
                  : `Open Media → pending (pool ${finishedRun.pool_id ?? 1})`}
              </Link>
            </p>
          ) : null}
          {success && (finishedRun.stored ?? 0) === 0 ? (
            <p className="mt-1 text-xs opacity-85">
              {isLinkRun
                ? "No new modifiers — dead links, duplicates, or nothing matching direct/paste filter."
                : "No new media — duplicates or nothing matching your media filter."}
            </p>
          ) : null}
        </div>
        <button
          type="button"
          className="text-xs underline opacity-80 hover:opacity-100 shrink-0"
          onClick={() => dismiss(finishedRun.id)}
        >
          Dismiss
        </button>
      </div>
    </div>
  );
}
