import { notFound } from "next/navigation";
import Link from "next/link";
import type { Metadata } from "next";
import { getVpapiLabel, getVpapiLabels, vpapiLabelOutboundHref } from "@/lib/vpapi-labels";
import { fetchVpapiList, vpapiConfigured } from "@/lib/awempire-vpapi";
import { VpapiDisclaimer, VpapiVideoGrid } from "@/components/VpapiVideoGrid";
import { TelegramConversionFooter } from "@/components/TelegramConversionFooter";
import { JsonLd } from "@/components/JsonLd";

// Third-party, rate-limited API backing this page — cache instead of
// force-dynamic (see lib/awempire-vpapi.ts fetch revalidate note).
export const revalidate = 900;

// Makes the 4 known labels genuinely static/ISR (right for an SEO surface)
// and keeps notFound() meaningful for anything outside the set. Note: the
// fixture-vs-live choice is baked in at generation time — see "Operator
// steps" in the P9 report for the post-credentials staleness window.
export async function generateStaticParams() {
  return getVpapiLabels().map((l) => ({ label: l.slug }));
}

function siteUrl(): string {
  return (process.env.NEXT_PUBLIC_SITE_URL || "http://127.0.0.1:3001").replace(/\/$/, "");
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ label: string }>;
}): Promise<Metadata> {
  const { label: labelSlug } = await params;
  const label = getVpapiLabel(labelSlug);
  if (!label) return { title: "Not found — AOF Hub" };

  const title = `${label.title} videos — AOF Hub`;
  const description =
    label.description?.trim() || `${label.title} video listing, powered by our promotion partner.`;
  return {
    title,
    description,
    alternates: { canonical: `/tube/awempire/${label.slug}` },
    openGraph: { title, description, type: "website" },
    twitter: { card: "summary", title, description },
  };
}

export default async function AwempireLabelPage({
  params,
}: {
  params: Promise<{ label: string }>;
}) {
  const { label: labelSlug } = await params;
  const label = getVpapiLabel(labelSlug);
  if (!label) notFound();

  const result = await fetchVpapiList({ tags: label.vpapiTags, limit: 24 });
  const outboundHref = vpapiLabelOutboundHref(label);

  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "ItemList",
    name: `${label.title} — AOF Hub`,
    url: `${siteUrl()}/tube/awempire/${label.slug}`,
    itemListElement: result.videos.map((v, i) => ({
      "@type": "ListItem",
      position: i + 1,
      name: v.title,
    })),
  };

  return (
    <article>
      <JsonLd data={jsonLd} />
      <h1>{label.title}</h1>
      {label.description && <p className="muted">{label.description}</p>}
      <VpapiDisclaimer />

      {!vpapiConfigured() && (
        <div className="card live-setup-hint" style={{ marginBottom: "1rem" }}>
          <p style={{ margin: 0 }}>
            <strong>Awempire VPAPI not configured — showing fixture data.</strong> Set{" "}
            <code>AWEMPIRE_PSID</code> / <code>AWEMPIRE_ACCESS_KEY</code> once the affiliate
            account is approved.
          </p>
        </div>
      )}

      <VpapiVideoGrid
        videos={result.videos}
        outboundHref={outboundHref}
        ctaLabel={`Browse more ${label.title} on our partner site`}
      />

      <TelegramConversionFooter
        context={{ surface: "vpapi", slug: label.slug }}
        title="Or skip the browse — go Telegram"
      />

      <p className="muted" style={{ fontSize: "0.85rem", marginTop: "1.5rem" }}>
        Other labels:{" "}
        {getVpapiLabels()
          .filter((l) => l.slug !== label.slug)
          .map((l, i, arr) => (
            <span key={l.slug}>
              <Link href={`/tube/awempire/${l.slug}`}>{l.title}</Link>
              {i < arr.length - 1 ? ", " : ""}
            </span>
          ))}
      </p>
    </article>
  );
}
