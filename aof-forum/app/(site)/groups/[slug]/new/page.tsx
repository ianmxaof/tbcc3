import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { attachExistingMediaToGroup, queueIngestToGroup } from "../actions";

export const dynamic = "force-dynamic";

export default async function GroupSubmitPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const db = await createClient();
  const { data: u } = await db.auth.getUser();
  if (!u.user) redirect(`/auth/sign-in?next=/groups/${slug}/new`);

  const { data: group } = await db.from("groups").select("id, name, slug").eq("slug", slug).maybeSingle();
  if (!group) notFound();

  const { data: mem } = await db
    .from("group_members")
    .select("role")
    .eq("group_id", group.id)
    .eq("user_id", u.user.id)
    .maybeSingle();
  if (!mem) {
    return (
      <article style={{ maxWidth: 560 }}>
        <h1>Submit to {group.name}</h1>
        <p className="muted">You need to join this group before you can submit.</p>
        <Link href={`/groups/${slug}`}>← Back to group</Link>
      </article>
    );
  }

  return (
    <article style={{ maxWidth: 560 }}>
      <p className="muted" style={{ marginTop: 0 }}>
        <Link href={`/groups/${slug}`}>← {group.name}</Link>
      </p>
      <h1>Submit to {group.name}</h1>

      <section className="card" style={{ marginBottom: "1.5rem" }}>
        <h3 style={{ marginTop: 0 }}>Add existing media</h3>
        <p className="muted" style={{ fontSize: "0.9rem" }}>
          Paste a public media id from the site (URL <code>/m/123</code> → <code>123</code>). You must be a member.
        </p>
        <form action={attachExistingMediaToGroup}>
          <input type="hidden" name="group_slug" value={group.slug} />
          <input name="media_id" type="number" min={1} placeholder="Media ID" required />
          <button type="submit" className="primary" style={{ marginTop: "0.75rem" }}>
            Add to group
          </button>
        </form>
      </section>

      <section className="card">
        <h3 style={{ marginTop: 0 }}>Ingest from URL</h3>
        <p className="muted" style={{ fontSize: "0.9rem" }}>
          Queues a job for your local <code>npm run ingest:watch</code> worker. When it finishes, the item is added
          to this group automatically.
        </p>
        <form action={queueIngestToGroup}>
          <input type="hidden" name="group_slug" value={group.slug} />
          <input name="source_url" type="url" placeholder="https://..." required />
          <button type="submit" className="primary" style={{ marginTop: "0.75rem" }}>
            Queue ingest
          </button>
        </form>
      </section>
    </article>
  );
}
