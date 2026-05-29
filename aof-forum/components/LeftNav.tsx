import Link from "next/link";
import { createClient } from "@/lib/supabase/server";

export async function LeftNav() {
  const db = await createClient();
  const { data: u } = await db.auth.getUser();

  const yourGroups: Array<{ slug: string; name: string }> = [];
  if (u.user) {
    const { data } = await db
      .from("group_members")
      .select("groups!inner(slug, name)")
      .eq("user_id", u.user.id)
      .order("joined_at", { ascending: false })
      .limit(20);
    for (const row of (data ?? []) as Array<{ groups: { slug: string; name: string } | { slug: string; name: string }[] | null }>) {
      const g = Array.isArray(row.groups) ? row.groups[0] : row.groups;
      if (g) yourGroups.push(g);
    }
  }

  return (
    <aside className="leftnav">
      <h4>Browse</h4>
      <Link href="/">Hot</Link>
      <Link href="/?sort=recent">New</Link>
      <Link href="/foryou">For You</Link>
      <Link href="/g">Galleries</Link>
      <Link href="/groups">Groups</Link>
      <Link href="/f">Forum</Link>

      {yourGroups.length > 0 && (
        <>
          <h4>Your Groups</h4>
          {yourGroups.map((g) => (
            <Link key={g.slug} href={`/groups/${g.slug}`}>{g.name}</Link>
          ))}
        </>
      )}

      <h4>You</h4>
      {u.user ? (
        <>
          <Link href="/u/me">Profile</Link>
          <Link href="/bookmarks">Bookmarks</Link>
          <Link href="/upload">Upload</Link>
          <Link href="/auth/sign-out">Sign out</Link>
        </>
      ) : (
        <Link href="/auth/sign-in">Sign in</Link>
      )}
    </aside>
  );
}
