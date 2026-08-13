import labelConfig from "@/data/vpapi-labels.json";

export interface VpapiLabel {
  slug: string;
  title: string;
  description?: string;
  /** VPAPI content tags this label maps to (see awempire-vpapi.ts fetchVpapiList). */
  vpapiTags: string[];
}

function parseLabels(raw: unknown): VpapiLabel[] {
  if (!raw || typeof raw !== "object") return [];
  const labels = (raw as { labels?: unknown }).labels;
  if (!Array.isArray(labels)) return [];
  return labels.filter(
    (l): l is VpapiLabel =>
      !!l &&
      typeof l === "object" &&
      typeof (l as VpapiLabel).slug === "string" &&
      typeof (l as VpapiLabel).title === "string" &&
      Array.isArray((l as VpapiLabel).vpapiTags)
  );
}

export function getVpapiLabels(): VpapiLabel[] {
  return parseLabels(labelConfig);
}

export function getVpapiLabel(slug: string): VpapiLabel | null {
  const needle = slug.trim().toLowerCase();
  return getVpapiLabels().find((l) => l.slug.toLowerCase() === needle) ?? null;
}

// Phase 2 / option (c): no per-video outbound URL exists in the verified
// VPAPI contract (see docs/handoffs/2026-08-10_aof-hub-p9-p10_report.md
// "Blockers" §1) — every card on a label page routes to the same
// beacon-wrapped destination, seeded server-side in
// tbcc/backend/app/data/web_hub_beacon_plan.py as `web-vpapi-<slug>`. The
// real destination lives there (single source of truth), not duplicated
// here, so this always resolves through the beacon when one is configured.
const VPAPI_FALLBACK_OUTBOUND_URL = "https://www.awempire.com/";

export function vpapiLabelOutboundHref(label: VpapiLabel): string {
  const base = process.env.NEXT_PUBLIC_TBCC_BEACON_BASE?.trim().replace(/\/$/, "");
  if (!base) return VPAPI_FALLBACK_OUTBOUND_URL;
  return `${base}/r/web-vpapi-${label.slug}`;
}
