import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { GalleryLazyThumb } from "../components/GalleryLazyThumb";
import { QueryErrorBanner } from "../components/QueryErrorBanner";
import { ApprovalQueueCounter } from "../components/ApprovalQueueCounter";
import { MediaMasterSuiteModal } from "../components/MediaMasterSuiteModal";
import type { GalleryMediaItem } from "../components/MediaGalleryModal";

const GALLERY_PAGE_SIZE = 24;

type GalleryRow = {
  id: number;
  media_type?: string;
  status?: string;
  pool_id?: number;
  nsfw_tier?: string;
};

type LayoutMode = "scroll" | "grid";

export function PoolCurateGallery() {
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const poolId = Math.max(0, Number(searchParams.get("pool_id") || 0));
  const statusFilter = searchParams.get("status") || "pending";
  const [layout, setLayout] = useState<LayoutMode>("grid");
  const [suiteIndex, setSuiteIndex] = useState<number | null>(null);
  const [pageIndex, setPageIndex] = useState(0);
  /** before_id cursor for page N = last id seen on page N-1 */
  const [pageCursors, setPageCursors] = useState<(number | undefined)[]>([undefined]);

  const { data: pools = [] } = useQuery({
    queryKey: ["pools"],
    queryFn: () => api.pools.list(),
    staleTime: 60_000,
  });

  const poolMap = useMemo(
    () =>
      Object.fromEntries(
        (pools as Array<{ id: number; name?: string }>).map((p) => [String(p.id), p.name || `Pool ${p.id}`])
      ),
    [pools]
  );

  const beforeId = pageIndex > 0 ? pageCursors[pageIndex - 1] : undefined;

  const {
    data: rows = [],
    isPending,
    isError,
    error,
    isFetching,
    refetch,
  } = useQuery({
    queryKey: ["pool-gallery-page", poolId, statusFilter, pageIndex, beforeId],
    enabled: poolId > 0,
    queryFn: () =>
      api.media.listGalleryPage({
        pool_id: poolId,
        status: statusFilter === "all" ? undefined : statusFilter,
        limit: GALLERY_PAGE_SIZE,
        before_id: beforeId,
      }),
    staleTime: 30_000,
    gcTime: 120_000,
  });

  const hasNextPage = rows.length >= GALLERY_PAGE_SIZE;

  useEffect(() => {
    setPageIndex(0);
    setPageCursors([undefined]);
  }, [poolId, statusFilter]);

  useEffect(() => {
    if (!rows.length) return;
    const ids = rows.map((m) => Number(m.id)).filter((n) => n > 0);
    if (!ids.length) return;
    api.media.warmThumbnails(ids).catch(() => {});
  }, [rows]);

  const patchStatus = useMutation({
    mutationFn: ({ id, status }: { id: number; status: string }) => api.media.updateStatus(id, status),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["pool-gallery-page", poolId, statusFilter] });
      queryClient.invalidateQueries({ queryKey: ["media-pending-summary"] });
    },
  });

  const setPoolParam = useCallback(
    (id: number) => {
      const next = new URLSearchParams(searchParams);
      if (id > 0) next.set("pool_id", String(id));
      else next.delete("pool_id");
      setSearchParams(next, { replace: true });
    },
    [searchParams, setSearchParams]
  );

  const setStatusParam = useCallback(
    (st: string) => {
      const next = new URLSearchParams(searchParams);
      if (st && st !== "pending") next.set("status", st);
      else next.delete("status");
      setSearchParams(next, { replace: true });
    },
    [searchParams, setSearchParams]
  );

  const goPrev = () => setPageIndex((i) => Math.max(0, i - 1));

  const goNext = () => {
    if (!hasNextPage || rows.length === 0) return;
    const lastId = Number(rows[rows.length - 1]?.id);
    if (!Number.isFinite(lastId) || lastId <= 0) return;
    setPageCursors((prev) => {
      const next = [...prev];
      next[pageIndex] = lastId;
      return next;
    });
    setPageIndex((i) => i + 1);
  };

  const galleryItems: GalleryMediaItem[] = useMemo(
    () =>
      rows.map((m) => ({
        id: Number(m.id),
        media_type: String(m.media_type || ""),
      })),
    [rows]
  );

  useEffect(() => {
    if (suiteIndex == null) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setSuiteIndex(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [suiteIndex]);

  const poolName = poolId > 0 ? poolMap[String(poolId)] : undefined;

  return (
    <div className="max-w-4xl mx-auto">
      <MediaMasterSuiteModal
        items={galleryItems}
        openIndex={suiteIndex}
        onClose={() => setSuiteIndex(null)}
        onIndexChange={setSuiteIndex}
      />
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">Pool gallery</h1>
          <p className="text-xs text-slate-500 mt-1 max-w-xl">
            Isolated from Media Library — <strong className="text-slate-400">one page at a time</strong> (24 rows),
            cache-only by default so imports and posters are not starved. Warm previews only for the current page on
            demand.
          </p>
        </div>
        <Link to="/" className="ml-auto text-xs text-cyan-400 hover:underline">
          ← Media Library
        </Link>
      </div>

      <ApprovalQueueCounter
        className="mb-3"
        poolId={poolId > 0 ? poolId : undefined}
        poolName={poolName}
      />

      <div className="mb-4 flex flex-wrap gap-3 items-center rounded-lg border border-slate-700 bg-slate-800/60 p-3">
        <label className="text-xs text-slate-400">
          Pool
          <select
            value={poolId || ""}
            onChange={(e) => setPoolParam(Number(e.target.value))}
            className="mt-1 block min-w-[12rem] bg-slate-700 border border-slate-600 rounded px-2 py-1.5 text-sm text-slate-200"
          >
            <option value="">Select pool…</option>
            {(pools as Array<{ id: number; name?: string }>).map((p) => (
              <option key={p.id} value={p.id}>
                {p.name || `Pool ${p.id}`}
              </option>
            ))}
          </select>
        </label>
        <label className="text-xs text-slate-400">
          Status
          <select
            value={statusFilter}
            onChange={(e) => setStatusParam(e.target.value)}
            className="mt-1 block bg-slate-700 border border-slate-600 rounded px-2 py-1.5 text-sm text-slate-200"
          >
            <option value="pending">pending</option>
            <option value="approved">approved</option>
            <option value="rejected">rejected</option>
            <option value="all">all</option>
          </select>
        </label>
        <label className="text-xs text-slate-400">
          Layout
          <select
            value={layout}
            onChange={(e) => setLayout(e.target.value as LayoutMode)}
            className="mt-1 block bg-slate-700 border border-slate-600 rounded px-2 py-1.5 text-sm text-slate-200"
          >
            <option value="grid">Grid 3×3</option>
            <option value="scroll">Scroll (large)</option>
          </select>
        </label>
        <button
          type="button"
          onClick={() => refetch()}
          className="self-end px-3 py-1.5 rounded bg-slate-600 text-slate-200 text-sm hover:bg-slate-500"
        >
          Refresh
        </button>
      </div>

      {poolId <= 0 ? (
        <p className="text-slate-500 text-sm">Pick a pool to browse. Open from Content Pools → Curate, or set ?pool_id=.</p>
      ) : isError ? (
        <QueryErrorBanner
          title="Pool gallery failed to load"
          message={error instanceof Error ? error.message : String(error)}
          onRetry={() => refetch()}
        />
      ) : isPending ? (
        <p className="text-slate-500 text-sm animate-pulse">Loading page…</p>
      ) : rows.length === 0 ? (
        <p className="text-slate-500 text-sm">No items in {poolMap[String(poolId)] ?? `pool ${poolId}`} ({statusFilter}).</p>
      ) : (
        <>
          <div className="mb-3 flex flex-wrap items-center gap-2 text-xs text-slate-500">
            <span>
              Page <strong className="text-slate-300">{pageIndex + 1}</strong> · {rows.length} items ·{" "}
              {poolMap[String(poolId)]} · {statusFilter}
            </span>
            <span className="text-slate-600">|</span>
            <button
              type="button"
              disabled={pageIndex === 0 || isFetching}
              onClick={goPrev}
              className="px-2 py-0.5 rounded bg-slate-700 text-slate-200 disabled:opacity-40"
            >
              ← Prev
            </button>
            <button
              type="button"
              disabled={!hasNextPage || isFetching}
              onClick={goNext}
              className="px-2 py-0.5 rounded bg-slate-700 text-slate-200 disabled:opacity-40"
            >
              Next →
            </button>
            {isFetching && <span className="text-slate-600 animate-pulse">Loading…</span>}
            <span className="text-emerald-600/80">previews warm in background</span>
          </div>
          <div
            className={
              layout === "grid"
                ? "grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 max-h-[70vh] overflow-y-auto pr-1"
                : "flex flex-col gap-4 max-h-[70vh] overflow-y-auto pr-1"
            }
          >
            {rows.map((m, idx) => {
              const id = Number(m.id);
              const st = String(m.status || "pending");
              return (
                <article
                  key={id}
                  className={`rounded-lg border border-slate-700 overflow-hidden bg-slate-800/40 ${
                    layout === "scroll" ? "shadow-lg shrink-0" : ""
                  }`}
                >
                  <GalleryLazyThumb
                    mediaId={id}
                    mediaType={String(m.media_type || "")}
                    fit={layout === "grid" ? "cover" : "contain"}
                    className={layout === "grid" ? "aspect-square" : "min-h-[160px] max-h-[50vh]"}
                    onOpen={() => setSuiteIndex(idx)}
                  />
                  <div className="flex flex-wrap items-center gap-2 px-2 py-2 border-t border-slate-700/80">
                    <span className="text-xs text-slate-400 font-mono">#{id}</span>
                    <span className="text-xs text-slate-500">{st}</span>
                    <div className="ml-auto flex gap-1">
                      {st !== "approved" && (
                        <button
                          type="button"
                          disabled={patchStatus.isPending}
                          onClick={() => patchStatus.mutate({ id, status: "approved" })}
                          className="px-2 py-0.5 rounded text-xs bg-emerald-900/80 text-emerald-100 hover:bg-emerald-800 disabled:opacity-50"
                        >
                          Approve
                        </button>
                      )}
                      {st !== "rejected" && (
                        <button
                          type="button"
                          disabled={patchStatus.isPending}
                          onClick={() => patchStatus.mutate({ id, status: "rejected" })}
                          className="px-2 py-0.5 rounded text-xs bg-red-900/60 text-red-100 hover:bg-red-800 disabled:opacity-50"
                        >
                          Reject
                        </button>
                      )}
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
