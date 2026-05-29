import Link from "next/link";
import { createClient } from "@/lib/supabase/server";
import { resolveMediaUrl } from "@/lib/media-url";
import type { MediaCardItem } from "@/components/MediaCard";

export const dynamic = "force-dynamic";

type MediaRow = {
  id: number;
  kind: MediaCardItem["kind"];
  title: string | null;
  b2_key: string;
  b2_thumb_key: string | null;
  width: number | null;
  height: number | null;
  duration_seconds: number | null;
  views_count: number;
};

type GalleryRow = {
  id: number;
  slug: string;
  title: string;
  cover_media_id: number | null;
  item_count: number;
  views_count: number;
  votes_up: number;
  votes_down: number;
};

async function railGalleries(order: { col: string; ascending?: boolean }, take: number): Promise<GalleryRow[]> {
  const db = await createClient();
  const q = db
    .from("galleries")
    .select("id, slug, title, cover_media_id, item_count, views_count, votes_up, votes_down")
    .eq("is_public", true)
    .order(order.col, { ascending: order.ascending ?? false })
    .limit(take);
  const { data, error } = await q;
  if (error || !data?.length) return [];
  return data as GalleryRow[];
}

async function coversMap(ids: number[]): Promise<Map<number, string>> {
  const m = new Map<number, string>();
  if (!ids.length) return m;
  const db = await createClient();
  const { data } = await db.from("media_items").select("id, b2_key").in("id", ids);
  for (const row of data ?? []) {
    m.set(row.id as number, await resolveMediaUrl(row.b2_key as string));
  }
  return m;
}

async function hotMediaThumbs(take: number): Promise<MediaCardItem[]> {
  const db = await createClient();
  const { data: rows } = await db
    .from("media_items")
    .select("id, kind, title, b2_key, b2_thumb_key, width, height, duration_seconds, views_count")
    .eq("is_public", true)
    .eq("is_deleted", false)
    .order("score", { ascending: false })
    .limit(take);
  if (!rows?.length) return [];
  const withUrls: MediaCardItem[] = [];
  for (const r of rows as MediaRow[]) {
    const url = await resolveMediaUrl(r.b2_key);
    const thumb_url = r.b2_thumb_key ? await resolveMediaUrl(r.b2_thumb_key) : url;
    withUrls.push({
      id: r.id,
      kind: r.kind,
      title: r.title,
      url,
      thumb_url,
      width: r.width,
      height: r.height,
      duration_seconds: r.duration_seconds,
      views_count: r.views_count,
    });
  }
  return withUrls;
}

function Rail({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="home-rail" style={{ marginBottom: "1.75rem" }}>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: "0.5rem" }}>
        <h2 style={{ margin: 0, fontSize: "1.05rem" }}>{title}</h2>
        <Link href="/g" className="muted" style={{ fontSize: "0.85rem" }}>
          Galleries
        </Link>
      </div>
      {subtitle && (
        <p className="muted" style={{ fontSize: "0.78rem", margin: "0 0 0.5rem" }}>
          {subtitle}
        </p>
      )}
      <div
        className="rail-scroll"
        style={{
          display: "flex",
          gap: "0.75rem",
          overflowX: "auto",
          paddingBottom: "0.35rem",
          scrollSnapType: "x mandatory",
        }}
      >
        {children}
      </div>
    </section>
  );
}

export async function HomeExploreRails() {
  const [byScore, byViews, recent, buzzing, hotMedia] = await Promise.all([
    railGalleries({ col: "score" }, 14),
    railGalleries({ col: "views_count" }, 14),
    railGalleries({ col: "created_at", ascending: false }, 14),
    (async () => {
      const db = await createClient();
      const { data } = await db
        .from("galleries")
        .select("id, slug, title, cover_media_id, item_count, views_count, votes_up, votes_down")
        .eq("is_public", true)
        .order("votes_up", { ascending: false })
        .limit(14);
      return (data ?? []) as GalleryRow[];
    })(),
    hotMediaThumbs(16),
  ]);

  const coverIds = [...byScore, ...byViews, ...recent, ...buzzing]
    .map((g) => g.cover_media_id)
    .filter((x): x is number => x != null);
  const uniq = [...new Set(coverIds)];
  const coverUrls = await coversMap(uniq);

  const mapGalleryCards = (list: GalleryRow[]) =>
    list.map((g) => (
      <Link
        key={`${g.id}-${g.slug}`}
        href={`/g/${g.slug}`}
        className="media-card"
        style={{ flex: "0 0 200px", scrollSnapAlign: "start", maxWidth: "200px" }}
      >
        <div className="thumb" style={{ aspectRatio: "4/3" }}>
          {g.cover_media_id && coverUrls.get(g.cover_media_id) ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={coverUrls.get(g.cover_media_id)} alt={g.title} loading="lazy" />
          ) : (
            <div className="empty" style={{ height: "100%", fontSize: "0.75rem" }}>
              No cover
            </div>
          )}
          <span className="badge">{g.item_count}</span>
        </div>
        <div className="meta">
          <div className="title" style={{ WebkitLineClamp: 2 }}>
            {g.title}
          </div>
          <div className="sub">
            <span>{g.views_count.toLocaleString()} views</span>
          </div>
        </div>
      </Link>
    ));

  const hasAnyRail =
    byScore.length + byViews.length + recent.length + buzzing.length + hotMedia.length > 0;
  if (!hasAnyRail) return null;

  return (
    <div style={{ marginBottom: "0.5rem" }}>
      <Rail title="Hot galleries" subtitle="By recommendation score (mock / live data).">
        {mapGalleryCards(byScore)}
      </Rail>
      <Rail title="Most viewed" subtitle="Gallery pages with the highest view counts.">
        {mapGalleryCards(byViews)}
      </Rail>
      <Rail title="Buzzing" subtitle="Gallery vote score proxy (no per-gallery comments in v1).">
        {mapGalleryCards(buzzing)}
      </Rail>
      <Rail title="Fresh galleries" subtitle="Newest public collections.">
        {mapGalleryCards(recent)}
      </Rail>
      <section className="home-rail" style={{ marginBottom: "1.75rem" }}>
        <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: "0.5rem" }}>
          <h2 style={{ margin: 0, fontSize: "1.05rem" }}>Popular now</h2>
          <Link href="/?sort=hot" className="muted" style={{ fontSize: "0.85rem" }}>
            Hot feed
          </Link>
        </div>
        <p className="muted" style={{ fontSize: "0.78rem", margin: "0 0 0.5rem" }}>
          Top scored public uploads (good demo rail until live “being watched” aggregates ship).
        </p>
        <div
          className="rail-scroll"
          style={{
            display: "flex",
            gap: "0.75rem",
            overflowX: "auto",
            paddingBottom: "0.35rem",
            scrollSnapType: "x mandatory",
          }}
        >
          {hotMedia.map((it) => (
            <Link
              key={it.id}
              href={`/m/${it.id}`}
              className="media-card"
              style={{ flex: "0 0 160px", scrollSnapAlign: "start", maxWidth: "160px" }}
            >
              <div className="thumb">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={it.thumb_url || it.url} alt={it.title ?? ""} loading="lazy" />
              </div>
              <div className="meta">
                <div className="title" style={{ WebkitLineClamp: 2 }}>
                  {it.title || `#${it.id}`}
                </div>
                <div className="sub">
                  <span>{it.views_count.toLocaleString()} views</span>
                </div>
              </div>
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
}
