import { GraphQLClient, gql } from "graphql-request";

/**
 * Minimal typed client for Stash's GraphQL API.
 * Stash docs: https://github.com/stashapp/stash/blob/develop/graphql/documents/data/*.graphql
 *
 * Only the queries the stash-sync worker needs are declared. Extend as needed.
 */

let cached: GraphQLClient | null = null;

export function getStashClient(): GraphQLClient {
  if (cached) return cached;
  const url = process.env.STASH_GRAPHQL_URL;
  if (!url) {
    throw new Error("Missing STASH_GRAPHQL_URL");
  }
  const headers: Record<string, string> = {};
  const apiKey = process.env.STASH_API_KEY;
  if (apiKey) headers.ApiKey = apiKey;
  cached = new GraphQLClient(url, { headers });
  return cached;
}

// ---------- Types (subset of Stash schema) ----------

export interface StashTag {
  id: string;
  name: string;
  description?: string | null;
  aliases?: string[] | null;
  image_path?: string | null;
}

export interface StashPerformer {
  id: string;
  name: string;
  aliases?: string[] | null;
  image_path?: string | null;
  details?: string | null;
}

export interface StashStudio {
  id: string;
  name: string;
  aliases?: string[] | null;
  image_path?: string | null;
}

export interface StashSceneFile {
  path: string;
  size?: string;
  duration?: number;
  width?: number;
  height?: number;
  mod_time?: string;
  fingerprints?: Array<{ type: string; value: string }>;
}

export interface StashScene {
  id: string;
  title?: string | null;
  details?: string | null;
  rating100?: number | null;
  date?: string | null;
  files: StashSceneFile[];
  tags: { id: string; name: string }[];
  performers: { id: string; name: string }[];
  studio?: { id: string; name: string } | null;
  paths: { screenshot?: string | null; preview?: string | null; stream?: string | null };
  created_at: string;
  updated_at: string;
}

// ---------- Queries ----------

const ALL_TAGS = gql`
  query AllTags {
    allTags { id name description aliases image_path }
  }
`;

const ALL_PERFORMERS = gql`
  query AllPerformers {
    allPerformers { id name aliases image_path details }
  }
`;

const ALL_STUDIOS = gql`
  query AllStudios {
    allStudios { id name aliases image_path }
  }
`;

const FIND_SCENES = gql`
  query FindScenes($page: Int!, $per_page: Int!) {
    findScenes(filter: { page: $page, per_page: $per_page, sort: "updated_at", direction: DESC }) {
      count
      scenes {
        id
        title
        details
        rating100
        date
        files {
          path
          size
          duration
          width
          height
          mod_time
          fingerprints { type value }
        }
        tags { id name }
        performers { id name }
        studio { id name }
        paths { screenshot preview stream }
        created_at
        updated_at
      }
    }
  }
`;

// ---------- Wrappers ----------

export async function getAllTags(): Promise<StashTag[]> {
  const data = await getStashClient().request<{ allTags: StashTag[] }>(ALL_TAGS);
  return data.allTags;
}

export async function getAllPerformers(): Promise<StashPerformer[]> {
  const data = await getStashClient().request<{ allPerformers: StashPerformer[] }>(ALL_PERFORMERS);
  return data.allPerformers;
}

export async function getAllStudios(): Promise<StashStudio[]> {
  const data = await getStashClient().request<{ allStudios: StashStudio[] }>(ALL_STUDIOS);
  return data.allStudios;
}

export async function findScenesPage(
  page: number,
  perPage = 100
): Promise<{ count: number; scenes: StashScene[] }> {
  const data = await getStashClient().request<{
    findScenes: { count: number; scenes: StashScene[] };
  }>(FIND_SCENES, { page, per_page: perPage });
  return data.findScenes;
}

/**
 * Iterate every scene in Stash, page by page.
 */
export async function* iterAllScenes(perPage = 100): AsyncGenerator<StashScene> {
  let page = 1;
  while (true) {
    const { count, scenes } = await findScenesPage(page, perPage);
    for (const s of scenes) yield s;
    if (page * perPage >= count || scenes.length === 0) return;
    page += 1;
  }
}

/**
 * Stash fingerprint -> our phash. Stash stores hex strings; we keep bytes for
 * fast Hamming-distance comparisons in the dedupe path.
 */
export function pickPhash(scene: StashScene): { type: string; value: string } | null {
  for (const f of scene.files) {
    for (const fp of f.fingerprints ?? []) {
      if (fp.type === "phash" || fp.type === "oshash") return fp;
    }
  }
  return null;
}
