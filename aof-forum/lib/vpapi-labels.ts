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
