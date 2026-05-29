"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";

interface Row {
  id: number;
  slug: string;
  title: string;
  description: string | null;
  item_count: number;
  score: number;
  reason: string;
}

export function RelatedGalleriesPanel({ slug }: { slug: string }) {
  const q = useQuery<{ items: Row[] }>({
    queryKey: ["related-galleries", slug],
    queryFn: async () => {
      const r = await fetch(`/api/galleries/${encodeURIComponent(slug)}/related`);
      if (!r.ok) throw new Error("related galleries failed");
      return r.json();
    },
  });
  return (
    <section style={{ marginTop: "1.5rem" }}>
      <h2>Related galleries</h2>
      <p className="muted" style={{ fontSize: "0.85rem", marginTop: 0 }}>
        Same curator and tag overlap with this collection.
      </p>
      {q.isLoading && (
        <div className="empty">
          <span className="spinner" />
        </div>
      )}
      {q.data && q.data.items.length === 0 && (
        <div className="empty muted">No related galleries yet.</div>
      )}
      {q.data && q.data.items.length > 0 && (
        <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))" }}>
          {q.data.items.map((g) => (
            <Link key={g.id} href={`/g/${g.slug}`} className="group-card">
              <div className="name">{g.title}</div>
              {g.description && <div className="desc">{g.description}</div>}
              <div className="stats">
                <span>{g.item_count} items</span>
                <span className="muted">{g.reason === "same_owner" ? "same owner" : "shared tags"}</span>
              </div>
            </Link>
          ))}
        </div>
      )}
    </section>
  );
}
