import { createAdminClient } from "../../../lib/supabase/admin";
import { logger } from "../../logger";
import { ingestOne } from "../pipeline";

/**
 * Pull captured media from the existing tbcc FastAPI backend into the forum.
 *
 * Contract assumption (intentionally minimal so it works against the current
 * tbcc API and any future paginated variant):
 *   GET  {TBCC_API_URL}/api/media?since_id=<n>&limit=50
 *   -> { items: [{ id, source_channel, media_type, url, telegram_message_id, ... }, ...] }
 *
 * Each item is treated as a `source_url` with `source_kind='telegram'`. The
 * pipeline downloads -> phash-dedupes -> uploads to B2 -> inserts media_items.
 *
 * State is stored in `payload` on a dedicated `ingest_jobs` row of kind 'telegram'
 * so we don't have to add a new table just for the cursor.
 */
export async function pullFromTelegram(opts: { watch: boolean }): Promise<void> {
  const apiUrl = process.env.TBCC_API_URL;
  const apiKey = process.env.TBCC_INTERNAL_API_KEY;
  if (!apiUrl) {
    logger.warn("TBCC_API_URL not set - telegram adapter disabled");
    return;
  }

  const db = createAdminClient();
  const pollMs = Number.parseInt(process.env.INGEST_POLL_MS || "5000", 10) * 6; // poll telegram less aggressively
  const headers: Record<string, string> = { Accept: "application/json" };
  if (apiKey) headers["X-Internal-Key"] = apiKey;

  const tick = async () => {
    // Get cursor (the highest tbcc media id we've already pulled).
    const cur = await db
      .from("ingest_jobs")
      .select("payload")
      .eq("source_kind", "telegram")
      .eq("status", "done")
      .order("id", { ascending: false })
      .limit(1)
      .maybeSingle();
    const sinceId =
      (cur.data?.payload as { tbcc_id?: number } | undefined)?.tbcc_id ?? 0;

    const url = new URL("/api/media", apiUrl);
    url.searchParams.set("since_id", String(sinceId));
    url.searchParams.set("limit", "50");

    let items: Array<{ id: number; url?: string; source_channel?: string; media_type?: string }> = [];
    try {
      const r = await fetch(url.toString(), { headers });
      if (!r.ok) {
        logger.warn({ status: r.status, url: url.toString() }, "tbcc fetch non-200 - check TBCC_API_URL and route shape");
        return;
      }
      const j = (await r.json()) as { items?: typeof items };
      items = j.items ?? [];
    } catch (e) {
      logger.warn({ err: (e as Error).message }, "tbcc fetch failed");
      return;
    }
    if (!items.length) return;
    logger.info({ count: items.length, sinceId }, "telegram: new items");

    for (const it of items) {
      if (!it.url) continue;
      const r = await ingestOne({
        source: it.url,
        sourceKind: "telegram",
        title: it.source_channel ? `tg/${it.source_channel}/${it.id}` : `tg/${it.id}`,
      });
      // Record cursor as a small ingest_jobs row so we can resume on restart.
      await db.from("ingest_jobs").insert({
        source_url: it.url,
        source_kind: "telegram",
        status: r.status,
        result_media_id: r.mediaId ?? null,
        error: r.reason ?? null,
        payload: { tbcc_id: it.id, source_channel: it.source_channel },
      });
    }
  };

  if (!opts.watch) {
    await tick();
    return;
  }
  logger.info({ pollMs, apiUrl }, "telegram adapter running");
  while (true) {
    await tick();
    await new Promise((r) => setTimeout(r, pollMs));
  }
}
