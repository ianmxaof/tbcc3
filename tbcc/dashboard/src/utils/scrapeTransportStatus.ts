/** Scrape transport classification — mirrors schedulerPostStatus for Ingest. */

export type ScrapePhase = "running" | "queued" | "stalled" | "error" | "paused" | "idle" | "skipped";

export type ScrapeTransportCounts = {
  total: number;
  running: number;
  queued: number;
  stalled: number;
  error: number;
  paused: number;
  idle: number;
  autonomous: number;
};

export type ScrapeTransportSource = {
  source_id: number;
  name?: string;
  identifier?: string;
  telegram_url?: string | null;
  pool_id?: number;
  pool_name?: string;
  active?: boolean;
  schedule_enabled?: boolean;
  schedule_cron?: string | null;
  media_types?: string;
  max_messages_per_run?: number;
  last_scraped_at?: string | null;
  phase?: ScrapePhase | string;
  latest_run?: Record<string, unknown> | null;
  participants_count?: number | null;
  avg_views_sample?: number | null;
  max_views_sample?: number | null;
  views_sampled?: number | null;
  posts_per_day?: number | null;
  posts_per_week?: number | null;
  tags_sample?: string | null;
  suggested_pool_keys?: string | null;
  folder_label?: string | null;
};

export type ScrapeColId =
  | "name"
  | "channel"
  | "pool"
  | "views"
  | "members"
  | "ppd"
  | "ppw"
  | "progress"
  | "status"
  | "schedule";

export const SCRAPE_COL_DEFS: { id: ScrapeColId; label: string; defaultOn: boolean }[] = [
  { id: "name", label: "Name", defaultOn: true },
  { id: "channel", label: "Channel", defaultOn: true },
  { id: "pool", label: "Pool", defaultOn: true },
  { id: "views", label: "Views", defaultOn: true },
  { id: "members", label: "Members", defaultOn: true },
  { id: "ppd", label: "Posts/day", defaultOn: true },
  { id: "ppw", label: "Posts/week", defaultOn: false },
  { id: "progress", label: "Progress", defaultOn: true },
  { id: "status", label: "Status", defaultOn: true },
  { id: "schedule", label: "Schedule", defaultOn: true },
];

const COL_PREF_KEY = "tbcc:scrapeTransportCols";

export function loadScrapeColPrefs(): Record<ScrapeColId, boolean> {
  const base = Object.fromEntries(SCRAPE_COL_DEFS.map((c) => [c.id, c.defaultOn])) as Record<
    ScrapeColId,
    boolean
  >;
  try {
    const raw = localStorage.getItem(COL_PREF_KEY);
    if (!raw) return base;
    const parsed = JSON.parse(raw) as Record<string, boolean>;
    for (const c of SCRAPE_COL_DEFS) {
      if (typeof parsed[c.id] === "boolean") base[c.id] = parsed[c.id];
    }
  } catch {
    /* ignore */
  }
  return base;
}

export function saveScrapeColPrefs(prefs: Record<ScrapeColId, boolean>) {
  try {
    localStorage.setItem(COL_PREF_KEY, JSON.stringify(prefs));
  } catch {
    /* ignore */
  }
}

export type ScrapeSortKey = ScrapeColId | "source_id";
export type ScrapeSortDir = "asc" | "desc";

export function formatViewers(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(Number(n))) return "—";
  const v = Number(n);
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `${(v / 1_000).toFixed(1)}k`;
  return String(Math.round(v));
}

export function channelHref(row: { telegram_url?: string | null; identifier?: string }): string | null {
  if (row.telegram_url) return row.telegram_url;
  const id = (row.identifier || "").trim();
  if (!id) return null;
  if (id.startsWith("http://") || id.startsWith("https://")) return id;
  if (id.startsWith("t.me/")) return `https://${id}`;
  if (id.startsWith("@")) return `https://t.me/${id.slice(1)}`;
  if (id.startsWith("+") || id.includes("joinchat")) return `https://t.me/${id.replace(/^\/+/, "")}`;
  if (/^-?\d+$/.test(id)) return null;
  return `https://t.me/${id}`;
}

export type ScrapeStatusFilter = "all" | ScrapePhase;

export function scrapePhaseStyle(phase: string | undefined): { chip: string; dot: string; label: string } {
  switch (phase) {
    case "running":
      return { chip: "text-emerald-300 bg-emerald-950/40 border-emerald-700/50", dot: "bg-emerald-400", label: "Running" };
    case "queued":
      return { chip: "text-cyan-300 bg-cyan-950/40 border-cyan-700/50", dot: "bg-cyan-400", label: "Queued" };
    case "stalled":
      return { chip: "text-yellow-300 bg-yellow-950/40 border-yellow-700/50", dot: "bg-yellow-400", label: "Stalled" };
    case "error":
      return { chip: "text-rose-300 bg-rose-950/40 border-rose-700/50", dot: "bg-rose-500", label: "Error" };
    case "paused":
      return { chip: "text-slate-300 bg-slate-800/60 border-slate-600/60", dot: "bg-slate-400", label: "Paused" };
    case "skipped":
      return { chip: "text-amber-300 bg-amber-950/30 border-amber-700/40", dot: "bg-amber-400", label: "Skipped" };
    default:
      return { chip: "text-slate-400 bg-slate-900/40 border-slate-700/50", dot: "bg-slate-500", label: "Idle" };
  }
}

export function filterScrapeSources(
  sources: ScrapeTransportSource[],
  filter: ScrapeStatusFilter
): ScrapeTransportSource[] {
  if (filter === "all") return sources;
  return sources.filter((s) => (s.phase || "idle") === filter);
}

export function runProgressLabel(run: Record<string, unknown> | null | undefined): string {
  if (!run) return "";
  const scanned = run.messages_scanned != null ? Number(run.messages_scanned) : null;
  const stored = run.stored != null ? Number(run.stored) : null;
  const err = run.error_summary != null ? String(run.error_summary) : "";
  const parts: string[] = [];
  if (scanned != null) parts.push(`${scanned} msgs`);
  if (stored != null) parts.push(`${stored} new`);
  if (err) parts.push(err.slice(0, 80));
  return parts.join(" · ");
}

/** 0–100 progress from latest run vs max_messages_per_run. */
export function runProgressPct(row: ScrapeTransportSource): number | null {
  const run = row.latest_run;
  if (!run) return null;
  const status = run.status != null ? String(run.status) : "";
  const scanned = run.messages_scanned != null ? Number(run.messages_scanned) : 0;
  const limit = Math.max(1, Number(row.max_messages_per_run || 50));
  if (status === "done") return 100;
  if (status === "failed" || status === "cancelled" || status === "skipped") {
    return Math.min(100, Math.round((scanned / limit) * 100));
  }
  if (status === "queued") return 0;
  if (status === "running") return Math.min(99, Math.round((scanned / limit) * 100));
  return null;
}

export function sortScrapeSources(
  sources: ScrapeTransportSource[],
  key: ScrapeSortKey,
  dir: ScrapeSortDir
): ScrapeTransportSource[] {
  const mul = dir === "asc" ? 1 : -1;
  const val = (r: ScrapeTransportSource): string | number => {
    switch (key) {
      case "name":
        return (r.name || "").toLowerCase();
      case "channel":
        return (r.identifier || "").toLowerCase();
      case "pool":
        return (r.pool_name || r.folder_label || "").toLowerCase();
      case "views":
        return Number(r.avg_views_sample ?? -1);
      case "members":
        return Number(r.participants_count ?? -1);
      case "ppd":
        return Number(r.posts_per_day ?? -1);
      case "ppw":
        return Number(r.posts_per_week ?? (r.posts_per_day != null ? Number(r.posts_per_day) * 7 : -1));
      case "progress":
        return runProgressPct(r) ?? -1;
      case "status":
        return (r.phase || "idle").toLowerCase();
      case "schedule":
        return r.schedule_enabled ? 1 : 0;
      default:
        return r.source_id;
    }
  };
  return [...sources].sort((a, b) => {
    const av = val(a);
    const bv = val(b);
    if (typeof av === "number" && typeof bv === "number") return (av - bv) * mul;
    return String(av).localeCompare(String(bv)) * mul;
  });
}
