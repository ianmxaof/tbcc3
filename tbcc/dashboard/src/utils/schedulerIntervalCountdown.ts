import { formatPtForDashboard, formatUtcForDashboard } from "./formatUtc";

export type SchedulerCountdownPhase =
  | "idle"
  | "running"
  | "stalled"
  | "paused"
  | "sent"
  | "pending_one_time";

export type SchedulerCountdownSnapshot = {
  phase: SchedulerCountdownPhase;
  /** Remaining ms until next fire (0 when stalled / paused / sent). */
  remainingMs: number;
  /** Wall-clock ms of next fire, if known. */
  nextRunMs: number | null;
  intervalMs: number;
  /** Recurring vs one-time scheduled_at. */
  mode: "recurring" | "one_time";
};

export type SchedulingStackHealth = {
  beatRunning: boolean;
  celeryPostRunning: boolean;
  schedulingPaused: boolean;
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

export function formatCountdownHms(ms: number): string {
  const totalSec = Math.max(0, Math.floor(ms / 1000));
  const h = Math.floor(totalSec / 3600);
  const m = Math.floor((totalSec % 3600) / 60);
  const s = totalSec % 60;
  return [h, m, s].map((n) => String(n).padStart(2, "0")).join(":");
}

/** Pacific wall clock HH:MM:SS (24h) for a given instant. */
export function formatPacificClock24FromMs(ms: number): string {
  return new Date(ms).toLocaleTimeString("en-US", {
    timeZone: "America/Los_Angeles",
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function computeSchedulerCountdown(params: {
  lastPostedAt?: unknown;
  intervalMinutes?: unknown;
  scheduledAt?: unknown;
  sentAt?: unknown;
  autoPausedAt?: unknown;
  nowMs: number;
}): SchedulerCountdownSnapshot | null {
  const { lastPostedAt, intervalMinutes, scheduledAt, sentAt, autoPausedAt, nowMs } = params;

  if (autoPausedAt) {
    const mins = Number(intervalMinutes);
    const intervalMs = Number.isFinite(mins) && mins > 0 ? mins * 60_000 : 0;
    const lastMs = parseBackendUtcMs(lastPostedAt);
    let remainingMs = 0;
    let nextRunMs: number | null = null;
    if (lastMs != null && intervalMs > 0) {
      nextRunMs = lastMs + intervalMs;
      remainingMs = Math.max(0, nextRunMs - nowMs);
    }
    return {
      phase: "paused",
      remainingMs,
      nextRunMs,
      intervalMs,
      mode: intervalMs > 0 ? "recurring" : "one_time",
    };
  }

  const mins = Number(intervalMinutes);
  const recurring = Number.isFinite(mins) && mins > 0;

  if (recurring) {
    const intervalMs = mins * 60_000;
    const lastMs = parseBackendUtcMs(lastPostedAt);
    if (lastMs == null) {
      return {
        phase: "idle",
        remainingMs: intervalMs,
        nextRunMs: null,
        intervalMs,
        mode: "recurring",
      };
    }
    const nextRunMs = lastMs + intervalMs;
    const remainingMs = nextRunMs - nowMs;
    if (remainingMs > 0) {
      return {
        phase: "running",
        remainingMs,
        nextRunMs,
        intervalMs,
        mode: "recurring",
      };
    }
    return {
      phase: "stalled",
      remainingMs: 0,
      nextRunMs,
      intervalMs,
      mode: "recurring",
    };
  }

  if (sentAt) {
    return {
      phase: "sent",
      remainingMs: 0,
      nextRunMs: null,
      intervalMs: 0,
      mode: "one_time",
    };
  }

  const schedMs = parseBackendUtcMs(scheduledAt);
  if (schedMs == null) return null;

  const remainingMs = schedMs - nowMs;
  if (remainingMs > 0) {
    return {
      phase: "pending_one_time",
      remainingMs,
      nextRunMs: schedMs,
      intervalMs: 0,
      mode: "one_time",
    };
  }
  return {
    phase: "stalled",
    remainingMs: 0,
    nextRunMs: schedMs,
    intervalMs: 0,
    mode: "one_time",
  };
}

export function schedulingStackHealthy(health?: SchedulingStackHealth | null): boolean {
  if (!health) return true;
  if (health.schedulingPaused) return false;
  return health.beatRunning && health.celeryPostRunning;
}

export function effectiveCountdownPhase(
  snapshot: SchedulerCountdownSnapshot,
  health?: SchedulingStackHealth | null
): SchedulerCountdownPhase {
  if (snapshot.phase === "paused" || snapshot.phase === "sent" || snapshot.phase === "idle") {
    return snapshot.phase;
  }
  if (!schedulingStackHealthy(health) && snapshot.mode === "recurring") {
    if (snapshot.phase === "running") return "stalled";
    if (snapshot.phase === "stalled") return "stalled";
  }
  return snapshot.phase;
}

const phaseTimerClass: Record<SchedulerCountdownPhase, string> = {
  idle: "text-amber-400",
  running: "text-emerald-400",
  stalled: "text-yellow-400",
  paused: "text-rose-400",
  sent: "text-slate-500",
  pending_one_time: "text-cyan-300",
};

const phaseStatusClass: Record<SchedulerCountdownPhase, string> = {
  idle: "text-amber-400/90",
  running: "text-emerald-400/90",
  stalled: "text-yellow-400/90",
  paused: "text-rose-400",
  sent: "text-emerald-400/90",
  pending_one_time: "text-cyan-300/90",
};

export function countdownTimerClass(phase: SchedulerCountdownPhase): string {
  return phaseTimerClass[phase] ?? "text-slate-400";
}

export function countdownStatusClass(phase: SchedulerCountdownPhase): string {
  return phaseStatusClass[phase] ?? "text-slate-400";
}

export function countdownStatusLabel(
  snapshot: SchedulerCountdownSnapshot,
  health?: SchedulingStackHealth | null
): { label: string; className: string; title: string } {
  const phase = effectiveCountdownPhase(snapshot, health);
  const cls = countdownStatusClass(phase);

  if (phase === "paused") {
    return { label: "Auto-paused", className: cls, title: "Too many send failures — beat will not enqueue until cleared." };
  }
  if (phase === "sent") {
    return { label: "Sent", className: cls, title: "One-time job already sent." };
  }
  if (phase === "idle") {
    return {
      label: "Post now",
      className: cls,
      title: "Recurring job — trigger Post now once to start the interval clock.",
    };
  }
  if (phase === "stalled") {
    if (!schedulingStackHealthy(health) && snapshot.mode === "recurring") {
      return {
        label: "Stalled",
        className: cls,
        title: "Interval overdue or TBCC-Beat / TBCC-Celery-Post is not running.",
      };
    }
    if (snapshot.mode === "one_time") {
      return { label: "Overdue", className: cls, title: "Scheduled time passed — not sent yet." };
    }
    const nextIso = snapshot.nextRunMs != null ? new Date(snapshot.nextRunMs).toISOString() : "";
    return {
      label: "Stalled",
      className: cls,
      title: nextIso
        ? `Past due — expected ${formatPtForDashboard(nextIso)} PT (${formatUtcForDashboard(nextIso)})`
        : "Past due — waiting for Beat to enqueue the next send.",
    };
  }
  if (phase === "pending_one_time") {
    return { label: "Scheduled", className: cls, title: "One-time post — countdown to scheduled time." };
  }
  return {
    label: "Running",
    className: cls,
    title: "Recurring — countdown active until next Beat enqueue.",
  };
}
