import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useEffect, useMemo, useRef, useState } from "react";
import { canPreviewInGallery } from "../components/MediaGalleryModal";
import { MediaMasterSuiteModal } from "../components/MediaMasterSuiteModal";
import { MediaThumbnailCell } from "../components/MediaThumbnailCell";
import { MediaLlmSuggestModal } from "../components/MediaLlmSuggestModal";
import { ContentPools } from "./ContentPools";
import { InfoDisclosure } from "../components/InfoDisclosure";

export function MediaLibrary() {
  const [statusFilter, setStatusFilter] = useState<string | undefined>("pending");
  const [tagFilter, setTagFilter] = useState("");
  const [tagSlugFilter, setTagSlugFilter] = useState("");
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [suiteIndex, setSuiteIndex] = useState<number | null>(null);
  const [viewMode, setViewMode] = useState<"list" | "grid">("list");
  const [gridCols, setGridCols] = useState<3 | 5 | 8>(5);
  const [llmSuggestMediaId, setLlmSuggestMediaId] = useState<number | null>(null);
  const [bulkPoolId, setBulkPoolId] = useState<number>(0);
  const [bulkTagsText, setBulkTagsText] = useState("");
  const queryClient = useQueryClient();
  const { data: media = [], isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: ["media", statusFilter, tagFilter, tagSlugFilter],
    queryFn: () =>
      api.media.list({
        status: statusFilter,
        ...(tagFilter.trim() ? { tag: tagFilter.trim() } : {}),
        ...(tagSlugFilter.trim() ? { tag_slug: tagSlugFilter.trim() } : {}),
      }),
  });
  const { data: tagList = [] } = useQuery({
    queryKey: ["tags"],
    queryFn: () => api.tags.list(),
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

  const [uploadPoolId, setUploadPoolId] = useState(1);
  /** pool-only: TBCC pool only; channel: import then post to channel/topic; saved-only: Telegram Saved Messages only (no Media rows) */
  const [uploadDestMode, setUploadDestMode] = useState<"pool-only" | "channel" | "saved-only">("pool-only");
  const [uploadChannelId, setUploadChannelId] = useState(0);
  /** null = post to channel/group main chat (not a forum subtopic) */
  const [uploadThreadId, setUploadThreadId] = useState<number | null>(null);
  const [uploadCaption, setUploadCaption] = useState("");
  const [markPostedAfterChannel, setMarkPostedAfterChannel] = useState(true);
  const [uploadMsg, setUploadMsg] = useState<string | null>(null);
  const uploadFileInputRef = useRef<HTMLInputElement>(null);

  const { data: channels = [] } = useQuery({
    queryKey: ["channels"],
    queryFn: () => api.channels.list(),
  });
  const { data: uploadForumTopicsRes } = useQuery({
    queryKey: ["forumTopics", uploadChannelId],
    queryFn: () => api.channels.forumTopics(uploadChannelId),
    enabled: uploadChannelId > 0 && uploadDestMode === "channel",
  });
  const uploadForumTopics = uploadForumTopicsRes?.topics ?? [];
  const uploadForumTopicsHint = uploadForumTopicsRes?.error;

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

  useEffect(() => {
    const ids = (pools as Array<{ id: number }>).map((p) => p.id);
    if (ids.length && !ids.includes(uploadPoolId)) {
      setUploadPoolId(ids[0]);
    }
  }, [pools, uploadPoolId]);

  const uploadLocalFiles = useMutation({
    /** Must be `File[]` — snapshot before clearing the `<input type="file">` or the list is empty when this runs async. */
    mutationFn: async (files: File[]) => {
      const list = files.filter(Boolean);
      if (!list.length) throw new Error("No files selected");
      const cap = uploadCaption.trim();
      const captionForTelegram = cap || undefined;

      if (uploadDestMode === "saved-only") {
        if (list.length === 1) {
          await api.import.bytes(list[0], uploadPoolId, "dashboard:media-library", {
            savedOnly: true,
            caption: captionForTelegram,
          });
          return { lines: [`${list[0].name}: sent to Saved Messages`] };
        }
        await api.import.savedBatch(list, captionForTelegram);
        return { lines: [`${list.length} file(s) sent to Saved Messages (albums up to 10 items)`] };
      }

      const mediaIds: number[] = [];
      const lines: string[] = [];
      for (const f of list) {
        const r = await api.import.bytes(f, uploadPoolId, "dashboard:media-library");
        if (r.error) lines.push(`${f.name}: ${String(r.error)}`);
        else if (r.media_id != null) {
          mediaIds.push(Number(r.media_id));
          lines.push(`${f.name}: imported to pool`);
        } else lines.push(`${f.name}: ${String(r.status || "skipped")}`);
      }

      if (uploadDestMode === "channel" && uploadChannelId > 0 && mediaIds.length > 0) {
        const post = await api.forum.postAlbum({
          channel_id: uploadChannelId,
          message_thread_id: uploadThreadId,
          media_ids: mediaIds,
          caption: captionForTelegram ?? "",
          mark_posted: markPostedAfterChannel,
        });
        if (post.error) lines.push(`Telegram: ${post.error}`);
        else if (post.errors?.length) lines.push(`Telegram: ${post.errors.join("; ")}`);
        else lines.push(`Posted to Telegram (${post.sent_chunks ?? 0} send group(s))`);
      }

      return { lines };
    },
    onSuccess: (data) => {
      void queryClient.invalidateQueries({ queryKey: ["media"] });
      setUploadMsg(data.lines.join("\n"));
      setTimeout(() => setUploadMsg(null), 12000);
    },
    onError: (e: Error) => setUploadMsg(e.message),
  });

  const [statusMutationErr, setStatusMutationErr] = useState<string | null>(null);
  const [bulkMoveFeedback, setBulkMoveFeedback] = useState<string | null>(null);
  const updateStatus = useMutation({
    mutationFn: ({ id, status }: { id: number; status: string }) =>
      api.media.updateStatus(id, status),
    onMutate: () => setStatusMutationErr(null),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["media"] });
      setStatusMutationErr(null);
    },
    onError: (e: Error) => setStatusMutationErr(e.message),
  });
  const updateStatusBulk = useMutation({
    mutationFn: ({ ids, status }: { ids: number[]; status: string }) =>
      api.media.updateStatusBulk(ids, status),
    onMutate: () => setStatusMutationErr(null),
    onSuccess: (_, { ids }) => {
      queryClient.invalidateQueries({ queryKey: ["media"] });
      setSelectedIds((prev) => prev.filter((id) => !ids.includes(id)));
      setStatusMutationErr(null);
    },
    onError: (e: Error) => setStatusMutationErr(e.message),
  });
  const bulkMovePool = useMutation({
    mutationFn: ({ ids, poolId }: { ids: number[]; poolId: number }) => api.media.bulkMovePool(ids, poolId),
    onMutate: () => setBulkMoveFeedback(null),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["media"] });
      queryClient.invalidateQueries({ queryKey: ["pools"] });
      setSelectedIds([]);
      const skipped = data.skipped_duplicate_in_target_pool ?? 0;
      if (data.updated === 0 && skipped === 0) {
        setBulkMoveFeedback("No rows moved (missing media ids?).");
      } else if (skipped > 0) {
        setBulkMoveFeedback(
          `Moved ${data.updated}. Skipped ${skipped} — same Telegram file already in the target pool, or duplicate file repeated in your selection (first wins).`
        );
      } else {
        setBulkMoveFeedback(`Moved ${data.updated} item(s) to the pool.`);
      }
    },
    onError: (e: Error) => setBulkMoveFeedback(`Move to pool failed: ${e.message}`),
  });
  const bulkSetTags = useMutation({
    mutationFn: ({ ids, tags }: { ids: number[]; tags: string }) => api.media.bulkSetTags(ids, tags),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["media"] });
      queryClient.invalidateQueries({ queryKey: ["tags"] });
      setSelectedIds([]);
    },
  });

  /** Same as Master suite “Remove from pool”: DELETE each row from TBCC only (Telegram copy untouched). */
  const bulkRemoveFromPool = useMutation({
    mutationFn: async (ids: number[]) => {
      for (const id of ids) {
        await api.media.delete(id);
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["media"] });
      queryClient.invalidateQueries({ queryKey: ["pools"] });
      setSelectedIds([]);
      setSuiteIndex(null);
    },
  });

  const reapplyTagRules = useMutation({
    mutationFn: async (ids: number[]) => {
      const out: string[] = [];
      for (const id of ids) {
        const r = await api.tags.reapplyRules(id);
        if (r.applied?.length) out.push(...r.applied);
      }
      return { count: ids.length, applied: out.length };
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["media"] });
      queryClient.invalidateQueries({ queryKey: ["tags"] });
    },
  });

  const pendingItems = (media as Array<Record<string, unknown>>).filter((m) => m.status === "pending");
  const pendingIds = pendingItems.map((m) => Number(m.id));
  const toggleSelected = (id: number) => {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };
  const selectAllCurrent = () => setSelectedIds((media as Array<Record<string, unknown>>).map((m) => Number(m.id)));
  const clearSelection = () => setSelectedIds([]);

  /** Display index anchor for Shift+click range (same idea as extension gallery `lastSelectionAnchorIndex`). */
  const gridSelectionAnchorRef = useRef(0);

  const previewable = useMemo(
    () => (media as Array<Record<string, unknown>>).filter((m) => canPreviewInGallery(m)),
    [media]
  );

  const handleGalleryCellPointer = (id: number, displayIdx: number, e: React.MouseEvent) => {
    if (e.shiftKey) {
      e.preventDefault();
      const a = Math.min(gridSelectionAnchorRef.current, displayIdx);
      const b = Math.max(gridSelectionAnchorRef.current, displayIdx);
      const rangeIds = previewable.slice(a, b + 1).map((m) => Number(m.id));
      setSelectedIds(rangeIds);
      return;
    }
    if (e.ctrlKey || e.metaKey) {
      e.preventDefault();
      setSelectedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
      return;
    }
    gridSelectionAnchorRef.current = displayIdx;
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const selectAllPreviewable = () =>
    setSelectedIds(previewable.map((m) => Number(m.id)));

  const openSuiteForId = (id: number) => {
    const idx = previewable.findIndex((m) => Number(m.id) === id);
    if (idx >= 0) setSuiteIndex(idx);
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

  const galleryTransportDocked = viewMode === "grid" && selectedIds.length > 0;

  return (
    <div>
      <MediaMasterSuiteModal
        items={previewable.map((m) => ({ id: Number(m.id), media_type: String(m.media_type || "") }))}
        openIndex={suiteIndex}
        onClose={() => setSuiteIndex(null)}
        onIndexChange={setSuiteIndex}
        onRemoveFromPool={async (id) => {
          const idx = suiteIndex;
          const len = previewable.length;
          await api.media.delete(id);
          setSelectedIds((prev) => prev.filter((x) => x !== id));
          await queryClient.invalidateQueries({ queryKey: ["media"] });
          await queryClient.invalidateQueries({ queryKey: ["pools"] });
          if (idx == null) return;
          if (len <= 1) setSuiteIndex(null);
          else if (idx === len - 1) setSuiteIndex(idx - 1);
          else setSuiteIndex(idx);
        }}
      />
      {llmSuggestMediaId != null && (
        <MediaLlmSuggestModal
          mediaId={llmSuggestMediaId}
          onClose={() => setLlmSuggestMediaId(null)}
          onTagsApplied={() => {
            void queryClient.invalidateQueries({ queryKey: ["media"] });
            void queryClient.invalidateQueries({ queryKey: ["tags"] });
          }}
        />
      )}
      <h1 className="text-2xl font-semibold mb-2">Master media pool</h1>
      <div className="mb-3 flex justify-end">
        <InfoDisclosure>
          Central store for imported media. <strong>List</strong>: click a row to open the <strong>gallery suite</strong> (full-size
          preview, tags, pool routing). <strong>Gallery</strong> grid: click tile to toggle selection; <strong>Ctrl/Cmd+click</strong>{" "}
          toggles one; <strong>Shift+click</strong> selects a range; <strong>double-click</strong> opens suite.
          <br />
          Tag registry:{" "}
          <Link to="/tags" className="text-cyan-400 hover:underline">
            /tags
          </Link>
          . With exactly one selection, <strong>AI suggest</strong> uses <code className="text-slate-400">TBCC_OPENAI_API_KEY</code>.
        </InfoDisclosure>
      </div>
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-3 mb-4 items-stretch">
        <div className="bg-slate-800 border border-slate-600 rounded-lg p-3 min-w-0">
          <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
            <h2 className="text-sm font-medium text-slate-200">Import from Saved Messages</h2>
            <InfoDisclosure>
              <p>
                Adds photos/videos already in your Telegram <strong>Saved Messages</strong> into a <strong>pool</strong> as{" "}
                <strong>pending</strong> media (newest first; skips duplicates already in that pool). Uses the same admin
                account session as other TBCC imports — not the payment bot.
              </p>
            </InfoDisclosure>
          </div>
          <div className="flex flex-wrap gap-2 sm:gap-3 items-end">
            <label className="block text-xs text-slate-400">
              Pool
              <select
                className="mt-1 block bg-slate-900 border border-slate-600 rounded px-2 py-1.5 text-slate-100 text-sm min-w-[8rem]"
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
              Scan up to
              <input
                type="number"
                min={1}
                max={200}
                title="Max messages to scan"
                className="mt-1 block w-20 bg-slate-900 border border-slate-600 rounded px-2 py-1.5 text-slate-100 text-sm"
                value={savedImportLimit}
                onChange={(e) => setSavedImportLimit(Math.min(200, Math.max(1, Number(e.target.value) || 50)))}
              />
            </label>
            <button
              type="button"
              onClick={() => importFromSaved.mutate()}
              disabled={importFromSaved.isPending || !(pools as unknown[]).length}
              className="px-3 py-2 rounded bg-amber-600/90 text-white text-sm font-medium hover:bg-amber-500 disabled:opacity-50 shrink-0"
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

        <div className="bg-slate-800 border border-slate-600 rounded-lg p-3 min-w-0">
          <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
            <h2 className="text-sm font-medium text-slate-200">Upload local files</h2>
            <InfoDisclosure>
              <p>
                Send photos/videos from your computer through the same admin Telegram session as other imports. Choose a{" "}
                <strong>pool</strong> for Media Library rows (except &quot;Saved Messages only&quot;). Destination options
                match the Scheduler: channel or forum topic, or Saved Messages only.
              </p>
            </InfoDisclosure>
          </div>
          <div className="flex flex-wrap gap-2 sm:gap-3 items-end mb-2">
            <label className="block text-xs text-slate-400">
              Pool
              <select
                className="mt-1 block bg-slate-900 border border-slate-600 rounded px-2 py-1.5 text-slate-100 text-sm min-w-[8rem]"
                value={uploadPoolId}
                onChange={(e) => setUploadPoolId(Number(e.target.value))}
                disabled={uploadDestMode === "saved-only"}
                title={
                  uploadDestMode === "saved-only"
                    ? "Not used when sending to Saved Messages only"
                    : "Media is indexed into this pool"
                }
              >
                {(pools as Array<{ id: number; name?: string }>).map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name || `Pool ${p.id}`}
                  </option>
                ))}
              </select>
            </label>
            <label className="block text-xs text-slate-400 flex-1 min-w-[12rem]">
              Telegram destination
              <select
                className="mt-1 block w-full bg-slate-900 border border-slate-600 rounded px-2 py-1.5 text-slate-100 text-sm"
                value={uploadDestMode}
                onChange={(e) => setUploadDestMode(e.target.value as "pool-only" | "channel" | "saved-only")}
              >
                <option value="pool-only">Pool only — pending in library</option>
                <option value="channel">Pool + post to channel / topic</option>
                <option value="saved-only">Saved Messages only (no library rows)</option>
              </select>
            </label>
          </div>
        {uploadDestMode === "channel" && (
          <div className="flex flex-wrap gap-3 items-end mb-3">
            <label className="block text-xs text-slate-400">
              Channel / group
              <select
                className="mt-1 block min-w-[200px] bg-slate-900 border border-slate-600 rounded px-2 py-1.5 text-slate-100 text-sm"
                value={uploadChannelId}
                onChange={(e) => {
                  setUploadChannelId(Number(e.target.value));
                  setUploadThreadId(null);
                }}
              >
                <option value={0}>Select channel</option>
                {(channels as Array<{ id: number; name?: string; identifier?: string }>).map((c) => (
                  <option key={c.id} value={c.id}>
                    {(c.name || c.identifier || `#${c.id}`).slice(0, 48)}
                  </option>
                ))}
              </select>
            </label>
            {uploadChannelId > 0 && (
              <label className="block text-xs text-slate-400">
                Forum topic (optional)
                <select
                  className="mt-1 block min-w-[200px] bg-slate-900 border border-slate-600 rounded px-2 py-1.5 text-slate-100 text-sm"
                  value={uploadThreadId ?? ""}
                  onChange={(e) => {
                    const v = e.target.value;
                    setUploadThreadId(v === "" ? null : Number(v));
                  }}
                >
                  <option value="">Main chat / broadcast</option>
                  {uploadForumTopics.map((t) => (
                    <option key={t.id} value={t.id}>
                      {(t.title || `Topic ${t.id}`).slice(0, 44)}
                    </option>
                  ))}
                </select>
                {uploadForumTopicsHint && (
                  <span className="block text-amber-400/90 text-[11px] mt-1">{uploadForumTopicsHint}</span>
                )}
              </label>
            )}
          </div>
        )}
        {uploadDestMode === "channel" && uploadChannelId > 0 && (
          <label className="flex items-center gap-2 text-xs text-slate-300 mb-3 cursor-pointer">
            <input
              type="checkbox"
              checked={markPostedAfterChannel}
              onChange={(e) => setMarkPostedAfterChannel(e.target.checked)}
            />
            After posting to Telegram, mark media as <strong>posted</strong> in the library
          </label>
        )}
        <label className="block text-xs text-slate-400 mb-3">
          Caption (optional)
          <textarea
            className="mt-1 block w-full max-w-full bg-slate-900 border border-slate-600 rounded px-2 py-1.5 text-slate-100 text-sm"
            rows={2}
            placeholder={
              uploadDestMode === "saved-only"
                ? "Caption on Saved Messages sends (and batches)"
                : uploadDestMode === "channel"
                  ? "Used for the Telegram post to channel/topic (not repeated on each pool import step)"
                  : "Not used for pool-only import (add captions per row or in Scheduler)"
            }
            value={uploadCaption}
            onChange={(e) => setUploadCaption(e.target.value)}
            disabled={uploadDestMode === "pool-only"}
          />
        </label>
        <input
          ref={uploadFileInputRef}
          type="file"
          multiple
          accept="image/*,video/*,.gif,.webp"
          className="hidden"
          onChange={(e) => {
            const input = e.target as HTMLInputElement;
            const snapshot = input.files?.length ? Array.from(input.files) : [];
            input.value = "";
            if (snapshot.length) uploadLocalFiles.mutate(snapshot);
          }}
        />
        <div className="flex flex-wrap gap-2 items-center">
          <button
            type="button"
            onClick={() => uploadFileInputRef.current?.click()}
            disabled={
              uploadLocalFiles.isPending ||
              !(pools as unknown[]).length ||
              (uploadDestMode === "channel" && !uploadChannelId)
            }
            className="px-3 py-2 rounded bg-cyan-700 text-white text-sm font-medium hover:bg-cyan-600 disabled:opacity-50"
          >
            {uploadLocalFiles.isPending ? "Uploading…" : "Choose files…"}
          </button>
          {uploadDestMode === "channel" && !uploadChannelId && (
            <span className="text-amber-400/90 text-xs">Select a channel to enable upload.</span>
          )}
        </div>
        {uploadMsg && (
          <pre className="mt-3 text-xs text-slate-300 whitespace-pre-wrap break-words max-w-full bg-slate-900/80 rounded p-2 border border-slate-600">
            {uploadMsg}
          </pre>
        )}
        </div>
      </div>

      {statusMutationErr && (
        <div className="mb-4 rounded-lg border border-red-700 bg-red-900/30 px-4 py-2 text-sm text-red-200">
          <span className="font-medium">Approve / reject failed: </span>
          {statusMutationErr}
          <button
            type="button"
            onClick={() => setStatusMutationErr(null)}
            className="ml-3 text-red-100 underline hover:no-underline"
          >
            Dismiss
          </button>
        </div>
      )}
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
        <label className="flex items-center gap-2 text-xs text-slate-400">
          Tag slug
          <select
            value={tagSlugFilter}
            onChange={(e) => setTagSlugFilter(e.target.value)}
            className="px-2 py-1 rounded bg-slate-800 border border-slate-600 text-slate-200 max-w-[160px]"
            title="Filter by structured tag (exact slug)"
          >
            <option value="">(any)</option>
            {tagList.map((t) => (
              <option key={t.id} value={t.slug}>
                {t.slug}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2 text-xs text-slate-400">
          Tag text contains
          <input
            type="text"
            value={tagFilter}
            onChange={(e) => setTagFilter(e.target.value)}
            placeholder="substring"
            className="px-2 py-1 rounded bg-slate-800 border border-slate-600 text-slate-200 w-28"
            title="Legacy substring match on combined tag string"
          />
        </label>
        <span className="text-slate-500 text-xs hidden sm:inline">View</span>
        <button
          type="button"
          onClick={() => setViewMode("list")}
          className={`px-3 py-1 rounded text-sm ${viewMode === "list" ? "bg-cyan-600 text-white" : "bg-slate-700 text-slate-300"}`}
        >
          List
        </button>
        <button
          type="button"
          onClick={() => setViewMode("grid")}
          className={`px-3 py-1 rounded text-sm ${viewMode === "grid" ? "bg-cyan-600 text-white" : "bg-slate-700 text-slate-300"}`}
        >
          Gallery
        </button>
        {viewMode === "grid" && (
          <>
            <label className="flex items-center gap-1 text-xs text-slate-400">
              Grid
              <select
                value={gridCols}
                onChange={(e) => setGridCols(Number(e.target.value) as 3 | 5 | 8)}
                className="bg-slate-800 border border-slate-600 rounded px-2 py-1 text-slate-200"
              >
                <option value={3}>3×3</option>
                <option value={5}>5×5</option>
                <option value={8}>8×8</option>
              </select>
            </label>
            {previewable.length > 0 && (
              <>
                <button
                  type="button"
                  onClick={selectAllPreviewable}
                  className="px-3 py-1 rounded bg-slate-600 text-slate-200 text-sm hover:bg-slate-500"
                >
                  Select all in gallery
                </button>
                <button
                  type="button"
                  onClick={clearSelection}
                  disabled={selectedIds.length === 0}
                  className="px-3 py-1 rounded bg-slate-600 text-slate-200 text-sm hover:bg-slate-500 disabled:opacity-50"
                >
                  Clear selection
                </button>
              </>
            )}
          </>
        )}
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className={`ml-auto px-3 py-1 rounded bg-slate-600 text-slate-200 disabled:opacity-50 disabled:cursor-not-allowed`}
        >
          {isFetching ? "Refreshing..." : "Refresh"}
        </button>
      </div>
      {selectedIds.length > 0 && (
        <div
          role="toolbar"
          aria-label={galleryTransportDocked ? "Gallery bulk actions (docked)" : "Bulk media actions"}
          className={`flex flex-wrap gap-2 items-end gap-y-2 ${
            galleryTransportDocked
              ? "fixed bottom-0 left-0 right-0 z-50 border-t border-slate-600 bg-slate-900/95 backdrop-blur-md px-4 py-3 shadow-[0_-12px_40px_rgba(0,0,0,0.5)] max-h-[min(50vh,22rem)] overflow-y-auto pb-[max(0.75rem,env(safe-area-inset-bottom,0px))]"
              : "mb-4 p-3 rounded-lg bg-slate-800/80 border border-slate-600"
          }`}
        >
          <span className="text-slate-300 text-sm shrink-0">
            {galleryTransportDocked && (
              <span className="text-cyan-400/90 font-medium mr-2">Gallery</span>
            )}
            {selectedIds.length} selected — bulk:
          </span>
          <select
            value={bulkPoolId || ""}
            onChange={(e) => setBulkPoolId(Number(e.target.value))}
            className="bg-slate-700 border border-slate-600 rounded px-2 py-1 text-sm text-slate-200"
          >
            <option value="">Move to pool…</option>
            {(pools as Array<{ id: number; name?: string }>).map((p) => (
              <option key={p.id} value={p.id}>
                {p.name || `Pool ${p.id}`}
              </option>
            ))}
          </select>
          <button
            type="button"
            disabled={!bulkPoolId || bulkMovePool.isPending}
            onClick={() => {
              if (!bulkPoolId) return;
              const ids = [...new Set(selectedIds)];
              bulkMovePool.mutate({ ids, poolId: bulkPoolId });
            }}
            className="px-3 py-1 rounded bg-cyan-800 text-cyan-100 text-sm hover:bg-cyan-700 disabled:opacity-50"
          >
            {bulkMovePool.isPending ? "Moving…" : "Move to pool"}
          </button>
          <input
            type="text"
            value={bulkTagsText}
            onChange={(e) => setBulkTagsText(e.target.value)}
            placeholder="tags (comma-separated)"
            className="px-2 py-1 rounded bg-slate-700 border border-slate-600 text-sm text-slate-200 min-w-[160px]"
          />
          <button
            type="button"
            disabled={bulkSetTags.isPending}
            onClick={() => bulkSetTags.mutate({ ids: selectedIds, tags: bulkTagsText })}
            className="px-3 py-1 rounded bg-slate-600 text-slate-200 text-sm hover:bg-slate-500 disabled:opacity-50"
          >
            Set tags
          </button>
          <button
            type="button"
            disabled={reapplyTagRules.isPending || selectedIds.length === 0}
            onClick={() => reapplyTagRules.mutate(selectedIds)}
            className="px-3 py-1 rounded bg-violet-800 text-violet-100 text-sm hover:bg-violet-700 disabled:opacity-50"
            title="Re-run built-in rules; keeps manual tags"
          >
            Re-apply auto rules
          </button>
          <button
            type="button"
            disabled={bulkRemoveFromPool.isPending}
            onClick={() => {
              if (
                !window.confirm(
                  `Remove ${selectedIds.length} item(s) from TBCC / pools? This does not delete the file(s) in Telegram Saved Messages.`
                )
              ) {
                return;
              }
              bulkRemoveFromPool.mutate([...selectedIds]);
            }}
            className="px-3 py-1 rounded bg-amber-900/90 text-amber-100 text-sm hover:bg-amber-800 disabled:opacity-50"
            title="Deletes TBCC media rows only (same as Master suite Remove from pool)"
          >
            {bulkRemoveFromPool.isPending ? "Removing…" : "Remove from pool"}
          </button>
          {selectedIds.length === 1 && (
            <button
              type="button"
              onClick={() => setLlmSuggestMediaId(selectedIds[0])}
              className="px-3 py-1 rounded bg-fuchsia-800 text-fuchsia-100 text-sm hover:bg-fuchsia-700"
              title="Step 2: suggest tags and caption via OpenAI (review before saving)"
            >
              AI suggest (tags + caption)
            </button>
          )}
          {bulkMoveFeedback && (
            <span className="text-slate-200 text-xs basis-full max-w-prose">
              {bulkMoveFeedback}
              <button
                type="button"
                className="ml-2 text-cyan-400 hover:underline"
                onClick={() => setBulkMoveFeedback(null)}
              >
                Dismiss
              </button>
            </span>
          )}
          {bulkRemoveFromPool.isError && (
            <span className="text-red-400 text-xs w-full basis-full">
              {bulkRemoveFromPool.error instanceof Error
                ? bulkRemoveFromPool.error.message
                : String(bulkRemoveFromPool.error)}
            </span>
          )}
        </div>
      )}
      {viewMode === "grid" && (
        <div className={`mb-4 ${galleryTransportDocked ? "pb-40 sm:pb-36" : ""}`}>
          {previewable.length > 0 && (
            <p className="text-slate-500 text-xs mb-2">
              Hover for pool · click / checkbox = toggle · Ctrl/Cmd+click = toggle one · Shift+click = range · double-click = open suite
            </p>
          )}
          <div
            className="grid gap-2"
            style={{ gridTemplateColumns: `repeat(${gridCols}, minmax(0, 1fr))` }}
          >
            {previewable.length === 0 ? (
              <p className="text-slate-500 text-sm col-span-full">
                No previewable items on this page (photos/videos/gif/document).
              </p>
            ) : (
              previewable.map((m, displayIdx) => {
                const id = Number(m.id);
                const poolLabel = poolMap[String(m.pool_id ?? "")] ?? String(m.pool_id ?? "—");
                const statusLabel = String(m.status ?? "—");
                const tagsHint = m.tags ? String(m.tags) : "";
                const selected = selectedIds.includes(id);
                return (
                  <div
                    key={String(m.id)}
                    className={`relative aspect-square rounded-lg overflow-hidden border bg-slate-800 group outline-none focus-within:ring-2 focus-within:ring-cyan-500 ${
                      selected ? "border-cyan-500 ring-1 ring-cyan-500/50" : "border-slate-600 hover:border-cyan-500/60"
                    }`}
                    title={`#${id} · ${poolLabel} · ${statusLabel}${tagsHint ? ` · ${tagsHint}` : ""}`}
                    onDoubleClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      openSuiteForId(id);
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={selected}
                      readOnly
                      className="absolute top-1 left-1 z-20 h-4 w-4 cursor-pointer rounded border-slate-500 bg-slate-900/90 text-cyan-600 shadow"
                      title="Toggle selection (Ctrl/Cmd and Shift supported)"
                      onMouseDown={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                      }}
                      onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        handleGalleryCellPointer(id, displayIdx, e);
                      }}
                    />
                    <button
                      type="button"
                      className="absolute inset-0 z-10 p-0 border-0 cursor-pointer bg-transparent"
                      aria-label={`Media ${id}, ${poolLabel}. Toggle selection; double-click for suite.`}
                      onClick={(e) => handleGalleryCellPointer(id, displayIdx, e)}
                    >
                      <MediaThumbnailCell
                        mediaId={id}
                        mediaType={String(m.media_type || "")}
                        className="w-full h-full object-cover pointer-events-none"
                      />
                    </button>
                    <div
                      className="pointer-events-none absolute bottom-0 left-0 right-0 z-[15] bg-slate-950/85 px-1 py-0.5 text-[10px] leading-tight text-slate-200 opacity-0 transition-opacity group-hover:opacity-100"
                      aria-hidden="true"
                    >
                      <span className="font-medium text-cyan-200/95">{poolLabel}</span>
                      <span className="text-slate-500"> · </span>
                      <span>{statusLabel}</span>
                      {tagsHint ? (
                        <>
                          <span className="text-slate-500"> · </span>
                          <span className="text-slate-400 truncate block">{tagsHint}</span>
                        </>
                      ) : null}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}

      <div className={`overflow-x-auto ${viewMode === "grid" ? "hidden" : ""}`}>
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
              <th className="text-left p-3">Tags</th>
              <th className="text-left p-3" title="Per-pool deduplication key">
                Dedup
              </th>
              <th className="text-left p-3">Created</th>
              <th className="text-left p-3">Actions</th>
            </tr>
          </thead>
          <tbody>
            {media.map((m: Record<string, unknown>) => (
              <tr
                key={String(m.id)}
                className={`border-t border-slate-600 hover:bg-slate-800/50 ${
                  canPreviewInGallery(m) ? "cursor-pointer" : "cursor-default"
                }`}
                onClick={(e) => {
                  const t = e.target as HTMLElement;
                  if (t.closest("input, button, textarea, a, label")) return;
                  if (!canPreviewInGallery(m)) return;
                  openSuiteForId(Number(m.id));
                }}
                title={canPreviewInGallery(m) ? "Click row to open gallery suite (preview + tags + pool)" : ""}
              >
                <td className="p-3">
                  <input
                    type="checkbox"
                    checked={selectedIds.includes(Number(m.id))}
                    onChange={() => toggleSelected(Number(m.id))}
                    onDoubleClick={(e) => e.stopPropagation()}
                    title="Select for bulk action"
                  />
                </td>
                <td className="p-3 w-[4.5rem]">
                  <div className="w-14 h-14 rounded overflow-hidden flex items-center justify-center border border-slate-600">
                    {canPreviewInGallery(m) ? (
                      <MediaThumbnailCell
                        mediaId={Number(m.id)}
                        mediaType={String(m.media_type || "")}
                        className="w-full h-full object-cover pointer-events-none"
                      />
                    ) : (
                      <span className="text-slate-500 text-xs px-1">{String(m.media_type || "—")}</span>
                    )}
                  </div>
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
                <td className="p-3 text-slate-400 text-xs max-w-[140px] truncate" title={String(m.tags ?? "")}>
                  {m.tags ? String(m.tags) : "—"}
                </td>
                <td className="p-3 text-slate-500 font-mono text-[10px] max-w-[100px] truncate" title={String(m.file_unique_id ?? "")}>
                  {m.file_unique_id ? String(m.file_unique_id).slice(0, 16) + (String(m.file_unique_id).length > 16 ? "…" : "") : "—"}
                </td>
                <td className="p-3 text-slate-400 text-sm">{String(m.created_at ?? "").slice(0, 19)}</td>
                <td className="p-3">
                  {m.status === "pending" && (
                    <div className="flex gap-1" onClick={(e) => e.stopPropagation()}>
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          updateStatus.mutate({ id: Number(m.id), status: "approved" });
                        }}
                        disabled={updateStatus.isPending}
                        className="px-2 py-0.5 rounded text-sm bg-green-700 text-green-100 hover:bg-green-600 disabled:opacity-50"
                      >
                        Approve
                      </button>
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          updateStatus.mutate({ id: Number(m.id), status: "rejected" });
                        }}
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
      <div className="mt-8 pt-6 border-t border-slate-700">
        <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
          <h2 className="text-xl font-semibold">Pools & channels</h2>
          <InfoDisclosure>
            Pool/channel management lives here. Autonomous pool posting is disabled; use Scheduler for all planned
            publishing.
          </InfoDisclosure>
        </div>
        <ContentPools />
      </div>
    </div>
  );
}
