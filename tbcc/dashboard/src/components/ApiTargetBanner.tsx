import { useApiTarget } from "../context/ApiTargetContext";

/** Persistent strip so operators always know which backend the dashboard is reading. */
export function ApiTargetBanner() {
  const { target, meta, canSwitch } = useApiTarget();

  const isIsland = target === "island";
  const border = isIsland ? "rgba(34, 211, 238, 0.45)" : "rgba(251, 191, 36, 0.45)";
  const bg = isIsland ? "rgba(8, 47, 73, 0.55)" : "rgba(69, 26, 3, 0.45)";

  return (
    <div
      className="border-b px-4 py-1.5 text-xs text-slate-200 flex flex-wrap items-center gap-x-3 gap-y-1"
      style={{ borderBottomColor: border, backgroundColor: bg }}
      role="status"
    >
      <span className="font-medium">
        API target: <span className="font-mono text-cyan-200">{meta.shortLabel}</span>
      </span>
      <span className="opacity-85">{meta.hint}</span>
      {!canSwitch ? (
        <span className="opacity-60">(fixed at build via VITE_API_BASE)</span>
      ) : !isIsland ? (
        <span className="text-amber-200/90">Switch to Island in the header for live production data.</span>
      ) : null}
    </div>
  );
}
