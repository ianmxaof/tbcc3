import { notFound } from "next/navigation";
import Link from "next/link";
import type { Metadata } from "next";
import { createClient } from "@/lib/supabase/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { resolveMediaUrl } from "@/lib/media-url";
import { Player } from "@/components/Player";
import { TagList } from "@/components/Tag";
import { VoteButtons } from "@/components/VoteButtons";
import { BookmarkButton } from "@/components/BookmarkButton";
import { ReportButton } from "@/components/ReportButton";
import { RelatedPanel } from "@/components/RelatedPanel";
import { TelegramConversionFooter } from "@/components/TelegramConversionFooter";
import { JsonLd } from "@/components/JsonLd";
import type { TagKind } from "@/lib/types";

export const dynamic = "force-dynamic";

interface PageProps {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ group?: string }>;
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { id: idStr } = await params;
  const id = Number.parseInt(idStr, 10);
  if (!Number.isFinite(id) || id <= 0) return { title: "Media not found — AOF Hub" };

  const db = createAdminClient();
  const { data: m } = await db
    .from("media_items")
    .select("title, description, b2_key, b2_thumb_key, views_count, is_public, is_deleted")
    .eq("id", id)
    .maybeSingle();
  if (!m || !m.is_public || m.is_deleted) return { title: "Media not found — AOF Hub" };

  const title = m.title ? `${m.title} — AOF Hub` : `Media #${id} — AOF Hub`;
  const description =
    m.description?.trim() || `${m.views_count.toLocaleString()} views on AOF Hub.`;
  // Gated on NEXT_PUBLIC_MEDIA_BASE_URL — see the matching note in g/[slug]/page.tsx.
  // Without a stable CDN URL, a presigned OG image just becomes a broken share
  // preview an hour after the first Telegram/X fetch caches it.
  const imageKey = m.b2_thumb_key || m.b2_key;
  const imageUrl =
    imageKey && process.env.NEXT_PUBLIC_MEDIA_BASE_URL
      ? await resolveMediaUrl(imageKey as string)
      : undefined;

  return {
    title,
    description,
    alternates: { canonical: `/m/${id}` },
    openGraph: {
      title,
      description,
      type: "website",
      images: imageUrl ? [{ url: imageUrl }] : undefined,
    },
    twitter: { card: "summary_large_image", title, description },
  };
}

export default async function MediaPage({ params, searchParams }: PageProps) {
  const { id: idStr } = await params;
  const sp = await searchParams;
  const groupSlug =
    typeof sp.group === "string" && sp.group.trim() !== "" ? sp.group.trim() : null;
  const id = Number.parseInt(idStr, 10);
  if (!Number.isFinite(id) || id <= 0) notFound();

  const db = await createClient();
  const { data: m, error } = await db
    .from("media_items")
    .select(
      "id, kind, title, description, b2_key, b2_thumb_key, width, height, duration_seconds, mime, byte_size, views_count, votes_up, votes_down, score, created_at, uploader_id, source_url, source_kind, is_public, is_deleted"
    )
    .eq("id", id)
    .maybeSingle();
  if (error || !m) notFound();

  const [{ data: tagsRaw }, { data: uploader }, { data: u }, { data: vote }, { data: bm }] = await Promise.all([
    db.from("media_tags").select("tags!inner(id, slug, name, kind)").eq("media_id", id),
    m.uploader_id
      ? db.from("profiles").select("id, handle, display_name, avatar_url").eq("id", m.uploader_id).maybeSingle()
      : Promise.resolve({ data: null }),
    db.auth.getUser(),
    db.from("votes").select("value").eq("target_kind", "media").eq("target_id", id).maybeSingle(),
    db.from("bookmarks").select("media_id").eq("media_id", id).maybeSingle(),
  ]);

  const tags =
    ((tagsRaw ?? []) as Array<{ tags: { id: number; slug: string; name: string; kind: TagKind } | { id: number; slug: string; name: string; kind: TagKind }[] | null }>)
      .map((row) => (Array.isArray(row.tags) ? row.tags[0] : row.tags))
      .filter((x): x is { id: number; slug: string; name: string; kind: TagKind } => !!x);

  const url = await resolveMediaUrl(m.b2_key);
  const thumbUrl = m.b2_thumb_key ? await resolveMediaUrl(m.b2_thumb_key) : undefined;

  const siteUrl = (process.env.NEXT_PUBLIC_SITE_URL || "http://127.0.0.1:3001").replace(/\/$/, "");
  const jsonLd =
    m.is_public && !m.is_deleted
      ? {
          "@context": "https://schema.org",
          "@type": m.kind === "video" ? "VideoObject" : "ImageObject",
          name: m.title || `Media #${m.id}`,
          description: m.description || undefined,
          contentUrl: process.env.NEXT_PUBLIC_MEDIA_BASE_URL ? url : undefined,
          thumbnailUrl: process.env.NEXT_PUBLIC_MEDIA_BASE_URL ? thumbUrl || url : undefined,
          url: `${siteUrl}/m/${m.id}`,
        }
      : null;

  return (
    <article style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr)", gap: "1rem" }}>
      {jsonLd && <JsonLd data={jsonLd} />}
      <Player kind={m.kind} url={url} thumbUrl={thumbUrl} title={m.title} width={m.width} height={m.height} />

      <header style={{ display: "flex", flexWrap: "wrap", gap: "0.75rem", alignItems: "center" }}>
        <h1 style={{ margin: 0, flex: 1 }}>{m.title || `Media #${m.id}`}</h1>
        <VoteButtons
          targetKind="media"
          targetId={m.id}
          initialUp={m.votes_up}
          initialDown={m.votes_down}
          initialValue={(vote?.value as -1 | 0 | 1 | undefined) ?? 0}
        />
        <BookmarkButton mediaId={m.id} initial={!!bm} />
        {!!u.user && <ReportButton targetKind="media" targetId={m.id} />}
      </header>

      <div style={{ color: "var(--muted)", display: "flex", flexWrap: "wrap", gap: "1rem" }}>
        <span>{m.views_count.toLocaleString()} views</span>
        {uploader && (
          <span>
            by <Link href={`/u/${uploader.handle}`}>{uploader.display_name || uploader.handle}</Link>
          </span>
        )}
        {m.source_url && (
          <span>
            source:{" "}
            <a href={m.source_url} target="_blank" rel="noopener noreferrer">
              {new URL(m.source_url).hostname}
            </a>
          </span>
        )}
        <span>{new Date(m.created_at).toLocaleDateString()}</span>
      </div>

      {m.description && <p>{m.description}</p>}

      <TagList tags={tags} />

      {tags.length === 0 && (
        <p className="muted">
          No tags yet. Once Stash auto-tags this item (or you add tags), the Related panel below fills in.
        </p>
      )}

      <RelatedPanel mediaId={m.id} groupSlug={groupSlug} />

      <TelegramConversionFooter
        context={{ surface: "media", id: m.id }}
        title="Want more like this?"
      />

      {!!u.user && (
        <details style={{ marginTop: "1rem", color: "var(--muted)" }}>
          <summary>Debug</summary>
          <pre style={{ fontSize: 12, overflowX: "auto" }}>{JSON.stringify({ b2_key: m.b2_key, mime: m.mime, byte_size: m.byte_size, source_kind: m.source_kind }, null, 2)}</pre>
        </details>
      )}
    </article>
  );
}
