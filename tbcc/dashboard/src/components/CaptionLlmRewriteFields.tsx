type Props = {
  enabled: boolean;
  onEnabledChange: (v: boolean) => void;
  mode: "" | "random" | "interval";
  onModeChange: (v: "" | "random" | "interval") => void;
  interval: number;
  onIntervalChange: (v: number) => void;
  probability: number;
  onProbabilityChange: (v: number) => void;
  sendCount?: number;
  disabled?: boolean;
};

export function CaptionLlmRewriteFields({
  enabled,
  onEnabledChange,
  mode,
  onModeChange,
  interval,
  onIntervalChange,
  probability,
  onProbabilityChange,
  sendCount,
  disabled,
}: Props) {
  return (
    <div className="rounded border border-violet-800/40 bg-violet-950/20 p-3 space-y-3">
      <label className="flex items-start gap-2 text-sm text-slate-300 cursor-pointer">
        <input
          type="checkbox"
          className="mt-0.5"
          checked={enabled}
          disabled={disabled}
          onChange={(e) => onEnabledChange(e.target.checked)}
        />
        <span>
          <strong className="text-violet-300">LLM rewrite captions</strong>
          <span className="block text-xs text-slate-500 mt-0.5">
            Requires <code className="text-slate-400">TBCC_CAPTION_LLM_REWRITE_ENABLED=1</code> and{" "}
            <code className="text-slate-400">TBCC_OPENAI_API_KEY</code>. Keeps all links; rephrases wording. Next
            sends use normal rotating captions unless this send hits random/interval.
          </span>
        </span>
      </label>
      {enabled ? (
        <>
          <div className="flex flex-wrap gap-3 items-end">
            <label className="text-xs text-slate-400">
              Mode
              <select
                value={mode}
                disabled={disabled}
                onChange={(e) => onModeChange(e.target.value as "" | "random" | "interval")}
                className="block mt-1 bg-slate-800 border border-slate-600 rounded px-2 py-1.5 text-slate-200 text-sm"
              >
                <option value="interval">Every N posts</option>
                <option value="random">Random chance</option>
              </select>
            </label>
            {mode === "interval" ? (
              <label className="text-xs text-slate-400">
                Rewrite every N sends
                <input
                  type="number"
                  min={1}
                  max={100}
                  value={interval}
                  disabled={disabled}
                  onChange={(e) => onIntervalChange(Math.max(1, Number(e.target.value) || 1))}
                  className="block mt-1 w-20 bg-slate-800 border border-slate-600 rounded px-2 py-1.5 text-slate-200 text-sm"
                />
              </label>
            ) : null}
            {mode === "random" ? (
              <label className="text-xs text-slate-400">
                Probability (0–1)
                <input
                  type="number"
                  min={0}
                  max={1}
                  step={0.05}
                  value={probability}
                  disabled={disabled}
                  onChange={(e) =>
                    onProbabilityChange(Math.max(0, Math.min(1, Number(e.target.value) || 0)))
                  }
                  className="block mt-1 w-24 bg-slate-800 border border-slate-600 rounded px-2 py-1.5 text-slate-200 text-sm"
                />
              </label>
            ) : null}
          </div>
          {sendCount != null ? (
            <p className="text-xs text-slate-500">Successful sends so far (interval counter): {sendCount}</p>
          ) : null}
        </>
      ) : null}
    </div>
  );
}
