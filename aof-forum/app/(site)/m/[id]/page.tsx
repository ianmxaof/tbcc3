import { notFound } from "next/navigation";
import Link from "next/link";
import { createClient } from "@/lib/supabase/server";
import { resolveMediaUrl } from "@/lib/media-url";
import { Player } from "@/components/Player";
import { TagList } from "@/components/Tag";
import { VoteButtons } from "@/components/VoteButtons";
import { BookmarkButton } from "@/components/BookmarkButton";
import { RelatedPanel } from "@/components/RelatedPanel";
import type { TagKind } from "@/lib/types";

export const dynamic = "force-dynamic";

interface PageProps {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ group?: string }>;
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
      "id, kind, title, description, b2_key, b2_thumb_key, width, height, duration_seconds, mime, byte_size, views_count, votes_up, votes_down, score, created_at, uploader_id, source_url, source_kind"
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

  return (
    <article style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr)", gap: "1rem" }}>
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

      {!!u.user && (
        <details style={{ marginTop: "1rem", color: "var(--muted)" }}>
          <summary>Debug</summary>
          <pre style={{ fontSize: 12, overflowX: "auto" }}>{JSON.stringify({ b2_key: m.b2_key, mime: m.mime, byte_size: m.byte_size, source_kind: m.source_kind }, null, 2)}</pre>
        </details>
      )}
    </article>
  );
}
