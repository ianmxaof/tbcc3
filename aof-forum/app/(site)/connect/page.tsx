import Link from "next/link";
import { Suspense } from "react";
import { ConnectDisclaimer } from "@/components/ConnectDisclaimer";
import { ConnectFilterSidebar } from "@/components/ConnectFilterSidebar";
import { ConnectListingCardView } from "@/components/ConnectListingCard";
import { fetchConnectListings } from "@/lib/connect/query";
import type { ConnectPlatform } from "@/lib/connect/types";
import { createClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

function parsePlatform(v: string | undefined): ConnectPlatform | undefined {
  if (v === "snapchat" || v === "telegram" || v === "instagram" || v === "other") return v;
  return undefined;
}

export default async function ConnectBrowsePage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const sp = await searchParams;
  const db = await createClient();
  const platform = parsePlatform(typeof sp.platform === "string" ? sp.platform : undefined);
  const sort =
    sp.sort === "new" || sp.sort === "active" ? sp.sort : ("hot" as const);

  let listings: Awaited<ReturnType<typeof fetchConnectListings>> = [];
  try {
    listings = await fetchConnectListings(db, {
      platform,
      gender: typeof sp.gender === "string" ? sp.gender : undefined,
      orientation: typeof sp.orientation === "string" ? sp.orientation : undefined,
      country: typeof sp.country === "string" ? sp.country : undefined,
      vip: sp.vip === "1",
      hasPhoto: sp.photo === "1",
      sort,
      limit: 60,
    });
  } catch (e) {
    return <div className="empty">Error: {(e as Error).message}</div>;
  }

  return (
    <article className="connect-page">
      <header className="connect-header">
        <div>
          <h1 style={{ margin: 0 }}>Connect</h1>
          <p className="muted" style={{ margin: "0.25rem 0 0" }}>
            Find Snap, Telegram &amp; social listings — browse, filter, link out.
          </p>
        </div>
        <div className="connect-header-actions">
          <Link href="/connect/snapchat" className="muted">
            Snapchat
          </Link>
          <Link href="/connect/telegram" className="muted">
            Telegram
          </Link>
          <Link href="/connect/new" className="primary" style={{ padding: "0.35rem 0.85rem" }}>
            Post listing
          </Link>
        </div>
      </header>

      <ConnectDisclaimer />

      <div className="connect-layout">
        <Suspense fallback={<aside className="connect-filters card muted">Loading filters…</aside>}>
          <ConnectFilterSidebar />
        </Suspense>

        {listings.length === 0 ? (
          <div className="empty muted">
            No listings match.{" "}
            <Link href="/connect/new">Be the first to post</Link> or run{" "}
            <code>npm run seed:demo</code> for sample data.
          </div>
        ) : (
          <div className="connect-grid">
            {listings.map((l) => (
              <ConnectListingCardView key={l.id} listing={l} />
            ))}
          </div>
        )}
      </div>
    </article>
  );
}
