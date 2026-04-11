import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api } from "../api";

export function MediaLlmSuggestModal({
  mediaId,
  onClose,
  onTagsApplied,
}: {
  mediaId: number;
  onClose: () => void;
  onTagsApplied: () => void;
}) {
  const [tagsCsv, setTagsCsv] = useState("");
  const [caption, setCaption] = useState("");
  const [voice, setVoice] = useState("");

  const statusQ = useQuery({
    queryKey: ["llm-status"],
    queryFn: () => api.llm.status(),
  });

  const suggest = useMutation({
    mutationFn: () =>
      api.llm.suggestMediaCaption({
        media_id: mediaId,
        brand_voice_hint: voice.trim() || undefined,
      }),
    onSuccess: (data) => {
      setTagsCsv(data.tags_csv || "");
      setCaption([data.caption, ...(data.caption_variants || [])].filter(Boolean).join("\n---\n"));
    },
  });

  const applyTags = useMutation({
    mutationFn: () => api.media.bulkSetTags([mediaId], tagsCsv),
    onSuccess: () => {
      onTagsApplied();
      onClose();
    },
  });

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const configured = statusQ.data?.openai_configured ?? false;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="llm-suggest-title"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="bg-slate-900 border border-slate-600 rounded-lg max-w-lg w-full max-h-[90vh] overflow-y-auto shadow-xl">
        <div className="p-4 border-b border-slate-700 flex justify-between items-start gap-2">
          <div>
            <h2 id="llm-suggest-title" className="text-lg font-medium text-slate-100">
              AI: tags &amp; caption
            </h2>
            <p className="text-xs text-slate-500 mt-1">Media #{mediaId} — review and edit before applying tags.</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-slate-400 hover:text-slate-200 px-2 py-1 rounded"
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        <div className="p-4 space-y-4">
          {!configured && (
            <p className="text-amber-400 text-sm">
              OpenAI is not configured (set <code className="text-amber-200">TBCC_OPENAI_API_KEY</code> or{" "}
              <code className="text-amber-200">OPENAI_API_KEY</code> on the API host).
            </p>
          )}

          <label className="block text-xs text-slate-400">
            Optional brand voice / tone (one line)
            <input
              type="text"
              value={voice}
              onChange={(e) => setVoice(e.target.value)}
              placeholder="e.g. playful, minimal hashtags"
              className="mt-1 w-full px-2 py-1.5 rounded bg-slate-800 border border-slate-600 text-slate-200 text-sm"
            />
          </label>

          <div className="flex gap-2 flex-wrap">
            <button
              type="button"
              disabled={!configured || suggest.isPending}
              onClick={() => suggest.mutate()}
              className="px-3 py-2 rounded bg-violet-700 text-violet-100 text-sm hover:bg-violet-600 disabled:opacity-50"
            >
              {suggest.isPending ? "Generating…" : "Generate suggestion"}
            </button>
          </div>

          {suggest.isError && (
            <p className="text-red-400 text-sm">{(suggest.error as Error)?.message}</p>
          )}

          {suggest.data?.curator_note && (
            <p className="text-slate-400 text-xs italic border-l-2 border-slate-600 pl-2">{suggest.data.curator_note}</p>
          )}

          <label className="block text-xs text-slate-400">
            Tags (comma-separated) — applied on &quot;Save tags&quot;
            <textarea
              value={tagsCsv}
              onChange={(e) => setTagsCsv(e.target.value)}
              rows={3}
              className="mt-1 w-full px-2 py-1.5 rounded bg-slate-800 border border-slate-600 text-slate-200 text-sm font-mono"
            />
          </label>

          <label className="block text-xs text-slate-400">
            Caption ideas (copy to clipboard or scheduler; not auto-posted)
            <textarea
              value={caption}
              onChange={(e) => setCaption(e.target.value)}
              rows={6}
              className="mt-1 w-full px-2 py-1.5 rounded bg-slate-800 border border-slate-600 text-slate-200 text-sm"
            />
          </label>

          <div className="flex flex-wrap gap-2 pt-2">
            <button
              type="button"
              disabled={applyTags.isPending || !tagsCsv.trim()}
              onClick={() => applyTags.mutate()}
              className="px-3 py-2 rounded bg-cyan-700 text-cyan-100 text-sm hover:bg-cyan-600 disabled:opacity-50"
            >
              {applyTags.isPending ? "Saving…" : "Save tags"}
            </button>
            <button
              type="button"
              onClick={async () => {
                try {
                  await navigator.clipboard.writeText(caption);
                } catch {
                  /* ignore */
                }
              }}
              disabled={!caption.trim()}
              className="px-3 py-2 rounded bg-slate-600 text-slate-200 text-sm hover:bg-slate-500 disabled:opacity-50"
            >
              Copy caption
            </button>
            <button type="button" onClick={onClose} className="px-3 py-2 rounded bg-slate-700 text-slate-300 text-sm">
              Close
            </button>
          </div>

          {suggest.data?.model && <p className="text-slate-600 text-[10px]">Model: {suggest.data.model}</p>}
        </div>
      </div>
    </div>
  );
}
