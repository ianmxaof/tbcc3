import { useMutation, useQueryClient } from "@tanstack/react-query";
import { getApiBase } from "../api";
import { api } from "../api";

type RowStrip = {
  row: number;
  preview_url: string;
  saved_path?: string | null;
  export_filename: string;
};

type Props = {
  jobId: string;
  rows: number;
  rowStrips?: RowStrip[];
  compact?: boolean;
};

export function EmojiFactoryRowDividers({ jobId, rows, rowStrips, compact = false }: Props) {
  const qc = useQueryClient();
  const strips =
    rowStrips ??
    Array.from({ length: rows }, (_, row) => ({
      row,
      preview_url: `${getApiBase()}/emoji-factory/jobs/${jobId}/rows/${row}/divider-png`,
      export_filename: `row_${String(row).padStart(2, "0")}_divider.png`,
    }));

  const saveRow = useMutation({
    mutationFn: (row: number) => api.emojiFactory.saveRowDivider(jobId, row),
  });

  const importRow = useMutation({
    mutationFn: (row: number) => api.emojiFactory.importRowDivider(jobId, row),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["mainChannelDivider"] });
      qc.invalidateQueries({ queryKey: ["mainChannelDividerEmojiSources"] });
    },
  });

  if (!jobId || rows < 1) return null;

  return (
    <div className={`rounded-lg border border-violet-900/40 bg-violet-950/15 ${compact ? "p-3" : "p-4"} space-y-3`}>
      <div>
        <h3 className={`font-medium text-violet-200 ${compact ? "text-sm" : "text-base"}`}>
          Row divider exports
        </h3>
        <p className="text-xs text-slate-500 mt-1">
          Each row is cropped from the normalized master (or stitched from tiles) into one horizontal PNG — useful for
          main-channel post dividers.
        </p>
      </div>
      <div className="flex flex-col gap-2">
        {strips.map((strip) => (
          <div
            key={strip.row}
            className="flex flex-wrap items-center gap-3 rounded border border-slate-700/80 bg-slate-900/50 p-2"
          >
            <img
              src={strip.preview_url}
              alt={`row ${strip.row}`}
              className="h-10 max-w-[min(100%,280px)] object-contain bg-black/30 rounded"
            />
            <span className="text-xs text-slate-400">Row {strip.row}</span>
            <div className="flex flex-wrap gap-2 ml-auto">
              <a
                href={strip.preview_url}
                download={strip.export_filename}
                className="px-2 py-1 rounded text-xs border border-slate-600 text-slate-300 hover:border-violet-500"
              >
                Download PNG
              </a>
              <button
                type="button"
                className="px-2 py-1 rounded text-xs border border-slate-600 text-slate-300 hover:border-cyan-500 disabled:opacity-40"
                disabled={saveRow.isPending}
                onClick={() => saveRow.mutate(strip.row)}
              >
                {saveRow.isPending ? "Saving…" : "Save to job folder"}
              </button>
              <button
                type="button"
                className="px-2 py-1 rounded text-xs bg-violet-800 text-white hover:bg-violet-700 disabled:opacity-40"
                disabled={importRow.isPending}
                onClick={() => importRow.mutate(strip.row)}
              >
                {importRow.isPending ? "Importing…" : "Use as main divider"}
              </button>
            </div>
            {strip.saved_path ? (
              <span className="text-[10px] text-emerald-500/80 w-full">Saved: {strip.export_filename}</span>
            ) : null}
          </div>
        ))}
      </div>
      {saveRow.isError ? (
        <p className="text-xs text-red-400">{(saveRow.error as Error).message}</p>
      ) : saveRow.isSuccess ? (
        <p className="text-xs text-emerald-400">Saved {saveRow.data?.filename} under pack-out/dividers/</p>
      ) : null}
      {importRow.isError ? <p className="text-xs text-red-400">{(importRow.error as Error).message}</p> : null}
      {importRow.isSuccess ? (
        <p className="text-xs text-emerald-400">Row imported into main-channel divider pool.</p>
      ) : null}
    </div>
  );
}
