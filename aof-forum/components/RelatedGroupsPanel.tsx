"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";

interface RelatedGroup {
  id: number;
  slug: string;
  name: string;
  description: string | null;
  member_count: number;
  item_count: number;
  score: number;
}

export function RelatedGroupsPanel({ slug }: { slug: string }) {
  const q = useQuery<{ items: RelatedGroup[] }>({
    queryKey: ["related-groups", slug],
    queryFn: async () => {
      const r = await fetch(`/api/groups/${encodeURIComponent(slug)}/related`);
      if (!r.ok) return { items: [] as RelatedGroup[] };
      return r.json();
    },
  });
  return (
    <section style={{ marginTop: "1.5rem" }}>
      <h2>Related Groups</h2>
      {q.isLoading && <div className="empty"><span className="spinner" /></div>}
      {q.data && q.data.items.length === 0 && (
        <div className="empty muted">No related groups yet — members need to overlap with other groups first.</div>
      )}
      {q.data && q.data.items.length > 0 && (
        <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))" }}>
          {q.data.items.map((g) => (
            <Link key={g.id} href={`/groups/${g.slug}`} className="group-card">
              <div className="name">{g.name}</div>
              {g.description && <div className="desc">{g.description}</div>}
              <div className="stats">
                <span>{g.member_count.toLocaleString()} members</span>
                <span>{g.item_count.toLocaleString()} items</span>
                <span className="muted">sim {(g.score * 100).toFixed(0)}%</span>
              </div>
            </Link>
          ))}
        </div>
      )}
    </section>
  );
}
