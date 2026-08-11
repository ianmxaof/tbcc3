import { notFound } from "next/navigation";
import Link from "next/link";
import { getVpapiLabel, getVpapiLabels } from "@/lib/vpapi-labels";
import { fetchVpapiList, vpapiConfigured } from "@/lib/awempire-vpapi";

// Third-party, rate-limited API backing this page — cache instead of
// force-dynamic (see lib/awempire-vpapi.ts fetch revalidate note).
export const revalidate = 900;

// Without this, a dynamic segment with `revalidate` set (no `dynamic` export)
// leaves Next 14 to infer static-vs-on-demand generation implicitly. Listing
// the known labels makes all four genuinely static/ISR — right for an SEO
// surface — and keeps notFound() meaningful for anything outside the set.
export async function generateStaticParams() {
  return getVpapiLabels().map((l) => ({ label: l.slug }));
}

/**
 * Phase 1 skeleton: proves the label -> VPAPI plumbing end-to-end (fixture or
 * live). No grid polish, no beacon-wrapped outbound links, no metadata yet —
 * those are Phase 2 per docs/handoffs/2026-08-10_aof-hub-p9-p10_report.md,
 * once the watch-page embed-script sandboxing question is settled.
 */
export default async function AwempireLabelPage({
  params,
}: {
  params: Promise<{ label: string }>;
}) {
  const { label: labelSlug } = await params;
  const label = getVpapiLabel(labelSlug);
  if (!label) notFound();

  const result = await fetchVpapiList({ tags: label.vpapiTags, limit: 24 });

  return (
    <article>
      <h1>{label.title}</h1>
      {label.description && <p className="muted">{label.description}</p>}
      <p className="live-disclaimer muted">
        Supplemental listing from our promotion partner — not hosted on AOF. Clicking through
        takes you to their site.
      </p>

      {!vpapiConfigured() && (
        <div className="card live-setup-hint" style={{ marginBottom: "1rem" }}>
          <p style={{ margin: 0 }}>
            <strong>Awempire VPAPI not configured — showing fixture data.</strong> Set{" "}
            <code>AWEMPIRE_PSID</code> / <code>AWEMPIRE_ACCESS_KEY</code> once the affiliate
            account is approved.
          </p>
        </div>
      )}

      {result.videos.length === 0 ? (
        <p className="empty muted">No videos returned for this label right now.</p>
      ) : (
        <ul style={{ listStyle: "none", padding: 0 }}>
          {result.videos.map((v) => (
            <li key={v.id} className="card" style={{ marginBottom: "0.5rem", padding: "0.75rem 1rem" }}>
              <div style={{ fontWeight: 600 }}>{v.title}</div>
              <div className="muted" style={{ fontSize: "0.8rem" }}>
                id: {v.id} · source: {result.source}
              </div>
            </li>
          ))}
        </ul>
      )}

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
