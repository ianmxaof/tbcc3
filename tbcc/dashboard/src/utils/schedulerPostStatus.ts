import {
  computeSchedulerCountdown,
  effectiveCountdownPhase,
  formatCountdownHms,
  schedulingStackHealthy,
  schedulingWorkersHealthy,
  type SchedulingStackHealth,
  type SchedulerCountdownPhase,
} from "./schedulerIntervalCountdown";

export type SchedulerPostRecord = Record<string, unknown>;

export type SchedulerGroupId =
  | "main_lane"
  | "bot_commands"
  | "liveness"
  | "promo_bulletin"
  | "manual";

export type SchedulerStatusFilter = "all" | "stalled" | "auto_paused" | "idle";

export type SchedulerListMode = "lean" | "details";

export const SCHEDULER_GROUP_LABELS: Record<SchedulerGroupId, string> = {
  main_lane: "Main channels",
  bot_commands: "Bot commands",
  liveness: "Network liveness",
  promo_bulletin: "Promos & bulletins",
  manual: "Manual & other",
};

export const SCHEDULER_GROUP_DEFAULT_EXPANDED: Record<SchedulerGroupId, boolean> = {
  main_lane: true,
  bot_commands: false,
  liveness: false,
  promo_bulletin: false,
  manual: false,
};

export const SCHEDULER_GROUP_ORDER: SchedulerGroupId[] = [
  "main_lane",
  "bot_commands",
  "liveness",
  "promo_bulletin",
  "manual",
];

export type ClassifiedSchedulerPost = {
  post: SchedulerPostRecord;
  phase: SchedulerCountdownPhase;
  stalledSinceMs: number | null;
  pausedSinceMs: number | null;
  errorText: string | null;
  group: SchedulerGroupId;
};

export type TransportStats = {
  total: number;
  onTrack: number;
  idle: number;
  stalled: number;
  autoPaused: number;
  focusPaused: number;
  healthyPrimary: number;
};

function parseBackendUtcMs(value: unknown): number | null {
  if (value == null || value === "") return null;
  const raw = String(value).trim();
  const d = /[zZ]|[+-]\d{2}:?\d{2}$/.test(raw)
    ? new Date(raw)
    : new Date(raw.includes("T") ? `${raw}Z` : `${raw.replace(" ", "T")}Z`);
  const ms = d.getTime();
  return Number.isNaN(ms) ? null : ms;
}

export function formatDurationHms(ms: number): string {
  return formatCountdownHms(ms);
}

export function isRecurringActive(post: SchedulerPostRecord): boolean {
  const mins = Number(post.interval_minutes);
  return Number.isFinite(mins) && mins > 0;
}

export function isSentOneShot(post: SchedulerPostRecord): boolean {
  const mins = Number(post.interval_minutes);
  const recurring = Number.isFinite(mins) && mins > 0;
  return !recurring && Boolean(post.sent_at);
}

export function inferSchedulerGroup(name: unknown, category?: unknown): SchedulerGroupId {
  const cat = String(category || "").trim().toLowerCase();
  if (cat === "main_lane") return "main_lane";
  if (cat === "bot_commands") return "bot_commands";
  if (cat === "liveness") return "liveness";
  if (cat === "promo_bulletin") return "promo_bulletin";
  if (cat === "manual") return "manual";

  const n = String(name || "").toLowerCase();
  if (n.includes("bot commands")) return "bot_commands";
  if (n.includes("network liveness") || n.includes("drop ticker") || n.includes("spotlight")) {
    return "liveness";
  }
  if (
    n.includes("packs") ||
    n.includes("links hub") ||
    n.includes("cross-channel") ||
    n.includes("celebration") ||
    n.includes("bulletin") ||
    n.includes("drop live") ||
    n.includes("feed rhythm")
  ) {
    return "promo_bulletin";
  }
  if (n.endsWith(" scheduler") || n.includes("main group")) return "main_lane";
  return "manual";
}

export function classifySchedulerPost(
  post: SchedulerPostRecord,
  health: SchedulingStackHealth | null | undefined,
  nowMs: number
): ClassifiedSchedulerPost {
  const snapshot = computeSchedulerCountdown({
    lastPostedAt: post.last_posted_at,
    intervalMinutes: post.interval_minutes,
    scheduledAt: post.scheduled_at,
    sentAt: post.sent_at,
    autoPausedAt: post.posting_auto_paused_at,
    nowMs,
  });
  const phase = snapshot
    ? effectiveCountdownPhase(snapshot, health)
    : ("idle" as SchedulerCountdownPhase);

  let stalledSinceMs: number | null = null;
  if (phase === "stalled" && snapshot?.nextRunMs != null) {
    stalledSinceMs = Math.max(0, nowMs - snapshot.nextRunMs);
  }

  let pausedSinceMs: number | null = null;
  const pausedAt = parseBackendUtcMs(post.posting_auto_paused_at);
  if (phase === "paused" && pausedAt != null) {
    pausedSinceMs = Math.max(0, nowMs - pausedAt);
  }

  const pauseReason = post.posting_auto_pause_reason ? String(post.posting_auto_pause_reason) : null;
  let errorText = pauseReason;
  if (!errorText && phase === "focus_paused") {
    errorText = "Focus profile paused Beat scheduling — not a send failure. Ends when focus restores.";
  }
  if (!errorText && phase === "stalled" && !schedulingWorkersHealthy(health)) {
    errorText = "TBCC-Beat or TBCC-Celery-Post is not running.";
  }

  return {
    post,
    phase,
    stalledSinceMs,
    pausedSinceMs,
    errorText,
    group: inferSchedulerGroup(post.name, post.scheduler_category),
  };
}

export function computeTransportStats(
  posts: SchedulerPostRecord[],
  health: SchedulingStackHealth | null | undefined,
  nowMs: number
): TransportStats {
  const recurring = posts.filter(isRecurringActive);
  let onTrack = 0;
  let idle = 0;
  let stalled = 0;
  let autoPaused = 0;
  let focusPaused = 0;

  for (const post of recurring) {
    const { phase } = classifySchedulerPost(post, health, nowMs);
    if (phase === "running") onTrack += 1;
    else if (phase === "idle") idle += 1;
    else if (phase === "stalled") stalled += 1;
    else if (phase === "paused") autoPaused += 1;
    else if (phase === "focus_paused") focusPaused += 1;
  }

  const total = recurring.length;
  const healthyPrimary = onTrack + idle + focusPaused;
  return { total, onTrack, idle, stalled, autoPaused, focusPaused, healthyPrimary };
}

export function matchesStatusFilter(
  classified: ClassifiedSchedulerPost,
  filter: SchedulerStatusFilter
): boolean {
  if (filter === "all") return true;
  if (filter === "stalled") return classified.phase === "stalled";
  if (filter === "auto_paused") return classified.phase === "paused";
  if (filter === "idle") return classified.phase === "idle";
  return true;
}

export function shouldUseFastSchedulerPoll(stats: TransportStats, health?: SchedulingStackHealth | null): boolean {
  if (stats.stalled + stats.autoPaused > 0) return true;
  return !schedulingStackHealthy(health);
}

export const LIST_MODE_STORAGE_KEY = "tbcc.scheduler.listMode";
export const HIDE_SENT_STORAGE_KEY = "tbcc.scheduler.hideSentOneShots";

export function readSchedulerListMode(): SchedulerListMode {
  try {
    const v = localStorage.getItem(LIST_MODE_STORAGE_KEY);
    return v === "details" ? "details" : "lean";
  } catch {
    return "lean";
  }
}

export function readHideSentOneShots(mode: SchedulerListMode): boolean {
  try {
    const stored = localStorage.getItem(HIDE_SENT_STORAGE_KEY);
    if (stored === "0") return false;
    if (stored === "1") return true;
  } catch {
    /* ignore */
  }
  return mode === "lean";
}
