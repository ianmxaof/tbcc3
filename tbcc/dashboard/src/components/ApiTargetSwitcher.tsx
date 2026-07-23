import { API_TARGET_META, type ApiTarget } from "../apiConfig";
import { useApiTarget } from "../context/ApiTargetContext";

const ORDER: ApiTarget[] = ["island", "local"];

export function ApiTargetSwitcher() {
  const { target, setTarget, canSwitch } = useApiTarget();

  if (!canSwitch) return null;

  return (
    <div
      className="inline-flex items-center rounded-md border border-slate-600/80 bg-slate-900/60 p-0.5 text-xs"
      role="group"
      aria-label="TBCC API target"
    >
      {ORDER.map((id) => {
        const active = target === id;
        const meta = API_TARGET_META[id];
        return (
          <button
            key={id}
            type="button"
            title={meta.hint}
            aria-pressed={active}
            onClick={() => setTarget(id)}
            className={[
              "rounded px-2 py-1 font-medium transition-colors",
              active
                ? id === "island"
                  ? "bg-cyan-800/90 text-cyan-50"
                  : "bg-amber-900/80 text-amber-50"
                : "text-slate-400 hover:text-slate-200 hover:bg-white/5",
            ].join(" ")}
          >
            {meta.shortLabel}
          </button>
        );
      })}
    </div>
  );
}
