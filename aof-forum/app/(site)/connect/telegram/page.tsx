import Link from "next/link";
import { ConnectDisclaimer } from "@/components/ConnectDisclaimer";
import { ConnectListingCardView } from "@/components/ConnectListingCard";
import { fetchConnectListings } from "@/lib/connect/query";
import { createClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

export default async function ConnectTelegramPage() {
  const db = await createClient();
  let listings: Awaited<ReturnType<typeof fetchConnectListings>> = [];
  try {
    listings = await fetchConnectListings(db, { platform: "telegram", limit: 48 });
  } catch {
    listings = [];
  }

  return (
    <article className="connect-page">
      <Link href="/connect" className="muted">
        ← All Connect
      </Link>
      <h1>Telegram listings</h1>
      <ConnectDisclaimer />

      {listings.length === 0 ? (
        <div className="empty muted">
          No listings yet. <Link href="/connect/new">Post one</Link> or run{" "}
          <code>npm run seed:demo</code>.
        </div>
      ) : (
        <div className="connect-grid" style={{ marginTop: "1rem" }}>
          {listings.map((l) => (
            <ConnectListingCardView key={l.id} listing={l} />
          ))}
        </div>
      )}
    </article>
  );
}
