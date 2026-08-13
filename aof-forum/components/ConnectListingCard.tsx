import Link from "next/link";
import type { ConnectListingCard } from "@/lib/connect/types";
import { PLATFORM_EMOJI, PLATFORM_LABELS } from "@/lib/connect/types";
import { formatLastActive } from "@/lib/connect/query";

export function ConnectListingCardView({ listing }: { listing: ConnectListingCard }) {
  const now = Date.now();
  const isFire = listing.fire_pin_until && new Date(listing.fire_pin_until).getTime() > now;
  const isVip =
    listing.is_vip && (!listing.vip_until || new Date(listing.vip_until).getTime() > now);
  const label = listing.display_name || listing.handle;

  return (
    <Link href={`/connect/${listing.id}`} className="connect-card">
      <div className="connect-card-avatar">
        {listing.avatar_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={listing.avatar_url} alt={label} loading="lazy" />
        ) : (
          <div className="connect-card-placeholder">{PLATFORM_EMOJI[listing.platform]}</div>
        )}
        <span className={`connect-platform-badge ${listing.platform}`}>
          {PLATFORM_EMOJI[listing.platform]} {PLATFORM_LABELS[listing.platform]}
        </span>
        {(isFire || isVip) && (
          <span className="connect-badges">
            {isFire && <span className="connect-badge fire">🔥</span>}
            {isVip && <span className="connect-badge vip">VIP</span>}
          </span>
        )}
      </div>
      <div className="connect-card-body">
        <div className="connect-card-handle">@{listing.handle}</div>
        <div className="connect-card-meta">
          {listing.age} · {listing.gender ?? "—"}
          {listing.country ? ` · ${listing.country}` : ""}
        </div>
        {listing.bulletin && <p className="connect-card-bulletin">{listing.bulletin}</p>}
        {listing.tags.length > 0 && (
          <div className="connect-card-tags">
            {listing.tags.slice(0, 4).map((t) => (
              <span key={t} className="tag-chip">
                {t}
              </span>
            ))}
          </div>
        )}
        <div className="connect-card-footer">
          <span>{formatLastActive(listing.last_active_at)}</span>
          <span>{listing.views_count.toLocaleString()} views</span>
        </div>
      </div>
    </Link>
  );
}
