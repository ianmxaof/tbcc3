import type { VpapiVideo } from "@/lib/awempire-vpapi";

/**
 * Option (c) from the P9 phase 1 report: no per-video watch page. VPAPI's
 * verified contract has no per-video outbound URL, so every card routes to
 * the same beacon-wrapped label destination (vpapiLabelOutboundHref()).
 */
export function VpapiDisclaimer() {
  return (
    <p className="live-disclaimer muted">
      Video listing from our promotion partner — not hosted on AOF. Clicking through takes you
      to their site. Affiliate disclosure applies.
    </p>
  );
}

/**
 * Cards are deliberately NOT individually clickable. VPAPI's verified
 * contract has no per-video outbound URL (see the P9 phase 1/2 report) — a
 * card linking to a generic homepage under a specific video's title would be
 * a duplicate-href pattern with mismatched anchor text on the one surface
 * whose entire purpose is SEO. One prominent CTA carries the actual click.
 */
export function VpapiVideoGrid({
  videos,
  outboundHref,
  ctaLabel,
}: {
  videos: VpapiVideo[];
  outboundHref: string;
  ctaLabel: string;
}) {
  if (videos.length === 0) {
    return <p className="empty muted">No videos returned for this label right now.</p>;
  }

  return (
    <>
      <div className="grid">
        {videos.map((v) => (
          <div key={v.id} className="media-card" style={{ cursor: "default" }}>
            <div className="thumb">
              {v.previewImages[0] ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={v.previewImages[0]} alt={v.title} loading="lazy" />
              ) : (
                <div className="empty" style={{ height: "100%", fontSize: "0.75rem" }}>
                  No preview
                </div>
              )}
            </div>
            <div className="meta">
              <div className="title">{v.title}</div>
            </div>
          </div>
        ))}
      </div>
      <a
        href={outboundHref}
        target="_blank"
        rel="noopener sponsored noreferrer"
        className="primary"
        style={{ display: "inline-block", textDecoration: "none", padding: "0.6rem 1.2rem", marginTop: "1rem" }}
      >
        {ctaLabel}
      </a>
    </>
  );
}
