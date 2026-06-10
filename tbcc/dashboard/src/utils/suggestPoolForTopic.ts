/** Match a forum topic title to an AOF-style content pool name (e.g. "Ass" → "AOF ASS POOL"). */

function normalizeKey(s: string): string {
  return s.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
}

export function suggestPoolIdForTopicTitle(
  topicTitle: string,
  pools: Array<{ id: number; name?: string }>
): number | null {
  const t = normalizeKey(topicTitle);
  if (!t) return null;
  let best: { id: number; score: number } | null = null;
  for (const p of pools) {
    const pn = normalizeKey(String(p.name ?? ""));
    if (!pn) continue;
    const poolCore = pn.replace(/\bpool\b/g, "").trim();
    let score = 0;
    if (pn === t || poolCore === t) score = 100;
    else if (pn.includes(t) || t.includes(poolCore)) score = 75;
    else {
      for (const tok of t.split(/\s+/).filter((x) => x.length >= 3)) {
        if (pn.includes(tok)) score = Math.max(score, 55);
      }
    }
    if (score > 0 && (!best || score > best.score)) best = { id: p.id, score };
  }
  return best?.id ?? null;
}
