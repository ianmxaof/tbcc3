"use client";

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useInfiniteQuery } from "@tanstack/react-query";
import { useWindowVirtualizer } from "@tanstack/react-virtual";
import { MediaCard, type MediaCardItem } from "./MediaCard";
import type { ViewContext } from "@/lib/types";

interface FeedPage {
  items: MediaCardItem[];
  nextCursor: string | null;
}

/** Align with `.grid` in globals.css: minmax(220px) and gap 0.75rem / 1rem. */
const MIN_CARD_PX = 220;
const GAP_NARROW = 12;
const GAP_WIDE = 16;

function chunk<T>(arr: T[], size: number): T[][] {
  if (size <= 0) return [];
  const out: T[][] = [];
  for (let i = 0; i < arr.length; i += size) out.push(arr.slice(i, i + size));
  return out;
}

/**
 * Infinite-scroll media grid. Hits any endpoint that returns
 *   { items: MediaCardItem[], nextCursor: string | null }
 * and supports `?cursor=` pagination.
 *
 * Long feeds use window-based row virtualization (fixed rows × responsive columns).
 */
export function MediaGrid({
  endpoint,
  context = "feed",
  sourceId = null,
  queryKey,
  autoplayVideo = true,
  emptyMessage = "No items yet.",
  groupLinkSlug,
}: {
  endpoint: string;
  context?: ViewContext;
  sourceId?: number | null;
  queryKey: unknown[];
  autoplayVideo?: boolean;
  emptyMessage?: string;
  /** Passed through to card links as `?group=` on `/m/[id]`. */
  groupLinkSlug?: string;
}) {
  const sentinelRef = useRef<HTMLDivElement | null>(null);
  const parentRef = useRef<HTMLDivElement | null>(null);
  const [layout, setLayout] = useState({ colCount: 3, rowHeight: 300, gap: GAP_NARROW });
  const [scrollMargin, setScrollMargin] = useState(0);

  const q = useInfiniteQuery<FeedPage>({
    queryKey,
    queryFn: async ({ pageParam }) => {
      const url = new URL(endpoint, window.location.origin);
      if (pageParam) url.searchParams.set("cursor", String(pageParam));
      const r = await fetch(url.toString(), { credentials: "include" });
      if (!r.ok) throw new Error(`feed ${r.status}`);
      return (await r.json()) as FeedPage;
    },
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.nextCursor,
  });

  useEffect(() => {
    const el = sentinelRef.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting && q.hasNextPage && !q.isFetchingNextPage) {
          q.fetchNextPage();
        }
      },
      { rootMargin: "1200px 0px" }
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, [q]);

  const all = useMemo(() => q.data?.pages.flatMap((p) => p.items) ?? [], [q.data?.pages]);
  const rows = useMemo(() => chunk(all, layout.colCount), [all, layout.colCount]);

  useLayoutEffect(() => {
    const root = parentRef.current;
    if (!root) return;
    const update = () => {
      const width = root.getBoundingClientRect().width;
      const wide = typeof window !== "undefined" && window.matchMedia("(min-width: 1100px)").matches;
      const gap = wide ? GAP_WIDE : GAP_NARROW;
      const colCount = Math.max(1, Math.floor((width + gap) / (MIN_CARD_PX + gap)));
      const capped = Math.min(colCount, 12);
      const cardW = capped > 0 ? (width - (capped - 1) * gap) / capped : width;
      const thumbH = cardW * 0.75;
      const rowHeight = Math.ceil(thumbH + 72 + gap);
      setLayout({ colCount: capped, rowHeight, gap });
      const top = root.getBoundingClientRect().top + window.scrollY;
      setScrollMargin(Math.round(top));
    };
    update();
    const ro = new ResizeObserver(update);
    ro.observe(root);
    window.addEventListener("resize", update);
    return () => {
      ro.disconnect();
      window.removeEventListener("resize", update);
    };
  }, [all.length]);

  const rowVirtualizer = useWindowVirtualizer({
    count: rows.length,
    estimateSize: () => layout.rowHeight,
    overscan: 5,
    scrollMargin,
  });

  if (q.isLoading) return <div className="empty">Loading...</div>;
  if (q.isError) return <div className="empty">Couldn&apos;t load feed: {(q.error as Error).message}</div>;
  if (all.length === 0) return <div className="empty">{emptyMessage}</div>;

  return (
    <>
      <div ref={parentRef}>
        <div style={{ height: `${rowVirtualizer.getTotalSize()}px`, position: "relative", width: "100%" }}>
          {rowVirtualizer.getVirtualItems().map((vRow) => {
            const rowItems = rows[vRow.index];
            if (!rowItems?.length) return null;
            return (
              <div
                key={vRow.key}
                style={{
                  position: "absolute",
                  top: 0,
                  left: 0,
                  width: "100%",
                  transform: `translateY(${vRow.start}px)`,
                }}
              >
                <div
                  className="grid"
                  style={{
                    gridTemplateColumns: `repeat(${layout.colCount}, minmax(0, 1fr))`,
                    gap: layout.gap,
                    marginBottom: 0,
                  }}
                >
                  {rowItems.map((it) => (
                    <MediaCard
                      key={`${it.id}-${queryKey.join(":")}-${vRow.index}`}
                      item={it}
                      context={context}
                      sourceId={sourceId}
                      autoplayVideo={autoplayVideo}
                      groupLinkSlug={groupLinkSlug}
                    />
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </div>
      <div ref={sentinelRef} className="scroll-sentinel">
        {q.isFetchingNextPage ? <span className="spinner" /> : q.hasNextPage ? "" : "End of feed"}
      </div>
    </>
  );
}
