import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

function useEscapeClose(onClose: () => void, enabled: boolean) {
  useEffect(() => {
    if (!enabled) return;
    const k = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [enabled, onClose]);
}
import { api } from "../api";

type Tab = "general" | "tags";

type Props = {
  mediaId: number | null;
  onClose: () => void;
};

export function MediaMetadataModal({ mediaId, onClose }: Props) {
  useEscapeClose(onClose, mediaId != null);
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<Tab>("general");
  const [status, setStatus] = useState("");
  const [poolId, setPoolId] = useState<number>(0);
  const [sourceChannel, setSourceChannel] = useState("");
  const [tagsText, setTagsText] = useState("");
  const [saveError, setSaveError] = useState<string | null>(null);

  const { data: row, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["media", "detail", mediaId],
    queryFn: async () => {
      const r = await api.media.get(mediaId!);
      if (r && typeof r === "object" && "error" in r && r.error) throw new Error(String(r.error));
      return r as Record<string, unknown>;
    },
    enabled: mediaId != null,
  });

  const { data: pools = [] } = useQuery({
    queryKey: ["pools"],
    queryFn: () => api.pools.list(),
  });

  const { data: tagList = [] } = useQuery({
    queryKey: ["tags"],
    queryFn: () => api.tags.list(),
  });

  useEffect(() => {
    if (mediaId == null) return;
    setTab("general");
    setSaveError(null);
  }, [mediaId]);

  useEffect(() => {
    if (!row) return;
    setStatus(String(row.status ?? "pending"));
    setPoolId(Number(row.pool_id ?? 0) || 0);
    setSourceChannel(String(row.source_channel ?? ""));
    setTagsText(String(row.tags ?? ""));
  }, [row]);

  const patchMutation = useMutation({
    mutationFn: async (body: Parameters<typeof api.media.patch>[1]) => {
      const r = await api.media.patch(mediaId!, body);
      if (r && typeof r === "object" && "error" in r && r.error) throw new Error(String(r.error));
      return r as Record<string, unknown>;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["media"] });
      setSaveError(null);
      void refetch();
    },
    onError: (e: Error) => setSaveError(e.message),
  });

  const reapplyRules = useMutation({
    mutationFn: () => api.tags.reapplyRules(mediaId!),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["media"] });
      void queryClient.invalidateQueries({ queryKey: ["tags"] });
      void refetch();
    },
  });

  if (mediaId == null) return null;

  const mediaType = String(row?.media_type ?? "—");
  const readOnlyBlock = (
    <div className="rounded border border-slate-600 bg-slate-900/50 p-3 text-xs text-slate-400 space-y-1">
      <div>
        <span className="text-slate-500">ID</span> {String(row?.id ?? mediaId)}
      </div>
      <div>
        <span className="text-slate-500">Type</span> {mediaType}
      </div>
      <div className="break-all">
        <span className="text-slate-500">Dedup (file_unique_id)</span> {String(row?.file_unique_id ?? "—")}
      </div>
      <div>
        <span className="text-slate-500">Telegram message id</span> {String(row?.telegram_message_id ?? "—")}
      </div>
      <div className="break-all">
        <span className="text-slate-500">file_id</span> {String(row?.file_id ?? "—")}
      </div>
      <div>
        <span className="text-slate-500">Created</span> {String(row?.created_at ?? "—").slice(0, 19)}
      </div>
    </div>
  );

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 p-4 overflow-y-auto"
      role="dialog"
      aria-modal="true"
      aria-labelledby="media-meta-title"
      hidden={!open}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className="bg-slate-800 border border-slate-600 rounded-lg shadow-xl w-full max-w-lg max-h-[min(90vh,800px)] flex flex-col my-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-2 p-4 border-b border-slate-600 shrink-0">
          <h2 id="media-meta-title" className="text-lg font-medium text-slate-100">
            Media metadata
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="text-slate-400 hover:text-slate-200 px-2 py-1 rounded text-sm"
          >
            Close
          </button>
        </div>

        <div className="flex gap-1 px-4 pt-3 border-b border-slate-600 shrink-0">
          {(
            [
              ["general", "General"],
              ["tags", "Tags & rules"],
            ] as const
          ).map(([k, label]) => (
            <button
              key={k}
              type="button"
              onClick={() => setTab(k)}
              className={`px-3 py-2 text-sm rounded-t border border-b-0 -mb-px ${
                tab === k
                  ? "bg-slate-800 border-slate-600 text-cyan-300 border-b-slate-800"
                  : "bg-slate-900/50 border-transparent text-slate-400 hover:text-slate-200"
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        <div className="p-4 overflow-y-auto flex-1 min-h-0">
          {isLoading && <p className="text-slate-400 text-sm">Loading…</p>}
          {isError && (
            <p className="text-red-400 text-sm">{(error as Error)?.message || "Could not load media."}</p>
          )}
          {!isLoading && !isError && row && (
            <>
              <div className="flex gap-3 mb-4">
                <div className="w-24 h-24 rounded overflow-hidden bg-slate-900 border border-slate-600 shrink-0">
                  {String(mediaType).toLowerCase() === "video" ? (
                    <video
                      src={api.media.thumbnailUrl(mediaId)}
                      className="w-full h-full object-cover"
                      muted
                      playsInline
                      preload="metadata"
                    />
                  ) : (
                    <img
                      src={api.media.thumbnailUrl(mediaId)}
                      alt=""
                      className="w-full h-full object-cover"
                      loading="lazy"
                    />
                  )}
                </div>
                {readOnlyBlock}
              </div>

              {tab === "general" && (
                <div className="space-y-3">
                  <label className="block">
                    <span className="text-slate-400 text-xs">Status</span>
                    <select
                      value={status}
                      onChange={(e) => setStatus(e.target.value)}
                      className="mt-1 w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200"
                    >
                      {["pending", "approved", "posted", "rejected"].map((s) => (
                        <option key={s} value={s}>
                          {s}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="block">
                    <span className="text-slate-400 text-xs">Pool</span>
                    <select
                      value={poolId || ""}
                      onChange={(e) => setPoolId(Number(e.target.value))}
                      className="mt-1 w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200"
                    >
                      {(pools as Array<{ id: number; name?: string }>).map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.name || `Pool ${p.id}`}
                        </option>
                      ))}
                      {poolId > 0 &&
                        !(pools as Array<{ id: number }>).some((p) => p.id === poolId) && (
                          <option value={poolId}>Pool {poolId} (not in list)</option>
                        )}
                    </select>
                  </label>
                  <label className="block">
                    <span className="text-slate-400 text-xs">Source (import URL or label; clear to remove)</span>
                    <textarea
                      value={sourceChannel}
                      onChange={(e) => setSourceChannel(e.target.value)}
                      rows={3}
                      className="mt-1 w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200 text-sm font-mono"
                      placeholder="https://… or extension:…"
                    />
                  </label>
                </div>
              )}

              {tab === "tags" && (
                <div className="space-y-3">
                  <label className="block">
                    <span className="text-slate-400 text-xs">Tags (comma-separated — same as bulk editor)</span>
                    <textarea
                      value={tagsText}
                      onChange={(e) => setTagsText(e.target.value)}
                      rows={5}
                      className="mt-1 w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200 text-sm"
                      placeholder="tag one, tag two"
                    />
                  </label>
                  <p className="text-slate-500 text-xs">Quick insert from catalog:</p>
                  <div className="flex flex-wrap gap-1 max-h-28 overflow-y-auto">
                    {tagList.map((t) => (
                      <button
                        key={t.id}
                        type="button"
                        className="px-2 py-0.5 rounded bg-slate-700 text-slate-300 text-xs hover:bg-slate-600"
                        onClick={() => {
                          const name = t.name || t.slug;
                          const cur = tagsText
                            .split(",")
                            .map((s) => s.trim())
                            .filter(Boolean);
                          if (cur.some((c) => c.toLowerCase() === name.toLowerCase())) return;
                          setTagsText((prev) => (prev.trim() ? `${prev.trim()}, ${name}` : name));
                        }}
                      >
                        {t.name || t.slug}
                      </button>
                    ))}
                  </div>
                  <button
                    type="button"
                    disabled={reapplyRules.isPending}
                    onClick={() => reapplyRules.mutate()}
                    className="px-3 py-2 rounded bg-violet-800 text-violet-100 text-sm hover:bg-violet-700 disabled:opacity-50"
                  >
                    {reapplyRules.isPending ? "Re-applying…" : "Re-apply auto-tag rules (keeps manual tags)"}
                  </button>
                  {reapplyRules.isError && (
                    <p className="text-red-400 text-xs">{(reapplyRules.error as Error)?.message}</p>
                  )}
                </div>
              )}

              {saveError && <p className="text-red-400 text-sm mt-2">{saveError}</p>}
            </>
          )}
        </div>

        <div className="p-4 border-t border-slate-600 flex justify-end gap-2 shrink-0">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 rounded bg-slate-600 text-slate-200 hover:bg-slate-500"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={!row || patchMutation.isPending}
            onClick={() => {
              setSaveError(null);
              patchMutation.mutate({
                status,
                pool_id: poolId,
                source_channel: sourceChannel.trim() || null,
                tags: tagsText,
              });
            }}
            className="px-4 py-2 rounded bg-cyan-600 text-white hover:bg-cyan-500 disabled:opacity-50"
          >
            {patchMutation.isPending ? "Saving…" : "Save changes"}
          </button>
        </div>
      </div>
    </div>
  );
}
