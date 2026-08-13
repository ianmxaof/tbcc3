import { notFound } from "next/navigation";
import Link from "next/link";
import type { Metadata } from "next";
import { createClient } from "@/lib/supabase/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { relatedTags } from "@/lib/reco";
import { MediaGrid } from "@/components/MediaGrid";
import { FollowButton } from "@/components/FollowButton";
import { TagPill } from "@/components/Tag";
import { TelegramConversionFooter } from "@/components/TelegramConversionFooter";
import { LivePerformerCta } from "@/components/LivePerformerCta";
import { JsonLd } from "@/components/JsonLd";

export const dynamic = "force-dynamic";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const db = createAdminClient();
  const { data: tag } = await db
    .from("tags")
    .select("name, kind, description, cover_url, uses_count")
    .eq("slug", slug)
    .maybeSingle();
  if (!tag) return { title: "Tag not found — AOF Hub" };

  const title = `${tag.name} (${tag.kind}) — AOF Hub`;
  const description =
    tag.description?.trim() ||
    `${(tag.uses_count ?? 0).toLocaleString()} items tagged ${tag.name} on AOF Hub.`;
  return {
    title,
    description,
    alternates: { canonical: `/t/${slug}` },
    openGraph: {
      title,
      description,
      type: "website",
      images: tag.cover_url ? [{ url: tag.cover_url }] : undefined,
    },
    twitter: { card: "summary_large_image", title, description },
  };
}

export default async function TagPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const db = await createClient();

  const { data: tag } = await db
    .from("tags")
    .select("id, slug, name, kind, description, cover_url, uses_count")
    .eq("slug", slug)
    .maybeSingle();
  if (!tag) notFound();

  const [{ data: u }, { data: followRow }, co] = await Promise.all([
    db.auth.getUser(),
    db
      .from("follows")
      .select("follower_id")
      .eq("target_kind", "tag")
      .eq("target_object_id", tag.id)
      .maybeSingle(),
    relatedTags(tag.id, 20),
  ]);

  return (
    <article>
      <JsonLd
        data={{
          "@context": "https://schema.org",
          "@type": "CollectionPage",
          name: tag.name,
          description: tag.description || `${tag.name} on AOF Hub`,
          url: `${(process.env.NEXT_PUBLIC_SITE_URL || "http://127.0.0.1:3001").replace(/\/$/, "")}/t/${slug}`,
        }}
      />
      <header style={{ display: "flex", flexWrap: "wrap", gap: "0.75rem", alignItems: "baseline" }}>
        <h1 style={{ margin: 0, flex: 1 }}>
          {tag.name}{" "}
          <span className="muted" style={{ fontSize: "0.85rem", fontWeight: 400 }}>
            ({tag.kind})
          </span>
        </h1>
        {u.user && (
          <FollowButton
            targetKind="tag"
            targetObjectId={tag.id}
            initial={!!followRow}
          />
        )}
      </header>
      <div className="muted" style={{ marginBottom: "1rem" }}>{tag.uses_count?.toLocaleString?.() ?? 0} items</div>
      {tag.description && <p>{tag.description}</p>}

      {tag.kind === "performer" && (
        <LivePerformerCta tagSlug={slug} performerName={tag.name} />
      )}

      {co.length > 0 && (
        <section style={{ margin: "1rem 0" }}>
          <h3 style={{ marginBottom: "0.5rem" }}>Often appears with</h3>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {co.map((t) => (
              <TagPill key={t.id} slug={t.slug} name={`${t.name} · ${t.c}`} kind={t.kind} />
            ))}
          </div>
        </section>
      )}

      <h2>Media</h2>
      <MediaGrid
        endpoint={`/api/tags/${encodeURIComponent(slug)}/feed?limit=24`}
        context="tag"
        sourceId={tag.id}
        queryKey={["tag-feed", slug]}
      />

      <TelegramConversionFooter context={{ surface: "tag", slug }} title="More on Telegram" />
    </article>
  );
}
