import Link from "next/link";
import { createClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

export default async function ForumIndex() {
  const db = await createClient();
  const { data: cats, error } = await db
    .from("forum_categories")
    .select("id, slug, name, description, thread_count")
    .order("position", { ascending: true })
    .order("name", { ascending: true });
  if (error) return <div className="empty">Error: {error.message}</div>;

  const visible = (cats ?? []).filter((c) => c.slug !== "demo-hub-seed-v1");

  return (
    <>
      <h1>Forum</h1>
      {visible.length === 0 ? (
        <div className="empty muted">
          No categories yet. An admin can insert rows into <code>forum_categories</code> via
          the Supabase dashboard or SQL: <code>insert into forum_categories (slug, name) values (&apos;general&apos;, &apos;General&apos;);</code>
        </div>
      ) : (
        <ul style={{ listStyle: "none", padding: 0 }}>
          {visible.map((c) => (
            <li key={c.id} className="card" style={{ marginBottom: "0.5rem" }}>
              <h3 style={{ margin: 0 }}><Link href={`/f/${c.slug}`}>{c.name}</Link></h3>
              {c.description && <p className="muted" style={{ margin: "0.25rem 0 0" }}>{c.description}</p>}
              <div className="muted" style={{ fontSize: "0.85rem", marginTop: "0.5rem" }}>{c.thread_count} threads</div>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
