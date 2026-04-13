import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api } from "../api";
import { MediaThumbnailCell } from "./MediaThumbnailCell";

type Tab = "general" | "tags";

type Props = {
  mediaId: number;
  /** Small preview thumb above metadata (metadata modal). Suite uses large preview elsewhere. */
  showPreviewThumb?: boolean;
  /** If set, show a Cancel button that calls this (metadata modal). */
  onCancel?: () => void;
  className?: string;
};

export function MediaItemEditorPanel({ mediaId, showPreviewThumb = false, onCancel, className = "" }: Props) {
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<Tab>("general");
  const [status, setStatus] = useState("");
  const [poolId, setPoolId] = useState<number>(0);
  const [sourceChannel, setSourceChannel] = useState("");
  const [tagsText, setTagsText] = useState("");
  const [newTagName, setNewTagName] = useState("");
  const [saveError, setSaveError] = useState<string | null>(null);

  const { data: row, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["media", "detail", mediaId],
    queryFn: async () => {
      const r = await api.media.get(mediaId);
      if (r && typeof r === "object" && "error" in r && r.error) throw new Error(String(r.error));
      return r as Record<string, unknown>;
    },
    enabled: mediaId > 0,
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
    setTab("general");
    setSaveError(null);
    setNewTagName("");
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
      const r = await api.media.patch(mediaId, body);
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
    mutationFn: () => api.tags.reapplyRules(mediaId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["media"] });
      void queryClient.invalidateQueries({ queryKey: ["tags"] });
      void refetch();
    },
  });

  const createTag = useMutation({
    mutationFn: (name: string) =>
      api.tags.create({ name: name.trim(), category: "manual" }),
    onSuccess: (_r, name) => {
      void queryClient.invalidateQueries({ queryKey: ["tags"] });
      const trimmed = name.trim();
      const cur = tagsText
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      if (!cur.some((c) => c.toLowerCase() === trimmed.toLowerCase())) {
        setTagsText((prev) => (prev.trim() ? `${prev.trim()}, ${trimmed}` : trimmed));
      }
      setNewTagName("");
    },
  });

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
    <div className={`flex flex-col min-h-0 ${className}`}>
      <div className="flex gap-1 border-b border-slate-600 shrink-0">
        {(
          [
            ["general", "General"],
            ["tags", "Tags & routing"],
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
            <div className={`flex gap-3 mb-4 ${showPreviewThumb ? "" : "flex-col"}`}>
              {showPreviewThumb && (
                <div className="w-24 h-24 rounded overflow-hidden bg-slate-900 border border-slate-600 shrink-0">
                  <MediaThumbnailCell
                    mediaId={mediaId}
                    mediaType={mediaType}
                    className="w-full h-full object-cover"
                  />
                </div>
              )}
              {readOnlyBlock}
            </div>
            {tab === "general" && (
              <div className="space-y-3">
                <p className="text-slate-500 text-xs">
                  Moving to another <strong>pool</strong> reroutes posting: each pool targets a Telegram channel on the Pools
                  tab.
                </p>
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
                  <span className="text-slate-400 text-xs">Pool (channel routing)</span>
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
                  <span className="text-slate-400 text-xs">Tags (comma-separated)</span>
                  <textarea
                    value={tagsText}
                    onChange={(e) => setTagsText(e.target.value)}
                    rows={5}
                    className="mt-1 w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200 text-sm"
                    placeholder="e.g. bigtits, cosplay"
                  />
                </label>
                <p className="text-slate-500 text-xs">Catalog — click to add; creates manual tag links (keeps auto tags unless you replace).</p>
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
                <div className="flex flex-wrap gap-2 items-end">
                  <label className="flex-1 min-w-[140px] block">
                    <span className="text-slate-400 text-xs">New tag in database</span>
                    <input
                      type="text"
                      value={newTagName}
                      onChange={(e) => setNewTagName(e.target.value)}
                      placeholder="e.g. bigtits"
                      className="mt-1 w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200 text-sm"
                      list="media-editor-tag-suggestions"
                    />
                    <datalist id="media-editor-tag-suggestions">
                      {tagList.map((t) => (
                        <option key={t.id} value={t.name || t.slug} />
                      ))}
                    </datalist>
                  </label>
                  <button
                    type="button"
                    disabled={!newTagName.trim() || createTag.isPending}
                    onClick={() => createTag.mutate(newTagName)}
                    className="px-3 py-2 rounded bg-emerald-800 text-emerald-100 text-sm hover:bg-emerald-700 disabled:opacity-50"
                  >
                    {createTag.isPending ? "Creating…" : "Create & add"}
                  </button>
                </div>
                {createTag.isError && (
                  <p className="text-red-400 text-xs">{(createTag.error as Error)?.message}</p>
                )}
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
        {onCancel && (
          <button
            type="button"
            onClick={onCancel}
            className="px-4 py-2 rounded bg-slate-600 text-slate-200 hover:bg-slate-500"
          >
            Cancel
          </button>
        )}
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
  );
}
