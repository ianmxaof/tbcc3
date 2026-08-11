/**
 * Awempire Video Promotion API (VPAPI) client — server-only.
 *
 * Contract verified against the vendor's own reference implementation
 * (github.com/DoclerLabs/awe-vpapi-demo, vpapi.js) rather than assumed —
 * see docs/handoffs/2026-08-10_aof-hub-p9-p10_report.md for citations.
 * Do not call this from a client component: AWEMPIRE_ACCESS_KEY is a credential.
 *
 * Doctrine: link-out / embed only. Video bytes stream from Awempire's own
 * player (`playerEmbedScript` on the details endpoint), never touch our B2.
 */

const API_BASE_URL = "https://pt.protoawe.com/api/video-promotion/v1";

export interface VpapiVideo {
  id: string;
  title: string;
  previewImages: string[];
}

export interface VpapiPagination {
  currentPage: number;
  totalPages: number;
}

export interface VpapiListResult {
  videos: VpapiVideo[];
  pagination: VpapiPagination;
  /** "live" when real credentials answered, "fixture" when degraded. */
  source: "live" | "fixture";
}

export interface VpapiListParams {
  /** VPAPI content tags (verified param name — see loadList() in vpapi.js). */
  tags?: string[];
  page?: number;
  limit?: number;
  sexualOrientation?: string;
}

interface VpapiCredentials {
  psid: string;
  accessKey: string;
}

function credentials(): VpapiCredentials | null {
  const psid = process.env.AWEMPIRE_PSID?.trim();
  const accessKey = process.env.AWEMPIRE_ACCESS_KEY?.trim();
  if (!psid || !accessKey) return null;
  return { psid, accessKey };
}

/** Mirrors liveEmbedsConfigured() in lib/live-embeds.ts — same degrade pattern. */
export function vpapiConfigured(): boolean {
  return credentials() != null;
}

// ---------------------------------------------------------------------------
// Fixture mode — lets the label route render and be reviewed without a live
// Awempire account. AWEMPIRE_VPAPI_FIXTURE_JSON overrides the built-in
// default; shape must match VpapiListResult["videos"].
// ---------------------------------------------------------------------------

// Self-contained placeholder so the Phase 2 grid has something to actually
// render in fixture mode — a real Awempire preview URL is an external host
// nobody can hit without credentials anyway.
const FIXTURE_PLACEHOLDER_IMAGE =
  "data:image/svg+xml;utf8," +
  encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" width="320" height="180"><rect width="320" height="180" fill="#1c1c20"/><text x="50%" y="50%" fill="#8a8784" font-family="sans-serif" font-size="14" text-anchor="middle" dominant-baseline="middle">fixture preview</text></svg>'
  );

const DEFAULT_FIXTURE_VIDEOS: VpapiVideo[] = [
  {
    id: "fixture-1",
    title: "Sample promo video (fixture — configure AWEMPIRE_PSID)",
    previewImages: [FIXTURE_PLACEHOLDER_IMAGE],
  },
  {
    id: "fixture-2",
    title: "Sample promo video 2 (fixture — configure AWEMPIRE_PSID)",
    previewImages: [FIXTURE_PLACEHOLDER_IMAGE],
  },
];

function readFixtureVideos(): VpapiVideo[] {
  const raw = process.env.AWEMPIRE_VPAPI_FIXTURE_JSON?.trim();
  if (!raw) return DEFAULT_FIXTURE_VIDEOS;
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return DEFAULT_FIXTURE_VIDEOS;
    return parsed.filter(
      (v): v is VpapiVideo =>
        !!v &&
        typeof v === "object" &&
        typeof (v as VpapiVideo).id === "string" &&
        typeof (v as VpapiVideo).title === "string"
    );
  } catch {
    return DEFAULT_FIXTURE_VIDEOS;
  }
}

function fixtureList(params: VpapiListParams): VpapiListResult {
  const all = readFixtureVideos();
  const limit = Math.max(1, params.limit ?? 24);
  return {
    videos: all.slice(0, limit),
    pagination: { currentPage: 1, totalPages: 1 },
    source: "fixture",
  };
}

// ---------------------------------------------------------------------------
// Live API
// ---------------------------------------------------------------------------

interface RawListResponse {
  data?: {
    videos?: VpapiVideo[];
    pagination?: VpapiPagination;
  };
}

/**
 * GET /client/list — verified against vpapi.js's loadList(). Response is
 * unwrapped from the vendor's `{ data: {...} }` envelope.
 */
export async function fetchVpapiList(params: VpapiListParams = {}): Promise<VpapiListResult> {
  const creds = credentials();
  if (!creds) return fixtureList(params);

  const url = new URL(`${API_BASE_URL}/client/list`);
  url.searchParams.set("psid", creds.psid);
  url.searchParams.set("accessKey", creds.accessKey);
  url.searchParams.set("pageIndex", String(Math.max(1, params.page ?? 1)));
  if (params.limit) url.searchParams.set("limit", String(params.limit));
  url.searchParams.set("sexualOrientation", params.sexualOrientation || "straight");
  // vpapi.js passes `tags` as an array into URLSearchParams(), which
  // stringifies an array via Array.prototype.toString() -> comma-joined.
  if (params.tags?.length) url.searchParams.set("tags", params.tags.join(","));

  let res: Response;
  try {
    // No per-fetch revalidate here on purpose: the calling route
    // (app/(site)/tube/awempire/[label]/page.tsx) sets `export const
    // revalidate = 900` at the segment level, which is authoritative for
    // this whole page including this fetch. A second, independent
    // revalidate value here would just invite the two to drift.
    res = await fetch(url, {
      headers: { "X-Requested-With": "XMLHttpRequest" },
    });
  } catch {
    // Network failure against a partner API must not break the page —
    // degrade to fixture rather than throw through generateMetadata/render.
    return fixtureList(params);
  }
  if (!res.ok) return fixtureList(params);

  const json = (await res.json().catch(() => null)) as RawListResponse | null;
  const videos = json?.data?.videos ?? [];
  const pagination = json?.data?.pagination ?? { currentPage: 1, totalPages: 1 };
  return { videos, pagination, source: "live" };
}
