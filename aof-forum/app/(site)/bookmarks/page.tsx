import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { resolveManyMediaUrls } from "@/lib/media-url";
import { MediaCard } from "@/components/MediaCard";

export const dynamic = "force-dynamic";

export default async function BookmarksPage() {
  const db = await createClient();
  const { data: u } = await db.auth.getUser();
  if (!u.user) redirect("/auth/sign-in?next=/bookmarks");

  const { data: rows } = await db
    .from("bookmarks")
    .select(
      "media_id, created_at, media_items!inner(id, kind, title, b2_key, b2_thumb_key, width, height, duration_seconds, views_count)"
    )
    .eq("user_id", u.user.id)
    .order("created_at", { ascending: false })
    .limit(120);

  type RowM = { id: number; kind: "image" | "video" | "gif"; title: string | null; b2_key: string; b2_thumb_key: string | null; width: number | null; height: number | null; duration_seconds: number | null; views_count: number };
  const flat = ((rows ?? []) as Array<{ media_items: RowM | RowM[] | null }>)
    .map((r) => (Array.isArray(r.media_items) ? r.media_items[0] : r.media_items))
    .filter((x): x is RowM => !!x);
  const items = await resolveManyMediaUrls(flat);

  return (
    <>
      <h1>Bookmarks</h1>
      {items.length === 0 ? (
        <div className="empty muted">No bookmarks yet. Tap ☆ Save on any media to bookmark it.</div>
      ) : (
        <div className="grid">
          {items.map((it) => <MediaCard key={it.id} item={it} context="profile" />)}
        </div>
      )}
    </>
  );
}
