import { createAdminClient } from "../../../lib/supabase/admin";
import { logger } from "../../logger";
import { ingestOne } from "../pipeline";

/**
 * Poll `ingest_jobs` for `status='queued'` rows (created by the api/ingest
 * Route Handler when a user pastes a URL in the UI) and process them.
 */
export async function startJobQueueWorker(opts: { watch: boolean }): Promise<void> {
  const db = createAdminClient();
  const pollMs = Number.parseInt(process.env.INGEST_POLL_MS || "5000", 10);

  const tick = async () => {
    const { data, error } = await db
      .from("ingest_jobs")
      .select("id, source_url, source_kind, requester_id, destination_group_id, destination_gallery_id, attempts")
      .eq("status", "queued")
      .order("created_at", { ascending: true })
      .limit(5);
    if (error) {
      logger.error({ err: error.message }, "queue poll failed");
      return;
    }
    if (!data?.length) return;
    for (const job of data) {
      await db
        .from("ingest_jobs")
        .update({ status: "fetching", attempts: (job.attempts ?? 0) + 1 })
        .eq("id", job.id);
      try {
        if (!job.source_url) {
          await db.from("ingest_jobs").update({ status: "failed", error: "no source_url" }).eq("id", job.id);
          continue;
        }
        const r = await ingestOne({
          source: job.source_url,
          sourceKind: job.source_kind,
          uploaderId: job.requester_id,
          groupId: job.destination_group_id,
          galleryId: job.destination_gallery_id,
        });
        await db
          .from("ingest_jobs")
          .update({ status: r.status, result_media_id: r.mediaId ?? null, error: r.reason ?? null })
          .eq("id", job.id);
        logger.info({ id: job.id, ...r }, "queue: processed");
      } catch (e) {
        const msg = (e as Error).message;
        await db.from("ingest_jobs").update({ status: "failed", error: msg }).eq("id", job.id);
        logger.error({ id: job.id, err: msg }, "queue: job failed");
      }
    }
  };

  if (!opts.watch) {
    await tick();
    return;
  }
  logger.info({ pollMs }, "job-queue worker running");
  while (true) {
    await tick();
    await new Promise((r) => setTimeout(r, pollMs));
  }
}
