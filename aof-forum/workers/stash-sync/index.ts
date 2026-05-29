import { config as loadEnv } from "dotenv";
loadEnv({ path: process.env.DOTENV_PATH ?? ".env.local" });
loadEnv({ path: ".env", override: false });

import { createAdminClient } from "../../lib/supabase/admin";
import {
  getAllPerformers,
  getAllStudios,
  getAllTags,
  iterAllScenes,
  pickPhash,
  type StashScene,
} from "../../lib/stash";
import { logger } from "../logger";

/**
 * Stash -> Supabase sync.
 *
 *   1. Tags / Performers / Studios from Stash become rows in public.tags
 *      (single table, kind discriminator). Idempotent upserts on slug.
 *   2. For each Stash Scene with a phash fingerprint, find the matching row
 *      in media_items by phash and copy its tags into media_tags with
 *      source='stash'. Idempotent on (media_id, tag_id).
 *
 * Usage:
 *   tsx workers/stash-sync/index.ts            # one pass
 *   tsx workers/stash-sync/index.ts --watch    # loop every SYNC_INTERVAL_MS
 */

function slugify(s: string): string {
  return s
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80);
}

async function syncTagsLike(
  kind: "tag" | "performer" | "studio",
  items: Array<{ id: string; name: string; description?: string | null; aliases?: string[] | null; image_path?: string | null }>
): Promise<Map<string, number>> {
  const db = createAdminClient();
  const result = new Map<string, number>();
  for (const it of items) {
    const slug = `${kind === "tag" ? "" : kind + "-"}${slugify(it.name)}`;
    const { data, error } = await db
      .from("tags")
      .upsert(
        {
          slug,
          name: it.name,
          kind,
          description: it.description ?? null,
          aliases: it.aliases ?? [],
          cover_url: it.image_path ?? null,
        },
        { onConflict: "slug" }
      )
      .select("id")
      .single();
    if (error || !data) {
      logger.warn({ err: error?.message, slug }, "tag upsert failed");
      continue;
    }
    result.set(it.id, data.id as number);
  }
  return result;
}

async function syncScene(
  scene: StashScene,
  tagIdMap: Map<string, number>,
  performerIdMap: Map<string, number>,
  studioIdMap: Map<string, number>
): Promise<void> {
  const db = createAdminClient();
  const fp = pickPhash(scene);
  if (!fp) return; // can't dedupe without a fingerprint

  // Match against media_items.phash (hex) OR media_items.stash_scene_id (already linked).
  let mediaId: number | null = null;
  const linked = await db
    .from("media_items")
    .select("id")
    .eq("stash_scene_id", scene.id)
    .maybeSingle();
  if (linked.data?.id) mediaId = linked.data.id as number;

  if (!mediaId) {
    // phash from Stash is a hex string; convert to bytea-compatible form.
    const hex = fp.value.replace(/^0x/, "");
    const buf = Buffer.from(hex.length % 2 === 0 ? hex : "0" + hex, "hex");
    if (buf.length === 8) {
      const byHash = await db
        .from("media_items")
        .select("id")
        .eq("phash", `\\x${buf.toString("hex")}`)
        .limit(1)
        .maybeSingle();
      if (byHash.data?.id) {
        mediaId = byHash.data.id as number;
        await db.from("media_items").update({ stash_scene_id: scene.id }).eq("id", mediaId);
      }
    }
  }

  if (!mediaId) return;

  const tagIds = new Set<number>();
  for (const t of scene.tags) {
    const id = tagIdMap.get(t.id);
    if (id) tagIds.add(id);
  }
  for (const p of scene.performers) {
    const id = performerIdMap.get(p.id);
    if (id) tagIds.add(id);
  }
  if (scene.studio) {
    const id = studioIdMap.get(scene.studio.id);
    if (id) tagIds.add(id);
  }

  if (tagIds.size === 0) return;

  const rows = [...tagIds].map((tagId) => ({
    media_id: mediaId!,
    tag_id: tagId,
    weight: 1.0,
    source: "stash" as const,
  }));
  const { error } = await db.from("media_tags").upsert(rows, { onConflict: "media_id,tag_id" });
  if (error) logger.warn({ err: error.message, mediaId }, "media_tags upsert failed");
}

async function runOnce(): Promise<void> {
  logger.info("stash-sync: fetching catalog");
  const [tags, performers, studios] = await Promise.all([
    getAllTags(),
    getAllPerformers(),
    getAllStudios(),
  ]);
  logger.info({ tags: tags.length, performers: performers.length, studios: studios.length }, "stash-sync: catalog");

  const tagIdMap = await syncTagsLike("tag", tags);
  const performerIdMap = await syncTagsLike("performer", performers);
  const studioIdMap = await syncTagsLike("studio", studios);

  logger.info("stash-sync: iterating scenes");
  let n = 0;
  for await (const scene of iterAllScenes(100)) {
    await syncScene(scene, tagIdMap, performerIdMap, studioIdMap);
    n += 1;
    if (n % 100 === 0) logger.info({ scenes: n }, "stash-sync: progress");
  }
  logger.info({ scenes: n }, "stash-sync: done");
}

async function main(): Promise<void> {
  const watch = process.argv.includes("--watch");
  const interval = Number.parseInt(process.env.STASH_SYNC_INTERVAL_MS || "300000", 10); // 5 min

  if (!watch) {
    await runOnce();
    return;
  }
  while (true) {
    try {
      await runOnce();
    } catch (e) {
      logger.error({ err: (e as Error).message }, "stash-sync pass failed");
    }
    await new Promise((r) => setTimeout(r, interval));
  }
}

main().catch((e) => {
  logger.fatal({ err: (e as Error).message, stack: (e as Error).stack }, "stash-sync crashed");
  process.exit(1);
});
