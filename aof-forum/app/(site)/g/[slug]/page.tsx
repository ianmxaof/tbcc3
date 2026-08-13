import { notFound } from "next/navigation";
import Link from "next/link";
import type { Metadata } from "next";
import { createClient } from "@/lib/supabase/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { resolveMediaUrl } from "@/lib/media-url";
import { MediaGrid } from "@/components/MediaGrid";
import { VoteButtons } from "@/components/VoteButtons";
import { RelatedGalleriesPanel } from "@/components/RelatedGalleriesPanel";
import { TelegramConversionFooter } from "@/components/TelegramConversionFooter";
import { JsonLd } from "@/components/JsonLd";

export const dynamic = "force-dynamic";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const db = createAdminClient();
  const { data: gallery } = await db
    .from("galleries")
    .select("title, description, cover_media_id, item_count, views_count, is_public")
    .eq("slug", slug)
    .maybeSingle();
  if (!gallery || !gallery.is_public) return { title: "Gallery not found — AOF Hub" };

  const title = `${gallery.title} — AOF Hub`;
  const description =
    gallery.description?.trim() ||
    `${gallery.item_count} items · ${gallery.views_count.toLocaleString()} views on AOF Hub.`;

  // Only attach an OG image once NEXT_PUBLIC_MEDIA_BASE_URL (stable CDN URL) is
  // set. Without it, resolveMediaUrl() falls back to a 1-hour presigned B2 URL —
  // fine for a live page render, but Telegram/X/Discord snapshot the OG image URL
  // at share time and will keep serving a 403'd preview long after it expires.
  let coverUrl: string | undefined;
  if (gallery.cover_media_id && process.env.NEXT_PUBLIC_MEDIA_BASE_URL) {
    const { data: cover } = await db
      .from("media_items")
      .select("b2_key")
      .eq("id", gallery.cover_media_id)
      .maybeSingle();
    if (cover?.b2_key) coverUrl = await resolveMediaUrl(cover.b2_key as string);
  }

  return {
    title,
    description,
    alternates: { canonical: `/g/${slug}` },
    openGraph: {
      title,
      description,
      type: "website",
      images: coverUrl ? [{ url: coverUrl }] : undefined,
    },
    twitter: { card: "summary_large_image", title, description },
  };
}

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
      {gallery.is_public && (
        <JsonLd
          data={{
            "@context": "https://schema.org",
            "@type": "ImageGallery",
            name: gallery.title,
            description: gallery.description || undefined,
            url: `${(process.env.NEXT_PUBLIC_SITE_URL || "http://127.0.0.1:3001").replace(/\/$/, "")}/g/${slug}`,
            numberOfItems: gallery.item_count,
          }}
        />
      )}
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

      {gallery.is_public && (
        <TelegramConversionFooter
          context={{ surface: "gallery", slug }}
          title="Unlock the full network"
        />
      )}
    </article>
  );
}
