/** Shared tag-catalog search / junk-filter helpers (extension mirrors in tag-catalog-combobox.js). */

export type TagCatalogRow = {
  id: number;
  slug: string;
  name?: string | null;
  category?: string | null;
};

export function tagPickerLabel(t: TagCatalogRow): string {
  const name = t.name != null ? String(t.name).trim() : "";
  const slug = t.slug != null ? String(t.slug).trim() : "";
  return name || slug;
}

/** Hide hex-ID-like rows in pickers (DB unchanged). */
export function isJunkCatalogTagRow(t: TagCatalogRow): boolean {
  const name = t.name != null && String(t.name).trim() ? String(t.name).trim() : "";
  const slug = t.slug != null && String(t.slug).trim() ? String(t.slug).trim() : "";
  const primary = name || slug;
  if (!primary || primary.length < 8) return false;
  const compact = primary.replace(/[\s_\-]/g, "");
  if (/^[0-9a-f]{10,}$/i.test(compact)) return true;
  const alnum = primary.replace(/[^a-z0-9]/gi, "");
  if (alnum.length >= 14) {
    const hexish = (alnum.match(/[0-9a-f]/gi) || []).length;
    if (hexish / alnum.length >= 0.82) return true;
  }
  if (/^[0-9]{12,}$/.test(alnum)) return true;
  return false;
}

export function catalogRowsForPicker(rows: TagCatalogRow[]): { kept: TagCatalogRow[]; filteredCount: number } {
  const full = Array.isArray(rows) ? rows : [];
  const kept = full.filter((t) => !isJunkCatalogTagRow(t));
  return { kept, filteredCount: full.length - kept.length };
}

export function searchCatalogTags(
  rows: TagCatalogRow[],
  query: string,
  limit = 48
): { items: TagCatalogRow[]; prefixLabel: string | null } {
  const q = query.trim().toLowerCase();
  if (!q) {
    const items = rows.slice(0, limit);
    return { items, prefixLabel: null };
  }
  type Scored = { row: TagCatalogRow; score: number; label: string };
  const scored: Scored[] = [];
  for (const row of rows) {
    const label = tagPickerLabel(row);
    if (!label) continue;
    const low = label.toLowerCase();
    const slugLow = (row.slug || "").toLowerCase();
    let score = -1;
    if (low.startsWith(q)) score = 1000 - low.length;
    else if (slugLow.startsWith(q)) score = 900 - slugLow.length;
    else if (low.includes(q)) score = 500 - low.indexOf(q);
    else if (slugLow.includes(q)) score = 400 - slugLow.indexOf(q);
    if (score >= 0) scored.push({ row, score, label });
  }
  scored.sort((a, b) => b.score - a.score || a.label.localeCompare(b.label, undefined, { sensitivity: "base" }));
  const top = scored[0];
  const prefixLabel = top && top.label.toLowerCase().startsWith(q) ? top.label : null;
  return { items: scored.slice(0, limit).map((s) => s.row), prefixLabel };
}

/** Suffix after typed query for inline ghost completion (e.g. query "BB" → "W" for "BBW"). */
export function autocompleteRemainder(query: string, fullLabel: string): string {
  const q = query.trim();
  if (!q || !fullLabel) return "";
  if (!fullLabel.toLowerCase().startsWith(q.toLowerCase())) return "";
  return fullLabel.slice(q.length);
}
