import { notFound } from "next/navigation";
import Link from "next/link";
import { createClient } from "@/lib/supabase/server";
import { VoteButtons } from "@/components/VoteButtons";
import { createReply } from "../actions";

export const dynamic = "force-dynamic";

export default async function ThreadPage({
  params,
}: {
  params: Promise<{ category: string; thread: string }>;
}) {
  const { category, thread: threadSlug } = await params;
  const db = await createClient();

  const { data: cat } = await db
    .from("forum_categories")
    .select("id, slug, name")
    .eq("slug", category)
    .maybeSingle();
  if (!cat) notFound();

  const { data: thread } = await db
    .from("forum_threads")
    .select("id, slug, title, reply_count, views_count, votes_up, votes_down, is_locked, author_id, created_at")
    .eq("category_id", cat.id)
    .eq("slug", threadSlug)
    .maybeSingle();
  if (!thread) notFound();

  const [{ data: posts }, { data: u }, { data: threadVote }] = await Promise.all([
    db
      .from("forum_posts")
      .select("id, body_md, parent_post_id, author_id, votes_up, votes_down, edited_at, created_at, is_deleted")
      .eq("thread_id", thread.id)
      .order("created_at", { ascending: true })
      .limit(500),
    db.auth.getUser(),
    db.from("votes").select("value").eq("target_kind", "thread").eq("target_id", thread.id).maybeSingle(),
  ]);

  const authorIds = [
    ...new Set([
      thread.author_id,
      ...(posts ?? []).map((p) => p.author_id),
    ]),
  ];
  const { data: authors } = authorIds.length
    ? await db.from("profiles").select("id, handle, display_name").in("id", authorIds)
    : { data: [] };
  const byId = new Map((authors ?? []).map((a) => [a.id, a]));

  return (
    <article>
      <header>
        <Link href={`/f/${cat.slug}`} className="muted">← {cat.name}</Link>
        <h1 style={{ marginTop: "0.25rem" }}>{thread.title}</h1>
        <div className="muted" style={{ display: "flex", gap: "0.75rem", alignItems: "center", marginBottom: "1rem" }}>
          <VoteButtons
            targetKind="thread"
            targetId={thread.id}
            initialUp={thread.votes_up}
            initialDown={thread.votes_down}
            initialValue={(threadVote?.value as -1 | 0 | 1 | undefined) ?? 0}
          />
          <span>{thread.reply_count} replies</span>
          <span>{thread.views_count.toLocaleString()} views</span>
          <span>started by @{byId.get(thread.author_id)?.handle ?? "?"}</span>
        </div>
      </header>

      {(posts ?? [])
        .filter((p) => !p.is_deleted)
        .map((p) => (
          <div key={p.id} className={p.parent_post_id ? "post child" : "post"}>
            <div className="by">
              <Link href={`/u/${byId.get(p.author_id)?.handle ?? ""}`}>
                @{byId.get(p.author_id)?.handle ?? "?"}
              </Link>{" "}
              · {new Date(p.created_at).toLocaleString()}
              {p.edited_at && <> · edited</>}
            </div>
            <div className="body">{p.body_md}</div>
            <div style={{ marginTop: "0.5rem" }}>
              <VoteButtons
                targetKind="post"
                targetId={p.id}
                initialUp={p.votes_up}
                initialDown={p.votes_down}
              />
            </div>
          </div>
        ))}

      {u.user && !thread.is_locked ? (
        <section className="card" style={{ marginTop: "1rem" }}>
          <h3 style={{ marginTop: 0 }}>Reply</h3>
          <form action={createReply}>
            <input type="hidden" name="thread_id" value={thread.id} />
            <input type="hidden" name="category_slug" value={cat.slug} />
            <input type="hidden" name="thread_slug" value={thread.slug} />
            <textarea name="body" rows={5} placeholder="Your reply..." required />
            <button type="submit" className="primary" style={{ marginTop: "0.5rem" }}>Post reply</button>
          </form>
        </section>
      ) : thread.is_locked ? (
        <div className="muted">This thread is locked.</div>
      ) : (
        <div className="muted">
          <Link href="/auth/sign-in">Sign in</Link> to reply.
        </div>
      )}
    </article>
  );
}
