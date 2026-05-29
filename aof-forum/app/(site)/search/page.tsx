import Link from "next/link";
import { createClient } from "@/lib/supabase/server";
import { TagPill } from "@/components/Tag";
import { GroupCard } from "@/components/GroupCard";

export const dynamic = "force-dynamic";

export default async function SearchPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string }>;
}) {
  const { q = "" } = await searchParams;
  const query = q.trim();

  if (!query) {
    return (
      <>
        <h1>Search</h1>
        <p className="muted">Type something into the search box above.</p>
      </>
    );
  }

  const db = await createClient();
  const ilike = `%${query.replace(/[%_]/g, "")}%`;
  const [{ data: tags }, { data: groups }, { data: profiles }] = await Promise.all([
    db.from("tags").select("id, slug, name, kind, uses_count").or(`name.ilike.${ilike},slug.ilike.${ilike}`).order("uses_count", { ascending: false }).limit(20),
    db.from("groups").select("id, slug, name, description, member_count, item_count, thread_count").neq("visibility", "private").or(`name.ilike.${ilike},slug.ilike.${ilike}`).limit(20),
    db.from("profiles").select("id, handle, display_name").or(`handle.ilike.${ilike},display_name.ilike.${ilike}`).limit(20),
  ]);

  return (
    <>
      <h1>Search: {query}</h1>

      {(tags ?? []).length > 0 && (
        <section style={{ margin: "1rem 0" }}>
          <h3>Tags</h3>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {(tags ?? []).map((t) => <TagPill key={t.id} slug={t.slug} name={t.name} kind={t.kind} />)}
          </div>
        </section>
      )}

      {(groups ?? []).length > 0 && (
        <section style={{ margin: "1rem 0" }}>
          <h3>Groups</h3>
          <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))" }}>
            {(groups ?? []).map((g) => (
              <GroupCard
                key={g.id}
                slug={g.slug}
                name={g.name}
                description={g.description}
                memberCount={g.member_count}
                itemCount={g.item_count}
                threadCount={g.thread_count}
              />
            ))}
          </div>
        </section>
      )}

      {(profiles ?? []).length > 0 && (
        <section style={{ margin: "1rem 0" }}>
          <h3>Users</h3>
          <ul style={{ listStyle: "none", padding: 0 }}>
            {(profiles ?? []).map((p) => (
              <li key={p.id} style={{ padding: "0.4rem 0", borderBottom: "1px solid var(--border)" }}>
                <Link href={`/u/${p.handle}`}>@{p.handle}</Link>
                {p.display_name && <span className="muted"> · {p.display_name}</span>}
              </li>
            ))}
          </ul>
        </section>
      )}

      {!tags?.length && !groups?.length && !profiles?.length && (
        <div className="empty muted">No matches.</div>
      )}
    </>
  );
}
