import Link from "next/link";
import { createClient } from "@/lib/supabase/server";
import { resolveMediaUrl } from "@/lib/media-url";

export const dynamic = "force-dynamic";

export default async function GalleriesIndex() {
  const db = await createClient();
  const { data, error } = await db
    .from("galleries")
    .select("id, slug, title, description, cover_media_id, item_count, views_count, score, created_at, owner_id")
    .eq("is_public", true)
    .order("score", { ascending: false })
    .limit(60);
  if (error) return <div className="empty">Error: {error.message}</div>;

  const galleries = data ?? [];
  const coverIds = galleries.map((g) => g.cover_media_id).filter((x): x is number => x != null);
  const coversById = new Map<number, string>();
  if (coverIds.length) {
    const { data: covers } = await db.from("media_items").select("id, b2_key").in("id", coverIds);
    for (const c of covers ?? []) coversById.set(c.id, await resolveMediaUrl(c.b2_key));
  }

  return (
    <>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: "1rem" }}>
        <h1 style={{ margin: 0 }}>Galleries</h1>
        <Link href="/g/new" className="primary" style={{ padding: "0.35rem 0.85rem", textDecoration: "none" }}>
          New gallery
        </Link>
      </div>
      {galleries.length === 0 ? (
        <div className="empty muted">
          No public galleries yet.{" "}
          <Link href="/g/new">Create your first gallery</Link>.
        </div>
      ) : (
        <div className="grid">
          {galleries.map((g) => (
            <Link key={g.id} href={`/g/${g.slug}`} className="media-card">
              <div className="thumb">
                {g.cover_media_id && coversById.get(g.cover_media_id) ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={coversById.get(g.cover_media_id)} alt={g.title} loading="lazy" />
                ) : (
                  <div className="empty" style={{ height: "100%" }}>No cover</div>
                )}
                <span className="badge">{g.item_count}</span>
              </div>
              <div className="meta">
                <div className="title">{g.title}</div>
                <div className="sub"><span>{g.views_count.toLocaleString()} views</span></div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </>
  );
}
