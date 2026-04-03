import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import { useEffect, useMemo, useState } from "react";
import { MediaGalleryModal, canPreviewInGallery } from "../components/MediaGalleryModal";

export function MediaLibrary() {
  const [statusFilter, setStatusFilter] = useState<string | undefined>("pending");
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [viewerIndex, setViewerIndex] = useState<number | null>(null);
  const queryClient = useQueryClient();
  const { data: media = [], isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: ["media", statusFilter],
    queryFn: () => api.media.list(statusFilter),
  });
  const { data: pools = [] } = useQuery({
    queryKey: ["pools"],
    queryFn: () => api.pools.list(),
  });
  const poolMap = Object.fromEntries(
    (pools as Array<Record<string, unknown>>).map((p) => [String(p.id), String(p.name ?? p.id)])
  );
  const [savedImportPool, setSavedImportPool] = useState(1);
  const [savedImportLimit, setSavedImportLimit] = useState(50);

  const importFromSaved = useMutation({
    mutationFn: () => api.import.fromSaved(savedImportPool, savedImportLimit),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["media"] }),
  });

  useEffect(() => {
    const ids = (pools as Array<{ id: number }>).map((p) => p.id);
    if (ids.length && !ids.includes(savedImportPool)) {
      setSavedImportPool(ids[0]);
    }
  }, [pools, savedImportPool]);

  const updateStatus = useMutation({
    mutationFn: ({ id, status }: { id: number; status: string }) =>
      api.media.updateStatus(id, status),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["media"] }),
  });
  const updateStatusBulk = useMutation({
    mutationFn: ({ ids, status }: { ids: number[]; status: string }) =>
      api.media.updateStatusBulk(ids, status),
    onSuccess: (_, { ids }) => {
      queryClient.invalidateQueries({ queryKey: ["media"] });
      setSelectedIds((prev) => prev.filter((id) => !ids.includes(id)));
    },
  });

  const pendingItems = (media as Array<Record<string, unknown>>).filter((m) => m.status === "pending");
  const pendingIds = pendingItems.map((m) => Number(m.id));
  const toggleSelected = (id: number) => {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };
  const selectAllCurrent = () => setSelectedIds((media as Array<Record<string, unknown>>).map((m) => Number(m.id)));
  const clearSelection = () => setSelectedIds([]);

  const previewable = useMemo(
    () => (media as Array<Record<string, unknown>>).filter((m) => canPreviewInGallery(m)),
    [media]
  );

  const openViewerForId = (id: number) => {
    const idx = previewable.findIndex((m) => Number(m.id) === id);
    if (idx >= 0) setViewerIndex(idx);
  };

  if (isError)
    return (
      <div className="rounded-lg bg-red-900/30 border border-red-700 p-4 text-red-200">
        <p className="font-medium">Could not load media.</p>
        <p className="text-sm mt-1 text-red-300">{String(error?.message || "Is the backend running on port 8000?")}</p>
        <button onClick={() => refetch()} className="mt-3 px-3 py-1 rounded bg-red-800 hover:bg-red-700">
          Retry
        </button>
      </div>
    );

  if (isLoading) return <div className="text-slate-400">Loading...</div>;

  return (
    <div>
      <MediaGalleryModal
        items={previewable.map((m) => ({ id: Number(m.id), media_type: String(m.media_type || "") }))}
        openIndex={viewerIndex}
        onClose={() => setViewerIndex(null)}
        onIndexChange={setViewerIndex}
      />
      <h1 className="text-2xl font-semibold mb-2">Media Library</h1>
      <div className="bg-slate-800 border border-slate-600 rounded-lg p-4 mb-4 max-w-2xl">
        <h2 className="text-sm font-medium text-slate-200 mb-1">Import from Saved Messages</h2>
        <p className="text-slate-400 text-xs mb-3">
          Adds photos/videos already sitting in your Telegram <strong>Saved Messages</strong> into a{" "}
          <strong>pool</strong> as <strong>pending</strong> media (newest first; skips duplicates already in that pool).
          Uses the same admin account session as other TBCC imports — not the payment bot.
        </p>
        <div className="flex flex-wrap gap-3 items-end">
          <label className="block text-xs text-slate-400">
            Pool
            <select
              className="mt-1 block bg-slate-900 border border-slate-600 rounded px-2 py-1.5 text-slate-100 text-sm"
              value={savedImportPool}
              onChange={(e) => setSavedImportPool(Number(e.target.value))}
            >
              {(pools as Array<{ id: number; name?: string }>).map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name || `Pool ${p.id}`}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-xs text-slate-400">
            Scan up to (messages)
            <input
              type="number"
              min={1}
              max={200}
              className="mt-1 block w-24 bg-slate-900 border border-slate-600 rounded px-2 py-1.5 text-slate-100 text-sm"
              value={savedImportLimit}
              onChange={(e) => setSavedImportLimit(Math.min(200, Math.max(1, Number(e.target.value) || 50)))}
            />
          </label>
          <button
            type="button"
            onClick={() => importFromSaved.mutate()}
            disabled={importFromSaved.isPending || !(pools as unknown[]).length}
            className="px-3 py-2 rounded bg-amber-600/90 text-white text-sm font-medium hover:bg-amber-500 disabled:opacity-50"
          >
            {importFromSaved.isPending ? "Importing…" : "Import from Saved"}
          </button>
        </div>
        {importFromSaved.isError && (
          <p className="text-red-400 text-xs mt-2">{(importFromSaved.error as Error)?.message}</p>
        )}
        {importFromSaved.isSuccess && importFromSaved.data && !importFromSaved.data.error && (
          <p className="text-green-400 text-xs mt-2">
            Indexed <strong>{String(importFromSaved.data.indexed ?? 0)}</strong> new item(s); skipped{" "}
            {String(importFromSaved.data.skipped_duplicates_or_unsupported ?? 0)} (duplicate or unsupported); scanned{" "}
            {String(importFromSaved.data.messages_scanned ?? 0)} message(s).
          </p>
        )}
        {importFromSaved.isSuccess && importFromSaved.data?.error && (
          <p className="text-red-400 text-xs mt-2">{String(importFromSaved.data.error)}</p>
        )}
      </div>
      <div className="flex flex-wrap gap-2 mb-4 items-center">
        <button
          onClick={() => setStatusFilter(undefined)}
          className={`px-3 py-1 rounded ${!statusFilter ? "bg-cyan-600 text-white" : "bg-slate-700 text-slate-300"}`}
        >
          All
        </button>
        {["pending", "approved", "posted", "rejected"].map((s) => (
          <button
            key={s}
            onClick={() => setStatusFilter(s)}
            className={`px-3 py-1 rounded ${statusFilter === s ? "bg-cyan-600 text-white" : "bg-slate-700 text-slate-300"}`}
          >
            {s}
          </button>
        ))}
        {statusFilter === "pending" && pendingIds.length > 0 && (
          <div className="flex gap-2 ml-2 flex-wrap items-center">
            <button
              onClick={() => updateStatusBulk.mutate({ ids: pendingIds, status: "approved" })}
              disabled={updateStatusBulk.isPending}
              className="px-3 py-1 rounded bg-green-700 text-green-100 hover:bg-green-600 disabled:opacity-50 text-sm"
            >
              Approve all ({pendingIds.length})
            </button>
            <button
              onClick={() => updateStatusBulk.mutate({ ids: pendingIds, status: "rejected" })}
              disabled={updateStatusBulk.isPending}
              className="px-3 py-1 rounded bg-red-700 text-red-100 hover:bg-red-600 disabled:opacity-50 text-sm"
            >
              Reject all
            </button>
            {selectedIds.length > 0 && (
              <>
                <span className="text-slate-400 text-sm">{selectedIds.length} selected</span>
                <button
                  onClick={() => updateStatusBulk.mutate({ ids: selectedIds, status: "approved" })}
                  disabled={updateStatusBulk.isPending}
                  className="px-3 py-1 rounded bg-green-700 text-green-100 hover:bg-green-600 disabled:opacity-50 text-sm"
                >
                  Approve selected
                </button>
                <button
                  onClick={() => updateStatusBulk.mutate({ ids: selectedIds, status: "rejected" })}
                  disabled={updateStatusBulk.isPending}
                  className="px-3 py-1 rounded bg-red-700 text-red-100 hover:bg-red-600 disabled:opacity-50 text-sm"
                >
                  Reject selected
                </button>
                <button onClick={clearSelection} className="px-3 py-1 rounded bg-slate-600 text-slate-200 text-sm">
                  Clear selection
                </button>
              </>
            )}
          </div>
        )}
        {!statusFilter && (
          <div className="flex gap-2 ml-2 items-center">
            <button onClick={selectAllCurrent} className="px-3 py-1 rounded bg-slate-600 text-slate-200 text-sm">
              Select all on page
            </button>
            {selectedIds.length > 0 && (
              <>
                <span className="text-slate-400 text-sm">{selectedIds.length} selected</span>
                <button onClick={clearSelection} className="px-3 py-1 rounded bg-slate-600 text-slate-200 text-sm">
                  Clear selection
                </button>
              </>
            )}
          </div>
        )}
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className={`ml-auto px-3 py-1 rounded bg-slate-600 text-slate-200 disabled:opacity-50 disabled:cursor-not-allowed`}
        >
          {isFetching ? "Refreshing..." : "Refresh"}
        </button>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full border border-slate-600 rounded-lg overflow-hidden">
          <thead className="bg-slate-700">
            <tr>
              <th className="text-left p-3 w-10">
                <input
                  type="checkbox"
                  checked={selectedIds.length > 0 && (media as Array<Record<string, unknown>>).every((m) => selectedIds.includes(Number(m.id)))}
                  ref={(el) => {
                    if (!el) return;
                    el.indeterminate = selectedIds.length > 0 && selectedIds.length < (media as Array<Record<string, unknown>>).length;
                  }}
                  onChange={(e) => (e.target.checked ? selectAllCurrent() : clearSelection())}
                  title="Select all on page"
                />
              </th>
              <th className="text-left p-3">Thumbnail</th>
              <th className="text-left p-3">ID</th>
              <th className="text-left p-3">Type</th>
              <th className="text-left p-3">Status</th>
              <th className="text-left p-3">Source</th>
              <th className="text-left p-3">Pool</th>
              <th className="text-left p-3">Created</th>
              <th className="text-left p-3">Actions</th>
            </tr>
          </thead>
          <tbody>
            {media.map((m: Record<string, unknown>) => (
              <tr key={String(m.id)} className="border-t border-slate-600 hover:bg-slate-800/50">
                <td className="p-3">
                  <input
                    type="checkbox"
                    checked={selectedIds.includes(Number(m.id))}
                    onChange={() => toggleSelected(Number(m.id))}
                    title="Select for bulk action"
                  />
                </td>
                <td className="p-3">
                  <button
                    type="button"
                    className="w-14 h-14 rounded bg-slate-700 overflow-hidden flex items-center justify-center border border-transparent hover:border-cyan-500/60 focus:outline-none focus:ring-2 focus:ring-cyan-500 disabled:opacity-50"
                    onClick={() => openViewerForId(Number(m.id))}
                    disabled={!canPreviewInGallery(m)}
                    title={canPreviewInGallery(m) ? "Open full size (gallery)" : "No preview"}
                  >
                    {canPreviewInGallery(m) ? (
                      (String(m.media_type || "").toLowerCase() === "video" ? (
                        <video
                          src={api.media.thumbnailUrl(Number(m.id))}
                          className="w-full h-full object-cover pointer-events-none"
                          muted
                          playsInline
                          preload="metadata"
                        />
                      ) : (
                        <img
                          src={api.media.thumbnailUrl(Number(m.id))}
                          alt=""
                          className="w-full h-full object-cover"
                          loading="lazy"
                          decoding="async"
                          onError={(e) => {
                            (e.target as HTMLImageElement).style.display = "none";
                          }}
                        />
                      ))
                    ) : (
                      <span className="text-slate-500 text-xs">{String(m.media_type || "—")}</span>
                    )}
                  </button>
                </td>
                <td className="p-3">{String(m.id)}</td>
                <td className="p-3">{String(m.media_type)}</td>
                <td className="p-3">
                  <span
                    className={`px-2 py-0.5 rounded text-sm ${
                      m.status === "approved"
                        ? "bg-green-900/50 text-green-300"
                        : m.status === "posted"
                          ? "bg-blue-900/50 text-blue-300"
                          : m.status === "rejected"
                            ? "bg-red-900/50 text-red-300"
                            : "bg-amber-900/50 text-amber-300"
                    }`}
                  >
                    {String(m.status)}
                  </span>
                </td>
                <td className="p-3 text-slate-400 truncate max-w-[120px]">{String(m.source_channel ?? "")}</td>
                <td className="p-3">
                  {poolMap[String(m.pool_id ?? "")] ?? String(m.pool_id ?? "-")}
                </td>
                <td className="p-3 text-slate-400 text-sm">{String(m.created_at ?? "").slice(0, 19)}</td>
                <td className="p-3">
                  {m.status === "pending" && (
                    <div className="flex gap-1">
                      <button
                        onClick={() => updateStatus.mutate({ id: Number(m.id), status: "approved" })}
                        disabled={updateStatus.isPending}
                        className="px-2 py-0.5 rounded text-sm bg-green-700 text-green-100 hover:bg-green-600 disabled:opacity-50"
                      >
                        Approve
                      </button>
                      <button
                        onClick={() => updateStatus.mutate({ id: Number(m.id), status: "rejected" })}
                        disabled={updateStatus.isPending}
                        className="px-2 py-0.5 rounded text-sm bg-red-700 text-red-100 hover:bg-red-600 disabled:opacity-50"
                      >
                        Reject
                      </button>
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {media.length === 0 && <p className="text-slate-500 mt-4">No media found.</p>}
    </div>
  );
}
