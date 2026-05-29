import { notFound } from "next/navigation";
import Link from "next/link";
import { createClient } from "@/lib/supabase/server";
import { MediaGrid } from "@/components/MediaGrid";
import { VoteButtons } from "@/components/VoteButtons";
import { RelatedGalleriesPanel } from "@/components/RelatedGalleriesPanel";

export const dynamic = "force-dynamic";

export default async function GalleryPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const db = await createClient();

  const { data: gallery, error } = await db
    .from("galleries")
    .select("id, slug, title, description, owner_id, item_count, views_count, votes_up, votes_down, score, is_public, created_at")
    .eq("slug", slug)
    .maybeSingle();
  if (error || !gallery) notFound();

  const [{ data: owner }, { data: vote }] = await Promise.all([
    db.from("profiles").select("handle, display_name").eq("id", gallery.owner_id).maybeSingle(),
    db.from("votes").select("value").eq("target_kind", "gallery").eq("target_id", gallery.id).maybeSingle(),
  ]);

  return (
    <article>
      <header style={{ display: "flex", flexWrap: "wrap", gap: "0.75rem", alignItems: "baseline" }}>
        <h1 style={{ margin: 0, flex: 1 }}>{gallery.title}</h1>
        <VoteButtons
          targetKind="gallery"
          targetId={gallery.id}
          initialUp={gallery.votes_up}
          initialDown={gallery.votes_down}
          initialValue={(vote?.value as -1 | 0 | 1 | undefined) ?? 0}
        />
      </header>
      <div className="muted" style={{ marginBottom: "1rem" }}>
        {owner && (
          <>
            by <Link href={`/u/${owner.handle}`}>{owner.display_name || owner.handle}</Link>{" "}
          </>
        )}
        · {gallery.item_count} items · {gallery.views_count.toLocaleString()} views
      </div>
      {gallery.description && <p>{gallery.description}</p>}

      {gallery.item_count === 0 ? (
        <div className="empty muted">Empty gallery.</div>
      ) : (
        <MediaGrid
          endpoint={`/api/galleries/${encodeURIComponent(slug)}/media?limit=24`}
          context="gallery"
          sourceId={gallery.id}
          queryKey={["gallery-media", slug, gallery.id]}
          emptyMessage="No items."
        />
      )}

      <RelatedGalleriesPanel slug={slug} />
    </article>
  );
}
