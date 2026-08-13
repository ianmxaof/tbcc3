import Link from "next/link";
import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { OpenDashboardButton } from "@/components/OpenDashboardButton";

export const dynamic = "force-dynamic";

export default async function AdminPage() {
  const db = await createClient();
  const { data: auth } = await db.auth.getUser();
  if (!auth.user) {
    redirect("/auth/sign-in?next=/admin");
  }

  const admin = createAdminClient();
  const { data: profile } = await admin
    .from("profiles")
    .select("is_admin, handle, display_name")
    .eq("id", auth.user.id)
    .maybeSingle();

  if (!profile?.is_admin) {
    return (
      <div className="page">
        <h1>Admin</h1>
        <p>Your account is signed in but not marked <code>is_admin</code>.</p>
        <p>
          <Link href="/">Back to hub</Link>
        </p>
      </div>
    );
  }

  return (
    <div className="page">
      <h1>AOF Forum admin</h1>
      <p>
        Signed in as {profile.display_name || profile.handle || auth.user.email || auth.user.id}.
      </p>
      <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap", marginTop: "1.25rem" }}>
        <OpenDashboardButton />
        <Link href="/upload">Upload</Link>
        <Link href="/groups">Groups</Link>
        <Link href="/">Hub home</Link>
      </div>
      <p style={{ marginTop: "1.5rem", opacity: 0.75, fontSize: "0.9rem" }}>
        Dashboard bridge opens the always-on TBCC control plane on the revenue island
        (media, bots, commerce). Forum stays the public social surface.
      </p>
    </div>
  );
}
