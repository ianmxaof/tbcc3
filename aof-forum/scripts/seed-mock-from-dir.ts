/**
 * Devops / mock: ingest every image & video under a folder, split into public galleries,
 * attach a chunk to a demo group, and bump views/scores so home-page rails look alive.
 *
 * Prereqs: aof-forum/.env.local with Supabase + B2 + NEXT_PUBLIC_MEDIA_BASE_URL set; ffmpeg optional for video thumbs.
 *
 * Usage (from repo aof-forum/):
 *   npx tsx scripts/seed-mock-from-dir.ts "D:\media\demo-pack"
 *
 * Also set in .env.local:
 *   MOCK_SEED_USER_ID=<uuid from auth.users / profiles — the account that should "own" the seed>
 */
import { config } from "dotenv";
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { createAdminClient } from "../lib/supabase/admin";
import { ingestOne } from "../workers/ingest/pipeline";

const root = process.cwd();
config({ path: path.join(root, ".env.local") });
config({ path: path.join(root, ".env") });

const IMG = new Set([".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"]);
const VID = new Set([".mp4", ".webm", ".mov", ".mkv", ".m4v"]);

function collectFiles(dir: string, out: string[], max: number) {
  if (out.length >= max) return;
  let entries: fs.Dirent[];
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true });
  } catch {
    return;
  }
  for (const e of entries) {
    if (out.length >= max) break;
    const p = path.join(dir, e.name);
    if (e.isDirectory()) collectFiles(p, out, max);
    else {
      const ext = path.extname(e.name).toLowerCase();
      if (IMG.has(ext) || VID.has(ext)) out.push(p);
    }
  }
}

function slugify(base: string): string {
  const s = base
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 48);
  return s || "gallery";
}

async function main() {
  const dirArg = process.argv.slice(2).find((a) => !a.startsWith("-"));
  if (!dirArg) {
    console.error('Usage: npx tsx scripts/seed-mock-from-dir.ts "C:\\path\\to\\folder"');
    process.exit(1);
  }
  const src = path.resolve(dirArg);
  if (!fs.existsSync(src) || !fs.statSync(src).isDirectory()) {
    console.error("Not a directory:", src);
    process.exit(1);
  }
  const ownerId = process.env.MOCK_SEED_USER_ID?.trim();
  if (!ownerId) {
    console.error("Set MOCK_SEED_USER_ID in .env.local to a real profiles.id (auth user UUID).");
    process.exit(1);
  }
  const perGallery = Math.min(
    Math.max(parseInt(process.env.MOCK_SEED_ITEMS_PER_GALLERY ?? "24", 10) || 24, 4),
    120
  );
  const maxFiles = Math.min(
    Math.max(parseInt(process.env.MOCK_SEED_MAX_FILES ?? "400", 10) || 400, 1),
    2000
  );

  const files: string[] = [];
  collectFiles(src, files, maxFiles);
  files.sort();
  if (files.length === 0) {
    console.error("No image/video files found under", src);
    process.exit(1);
  }

  console.log(`Found ${files.length} file(s). Ingesting (B2 + DB)…`);
  const mediaIds: number[] = [];
  for (const file of files) {
    const r = await ingestOne({
      source: file,
      sourceKind: "local_inbox",
      uploaderId: ownerId,
      title: path.basename(file, path.extname(file)),
    });
    if (r.status === "done" && r.mediaId) {
      mediaIds.push(r.mediaId);
      console.log("  ok", r.mediaId, path.basename(file));
    } else if (r.status === "skipped_duplicate") {
      console.log("  skip duplicate", path.basename(file));
    } else {
      console.warn("  fail", path.basename(file), r.reason ?? r.status);
    }
  }
  if (mediaIds.length === 0) {
    console.error("No media ingested — check B2 creds and pipeline logs.");
    process.exit(1);
  }

  const db = createAdminClient();
  const galleryIds: number[] = [];
  const baseStamp = Date.now().toString(36);

  for (let i = 0; i < mediaIds.length; i += perGallery) {
    const chunk = mediaIds.slice(i, i + perGallery);
    const idx = i / perGallery;
    const title = `Mock ${path.basename(src)} · ${idx + 1}`;
    const slug = `${slugify(path.basename(src))}-${baseStamp}-${idx}`;
    const { data: g, error: ge } = await db
      .from("galleries")
      .insert({
        owner_id: ownerId,
        title,
        description: `Seeded from ${pathToFileURL(src).href}`,
        slug,
        is_public: true,
        cover_media_id: chunk[0],
      })
      .select("id")
      .single();
    if (ge || !g) {
      console.error("Gallery insert failed", ge?.message);
      process.exit(1);
    }
    const gid = g.id as number;
    galleryIds.push(gid);
    const rows = chunk.map((mediaId, position) => ({ gallery_id: gid, media_id: mediaId, position }));
    const { error: ie } = await db.from("gallery_items").insert(rows);
    if (ie) {
      console.error("gallery_items insert failed", ie.message);
      process.exit(1);
    }
    const views = 2000 + Math.floor(Math.random() * 80000);
    const score = 5 + Math.random() * 95;
    await db.from("galleries").update({ views_count: views, score }).eq("id", gid);
    console.log("Gallery", slug, gid, chunk.length, "items");
  }

  const groupSlug = `mock-hub-${baseStamp}`;
  const groupName = `Mock hub · ${path.basename(src)}`;
  const { data: grp, error: gErr } = await db
    .from("groups")
    .insert({
      slug: groupSlug,
      name: groupName,
      description: "Auto-seeded group for UI mockups.",
      owner_id: ownerId,
      visibility: "public",
    })
    .select("id")
    .single();
  if (gErr || !grp) {
    console.error("Group insert failed", gErr?.message);
    process.exit(1);
  }
  const groupId = grp.id as number;
  const attach = mediaIds.slice(0, Math.min(80, mediaIds.length));
  const gmRows = attach.map((mediaId, position) => ({
    group_id: groupId,
    media_id: mediaId,
    added_by: ownerId,
    position,
  }));
  const { error: gmErr } = await db.from("group_media").insert(gmRows);
  if (gmErr) console.warn("group_media insert:", gmErr.message);

  for (const gid of galleryIds.slice(0, 6)) {
    await db
      .from("galleries")
      .update({ votes_up: 15 + Math.floor(Math.random() * 180) })
      .eq("id", gid);
  }

  for (const mid of mediaIds) {
    const vc = 300 + Math.floor(Math.random() * 120_000);
    const sc = 1 + Math.random() * 40;
    await db.from("media_items").update({ views_count: vc, score: sc }).eq("id", mid);
  }

  console.log("");
  console.log("Done.");
  console.log("  Home:", "http://127.0.0.1:3001/");
  console.log("  Galleries index:", "http://127.0.0.1:3001/g");
  console.log("  Demo group:", `http://127.0.0.1:3001/groups/${groupSlug}`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
