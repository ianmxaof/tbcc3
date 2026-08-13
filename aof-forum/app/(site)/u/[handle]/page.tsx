import { notFound, redirect } from "next/navigation";
import Link from "next/link";
import { createClient } from "@/lib/supabase/server";
import { resolveManyMediaUrls } from "@/lib/media-url";
import { MediaCard } from "@/components/MediaCard";
import { FollowButton } from "@/components/FollowButton";

export const dynamic = "force-dynamic";

export default async function ProfilePage({
  params,
  searchParams,
}: {
  params: Promise<{ handle: string }>;
  searchParams: Promise<{ tab?: string }>;
}) {
  const { handle: rawHandle } = await params;
  const { tab = "uploads" } = await searchParams;
  const db = await createClient();

  let handle = rawHandle;
  if (handle === "me") {
    const { data: u } = await db.auth.getUser();
    if (!u.user) redirect("/auth/sign-in");
    const { data: own } = await db.from("profiles").select("handle").eq("id", u.user.id).maybeSingle();
    if (!own?.handle) notFound();
    handle = own.handle;
  }

  const { data: profile } = await db
    .from("profiles")
    .select("id, handle, display_name, avatar_url, bio, created_at")
    .eq("handle", handle)
    .maybeSingle();
  if (!profile) notFound();

  const { data: me } = await db.auth.getUser();
  const isOwn = me.user?.id === profile.id;

  const [{ data: followRow }, { data: uploadsRaw }, { data: galleries }] = await Promise.all([
    db
      .from("follows")
      .select("follower_id")
      .eq("target_kind", "user")
      .eq("target_user_id", profile.id)
      .maybeSingle(),
    tab === "uploads"
      ? (() => {
          let q = db
            .from("media_items")
            .select("id, kind, title, b2_key, b2_thumb_key, width, height, duration_seconds, views_count, is_public")
            .eq("uploader_id", profile.id)
            .eq("is_deleted", false);
          if (!isOwn) q = q.eq("is_public", true);
          return q.order("created_at", { ascending: false }).limit(60);
        })()
      : Promise.resolve({ data: [] }),
    tab === "galleries"
      ? (() => {
          let q = db
            .from("galleries")
            .select("id, slug, title, item_count, is_public")
            .eq("owner_id", profile.id);
          if (!isOwn) q = q.eq("is_public", true);
          return q.order("created_at", { ascending: false }).limit(60);
        })()
      : Promise.resolve({ data: [] }),
  ]);

  type UploadRow = {
    id: number;
    kind: "image" | "video" | "gif";
    title: string | null;
    b2_key: string;
    b2_thumb_key: string | null;
    width: number | null;
    height: number | null;
    duration_seconds: number | null;
    views_count: number;
  };
  const uploads = await resolveManyMediaUrls((uploadsRaw ?? []) as UploadRow[]);

  return (
    <article>
      <header style={{ display: "flex", alignItems: "center", gap: "1rem", marginBottom: "1rem" }}>
        <div style={{ width: 80, height: 80, borderRadius: "50%", background: "var(--bg-3)", overflow: "hidden" }}>
          {profile.avatar_url && (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={profile.avatar_url} alt={profile.handle} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
          )}
        </div>
        <div style={{ flex: 1 }}>
          <h1 style={{ margin: 0 }}>{profile.display_name || profile.handle}</h1>
          <div className="muted">@{profile.handle}</div>
          {profile.bio && <p style={{ marginTop: "0.5rem" }}>{profile.bio}</p>}
        </div>
        {!isOwn && (
          <FollowButton targetKind="user" targetUserId={profile.id} initial={!!followRow} />
        )}
      </header>

      <nav className="tabs">
        <Link href={`/u/${handle}?tab=uploads`} className={tab === "uploads" ? "active" : ""}>Uploads</Link>
        <Link href={`/u/${handle}?tab=galleries`} className={tab === "galleries" ? "active" : ""}>Galleries</Link>
      </nav>

      {tab === "uploads" && (
        uploads.length === 0 ? (
          <div className="empty muted">No public uploads yet.</div>
        ) : (
          <div className="grid">
            {uploads.map((it) => <MediaCard key={it.id} item={it} context="profile" sourceId={profile.id ? undefined : undefined} />)}
          </div>
        )
      )}

      {tab === "galleries" && (
        <>
          {isOwn && (
            <p style={{ margin: "0 0 1rem" }}>
              <Link href="/g/new" className="primary" style={{ padding: "0.35rem 0.85rem", textDecoration: "none" }}>
                New gallery
              </Link>
            </p>
          )}
          {(galleries ?? []).length === 0 ? (
            <div className="empty muted">
              No galleries yet.
              {isOwn && (
                <>
                  {" "}
                  <Link href="/g/new">Create one</Link>.
                </>
              )}
            </div>
          ) : (
            <ul style={{ padding: 0, listStyle: "none" }}>
              {(galleries ?? []).map((g) => (
                <li key={g.id} style={{ padding: "0.5rem 0", borderBottom: "1px solid var(--border)" }}>
                  <Link href={`/g/${g.slug}`}>{g.title}</Link>{" "}
                  <span className="muted">
                    · {g.item_count} items
                    {isOwn && g.is_public === false ? " · private" : ""}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </article>
  );
}
