import { notFound } from "next/navigation";
import Link from "next/link";
import { createClient } from "@/lib/supabase/server";
import { resolveMediaUrl } from "@/lib/media-url";
import { MediaGrid } from "@/components/MediaGrid";
import { RelatedGroupsPanel } from "@/components/RelatedGroupsPanel";
import { JoinLeaveButton } from "@/components/JoinLeaveButton";
export const dynamic = "force-dynamic";

export default async function GroupHome({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string }>;
  searchParams: Promise<{ tab?: string }>;
}) {
  const { slug } = await params;
  const { tab = "media" } = await searchParams;
  const db = await createClient();

  const { data: group } = await db
    .from("groups")
    .select(
      "id, slug, name, description, rules, avatar_media_id, banner_media_id, owner_id, visibility, member_count, item_count, thread_count, score, created_at"
    )
    .eq("slug", slug)
    .maybeSingle();
  if (!group) notFound();

  const { data: u } = await db.auth.getUser();
  let role: "owner" | "mod" | "member" | null = null;
  if (u.user) {
    const { data: gm } = await db
      .from("group_members")
      .select("role")
      .eq("group_id", group.id)
      .eq("user_id", u.user.id)
      .maybeSingle();
    role = (gm?.role as typeof role) ?? null;
  }

  const banner = group.banner_media_id
    ? await db.from("media_items").select("b2_key").eq("id", group.banner_media_id).maybeSingle().then(async (r) => r.data ? await resolveMediaUrl(r.data.b2_key) : null)
    : null;

  return (
    <article>
      {banner && (
        <div style={{ aspectRatio: "5/1", borderRadius: "var(--radius)", overflow: "hidden", marginBottom: "1rem" }}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={banner} alt="" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
        </div>
      )}

      <header style={{ display: "flex", alignItems: "flex-start", gap: "1rem", flexWrap: "wrap" }}>
        <div style={{ flex: 1, minWidth: 240 }}>
          <h1 style={{ margin: 0 }}>{group.name}</h1>
          <div className="muted" style={{ fontSize: "0.9rem" }}>
            /groups/{group.slug} · {group.member_count.toLocaleString()} members · {group.item_count.toLocaleString()} items
          </div>
        </div>
        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", alignItems: "center" }}>
          {u.user && role && (
            <Link href={`/groups/${group.slug}/new`}>
              <button type="button" className="primary">Submit</button>
            </Link>
          )}
          <JoinLeaveButton slug={group.slug} initialRole={role} />
        </div>
      </header>

      {group.description && <p style={{ marginTop: "1rem" }}>{group.description}</p>}

      <nav className="tabs">
        <Link className={tab === "media" ? "active" : ""} href={`/groups/${group.slug}?tab=media`}>Media</Link>
        <Link className={tab === "threads" ? "active" : ""} href={`/groups/${group.slug}?tab=threads`}>Threads</Link>
        <Link className={tab === "members" ? "active" : ""} href={`/groups/${group.slug}?tab=members`}>Members</Link>
        <Link className={tab === "about" ? "active" : ""} href={`/groups/${group.slug}?tab=about`}>About</Link>
      </nav>

      {tab === "media" && (
        <>
          <MediaGrid
            endpoint={`/api/groups/${encodeURIComponent(group.slug)}/feed?limit=24`}
            context="group"
            sourceId={group.id}
            queryKey={["group-feed", group.slug]}
            emptyMessage="No media in this group yet."
            groupLinkSlug={group.slug}
          />
          <RelatedGroupsPanel slug={group.slug} />
        </>
      )}

      {tab === "threads" && <GroupThreads groupId={group.id} groupSlug={group.slug} canPost={!!role} />}

      {tab === "members" && <GroupMembers groupId={group.id} />}

      {tab === "about" && (
        <section>
          {group.rules ? <pre style={{ whiteSpace: "pre-wrap" }}>{group.rules}</pre> : <p className="muted">No rules posted.</p>}
          <p className="muted" style={{ fontSize: "0.85rem" }}>
            Created {new Date(group.created_at).toLocaleDateString()}. Visibility: {group.visibility}.
          </p>
        </section>
      )}
    </article>
  );
}

async function GroupThreads({ groupId, groupSlug, canPost }: { groupId: number; groupSlug: string; canPost: boolean }) {
  const db = await createClient();
  const { data: threads } = await db
    .from("forum_threads")
    .select(
      "id, slug, title, reply_count, votes_up, votes_down, last_reply_at, author_id, category_id, forum_categories!inner(slug)"
    )
    .eq("group_id", groupId)
    .order("is_pinned", { ascending: false })
    .order("last_reply_at", { ascending: false })
    .limit(40);

  return (
    <>
      {(threads ?? []).length === 0 ? (
        <div className="empty muted">No threads in this group yet.</div>
      ) : (
        <ul style={{ listStyle: "none", padding: 0 }}>
          {(threads ?? []).map((t) => {
            const cat = (t as unknown as { forum_categories: { slug: string } | { slug: string }[] }).forum_categories;
            const catSlug = Array.isArray(cat) ? cat[0]?.slug : cat?.slug;
            return (
              <li key={t.id} className="thread-row">
                <div className="votes">{t.votes_up - t.votes_down}</div>
                <div style={{ flex: 1 }}>
                  {catSlug ? (
                    <Link href={`/f/${catSlug}/${t.slug}`} className="title" style={{ color: "var(--fg)" }}>
                      {t.title}
                    </Link>
                  ) : (
                    <span className="title">{t.title}</span>
                  )}
                  <div className="meta">
                    {t.reply_count} replies · last activity {new Date(t.last_reply_at).toLocaleString()}
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      )}
      {!canPost && (
        <div className="muted" style={{ marginTop: "1rem" }}>Join the group to post threads.</div>
      )}
      {canPost && (
        <p className="muted" style={{ fontSize: "0.85rem", marginTop: "1rem" }}>
          Start a group thread from any forum category (thread creation UI sets <code>group_id</code>) or use the API —
          links above open the thread in site-wide forum routes.
        </p>
      )}
    </>
  );
}

async function GroupMembers({ groupId }: { groupId: number }) {
  const db = await createClient();
  const { data } = await db
    .from("group_members")
    .select("role, joined_at, profiles!inner(id, handle, display_name)")
    .eq("group_id", groupId)
    .order("joined_at", { ascending: false })
    .limit(100);

  type Row = { role: string; joined_at: string; profiles: { id: string; handle: string; display_name: string | null } | { id: string; handle: string; display_name: string | null }[] | null };
  const flat = ((data ?? []) as Row[]).map((r) => ({
    role: r.role,
    joined_at: r.joined_at,
    profile: Array.isArray(r.profiles) ? r.profiles[0] : r.profiles,
  })).filter((r) => r.profile);

  return (
    <ul style={{ listStyle: "none", padding: 0 }}>
      {flat.map((m) => (
        <li key={m.profile!.id} style={{ padding: "0.4rem 0", borderBottom: "1px solid var(--border)" }}>
          <Link href={`/u/${m.profile!.handle}`}>@{m.profile!.handle}</Link>{" "}
          <span className="muted">· {m.role} · joined {new Date(m.joined_at).toLocaleDateString()}</span>
        </li>
      ))}
    </ul>
  );
}
