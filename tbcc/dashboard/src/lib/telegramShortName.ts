/** Telegram custom emoji pack short name base (before ``_by_<user_id>`` is appended server-side). */
export function slugShortNameBase(raw: string): string {
  let s = (raw || "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/_+/g, "_")
    .replace(/^_|_$/g, "");
  if (!s) s = "pack";
  if (!/^[a-z]/.test(s)) s = `pack_${s}`.replace(/_+/g, "_").replace(/^_|_$/g, "");
  return s.slice(0, 40) || "pack";
}

export function shortNameLooksValidBase(raw: string): boolean {
  const s = slugShortNameBase(raw);
  return /^[a-z][a-z0-9_]*$/.test(s) && !s.includes("__");
}
