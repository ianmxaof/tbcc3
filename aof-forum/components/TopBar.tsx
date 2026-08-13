import Link from "next/link";
import { createClient } from "@/lib/supabase/server";

export async function TopBar() {
  const db = await createClient();
  const { data: u } = await db.auth.getUser();
  return (
    <header className="topbar">
      <Link href="/" className="brand">AOF Hub</Link>
      <form action="/search" className="search" method="get">
        <input type="search" name="q" placeholder="Search media, tags, groups..." />
      </form>
      <div className="spacer" />
      <nav className="actions">
        <Link href="/live" style={{ color: "var(--live-accent-2)" }}>Live</Link>
        <Link href="/foryou">For You</Link>
        <Link href="/groups">Groups</Link>
        <Link href="/connect">Connect</Link>
        <Link href="/f">Forum</Link>
        {u.user ? (
          <>
            <Link href="/upload">Upload</Link>
            <Link href={`/u/me`}>Profile</Link>
            <Link href="/admin">Admin</Link>
          </>
        ) : (
          <Link href="/auth/sign-in">Sign in</Link>
        )}
      </nav>
    </header>
  );
}
