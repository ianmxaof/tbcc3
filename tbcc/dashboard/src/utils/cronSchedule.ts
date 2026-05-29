/** Visual schedule builder -> 5-field cron (UTC; matches Celery Beat). */

export type ScheduleMode = "daily" | "interval";

export type ScheduleState = {
  mode: ScheduleMode;
  /** 0-23 UTC */
  hourUtc: number;
  /** 0, 15, 30, 45 */
  minuteUtc: number;
  /** 5-60, step 5 */
  intervalMinutes: number;
};

export const MINUTE_OPTIONS = [0, 15, 30, 45] as const;
export const HOUR_OPTIONS = Array.from({ length: 24 }, (_, i) => i);
export const INTERVAL_OPTIONS = [5, 10, 15, 20, 30, 45, 60];

export function defaultScheduleState(): ScheduleState {
  return { mode: "daily", hourUtc: 6, minuteUtc: 0, intervalMinutes: 15 };
}

export function buildCronFromState(s: ScheduleState): string {
  if (s.mode === "interval") {
    const n = Math.min(60, Math.max(5, s.intervalMinutes));
    if (n >= 60) return "0 * * * *";
    if (60 % n === 0) return `*/${n} * * * *`;
    return `*/${n} * * * *`;
  }
  const m = MINUTE_OPTIONS.includes(s.minuteUtc as (typeof MINUTE_OPTIONS)[number])
    ? s.minuteUtc
    : 0;
  const h = Math.min(23, Math.max(0, s.hourUtc));
  return `${m} ${h} * * *`;
}

export function parseCronToState(cron: string | null | undefined): ScheduleState {
  const base = defaultScheduleState();
  const raw = (cron || "").trim();
  if (!raw) return base;
  const parts = raw.split(/\s+/);
  if (parts.length !== 5) return base;
  const [min, hour, dom, mon, dow] = parts;
  if (min.startsWith("*/") && hour === "*" && dom === "*" && mon === "*" && dow === "*") {
    const n = parseInt(min.slice(2), 10);
    if (Number.isFinite(n) && n > 0) {
      return { mode: "interval", hourUtc: 6, minuteUtc: 0, intervalMinutes: n };
    }
  }
  if (dom === "*" && mon === "*" && dow === "*" && /^\d+$/.test(min) && /^\d+$/.test(hour)) {
    return {
      mode: "daily",
      hourUtc: Math.min(23, parseInt(hour, 10)),
      minuteUtc: MINUTE_OPTIONS.includes(parseInt(min, 10) as (typeof MINUTE_OPTIONS)[number])
        ? (parseInt(min, 10) as (typeof MINUTE_OPTIONS)[number])
        : 0,
      intervalMinutes: 15,
    };
  }
  return base;
}

export function describeCron(cron: string | null | undefined): string {
  const s = parseCronToState(cron);
  if (s.mode === "interval") {
    return s.intervalMinutes >= 60 ? "Every hour (UTC)" : `Every ${s.intervalMinutes} minutes (UTC)`;
  }
  const mm = String(s.minuteUtc).padStart(2, "0");
  const hh = String(s.hourUtc).padStart(2, "0");
  return `Daily at ${hh}:${mm} UTC`;
}

/** One-shot cron for "run at this UTC minute/hour today or tomorrow". */
export function cronForUtcDate(d: Date): string {
  return `${d.getUTCMinutes()} ${d.getUTCHours()} ${d.getUTCDate()} ${d.getUTCMonth() + 1} *`;
}

export function utcDateMinutesFromNow(minutes: number): Date {
  return new Date(Date.now() + minutes * 60_000);
}

export function bumpMinute(current: number, delta: number): number {
  const idx = MINUTE_OPTIONS.indexOf(current as (typeof MINUTE_OPTIONS)[number]);
  const base = idx >= 0 ? idx : 0;
  const next = (base + delta + MINUTE_OPTIONS.length) % MINUTE_OPTIONS.length;
  return MINUTE_OPTIONS[next];
}

export function bumpHour(current: number, delta: number): number {
  return (current + delta + 24) % 24;
}

export function bumpInterval(current: number, delta: number): number {
  const idx = INTERVAL_OPTIONS.indexOf(current);
  const base = idx >= 0 ? idx : INTERVAL_OPTIONS.indexOf(15);
  const next = (base + delta + INTERVAL_OPTIONS.length) % INTERVAL_OPTIONS.length;
  return INTERVAL_OPTIONS[next];
}
