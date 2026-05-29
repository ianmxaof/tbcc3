import Link from "next/link";
import { GroupCard } from "@/components/GroupCard";
import { createClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

export default async function GroupsDirectory({
  searchParams,
}: {
  searchParams: Promise<{ sort?: string }>;
}) {
  const { sort = "hot" } = await searchParams;
  const db = await createClient();
  let q = db
    .from("groups")
    .select("id, slug, name, description, member_count, item_count, thread_count, score, created_at")
    .neq("visibility", "private");
  q = sort === "new"
    ? q.order("created_at", { ascending: false })
    : q.order("score", { ascending: false }).order("member_count", { ascending: false });
  const { data, error } = await q.limit(60);
  if (error) return <div className="empty">Error: {error.message}</div>;

  const groups = data ?? [];

  return (
    <>
      <header style={{ display: "flex", alignItems: "baseline", gap: "1rem", marginBottom: "1rem" }}>
        <h1 style={{ flex: 1, margin: 0 }}>Groups</h1>
        <div className="tabs" style={{ margin: 0, border: 0 }}>
          <Link className={sort !== "new" ? "active" : ""} href="/groups">Hot</Link>
          <Link className={sort === "new" ? "active" : ""} href="/groups?sort=new">New</Link>
        </div>
        <Link href="/groups/new" className="" style={{ marginLeft: "auto" }}>
          <button className="primary">Create group</button>
        </Link>
      </header>

      {groups.length === 0 ? (
        <div className="empty muted">No groups yet. Create the first one.</div>
      ) : (
        <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))" }}>
          {groups.map((g) => (
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
      )}
    </>
  );
}
