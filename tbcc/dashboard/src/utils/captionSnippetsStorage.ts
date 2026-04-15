export const CAPTION_SNIPPETS_STORAGE_KEY = "tbcc.dashboard.captionSnippets.v1";

export type CaptionSnippet = {
  id: string;
  /** Short label for menus; falls back to first line of body if empty */
  title: string;
  body: string;
  createdAt: number;
};

function safeParse(raw: string | null): CaptionSnippet[] {
  if (!raw) return [];
  try {
    const j = JSON.parse(raw) as unknown;
    if (!Array.isArray(j)) return [];
    return j
      .filter(
        (x): x is CaptionSnippet =>
          typeof x === "object" &&
          x != null &&
          typeof (x as CaptionSnippet).id === "string" &&
          typeof (x as CaptionSnippet).body === "string"
      )
      .map((x) => ({
        id: x.id,
        title: typeof x.title === "string" ? x.title : "",
        body: x.body,
        createdAt: typeof x.createdAt === "number" ? x.createdAt : Date.now(),
      }));
  } catch {
    return [];
  }
}

export function loadCaptionSnippets(): CaptionSnippet[] {
  try {
    return safeParse(localStorage.getItem(CAPTION_SNIPPETS_STORAGE_KEY));
  } catch {
    return [];
  }
}

export function saveCaptionSnippets(items: CaptionSnippet[]): void {
  try {
    localStorage.setItem(CAPTION_SNIPPETS_STORAGE_KEY, JSON.stringify(items));
  } catch {
    /* quota / private mode */
  }
}

export function snippetMenuLabel(s: CaptionSnippet): string {
  const t = s.title.trim();
  if (t) return t.length > 40 ? `${t.slice(0, 37)}…` : t;
  const line = s.body.split(/\r?\n/).find((l) => l.trim()) ?? "";
  const p = line.trim().slice(0, 36);
  return p ? (line.trim().length > 36 ? `${p}…` : p) : "(untitled)";
}
