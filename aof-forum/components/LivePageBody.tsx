import Link from "next/link";
import { getLiveEmbeds, liveEmbedsConfigured, resolveLiveOutboundUrl } from "@/lib/live-embeds";
import { TelegramConversionFooter } from "@/components/TelegramConversionFooter";

export function AwempireDisclaimer() {
  return (
    <p className="live-disclaimer muted">
      Live cams are hosted by our streaming partner, not AOF. Clicking through takes you to their
      site. Affiliate disclosure applies.
    </p>
  );
}

export function LiveEmbedGrid() {
  const slots = getLiveEmbeds();
  const configured = liveEmbedsConfigured();

  if (!configured) {
    return (
      <div className="card live-setup-hint">
        <p style={{ margin: 0 }}>
          <strong>Awempire embeds not configured yet.</strong> Paste promo-tool iframe URLs into{" "}
          <code>data/live-embeds.json</code> or set <code>AWEMPIRE_LIVE_EMBEDS_JSON</code> after your
          affiliate account is approved.
        </p>
        <p className="muted" style={{ fontSize: "0.85rem", margin: "0.75rem 0 0" }}>
          Operator: Awempire dashboard → Promo Tools → copy widget iframe <code>src</code> per
          category.
        </p>
      </div>
    );
  }

  return (
    <div className="live-embed-grid">
      {slots
        .filter((s) => s.iframeSrc?.trim())
        .map((slot) => {
          const outbound = resolveLiveOutboundUrl(slot);
          return (
            <div key={slot.id} className="live-embed-card card">
              <div className="live-embed-card-head">
                <h2 style={{ margin: 0, fontSize: "1rem" }}>
                  <span className="live-dot" />
                  {slot.label}
                </h2>
                {outbound && (
                  <a href={outbound} target="_blank" rel="noopener sponsored noreferrer" className="primary" style={{ padding: "0.3rem 0.65rem", textDecoration: "none", fontSize: "0.85rem" }}>
                    Open room
                  </a>
                )}
              </div>
              <div className="live-embed-frame-wrap">
                <iframe
                  title={slot.label}
                  src={slot.iframeSrc}
                  loading="lazy"
                  referrerPolicy="no-referrer-when-downgrade"
                  allow="autoplay; encrypted-media; picture-in-picture"
                />
              </div>
            </div>
          );
        })}
    </div>
  );
}

export function LivePageBody() {
  return (
    <>
      <AwempireDisclaimer />
      <LiveEmbedGrid />
      <TelegramConversionFooter context={{ surface: "live" }} title="Or skip the cam — go Telegram" />
      <p className="muted" style={{ fontSize: "0.85rem", marginTop: "1rem" }}>
        Prefer the tube? <Link href="/">Back to Hot feed</Link>
      </p>
    </>
  );
}
