"use client";

import { useQuery } from "@tanstack/react-query";
import { MediaCard, type MediaCardItem } from "./MediaCard";

/**
 * "Related" panel placed under a media item / gallery / group. This is the
 * Motherless-style addictive loop entry point.
 */
export function RelatedPanel({
  mediaId,
  limit = 24,
  title = "You might also like",
  groupSlug = null,
}: {
  mediaId: number;
  limit?: number;
  title?: string;
  /** When set (e.g. `?group=` on the media page), related picks from that group&apos;s corpus only. */
  groupSlug?: string | null;
}) {
  const q = useQuery<{ items: MediaCardItem[] }>({
    queryKey: ["related", mediaId, limit, groupSlug],
    queryFn: async () => {
      const u = new URL("/api/related", window.location.origin);
      u.searchParams.set("media_id", String(mediaId));
      u.searchParams.set("limit", String(limit));
      if (groupSlug) u.searchParams.set("group_slug", groupSlug);
      const r = await fetch(u.toString(), { credentials: "include" });
      if (!r.ok) throw new Error("related failed");
      return r.json();
    },
  });
  const relatedTitle = groupSlug ? `More in this group` : title;
  return (
    <section style={{ marginTop: "1.5rem" }}>
      <h2>{relatedTitle}</h2>
      {q.isLoading && <div className="empty"><span className="spinner" /></div>}
      {q.isError && <div className="empty">Couldn&apos;t load related</div>}
      {!q.isLoading && q.data && q.data.items.length === 0 && <div className="empty muted">Nothing related yet — try tagging this item.</div>}
      {q.data && q.data.items.length > 0 && (
        <div className="grid">
          {q.data.items.map((it) => (
            <MediaCard
              key={it.id}
              item={it}
              context="related"
              sourceId={mediaId}
              groupLinkSlug={groupSlug ?? undefined}
            />
          ))}
        </div>
      )}
    </section>
  );
}
