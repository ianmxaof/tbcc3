/**
 * Populate forum, galleries, groups, tube feed, and Connect listings with demo data.
 * Uses HTTPS placeholder images (no B2 required).
 *
 *   npm run seed:demo
 *   npm run seed:demo -- --force
 */
import { config } from "dotenv";
import path from "node:path";
import { createAdminClient } from "../lib/supabase/admin";

const root = process.cwd();
config({ path: path.join(root, ".env.local") });
config({ path: path.join(root, ".env") });

const MARKER_SLUG = "demo-hub-seed-v1";
const DEMO_PREFIX = "demo-";

function demoImageUrl(seed: number, w = 480, h = 640): string {
  return `https://picsum.photos/seed/aof-hub-${seed}/${w}/${h}`;
}

function rand(min: number, max: number): number {
  return min + Math.floor(Math.random() * (max - min + 1));
}

function hoursAgo(h: number): string {
  return new Date(Date.now() - h * 3600_000).toISOString();
}

async function hasExistingSeed(db: ReturnType<typeof createAdminClient>): Promise<boolean> {
  const { data } = await db.from("forum_categories").select("id").eq("slug", MARKER_SLUG).maybeSingle();
  return !!data;
}

async function insertDemoMedia(
  db: ReturnType<typeof createAdminClient>,
  ownerId: string,
  count: number
): Promise<number[]> {
  const ids: number[] = [];
  for (let i = 0; i < count; i++) {
    const seed = 1000 + i;
    const { data, error } = await db
      .from("media_items")
      .insert({
        kind: "image",
        title: `Demo clip ${i + 1}`,
        b2_key: demoImageUrl(seed, 640, 900),
        b2_thumb_key: demoImageUrl(seed, 320, 450),
        mime: "image/jpeg",
        byte_size: 120_000,
        width: 640,
        height: 900,
        source_kind: "upload",
        uploader_id: ownerId,
        is_public: true,
        is_nsfw: true,
        views_count: rand(500, 95_000),
        score: 2 + Math.random() * 45,
        votes_up: rand(5, 200),
      })
      .select("id")
      .single();
    if (error) {
      if (error.code === "23505") continue;
      throw new Error(`media insert: ${error.message}`);
    }
    ids.push(data.id as number);
  }
  return ids;
}

async function seedForum(db: ReturnType<typeof createAdminClient>, ownerId: string) {
  const categories = [
    { slug: MARKER_SLUG, name: "Demo hub (seed marker)", description: "Internal — marks demo seed run.", position: 0 },
    { slug: `${DEMO_PREFIX}general`, name: "General", description: "Site chat, intros, off-topic.", position: 1 },
    { slug: `${DEMO_PREFIX}creators`, name: "Creators", description: "Tips for building galleries and growing reach.", position: 2 },
    { slug: `${DEMO_PREFIX}feedback`, name: "Feedback", description: "Bugs, feature requests, UX notes.", position: 3 },
    { slug: `${DEMO_PREFIX}marketplace`, name: "Marketplace", description: "Promos, collabs, and creator services.", position: 4 },
  ];

  const catIds = new Map<string, number>();
  for (const c of categories) {
    const { data, error } = await db.from("forum_categories").insert(c).select("id, slug").single();
    if (error) {
      if (error.code === "23505") {
        const { data: existing } = await db.from("forum_categories").select("id").eq("slug", c.slug).single();
        if (existing) catIds.set(c.slug, existing.id as number);
        continue;
      }
      throw new Error(`forum category: ${error.message}`);
    }
    catIds.set(data.slug, data.id as number);
  }

  const threads: Array<{ cat: string; slug: string; title: string; body: string; replies: string[] }> = [
    {
      cat: `${DEMO_PREFIX}general`,
      slug: "welcome-to-aof-hub",
      title: "Welcome to AOF Hub — read this first",
      body: "Tube, galleries, live cams, forum, and Connect listings all funnel to Telegram for unlocks. Say hi and tell us what you want to see next.",
      replies: [
        "Signed up via magic link — gallery grid looks great on mobile.",
        "Would love more tag filters on the home feed.",
      ],
    },
    {
      cat: `${DEMO_PREFIX}general`,
      slug: "best-time-to-post",
      title: "When do you usually see the most traffic?",
      body: "Trying to schedule gallery drops and Connect bumps. What windows work for you?",
      replies: ["Evenings US Eastern.", "Weekend mornings surprisingly good for EU audience."],
    },
    {
      cat: `${DEMO_PREFIX}creators`,
      slug: "gallery-cover-tips",
      title: "Gallery cover image tips",
      body: "First thumb in the grid sets the tone. Use high contrast, crop tight, and keep text out of the frame.",
      replies: ["+1 — vertical covers outperform on mobile.", "I batch upload then reorder in the wizard."],
    },
    {
      cat: `${DEMO_PREFIX}creators`,
      slug: "connect-vs-gallery",
      title: "Connect listing vs gallery — when to use which?",
      body: "Galleries for hosted media; Connect for Snap/Telegram handles and bulletin updates. Both can point to the same Telegram bot CTA.",
      replies: [],
    },
    {
      cat: `${DEMO_PREFIX}feedback`,
      slug: "dark-mode-contrast",
      title: "Dark mode contrast on vote buttons",
      body: "Minor nit: downvote active state could be a touch brighter on OLED.",
      replies: ["Noted — will tweak in the next UI pass."],
    },
    {
      cat: `${DEMO_PREFIX}marketplace`,
      slug: "looking-for-editor",
      title: "[Hiring] Short-form clip editor",
      body: "Need someone for 10–15s teasers from longer gallery sets. DM on Telegram.",
      replies: ["Sent you a message — portfolio in bio."],
    },
  ];

  for (const t of threads) {
    const categoryId = catIds.get(t.cat);
    if (!categoryId) continue;

    const { data: thread, error: te } = await db
      .from("forum_threads")
      .insert({
        category_id: categoryId,
        author_id: ownerId,
        title: t.title,
        slug: t.slug,
        views_count: rand(80, 12_000),
        votes_up: rand(3, 120),
        score: 5 + Math.random() * 40,
        last_reply_at: hoursAgo(rand(1, 72)),
      })
      .select("id")
      .single();
    if (te) {
      if (te.code === "23505") continue;
      throw new Error(`thread: ${te.message}`);
    }

    const { error: pe } = await db.from("forum_posts").insert({
      thread_id: thread.id,
      author_id: ownerId,
      body_md: t.body,
      votes_up: rand(2, 40),
      score: 3 + Math.random() * 10,
    });
    if (pe) throw new Error(`post: ${pe.message}`);

    for (let i = 0; i < t.replies.length; i++) {
      await db.from("forum_posts").insert({
        thread_id: thread.id,
        author_id: ownerId,
        body_md: t.replies[i],
        created_at: hoursAgo(rand(1, 48)),
      });
    }
  }
}

async function seedGalleries(
  db: ReturnType<typeof createAdminClient>,
  ownerId: string,
  mediaIds: number[]
) {
  const titles = [
    "Late night set",
    "Weekend favorites",
    "Editor picks · vol 1",
    "Behind the scenes",
    "Fan submissions",
    "Classic archive",
  ];

  for (let i = 0; i < titles.length; i++) {
    const slug = `${DEMO_PREFIX}gallery-${i + 1}`;
    const start = i * 8;
    const chunk = mediaIds.slice(start, start + 8);
    if (chunk.length < 4) break;

    const { data: g, error: ge } = await db
      .from("galleries")
      .insert({
        owner_id: ownerId,
        title: titles[i],
        description: `Demo gallery ${i + 1} — seeded for UI review.`,
        slug,
        is_public: true,
        cover_media_id: chunk[0],
        views_count: rand(2_000, 90_000),
        votes_up: rand(10, 180),
        score: 8 + Math.random() * 80,
      })
      .select("id")
      .single();
    if (ge) {
      if (ge.code === "23505") continue;
      throw new Error(`gallery: ${ge.message}`);
    }

    const rows = chunk.map((mediaId, position) => ({ gallery_id: g.id, media_id: mediaId, position }));
    const { error: ie } = await db.from("gallery_items").insert(rows);
    if (ie) throw new Error(`gallery_items: ${ie.message}`);
  }
}

async function seedGroups(
  db: ReturnType<typeof createAdminClient>,
  ownerId: string,
  mediaIds: number[]
) {
  const groups = [
    { slug: `${DEMO_PREFIX}amateur`, name: "Amateur hub", description: "Community-curated amateur collections." },
    { slug: `${DEMO_PREFIX}cosplay`, name: "Cosplay & fantasy", description: "Costumes, characters, creative sets." },
    { slug: `${DEMO_PREFIX}vintage`, name: "Vintage vault", description: "Throwback aesthetics and film grain." },
    { slug: `${DEMO_PREFIX}creators-circle`, name: "Creators circle", description: "Growth tactics and collab threads." },
  ];

  for (let gi = 0; gi < groups.length; gi++) {
    const g = groups[gi];
    const { data: row, error } = await db
      .from("groups")
      .insert({
        ...g,
        owner_id: ownerId,
        visibility: "public",
        member_count: rand(40, 800),
        item_count: 0,
        thread_count: rand(2, 30),
        score: 10 + Math.random() * 50,
      })
      .select("id, slug")
      .single();
    if (error) {
      if (error.code === "23505") continue;
      throw new Error(`group: ${error.message}`);
    }

    const attach = mediaIds.slice(gi * 6, gi * 6 + 12);
    if (attach.length) {
      const gmRows = attach.map((mediaId, position) => ({
        group_id: row.id,
        media_id: mediaId,
        added_by: ownerId,
        position,
      }));
      await db.from("group_media").insert(gmRows);
    }
  }
}

const CONNECT_SAMPLES = [
  { platform: "snapchat", handle: "demo_luna_snap", display_name: "Luna", gender: "female", orientation: "bi", country: "US", bulletin: "Online now · reply fast 💋", vip: true, fire: true },
  { platform: "telegram", handle: "demo_aria_tg", display_name: "Aria", gender: "female", orientation: "straight", country: "GB", bulletin: "Free preview in bio", vip: true, fire: false },
  { platform: "snapchat", handle: "demo_jade_snap", display_name: "Jade", gender: "female", orientation: "lesbian", country: "CA", bulletin: "Weekend specials", vip: false, fire: true },
  { platform: "telegram", handle: "demo_mia_tg", display_name: "Mia", gender: "female", orientation: "bi", country: "DE", bulletin: "Custom requests open", vip: false, fire: false },
  { platform: "instagram", handle: "demo_nova_ig", display_name: "Nova", gender: "female", orientation: "straight", country: "US", bulletin: "Link in story highlights", vip: true, fire: false },
  { platform: "snapchat", handle: "demo_raven_snap", display_name: "Raven", gender: "trans", orientation: "other", country: "AU", bulletin: "New menu dropped", vip: false, fire: false },
  { platform: "telegram", handle: "demo_skye_tg", display_name: "Skye", gender: "couple", orientation: "straight", country: "US", bulletin: "Couple account · both reply", vip: true, fire: false },
  { platform: "snapchat", handle: "demo_peach_snap", display_name: "Peach", gender: "female", orientation: "straight", country: "FR", bulletin: "Accepting new friends", vip: false, fire: false },
  { platform: "telegram", handle: "demo_bliss_tg", display_name: "Bliss", gender: "female", orientation: "gay", country: "NL", bulletin: "Voice notes welcome", vip: false, fire: true },
  { platform: "other", handle: "demo_kiki_other", display_name: "Kiki", gender: "female", orientation: "bi", country: "ES", bulletin: "Check pinned message", vip: false, fire: false },
  { platform: "snapchat", handle: "demo_honey_snap", display_name: "Honey", gender: "female", orientation: "straight", country: "US", bulletin: "🔥 fire sale tonight", vip: true, fire: true },
  { platform: "telegram", handle: "demo_vex_tg", display_name: "Vex", gender: "male", orientation: "gay", country: "US", bulletin: "DM for rates", vip: false, fire: false },
  { platform: "snapchat", handle: "demo_pixie_snap", display_name: "Pixie", gender: "female", orientation: "bi", country: "IE", bulletin: "Small account · real replies", vip: false, fire: false },
  { platform: "telegram", handle: "demo_storm_tg", display_name: "Storm", gender: "female", orientation: "straight", country: "PL", bulletin: "Bundles in channel", vip: true, fire: false },
  { platform: "instagram", handle: "demo_elle_ig", display_name: "Elle", gender: "female", orientation: "lesbian", country: "SE", bulletin: "IG for teasers only", vip: false, fire: false },
  { platform: "snapchat", handle: "demo_coco_snap", display_name: "Coco", gender: "female", orientation: "straight", country: "BR", bulletin: "Portuguese / English", vip: false, fire: false },
  { platform: "telegram", handle: "demo_zara_tg", display_name: "Zara", gender: "female", orientation: "bi", country: "IT", bulletin: "Tip menu updated", vip: true, fire: false },
  { platform: "snapchat", handle: "demo_ivy_snap", display_name: "Ivy", gender: "female", orientation: "straight", country: "MX", bulletin: "Add with 🔥 emoji", vip: false, fire: true },
  { platform: "telegram", handle: "demo_rose_tg", display_name: "Rose", gender: "female", orientation: "straight", country: "US", bulletin: "Stars unlock in bot", vip: false, fire: false },
  { platform: "snapchat", handle: "demo_faye_snap", display_name: "Faye", gender: "female", orientation: "bi", country: "NO", bulletin: "Europe mornings", vip: false, fire: false },
] as const;

async function ensureTags(db: ReturnType<typeof createAdminClient>, names: string[]): Promise<Map<string, number>> {
  const out = new Map<string, number>();
  for (const name of names) {
    const slug = name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
    const { data: existing } = await db.from("tags").select("id").eq("slug", slug).maybeSingle();
    if (existing) {
      out.set(name, existing.id as number);
      continue;
    }
    const { data, error } = await db
      .from("tags")
      .insert({ slug, name, kind: "tag" })
      .select("id")
      .single();
    if (error) throw new Error(`tag ${name}: ${error.message}`);
    out.set(name, data.id as number);
  }
  return out;
}

async function seedConnect(
  db: ReturnType<typeof createAdminClient>,
  ownerId: string,
  avatarMediaIds: number[]
) {
  const tagMap = await ensureTags(db, ["verified", "fast reply", "custom", "cosplay", "fitness", "gfe"]);

  for (let i = 0; i < CONNECT_SAMPLES.length; i++) {
    const s = CONNECT_SAMPLES[i];
    const avatarId = avatarMediaIds[i % avatarMediaIds.length] ?? null;
    const now = Date.now();
    const fireUntil = s.fire ? new Date(now + 24 * 3600_000).toISOString() : null;
    const vipUntil = s.vip ? new Date(now + 30 * 24 * 3600_000).toISOString() : null;

    const { data: listing, error } = await db
      .from("connect_listings")
      .insert({
        owner_id: ownerId,
        platform: s.platform,
        handle: s.handle,
        display_name: s.display_name,
        age: 21 + (i % 8),
        age_attested: true,
        gender: s.gender,
        orientation: s.orientation,
        country: s.country,
        bio: `${s.display_name} — demo Connect listing for UI review. Links out to ${s.platform}.`,
        bulletin: s.bulletin,
        bulletin_updated_at: hoursAgo(rand(0, 12)),
        avatar_media_id: avatarId,
        status: "approved",
        is_public: true,
        is_vip: s.vip,
        vip_until: vipUntil,
        fire_pin_until: fireUntil,
        last_active_at: hoursAgo(rand(0, 48)),
        views_count: rand(200, 45_000),
        click_count: rand(20, 3_000),
        score: 15 + Math.random() * 85,
      })
      .select("id")
      .single();

    if (error) {
      if (error.code === "23505") continue;
      if (error.message.includes("connect_listings")) {
        console.warn("Connect table missing — run npm run db:push first.");
        return;
      }
      throw new Error(`connect listing: ${error.message}`);
    }

    const tagNames = [["fast reply"], ["custom", "gfe"], ["cosplay"], ["fitness"], ["verified"]][i % 5];
    for (const tn of tagNames) {
      const tagId = tagMap.get(tn);
      if (!tagId) continue;
      await db.from("connect_listing_tags").insert({
        listing_id: listing.id,
        tag_id: tagId,
        added_by: ownerId,
      });
    }
  }
}

async function ensureOwnerProfile(db: ReturnType<typeof createAdminClient>, ownerId: string) {
  const { data: existing } = await db.from("profiles").select("id").eq("id", ownerId).maybeSingle();
  if (existing) {
    await db.from("profiles").update({ handle: "demo_operator", display_name: "Demo Operator" }).eq("id", ownerId);
    return;
  }
  const { error } = await db.from("profiles").insert({
    id: ownerId,
    handle: "demo_operator",
    display_name: "Demo Operator",
  });
  if (error) throw new Error(`profile: ${error.message} — run npm run dev:bootstrap-user first.`);
}

async function main() {
  const force = process.argv.includes("--force");
  const ownerId = process.env.MOCK_SEED_USER_ID?.trim();
  if (!ownerId) {
    console.error("Set MOCK_SEED_USER_ID in .env.local (bootstrap user UUID).");
    process.exit(1);
  }

  const db = createAdminClient();

  if (!force && (await hasExistingSeed(db))) {
    console.log("Demo seed already present (forum category marker exists). Use --force to add more.");
    console.log("URLs:");
    console.log("  http://127.0.0.1:3001/f");
    console.log("  http://127.0.0.1:3001/g");
    console.log("  http://127.0.0.1:3001/groups");
    console.log("  http://127.0.0.1:3001/connect");
    process.exit(0);
  }

  await ensureOwnerProfile(db, ownerId);

  console.log("Seeding demo media…");
  const mediaIds = await insertDemoMedia(db, ownerId, 48);
  console.log(`  ${mediaIds.length} media items`);

  console.log("Seeding forum…");
  await seedForum(db, ownerId);

  console.log("Seeding galleries…");
  await seedGalleries(db, ownerId, mediaIds);

  console.log("Seeding groups…");
  await seedGroups(db, ownerId, mediaIds);

  console.log("Seeding Connect listings…");
  await seedConnect(db, ownerId, mediaIds.slice(0, 20));

  console.log("");
  console.log("Done — browse locally:");
  console.log("  Tube:      http://127.0.0.1:3001/");
  console.log("  Galleries: http://127.0.0.1:3001/g");
  console.log("  Groups:    http://127.0.0.1:3001/groups");
  console.log("  Forum:     http://127.0.0.1:3001/f");
  console.log("  Connect:   http://127.0.0.1:3001/connect");
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
