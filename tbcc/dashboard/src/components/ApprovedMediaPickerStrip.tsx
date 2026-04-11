import { api } from "../api";

type Row = Record<string, unknown>;

/**
 * Horizontal scroller of approved media — avoids a tall wrapping grid of many items.
 * Shows #id when the thumbnail URL fails (common for some media types).
 */
export function ApprovedMediaPickerStrip({
  rows,
  selectedIds,
  onToggle,
  rowKeyPrefix,
}: {
  rows: Row[];
  selectedIds: number[];
  onToggle: (mediaId: number) => void;
  rowKeyPrefix: string;
}) {
  const n = rows.length;
  return (
    <div className="min-w-0">
      <div className="mb-1 flex flex-wrap items-center justify-between gap-x-2 gap-y-0">
        <span className="text-slate-500 text-xs">Approved media ({n})</span>
        {n > 6 ? (
          <span className="text-[10px] text-slate-600">Scroll sideways for more</span>
        ) : null}
      </div>
      <div
        className="flex max-w-full min-h-[2.75rem] flex-nowrap gap-1.5 overflow-x-auto pb-1 scroll-smooth"
        style={{ scrollbarWidth: "thin" }}
      >
        {rows.map((m) => {
          const mid = Number(m.id);
          const sel = selectedIds.includes(mid);
          const mt = String(m.media_type || "");
          return (
            <button
              key={`${rowKeyPrefix}-${mid}`}
              type="button"
              onClick={() => onToggle(mid)}
              className={`relative h-11 w-11 shrink-0 overflow-hidden rounded border-2 transition-colors ${
                sel
                  ? "border-cyan-500 ring-1 ring-cyan-500/35"
                  : "border-slate-600 hover:border-slate-500"
              } bg-slate-800`}
              title={`${mt || "media"} #${mid}`}
            >
              <img
                src={api.media.thumbnailUrl(mid)}
                alt=""
                className="absolute inset-0 z-[1] h-full w-full object-cover"
                onError={(e) => {
                  e.currentTarget.classList.add("hidden");
                  e.currentTarget.nextElementSibling?.classList.remove("hidden");
                }}
              />
              <span className="absolute inset-0 z-[2] hidden flex-col items-center justify-center bg-slate-900/95 px-0.5 text-center text-[9px] leading-tight text-slate-400">
                <span className="font-mono">#{mid}</span>
                <span className="mt-0.5 text-[8px] uppercase text-slate-500">
                  {mt === "video" ? "vid" : mt === "photo" ? "img" : mt ? mt.slice(0, 3) : "—"}
                </span>
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
