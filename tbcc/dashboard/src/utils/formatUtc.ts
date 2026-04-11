function parseBackendUtc(s: string): Date {
  const t = s.trim();
  if (/[zZ]|[+-]\d{2}:?\d{2}$/.test(t)) return new Date(t);
  const iso = t.includes("T") ? t : t.replace(" ", "T");
  return new Date(`${iso}Z`);
}

/** Backend stores naive UTC; API often returns ISO without Z — normalize for display. */
export function formatUtcForDashboard(iso: string | null | undefined): string {
  if (iso == null || iso === "") return "—";
  const s = String(iso).trim();
  const d = parseBackendUtc(s);
  if (Number.isNaN(d.getTime())) return s;
  return `${d.toISOString().replace("T", " ").slice(0, 19)} UTC`;
}

/** Tooltip: same instant in local timezone for comparing to Telegram app times. */
export function formatUtcWithLocalHint(iso: string | null | undefined): string {
  if (iso == null || iso === "") return "";
  const s = String(iso).trim();
  const d = parseBackendUtc(s);
  if (Number.isNaN(d.getTime())) return s;
  const utc = `${d.toISOString().replace("T", " ").slice(0, 19)} UTC`;
  const local = d.toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" });
  return `${utc} · ${local} (your time)`;
}
