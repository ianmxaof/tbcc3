import Link from "next/link";
import { redirect } from "next/navigation";
import { ConnectDisclaimer } from "@/components/ConnectDisclaimer";
import { createClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

export default async function ConnectNewPage() {
  const db = await createClient();
  const { data: u } = await db.auth.getUser();
  if (!u.user) redirect("/auth/sign-in?next=/connect/new");

  return (
    <article style={{ maxWidth: 560 }}>
      <Link href="/connect" className="muted">
        ← Connect browse
      </Link>
      <h1>Post a listing</h1>
      <ConnectDisclaimer />
      <div className="card muted" style={{ lineHeight: 1.6 }}>
        <p style={{ marginTop: 0 }}>
          Full create flow (avatar upload, Turnstile, moderation queue) ships in Connect P-A after
          operator ACK on the parity plan. For now, populate the browse UI with demo data:
        </p>
        <pre style={{ overflow: "auto", fontSize: "0.85rem" }}>npm run seed:demo</pre>
        <p style={{ marginBottom: 0 }}>
          Or ask an agent to wire the create form once the plan is ACK&apos;d.
        </p>
      </div>
    </article>
  );
}
