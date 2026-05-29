import { notFound } from "next/navigation";
import Link from "next/link";
import { createClient } from "@/lib/supabase/server";
import { createThread } from "./actions";

export const dynamic = "force-dynamic";

export default async function CategoryPage({ params }: { params: Promise<{ category: string }> }) {
  const { category } = await params;
  const db = await createClient();

  const { data: cat } = await db
    .from("forum_categories")
    .select("id, slug, name, description")
    .eq("slug", category)
    .maybeSingle();
  if (!cat) notFound();

  const [{ data: threads }, { data: u }] = await Promise.all([
    db
      .from("forum_threads")
      .select("id, slug, title, reply_count, views_count, votes_up, votes_down, score, last_reply_at, created_at, author_id")
      .eq("category_id", cat.id)
      .is("group_id", null)
      .order("is_pinned", { ascending: false })
      .order("last_reply_at", { ascending: false })
      .limit(50),
    db.auth.getUser(),
  ]);

  const authorIds = [...new Set((threads ?? []).map((t) => t.author_id))];
  const { data: authors } = authorIds.length
    ? await db.from("profiles").select("id, handle").in("id", authorIds)
    : { data: [] };
  const byId = new Map((authors ?? []).map((a) => [a.id, a]));

  return (
    <article>
      <header>
        <Link href="/f" className="muted">← Forum</Link>
        <h1>{cat.name}</h1>
        {cat.description && <p className="muted">{cat.description}</p>}
      </header>

      {(threads ?? []).length === 0 ? (
        <div className="empty muted">No threads yet. Start one below.</div>
      ) : (
        <ul style={{ listStyle: "none", padding: 0 }}>
          {(threads ?? []).map((t) => (
            <li key={t.id} className="thread-row">
              <div className="votes">{t.votes_up - t.votes_down}</div>
              <div style={{ flex: 1 }}>
                <Link href={`/f/${cat.slug}/${t.slug}`} className="title" style={{ color: "var(--fg)" }}>
                  {t.title}
                </Link>
                <div className="meta">
                  {byId.get(t.author_id)?.handle && <>by @{byId.get(t.author_id)!.handle} · </>}
                  {t.reply_count} replies · last activity {new Date(t.last_reply_at).toLocaleString()}
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}

      {u.user ? (
        <section className="card" style={{ marginTop: "2rem" }}>
          <h3 style={{ marginTop: 0 }}>New thread</h3>
          <form action={createThread}>
            <input type="hidden" name="category_slug" value={cat.slug} />
            <input name="title" placeholder="Title" required minLength={3} maxLength={200} />
            <textarea name="body" placeholder="Body (markdown)" rows={6} required minLength={3} style={{ marginTop: "0.5rem" }} />
            <button type="submit" className="primary" style={{ marginTop: "0.5rem" }}>Post</button>
          </form>
        </section>
      ) : (
        <div className="muted" style={{ marginTop: "2rem" }}>
          <Link href="/auth/sign-in">Sign in</Link> to start a thread.
        </div>
      )}
    </article>
  );
}
