import {
  buildCronFromState,
  bumpHour,
  bumpInterval,
  bumpMinute,
  cronForUtcDate,
  defaultScheduleState,
  describeCron,
  HOUR_OPTIONS,
  MINUTE_OPTIONS,
  parseCronToState,
  utcDateMinutesFromNow,
  type ScheduleState,
} from "../utils/cronSchedule";

type Props = {
  cron: string;
  enabled: boolean;
  onCronChange: (cron: string) => void;
  onEnabledChange: (enabled: boolean) => void;
};

function Stepper({
  label,
  value,
  onDec,
  onInc,
}: {
  label: string;
  value: string;
  onDec: () => void;
  onInc: () => void;
}) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-slate-400 text-xs uppercase tracking-wide">{label}</span>
      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={onDec}
          className="h-9 w-9 rounded bg-slate-700 border border-slate-600 text-slate-200 hover:bg-slate-600 text-lg leading-none"
          aria-label={`Decrease ${label}`}
        >
          −
        </button>
        <span className="min-w-[4.5rem] text-center font-mono text-slate-100 py-2 px-2 bg-slate-900/50 rounded border border-slate-600">
          {value}
        </span>
        <button
          type="button"
          onClick={onInc}
          className="h-9 w-9 rounded bg-slate-700 border border-slate-600 text-slate-200 hover:bg-slate-600 text-lg leading-none"
          aria-label={`Increase ${label}`}
        >
          +
        </button>
      </div>
    </div>
  );
}

export function CronScheduleBuilder({ cron, enabled, onCronChange, onEnabledChange }: Props) {
  const state = parseCronToState(cron || buildCronFromState(defaultScheduleState()));

  const apply = (next: ScheduleState) => {
    onCronChange(buildCronFromState(next));
  };

  const setMode = (mode: ScheduleState["mode"]) => {
    apply({ ...state, mode });
  };

  return (
    <div className="space-y-3">
      <label className="flex items-center gap-2 text-slate-300">
        <input type="checkbox" checked={enabled} onChange={(e) => onEnabledChange(e.target.checked)} />
        Enable scheduled scrape (Celery Beat, UTC)
      </label>

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => setMode("daily")}
          className={`px-3 py-1.5 rounded text-sm border ${
            state.mode === "daily"
              ? "border-cyan-500 bg-cyan-900/40 text-cyan-200"
              : "border-slate-600 text-slate-400 hover:text-slate-200"
          }`}
        >
          Daily time
        </button>
        <button
          type="button"
          onClick={() => setMode("interval")}
          className={`px-3 py-1.5 rounded text-sm border ${
            state.mode === "interval"
              ? "border-cyan-500 bg-cyan-900/40 text-cyan-200"
              : "border-slate-600 text-slate-400 hover:text-slate-200"
          }`}
        >
          Every N minutes
        </button>
        <button
          type="button"
          onClick={() => {
            const d = utcDateMinutesFromNow(15);
            onCronChange(cronForUtcDate(d));
            onEnabledChange(true);
          }}
          className="px-3 py-1.5 rounded text-sm border border-amber-600/80 text-amber-200 hover:bg-amber-950/40"
          title="One-time style: cron for ~15 minutes from now (local clock converted to UTC)"
        >
          Run ~15 min from now
        </button>
      </div>

      {state.mode === "daily" ? (
        <div className="flex flex-wrap gap-4">
          <Stepper
            label="Hour (UTC)"
            value={String(state.hourUtc).padStart(2, "0")}
            onDec={() => apply({ ...state, hourUtc: bumpHour(state.hourUtc, -1) })}
            onInc={() => apply({ ...state, hourUtc: bumpHour(state.hourUtc, 1) })}
          />
          <Stepper
            label="Minute"
            value={String(state.minuteUtc).padStart(2, "0")}
            onDec={() => apply({ ...state, minuteUtc: bumpMinute(state.minuteUtc, -1) })}
            onInc={() => apply({ ...state, minuteUtc: bumpMinute(state.minuteUtc, 1) })}
          />
          <div className="flex flex-col gap-1 min-w-[120px]">
            <span className="text-slate-400 text-xs uppercase tracking-wide">Quick pick</span>
            <select
              value={`${state.hourUtc}:${state.minuteUtc}`}
              onChange={(e) => {
                const [h, m] = e.target.value.split(":").map(Number);
                apply({ ...state, hourUtc: h, minuteUtc: m });
              }}
              className="bg-slate-700 border border-slate-600 rounded px-2 py-2 text-slate-200 text-sm"
            >
              {HOUR_OPTIONS.flatMap((h) =>
                MINUTE_OPTIONS.map((m) => {
                  const v = `${h}:${m}`;
                  return (
                    <option key={v} value={v}>
                      {String(h).padStart(2, "0")}:{String(m).padStart(2, "0")} UTC
                    </option>
                  );
                })
              )}
            </select>
          </div>
        </div>
      ) : (
        <Stepper
          label="Interval (minutes)"
          value={String(state.intervalMinutes)}
          onDec={() => apply({ ...state, intervalMinutes: bumpInterval(state.intervalMinutes, -1) })}
          onInc={() => apply({ ...state, intervalMinutes: bumpInterval(state.intervalMinutes, 1) })}
        />
      )}

      <p className="text-slate-500 text-xs">
        {describeCron(cron)} · stored as <code className="text-slate-400">{cron || buildCronFromState(state)}</code>
      </p>
      <p className="text-slate-500 text-xs">
        Multi-channel: add one source per channel, each with its own schedule. Beat runs one scrape at a time in
        order.
      </p>
    </div>
  );
}
