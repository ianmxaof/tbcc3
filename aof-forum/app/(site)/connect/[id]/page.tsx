import { notFound } from "next/navigation";
import Link from "next/link";
import { ConnectDisclaimer } from "@/components/ConnectDisclaimer";
import { ReportButton } from "@/components/ReportButton";
import { formatLastActive } from "@/lib/connect/query";
import { CONNECT_DEMO_FIXTURES } from "@/lib/connect/demo-fixtures";
import { PLATFORM_EMOJI, PLATFORM_LABELS } from "@/lib/connect/types";
import { resolveMediaUrl } from "@/lib/media-url";
import { createClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

function ConnectDetailView({
  listing,
  avatarUrl,
  tags,
  showReport,
}: {
  listing: {
    id: number;
    platform: keyof typeof PLATFORM_LABELS;
    handle: string;
    display_name: string | null;
    age: number;
    gender: string | null;
    orientation: string | null;
    country: string | null;
    bulletin: string | null;
    bio: string | null;
    last_active_at: string;
    views_count: number;
    fire_pin_until: string | null;
    is_vip: boolean;
    vip_until: string | null;
  };
  avatarUrl: string | null;
  tags: string[];
  showReport: boolean;
}) {
  const platform = listing.platform;
  const display = listing.display_name || listing.handle;
  const now = Date.now();
  const isFire = listing.fire_pin_until && new Date(listing.fire_pin_until).getTime() > now;
  const isVip =
    listing.is_vip && (!listing.vip_until || new Date(listing.vip_until).getTime() > now);

  return (
    <article className="connect-detail">
      <Link href="/connect" className="muted">
        ← Connect browse
      </Link>

      <ConnectDisclaimer />

      <div className="connect-detail-grid">
        <div className="connect-detail-avatar card">
          {avatarUrl ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={avatarUrl} alt={display} />
          ) : (
            <div className="connect-card-placeholder large">{PLATFORM_EMOJI[platform]}</div>
          )}
        </div>

        <div className="connect-detail-main">
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
            <h1 style={{ margin: 0 }}>@{listing.handle}</h1>
            <span className={`connect-platform-badge ${platform}`}>
              {PLATFORM_EMOJI[platform]} {PLATFORM_LABELS[platform]}
            </span>
            {isFire && <span className="connect-badge fire">🔥 Pinned</span>}
            {isVip && <span className="connect-badge vip">VIP</span>}
          </div>

          {listing.display_name && (
            <p className="muted" style={{ margin: "0.25rem 0 0" }}>
              {listing.display_name}
            </p>
          )}

          <p style={{ margin: "0.75rem 0" }}>
            {listing.age} · {listing.gender ?? "—"} · {listing.orientation ?? "—"}
            {listing.country ? ` · ${listing.country}` : ""}
          </p>

          {listing.bulletin && (
            <blockquote className="connect-bulletin card">{listing.bulletin}</blockquote>
          )}

          {listing.bio && <p className="connect-bio">{listing.bio}</p>}

          {tags.length > 0 && (
            <div className="connect-card-tags" style={{ marginTop: "0.75rem" }}>
              {tags.map((t) => (
                <span key={t} className="tag-chip">
                  {t}
                </span>
              ))}
            </div>
          )}

          <div className="muted" style={{ marginTop: "1rem", fontSize: "0.85rem" }}>
            Last active {formatLastActive(listing.last_active_at)} ·{" "}
            {listing.views_count.toLocaleString()} views
          </div>

          <div className="connect-cta-row" style={{ marginTop: "1.25rem" }}>
            <a
              href={
                platform === "telegram"
                  ? `https://t.me/${listing.handle.replace(/^@/, "")}`
                  : platform === "snapchat"
                    ? `https://www.snapchat.com/add/${listing.handle}`
                    : "#"
              }
              className="primary"
              style={{ padding: "0.5rem 1rem", textDecoration: "none" }}
              target="_blank"
              rel="noopener noreferrer"
            >
              Open on {PLATFORM_LABELS[platform]}
            </a>
            {showReport && <ReportButton targetKind="connect_listing" targetId={listing.id} />}
          </div>
        </div>
      </div>
    </article>
  );
}

export default async function ConnectDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!/^\d+$/.test(id)) notFound();

  const numericId = Number(id);
  const demo = CONNECT_DEMO_FIXTURES.find((l) => l.id === numericId);
  if (demo && process.env.NODE_ENV === "development") {
    return (
      <ConnectDetailView
        listing={demo}
        avatarUrl={demo.avatar_url}
        tags={demo.tags}
        showReport={false}
      />
    );
  }

  const db = await createClient();
  const { data: listing, error } = await db
    .from("connect_listings")
    .select("*")
    .eq("id", numericId)
    .eq("status", "approved")
    .eq("is_public", true)
    .maybeSingle();

  if (error || !listing) notFound();

  let avatarUrl: string | null = null;
  if (listing.avatar_media_id) {
    const { data: media } = await db
      .from("media_items")
      .select("b2_key")
      .eq("id", listing.avatar_media_id)
      .maybeSingle();
    if (media?.b2_key) avatarUrl = await resolveMediaUrl(media.b2_key);
  }

  const { data: tagRows } = await db
    .from("connect_listing_tags")
    .select("tags!inner(name)")
    .eq("listing_id", listing.id);
  const tags: string[] = [];
  for (const tr of tagRows ?? []) {
    const tag = (tr as { tags: { name: string } | { name: string }[] }).tags;
    const name = Array.isArray(tag) ? tag[0]?.name : tag?.name;
    if (name) tags.push(name);
  }

  const platform = listing.platform as keyof typeof PLATFORM_LABELS;

  return (
    <ConnectDetailView
      listing={{ ...listing, platform }}
      avatarUrl={avatarUrl}
      tags={tags}
      showReport
    />
  );
}
