/**
 * Default `/api` is rewritten by Vite to the TBCC backend (see vite.config.ts).
 * For static hosting without a proxy, set e.g. `VITE_API_BASE=http://127.0.0.1:8000` at build time.
 */
const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, "") || "/api";

/** Avoid infinite “Loading…” if the backend or DB never responds (default fetch has no timeout). */
const FETCH_TIMEOUT_MS = 60_000;
/** Media list can wait behind SQLite writes + many parallel thumbnail reads on the same API host. */
const MEDIA_LIST_TIMEOUT_MS = 90_000;
/** Bulk writes can wait behind SQLite + many parallel thumbnail reads — allow longer per chunk. */
const BULK_PATCH_TIMEOUT_MS = 300_000;
const BULK_MEDIA_CHUNK_SIZE = 15;
/** Status-only PATCH /media/bulk is a single fast UPDATE — large chunks reduce SQLite lock churn vs thumbnails. */
const BULK_STATUS_CHUNK_SIZE = 200;
/** Move-pool does heavier server-side work but one optimized UPDATE per chunk — larger chunks than 15 for reliability. */
const BULK_MOVE_POOL_CHUNK_SIZE = 120;
/** Yield between chunks so thumbnail / other API traffic can finish and release SQLite locks. */
const BULK_CHUNK_GAP_MS = 200;
/** Channel/topic imports run on Celery — poll until done (50–200 items can take many minutes). */
const CHANNEL_IMPORT_POLL_INTERVAL_MS = 2500;
const CHANNEL_IMPORT_MAX_WAIT_MS = 3_600_000;

export type ImportJobPollResult = {
  job_id?: string;
  job_kind?: string;
  status?: string;
  stage?: string;
  pool_id?: number;
  error?: string | null;
  poll_url?: string;
  async?: boolean;
  params?: Record<string, unknown>;
  result?: Record<string, unknown>;
};

const IMPORT_JOB_TERMINAL = new Set(["done", "failed", "skipped", "cancelled"]);

function sleepMs(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function isTimedOutFetchError(e: unknown): boolean {
  if (e instanceof DOMException && (e.name === "AbortError" || e.name === "TimeoutError")) return true;
  if (e instanceof Error && e.name === "TimeoutError") return true;
  return false;
}

function timeoutSignal(ms: number): AbortSignal {
  if (typeof AbortSignal !== "undefined" && typeof AbortSignal.timeout === "function") {
    return AbortSignal.timeout(ms);
  }
  const c = new AbortController();
  setTimeout(() => c.abort(), ms);
  return c.signal;
}

type ApiFetchOptions = RequestInit & { timeoutMs?: number };

/** FastAPI returns `{ "detail": "..." }` or validation arrays — avoid raw JSON in UI. */
function parseFastApiErrorBody(text: string): string {
  const raw = text.trim();
  if (!raw) return "Request failed";
  try {
    const j = JSON.parse(raw) as {
      detail?: string | Array<{ msg?: string } | string>;
    };
    if (typeof j.detail === "string") return j.detail;
    if (Array.isArray(j.detail)) {
      const parts = j.detail
        .map((x) => (typeof x === "object" && x && "msg" in x ? String((x as { msg: string }).msg) : String(x)))
        .filter(Boolean);
      if (parts.length) return parts.join("; ");
    }
  } catch {
    /* not JSON */
  }
  return raw.length > 500 ? raw.slice(0, 500) + "…" : raw;
}

async function fetchApi<T>(path: string, options?: ApiFetchOptions): Promise<T> {
  const timeoutMs = options?.timeoutMs ?? FETCH_TIMEOUT_MS;
  const { timeoutMs: _omit, ...fetchInit } = options ?? {};
  const isFormDataBody = typeof FormData !== "undefined" && fetchInit.body instanceof FormData;
  const mergedHeaders = isFormDataBody
    ? { ...(fetchInit.headers ?? {}) }
    : { "Content-Type": "application/json", ...(fetchInit.headers ?? {}) };
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...fetchInit,
      signal: fetchInit.signal ?? timeoutSignal(timeoutMs),
      headers: mergedHeaders,
    });
  } catch (e) {
    const msg = isTimedOutFetchError(e)
      ? `Request timed out after ${timeoutMs / 1000}s. Is the API up (port 8000) and the database reachable? If you bulk-approved many items, try again once thumbnails finish loading, or approve in smaller groups.`
      : e instanceof TypeError && e.message === "Failed to fetch"
        ? "Cannot reach backend. Use `npm run dev` (Vite proxies /api → port 8000), or set VITE_API_BASE to your API URL when serving a static build."
        : String(e);
    throw new Error(msg);
  }
  if (!res.ok) throw new Error(parseFastApiErrorBody(await res.text()));
  return res.json();
}

/** Many TBCC endpoints return HTTP 200 with `{ "error": "..." }` — treat as failure for mutations. */
function throwIfBodyError<T extends object>(data: T): T {
  if (data && typeof data === "object" && "error" in data && (data as { error?: unknown }).error) {
    throw new Error(String((data as { error: unknown }).error));
  }
  return data;
}

export type WatchFolderStatus =
  | { configured: false; hint: string }
  | {
      configured: true;
      debounce_s: number;
      stable_wait_s: number;
      media_only: boolean;
      reject_dir: string | null;
      inbox: {
        path: string;
        resolved: boolean;
        exists: boolean;
        is_dir: boolean;
        file_count: number | null;
      };
      library: {
        path: string;
        resolved: boolean;
        exists: boolean;
        is_dir: boolean;
        files_per_category: Record<string, number | null>;
      };
      log: {
        path: string | null;
        exists: boolean;
        recent: Array<Record<string, unknown>>;
      };
      runbook: { watch: string; once: string; dry_run: string };
    };

export type PaymentBotMenuButton = { label: string; action: string };
export type SecretarySettingsEffective = {
  format_engine_enabled: boolean;
  fe_verbosity: "compact" | "standard";
  public_faq_enabled: boolean;
  llm_refine_on_phase_change: boolean;
  rag_enabled: boolean;
  rag_top_k: number;
  system_prompt: string;
  system_prompt_source: "dashboard" | "env" | "builtin" | string;
  system_prompt_extra: string;
  message_retention: number;
  llm_history: number;
  rag_embeddings: boolean;
  llm_provider: string;
  llm_model: string;
  llm_base_url: string | null;
  llm?: {
    provider: string;
    model: string;
    base_url: string | null;
    configured: boolean;
    api_key_override: boolean;
    api_key_hint: string | null;
  };
};

export type SecretaryUserContext = {
  id: number;
  telegram_user_id: number;
  telegram_username: string | null;
  current_phase: string;
  emotional_summary: string | null;
  message_count: number;
  last_user_at: string | null;
  last_assistant_at: string | null;
  created_at: string | null;
  updated_at: string | null;
  interaction_format: Record<string, unknown>;
  messages?: Array<{
    id: number;
    role: string;
    content: string;
    emotion: Record<string, unknown> | null;
    created_at: string | null;
  }>;
};

export type SecretaryKnowledgeEntry = {
  id: number;
  title: string | null;
  body: string;
  tags: string | null;
  source_path: string | null;
  chunk_index: number | null;
  is_active: boolean;
  has_embedding?: boolean;
  created_at: string | null;
};

export type PaymentBotSettings = {
  main_menu: PaymentBotMenuButton[][];
  welcome_html: string;
  loot_intro_html: string;
  subscribe_title_main: string;
  subscribe_title_loot: string;
  subscription_catalog_columns: number;
  min_subscription_stars: number;
  runtime_adapter?: "local" | "command" | null;
  runtime_cmd_start?: string | null;
  runtime_cmd_stop?: string | null;
  runtime_cmd_restart?: string | null;
  runtime_cmd_reload?: string | null;
  runtime_cmd_status?: string | null;
  video_finder_enabled?: boolean;
  video_finder_sources?: Array<{ id: string; name: string; url: string }>;
  video_finder_max_links_per_source?: number;
};

export type LootBotSettingsEffective = {
  bot_username: string;
  primary_loot_room_invite_url: string;
  primary_loot_room_chat_id: number | null;
  aof_group_chat_id: number | null;
  aof_group_message_thread_id: number | null;
  daily_promo_enabled: boolean;
  daily_promo_hour_utc: number;
  daily_promo_intro_html: string | null;
  buffer_mirror_enabled: boolean;
  buffer_publish_now: boolean;
  buffer_x_queue?: Array<{ text: string; image_url?: string }>;
  config_poll_seconds: number;
  narrative_enabled: boolean;
  narrative_system_prompt: string | null;
  loot_referral_enabled?: boolean;
  referral_bonus_pulls?: number | null;
  drop_spoiler_default: boolean;
  runtime_adapter: string;
  runtime_cmd_start?: string | null;
  runtime_cmd_stop?: string | null;
  runtime_cmd_restart?: string | null;
  runtime_cmd_reload?: string | null;
  runtime_cmd_status?: string | null;
  operator_notes?: string | null;
  bot_token_masked: string | null;
  bot_token_configured: boolean;
  bot_token_source: string;
};

export type ListeningRelaySettings = {
  enabled: boolean;
  channel_id: number | null;
  message_thread_id: number | null;
  lastfm_username: string | null;
  lastfm_api_key_masked: string | null;
  poll_interval_minutes: number;
  message_template_html: string | null;
  /** Effective templates (DB variations JSON, else legacy single `message_template_html`). */
  message_template_variations: string[];
  template_rotation_active: boolean;
  /** Legacy single footer; cleared when variations are saved from the dashboard. */
  message_footer_html: string | null;
  /** One entry per template slot — flavor/promo caption above the Last.fm preview (no placeholders). */
  message_footer_variations: string[];
  /** One entry per template slot — <pre> tap-to-copy block (second message under preview). */
  message_copy_block_variations: string[];
  /** Per-slot copy panel: buttons, promo media, albums (scheduler parity). */
  message_slot_extras: RelaySlotExtra[];
  template_rotation_mode: "sequential" | "random";
  ascii_art_enabled: boolean;
  ascii_art_min_interval: number;
  ascii_art_max_interval: number;
  ascii_art_scrobble_counter: number;
  ascii_art_next_threshold: number | null;
  tryptych_enabled: boolean;
  tryptych_on_ascii_beat: boolean;
  ascii_art_max_width: number;
  ascii_art_max_lines: number;
  webhook_secret_masked: string | null;
  send_silent: boolean;
  buffer_relay_enabled: boolean;
  buffer_relay_min_interval_minutes: number;
  buffer_relay_max_per_day_utc: number;
  buffer_relay_utc_day: string | null;
  buffer_relay_posts_today: number;
  buffer_relay_last_post_at: string | null;
  last_poll_at: string | null;
  has_lastfm_dedupe: boolean;
  has_webhook_dedupe: boolean;
};

export type RelaySlotExtra = {
  copy_buttons: Array<{ text: string; url: string }>;
  copy_media_ids: number[];
  copy_attachment_urls: string[];
  copy_album_order_mode: "static" | "shuffle" | "carousel";
  copy_pin_after_send: boolean;
  copy_checkout_stars_enabled: boolean;
  copy_checkout_stars_plan_id: number | null;
  copy_checkout_button_label: string | null;
  copy_checkout_referral_code: string | null;
};

export type RelayAsciiEntry = {
  id: string;
  name: string;
  content: string;
  builtin?: boolean;
};

export type ListeningRelayLastfmPreview = {
  ok: boolean;
  track: Record<string, unknown> | null;
  formatted: string | null;
  copy_followups?: Array<Record<string, unknown>>;
  copy_followups_json?: string | null;
  ascii_beat_preview?: boolean;
  tryptych_preview?: boolean;
  detail?: string;
};

export type LootModifier = {
  id: number;
  kind: string;
  label?: string | null;
  target_url?: string | null;
  telegram_chat_id?: number | null;
  weight_base: number;
  rarity_focus: number;
  bypass_vip: boolean;
  active: boolean;
  source_note?: string | null;
  created_at?: string | null;
};

export type LootRollPreview = {
  ok: boolean;
  reason?: string;
  seed?: number;
  interval_code?: string;
  interval_seconds?: number;
  bonus_album_draws?: number;
  rarity_tier?: number;
  album_size?: number;
  modifier_slot_count?: number;
  eligible_pool_ids?: number[];
  media?: Array<{ id: number; pool_id: number; media_type?: string; tags?: string | null }>;
  modifiers?: Array<{ id: number; kind: string; label?: string | null; target_url?: string | null }>;
};

export type CaptureArchiveEntry = {
  id: number | null;
  kind: "url" | "username";
  value: string;
  source?: string;
  ref?: string;
  note?: string;
  description?: string;
  tags?: string;
  origin?: string;
  status?: string;
  submitted_by?: string;
  summary?: string;
  added_at?: string | null;
  addedAt?: number | null;
};

export type CaptureArchiveEntryInput = {
  kind?: string;
  value: string;
  source?: string;
  ref?: string;
  note?: string;
  tags?: string;
  origin?: string;
  added_at?: string | null;
  addedAt?: number | null;
};

export const api = {
  health: () => fetchApi<{ status: string }>("/health"),
  healthDb: () =>
    fetchApi<{ status?: string; database?: string; error?: string; detail?: string }>("/health/db"),
  watchFolder: {
    status: () => fetchApi<WatchFolderStatus>("/watch-folder/status"),
  },
  media: {
    list: (
      statusOrOpts?: string | { status?: string; pool_id?: number; tag?: string; tag_slug?: string; sort?: "newest" | "recommended"; target_pool_id?: number }
    ) => {
      const opts = typeof statusOrOpts === "string" ? { status: statusOrOpts } : statusOrOpts;
      const params = new URLSearchParams();
      if (opts?.status) params.set("status", opts.status);
      if (opts?.pool_id != null) params.set("pool_id", String(opts.pool_id));
      if (opts?.tag) params.set("tag", opts.tag);
      if (opts?.tag_slug) params.set("tag_slug", opts.tag_slug);
      if (opts?.sort) params.set("sort", opts.sort);
      if (opts?.target_pool_id != null) params.set("target_pool_id", String(opts.target_pool_id));
      const q = params.toString();
      return fetchApi<Array<Record<string, unknown>>>(q ? `/media?${q}` : "/media", {
        timeoutMs: MEDIA_LIST_TIMEOUT_MS,
      });
    },
    /** Paginated pool gallery — isolated from main library list (minimal rows, cursor). */
    listGalleryPage: (opts: {
      pool_id: number;
      status?: string;
      limit?: number;
      before_id?: number;
    }) => {
      const params = new URLSearchParams();
      params.set("pool_id", String(opts.pool_id));
      params.set("fields", "minimal");
      if (opts.status) params.set("status", opts.status);
      if (opts.limit != null) params.set("limit", String(opts.limit));
      if (opts.before_id != null && opts.before_id > 0) params.set("before_id", String(opts.before_id));
      return fetchApi<Array<{ id: number; media_type?: string; status?: string; pool_id?: number; nsfw_tier?: string }>>(
        `/media?${params.toString()}`,
        { timeoutMs: 45_000 }
      );
    },
    pendingSummary: () =>
      fetchApi<{
        total_pending: number;
        total_queue: number;
        pools: Array<{ pool_id: number; pool_name: string; pending: number; queue_total: number }>;
      }>("/media/pending-summary"),
    get: async (mediaId: number) =>
      throwIfBodyError(await fetchApi<Record<string, unknown>>(`/media/${mediaId}`)),
    updateStatus: async (mediaId: number, status: string) =>
      throwIfBodyError(
        await fetchApi<Record<string, unknown>>(`/media/${mediaId}`, {
          method: "PATCH",
          body: JSON.stringify({ status }),
        })
      ),
    patch: async (mediaId: number, body: { status?: string; tags?: string; pool_id?: number; source_channel?: string | null }) =>
      throwIfBodyError(
        await fetchApi<Record<string, unknown>>(`/media/${mediaId}`, {
          method: "PATCH",
          body: JSON.stringify(body),
        })
      ),
    /** Remove media row from TBCC (Telegram copy in Saved Messages is unchanged). */
    delete: (mediaId: number) => fetchApi<{ deleted: number }>(`/media/${mediaId}`, { method: "DELETE" }),
    updateStatusBulk: async (ids: number[], status: string) => {
      if (ids.length === 0) return { updated: 0 };
      let total = 0;
      for (let i = 0; i < ids.length; i += BULK_STATUS_CHUNK_SIZE) {
        if (i > 0) {
          await new Promise((r) => setTimeout(r, BULK_CHUNK_GAP_MS));
        }
        const slice = ids.slice(i, i + BULK_STATUS_CHUNK_SIZE);
        const r = await fetchApi<{ updated: number; error?: string }>(`/media/bulk`, {
          method: "PATCH",
          body: JSON.stringify({ ids: slice, status }),
          timeoutMs: BULK_PATCH_TIMEOUT_MS,
        });
        if (r.error) throw new Error(r.error);
        total += r.updated;
      }
      if (total === 0) {
        throw new Error("No media rows were updated (invalid ids or status, or database error).");
      }
      return { updated: total };
    },
    bulkMovePool: async (ids: number[], poolId: number) => {
      const unique = [...new Set(ids.map((n) => Number(n)).filter((n) => Number.isFinite(n)))];
      if (unique.length === 0) return { updated: 0, skipped_duplicate_in_target_pool: 0 };
      let updated = 0;
      let skipped = 0;
      for (let i = 0; i < unique.length; i += BULK_MOVE_POOL_CHUNK_SIZE) {
        if (i > 0) {
          await new Promise((r) => setTimeout(r, BULK_CHUNK_GAP_MS));
        }
        const slice = unique.slice(i, i + BULK_MOVE_POOL_CHUNK_SIZE);
        const r = await fetchApi<{
          updated: number;
          error?: string | null;
          skipped_duplicate_in_target_pool?: number;
        }>(`/media/bulk/move-pool`, {
          method: "PATCH",
          body: JSON.stringify({ ids: slice, pool_id: poolId }),
          timeoutMs: BULK_PATCH_TIMEOUT_MS,
        });
        if (r.error) throw new Error(r.error);
        updated += r.updated;
        skipped += r.skipped_duplicate_in_target_pool ?? 0;
      }
      return { updated, skipped_duplicate_in_target_pool: skipped };
    },
    bulkSetTags: async (ids: number[], tags: string) => {
      if (ids.length === 0) return { updated: 0 };
      let total = 0;
      for (let i = 0; i < ids.length; i += BULK_MEDIA_CHUNK_SIZE) {
        if (i > 0) {
          await new Promise((r) => setTimeout(r, BULK_CHUNK_GAP_MS));
        }
        const slice = ids.slice(i, i + BULK_MEDIA_CHUNK_SIZE);
        const r = await fetchApi<{ updated: number; error?: string }>(`/media/bulk/tags`, {
          method: "PATCH",
          body: JSON.stringify({ ids: slice, tags }),
          timeoutMs: BULK_PATCH_TIMEOUT_MS,
        });
        if (r.error) throw new Error(r.error);
        total += r.updated;
      }
      return { updated: total };
    },
    /** Queue Celery: OpenAI vision tags against /tags catalog (photos; skips video in worker). */
    queueAutoTagLlm: (mediaId: number) =>
      fetchApi<{ queued: boolean; media_id: number; task_id?: string }>(
        `/media/${mediaId}/auto-tag-llm`,
        { method: "POST" }
      ),
    bulkQueueAutoTagLlm: (ids: number[]) =>
      fetchApi<{ queued: number; task_ids?: string[]; error?: string }>(`/media/bulk/auto-tag-llm`, {
        method: "POST",
        body: JSON.stringify({ ids }),
      }),
    thumbnailUrl: (id: number, opts?: { cacheOnly?: boolean }) => {
      const base = `${API_BASE}/media/${id}/thumbnail`;
      if (opts?.cacheOnly) return `${base}?cache_only=1`;
      return base;
    },
    warmThumbnails: (ids: number[]) =>
      fetchApi<{ queued: number; already_cached: number }>(`/media/thumbnails/warm`, {
        method: "POST",
        body: JSON.stringify({ ids }),
      }),
    /** Full bytes (Telegram download or URL proxy) — use in lightbox / video src. */
    fileUrl: (id: number) => `${API_BASE}/media/${id}/file`,
  },
  tags: {
    list: () =>
      fetchApi<Array<{ id: number; slug: string; name: string; category: string | null; usage_count: number }>>(
        "/tags"
      ),
    create: (body: { name: string; slug?: string; category?: string }) =>
      fetchApi<Record<string, unknown>>("/tags", { method: "POST", body: JSON.stringify(body) }),
    reapplyRules: (mediaId: number) =>
      fetchApi<{ ok?: boolean; applied?: string[]; error?: string }>(
        `/tags/media/${mediaId}/reapply-rules`,
        { method: "POST", body: "{}" }
      ),
  },
  captionSnippets: {
    list: () => fetchApi<Array<{ id: number; title: string | null; body: string }>>("/caption-snippets/"),
    create: (body: { title?: string | null; body: string }) =>
      fetchApi<{ id: number; title: string | null; body: string }>("/caption-snippets/", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    bulk: (body: { items: Array<{ title?: string | null; body: string }> }) =>
      fetchApi<{ created: number }>("/caption-snippets/bulk", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    delete: (id: number) =>
      fetchApi<{ deleted: boolean; id: number }>(`/caption-snippets/${id}`, { method: "DELETE" }),
    patch: (id: number, body: { title?: string | null; body?: string }) =>
      fetchApi<{ id: number; title: string | null; body: string }>(`/caption-snippets/${id}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      }),
  },
  promoAffiliateLinks: {
    list: (opts?: { sort?: string; active_only?: boolean }) => {
      const q = new URLSearchParams();
      if (opts?.sort) q.set("sort", opts.sort);
      if (opts?.active_only === false) q.set("active_only", "false");
      const qs = q.toString();
      return fetchApi<
        Array<{
          id: number;
          label: string;
          url: string;
          short_url: string | null;
          payout_kind: string;
          payout_detail: string | null;
          priority_tier: number;
          expires_at: string | null;
          active: boolean;
          created_at: string | null;
          placements: string[];
          network_keys: string[];
          copy_template: string | null;
        }>
      >(`/promo-affiliate-links/${qs ? `?${qs}` : ""}`);
    },
    placements: () => fetchApi<{ placements: string[] }>("/promo-affiliate-links/placements"),
    stats: () =>
      fetchApi<{ active_rows: number; by_placement: Record<string, number>; cursors: number }>(
        "/promo-affiliate-links/stats"
      ),
    previewRotation: (opts: { placement: string; network_key?: string; count?: number }) => {
      const q = new URLSearchParams();
      q.set("placement", opts.placement);
      if (opts.network_key) q.set("network_key", opts.network_key);
      if (opts.count != null) q.set("count", String(opts.count));
      return fetchApi<{
        placement: string;
        network_key?: string | null;
        picks: Array<{
          id: number;
          label: string;
          url: string;
          priority_tier: number;
          line_html: string;
          line_plain: string;
        }>;
      }>(`/promo-affiliate-links/preview-rotation?${q.toString()}`);
    },
    bulk: (body: {
      items: Array<{
        label: string;
        url: string;
        short_url?: string | null;
        payout_kind?: string;
        payout_detail?: string | null;
        priority_tier?: number;
        expires_at?: string | null;
        active?: boolean;
        placements?: string[];
        network_keys?: string[];
        copy_template?: string | null;
      }>;
    }) =>
      fetchApi<{ created: number }>("/promo-affiliate-links/bulk", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    shorten: (id: number) =>
      fetchApi<{
        id: number;
        label: string;
        url: string;
        short_url: string | null;
        payout_kind: string;
        payout_detail: string | null;
        priority_tier: number;
        expires_at: string | null;
        active: boolean;
        created_at: string | null;
      }>(`/promo-affiliate-links/${id}/shorten`, { method: "POST", body: "{}" }),
    delete: (id: number) =>
      fetchApi<{ deleted: boolean; id: number }>(`/promo-affiliate-links/${id}`, { method: "DELETE" }),
  },
  pools: {
    list: () => fetchApi<Array<Record<string, unknown>>>("/pools"),
    create: (body: {
      name: string;
      channel_id: number;
      album_size?: number;
      interval_minutes?: number;
      auto_post_enabled?: boolean;
      randomize_queue?: boolean;
      route_match_tag_slugs?: string | null;
      route_nsfw_tiers?: string | null;
      route_priority?: number;
    }) => fetchApi<Record<string, unknown>>("/pools", { method: "POST", body: JSON.stringify(body) }),
    update: (
      id: number,
      body: Partial<{
        name: string;
        channel_id: number;
        album_size: number;
        interval_minutes: number;
        auto_post_enabled: boolean;
        randomize_queue: boolean;
        route_match_tag_slugs: string | null;
        route_nsfw_tiers: string | null;
        route_priority: number;
      }>
    ) =>
      fetchApi<Record<string, unknown>>(`/pools/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
    deletePool: (id: number) =>
      fetchApi<{ deleted: number }>(`/pools/${id}`, { method: "DELETE" }),
    suggestAlbum: (
      poolId: number,
      opts?: { seed_media_id?: number; limit?: number; status?: string }
    ) => {
      const q = new URLSearchParams();
      if (opts?.seed_media_id != null) q.set("seed_media_id", String(opts.seed_media_id));
      if (opts?.limit != null) q.set("limit", String(opts.limit));
      if (opts?.status) q.set("status", opts.status);
      const qs = q.toString();
      return fetchApi<{ pool_id: number; media_ids: number[]; seed_media_id?: number | null; error?: string }>(
        `/pools/${poolId}/suggest-album${qs ? `?${qs}` : ""}`
      );
    },
  },
  forum: {
    postAlbum: (body: {
      channel_id: number;
      message_thread_id?: number | null;
      media_ids: number[];
      caption?: string;
      mark_posted?: boolean;
      send_silent?: boolean;
    }) =>
      fetchApi<{
        ok?: boolean;
        sent_chunks?: number;
        errors?: string[];
        error?: string;
      }>("/forum/post-album", { method: "POST", body: JSON.stringify(body) }),
  },
  import: {
    bytes: async (
      file: File,
      poolId: number,
      source?: string,
      opts?: {
        savedOnly?: boolean;
        caption?: string;
        /** Bypass Celery fast-import queue (dashboard uploads). */
        sync?: boolean;
        skipWatermark?: boolean;
      }
    ) => {
      const form = new FormData();
      form.append("file", file);
      form.append("pool_id", String(poolId));
      form.append("saved_only", opts?.savedOnly ? "true" : "false");
      form.append("source", source || "dashboard:upload");
      if (opts?.sync) form.append("sync", "true");
      if (opts?.caption?.trim()) form.append("caption", opts.caption.trim());
      if (opts?.skipWatermark) form.append("skip_watermark", "true");
      let res: Response;
      try {
        res = await fetch(`${API_BASE}/import/bytes`, { method: "POST", body: form });
      } catch (e) {
        const msg =
          e instanceof TypeError && e.message === "Failed to fetch"
            ? "Cannot reach backend. Is it running on http://localhost:8000?"
            : String(e);
        throw new Error(msg);
      }
      const text = await res.text();
      let data: Record<string, unknown> = {};
      try {
        data = text ? (JSON.parse(text) as Record<string, unknown>) : {};
      } catch {
        throw new Error(text || res.statusText);
      }
      if (!res.ok) throw new Error(String(data.error || text || res.statusText));
      if (data.error) throw new Error(String(data.error));
      return data;
    },
    /** Multiple files → Saved Messages as Telegram albums (≤10 per album). No Media Library rows. */
    savedBatch: async (files: File[], caption?: string) => {
      const form = new FormData();
      for (const f of files) form.append("files", f);
      if (caption?.trim()) form.append("caption", caption.trim());
      let res: Response;
      try {
        res = await fetch(`${API_BASE}/import/saved-batch`, { method: "POST", body: form });
      } catch (e) {
        const msg =
          e instanceof TypeError && e.message === "Failed to fetch"
            ? "Cannot reach backend. Is it running on http://localhost:8000?"
            : String(e);
        throw new Error(msg);
      }
      const text = await res.text();
      let data: Record<string, unknown> = {};
      try {
        data = text ? (JSON.parse(text) as Record<string, unknown>) : {};
      } catch {
        throw new Error(text || res.statusText);
      }
      if (!res.ok) throw new Error(String(data.error || text || res.statusText));
      if (data.error) throw new Error(String(data.error));
      return data;
    },
    /** Index existing media in Telegram Saved Messages into a pool (admin Telethon session). */
    fromSaved: (
      poolId: number,
      limit?: number,
      options?: { applyWatermark?: boolean; watermark?: Record<string, unknown> }
    ) =>
      fetchApi<{
        status?: string;
        indexed?: number;
        skipped_duplicates_or_unsupported?: number;
        messages_scanned?: number;
        watermarked?: boolean;
        error?: string;
      }>("/import/from-saved", {
        method: "POST",
        body: JSON.stringify({
          pool_id: poolId,
          limit: limit ?? 50,
          apply_watermark: options?.applyWatermark === true,
          watermark: options?.watermark,
        }),
      }),
    getImportJob: (jobId: string) =>
      fetchApi<ImportJobPollResult>(`/import/jobs/${encodeURIComponent(jobId)}`, { timeoutMs: 20_000 }),
    pollImportJob: async (
      jobId: string,
      options?: { onUpdate?: (job: ImportJobPollResult) => void; maxWaitMs?: number; intervalMs?: number }
    ): Promise<ImportJobPollResult> => {
      const deadline = Date.now() + (options?.maxWaitMs ?? CHANNEL_IMPORT_MAX_WAIT_MS);
      const interval = options?.intervalMs ?? CHANNEL_IMPORT_POLL_INTERVAL_MS;
      for (;;) {
        const job = await api.import.getImportJob(jobId);
        options?.onUpdate?.(job);
        if (job.error === "not_found") {
          throw new Error("Import job not found (server restarted?)");
        }
        const status = String(job.status || "");
        if (IMPORT_JOB_TERMINAL.has(status)) {
          if (status === "failed" && job.error) throw new Error(String(job.error));
          if (status === "cancelled") throw new Error(job.error ? String(job.error) : "Import cancelled");
          return job;
        }
        if (Date.now() >= deadline) {
          throw new Error(
            "Import still running after 60 minutes. Check Celery (telegram queue) and GET /import/jobs/" + jobId
          );
        }
        await sleepMs(interval);
      }
    },
    /** Import from a Telegram channel/group (admin session must have access). Queued on Celery by default. */
    fromChannel: (body: {
      pool_id: number;
      channel: string;
      limit?: number;
      media_types?: "both" | "photos" | "videos";
      message_thread_id?: number | null;
      topic_title?: string;
      apply_watermark?: boolean;
    }) =>
      fetchApi<
        ImportJobPollResult & {
          status?: string;
          stored?: number;
          skipped_duplicate?: number;
          skipped_media_type?: number;
          skipped_no_media?: number;
          messages_scanned?: number;
          message_thread_id?: number | null;
          error?: string;
        }
      >("/import/from-channel", {
        method: "POST",
        body: JSON.stringify(body),
        timeoutMs: 30_000,
      }),
    forumTopicsForChannel: (channel: string) =>
      fetchApi<{ topics: Array<{ id: number; title: string }>; error?: string | null }>(
        `/import/forum-topics?${new URLSearchParams({ channel: channel.trim() })}`
      ),
    fromChannelBatch: (body: {
      channel: string;
      limit?: number;
      media_types?: "both" | "photos" | "videos";
      apply_watermark?: boolean;
      imports: Array<{
        message_thread_id: number;
        pool_id: number;
        topic_title?: string;
        limit?: number;
        media_types?: "both" | "photos" | "videos";
      }>;
    }) =>
      fetchApi<{
        status?: string;
        async?: boolean;
        jobs?: ImportJobPollResult[];
        results?: Array<Record<string, unknown>>;
        error?: string;
      }>("/import/from-channel-batch", {
        method: "POST",
        body: JSON.stringify(body),
        timeoutMs: 60_000,
      }),
    storageHubLanes: () =>
      fetchApi<{
        storage_hub_ident: string;
        default_batch_size: number;
        lanes: Array<{
          network_key: string;
          topic_title: string;
          message_thread_id: number;
          topic_deep_link: string;
          pool_id: number;
          pool_name: string;
          channel_name: string;
          receive_channel: string;
          channel_id?: number | null;
        }>;
      }>("/import/storage-hub-lanes"),
    fromStorageHub: (body: {
      limit?: number;
      network_keys?: string[];
      media_types?: "both" | "photos" | "videos";
      apply_watermark?: boolean;
    }) =>
      fetchApi<{
        ok?: boolean;
        async?: boolean;
        limit_per_lane?: number;
        matched_count?: number;
        jobs?: ImportJobPollResult[];
        error?: string;
      }>("/import/from-storage-hub", {
        method: "POST",
        body: JSON.stringify(body),
        timeoutMs: 60_000,
      }),
    /** Crop / blur + watermark preview (curate lightbox). Returns processed blob. */
    processBytes: async (
      file: Blob,
      opts: {
        mediaType?: string;
        crop?: Record<string, unknown>;
        watermark?: Record<string, unknown>;
        skipWatermark?: boolean;
        filename?: string;
      }
    ) => {
      const form = new FormData();
      form.append("file", file, opts.filename || "media.jpg");
      form.append("media_type", opts.mediaType || "photo");
      if (opts.crop) form.append("crop_json", JSON.stringify(opts.crop));
      if (opts.watermark) form.append("watermark_json", JSON.stringify(opts.watermark));
      if (opts.skipWatermark) form.append("skip_watermark", "true");
      let res: Response;
      try {
        res = await fetch(`${API_BASE}/import/process-bytes`, { method: "POST", body: form });
      } catch (e) {
        throw new Error(e instanceof TypeError ? "Cannot reach backend." : String(e));
      }
      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || res.statusText);
      }
      return res.blob();
    },
  },
  sources: {
    list: () => fetchApi<Array<Record<string, unknown>>>("/sources"),
    get: (id: number) => fetchApi<Record<string, unknown>>(`/sources/${id}`),
    listScrapeRuns: (limit = 8) =>
      fetchApi<Array<Record<string, unknown>>>(`/sources/scrape-runs/latest?limit=${limit}`),
    listChannelIntel: (params?: { forward_enabled?: boolean; pool_key?: string; limit?: number }) => {
      const q = new URLSearchParams();
      if (params?.forward_enabled != null) q.set("forward_enabled", String(params.forward_enabled));
      if (params?.pool_key) q.set("pool_key", params.pool_key);
      q.set("limit", String(params?.limit ?? 200));
      return fetchApi<Array<Record<string, unknown>>>(`/sources/channel-intel?${q.toString()}`);
    },
    listSourceScrapeRuns: (sourceId: number, limit = 20) =>
      fetchApi<Array<Record<string, unknown>>>(`/sources/${sourceId}/scrape-runs?limit=${limit}`),
    create: (body: {
      name: string;
      source_type?: string;
      identifier: string;
      pool_id: number;
      active?: boolean;
      schedule_cron?: string | null;
      schedule_enabled?: boolean;
      media_types?: "both" | "photos" | "videos";
      max_messages_per_run?: number;
    }) => fetchApi<Record<string, unknown>>("/sources", { method: "POST", body: JSON.stringify(body) }),
    update: async (
      id: number,
      body: Partial<{
        name: string;
        source_type: string;
        identifier: string;
        pool_id: number;
        active: boolean;
        schedule_cron: string | null;
        schedule_enabled: boolean;
        media_types: "both" | "photos" | "videos";
        max_messages_per_run: number;
      }>
    ) => {
      const payload = JSON.stringify(body);
      try {
        return await fetchApi<Record<string, unknown>>(`/sources/${id}`, {
          method: "PATCH",
          body: payload,
        });
      } catch (e) {
        const msg = String((e as Error)?.message ?? e);
        if (!/method not allowed/i.test(msg)) throw e;
        return fetchApi<Record<string, unknown>>(`/sources/${id}/update`, {
          method: "POST",
          body: payload,
        });
      }
    },
    delete: async (id: number) => {
      try {
        return await fetchApi<{ deleted: boolean; id: number }>(`/sources/${id}`, { method: "DELETE" });
      } catch (e) {
        const msg = String((e as Error)?.message ?? e);
        if (!/method not allowed/i.test(msg)) throw e;
        return fetchApi<{ deleted: boolean; id: number }>(`/sources/${id}/delete`, { method: "POST" });
      }
    },
    scraperAuthStatus: () => fetchApi<Record<string, unknown>>("/sources/scraper-auth/status"),
    scraperAuthPhone: (phone: string) =>
      fetchApi<Record<string, unknown>>("/sources/scraper-auth/phone", {
        method: "POST",
        body: JSON.stringify({ phone }),
      }),
    scraperAuthCode: (code: string) =>
      fetchApi<Record<string, unknown>>("/sources/scraper-auth/code", {
        method: "POST",
        body: JSON.stringify({ code }),
      }),
    scraperAuthPassword: (password: string) =>
      fetchApi<Record<string, unknown>>("/sources/scraper-auth/password", {
        method: "POST",
        body: JSON.stringify({ password }),
      }),
    scraperAuthCancel: () =>
      fetchApi<Record<string, unknown>>("/sources/scraper-auth/cancel", { method: "POST" }),
  },
  channels: {
    list: () => fetchApi<Array<Record<string, unknown>>>("/channels"),
    create: (body: { name: string; identifier: string; invite_link?: string }) =>
      fetchApi<Record<string, unknown>>("/channels", { method: "POST", body: JSON.stringify(body) }),
    update: (
      id: number,
      body: Partial<{ name: string; identifier: string; invite_link: string | null; webhook_url: string | null }>
    ) => fetchApi<Record<string, unknown>>(`/channels/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
    deleteChannel: (id: number) =>
      fetchApi<{ deleted: number; pools_removed: number[] }>(`/channels/${id}`, { method: "DELETE" }),
    /** Forum-enabled supergroups only — topic `id` is message_thread_id for scheduled posts */
    forumTopics: (channelId: number) =>
      fetchApi<{ topics: Array<{ id: number; title: string }>; error?: string | null }>(
        `/channels/${channelId}/forum-topics`
      ),
    /** Pin or unpin by Telegram message id in that channel (admin session needs pin rights). */
    pinMessage: async (channelId: number, body: { message_id: number; unpin?: boolean }) =>
      throwIfBodyError(
        await fetchApi<{ ok?: boolean; error?: string | null }>(`/channels/${channelId}/pin-message`, {
          method: "POST",
          body: JSON.stringify(body),
        })
      ),
    /** Rotate channel invite with optional join-request gate, limits, and expiry. */
    rotateInvite: async (
      channelId: number,
      body?: {
        request_needed?: boolean;
        usage_limit?: number | null;
        expire_hours?: number | null;
        title?: string | null;
        revoke_previous?: boolean;
      }
    ) =>
      throwIfBodyError(
        await fetchApi<{
          ok?: boolean;
          error?: string | null;
          invite_link?: string;
          revoked_previous?: boolean;
          revoke_error?: string | null;
        }>(`/channels/${channelId}/rotate-invite`, {
          method: "POST",
          body: JSON.stringify(body ?? {}),
        })
      ),
  },
  bots: {
    list: () => fetchApi<Array<Record<string, unknown>>>("/bots"),
    runtime: (botKey: string) =>
      fetchApi<{ bot_key: string; status: string; pid: number | null; started_at?: string; adapter?: string; message?: string }>(
        `/bots/runtime/${encodeURIComponent(botKey)}`
      ),
    control: (botKey: string, action: "start" | "stop" | "restart" | "reload") =>
      fetchApi<{ ok: boolean; status: string; pid: number | null; message?: string }>(
        `/bots/runtime/${encodeURIComponent(botKey)}/${action}`,
        { method: "POST", body: "{}" }
      ),
  },
  automation: {
    overview: () => fetchApi<{
      scraper: {
        authorized: boolean;
        pending_login?: boolean;
        user?: { username?: string; first_name?: string };
        error?: string;
      };
      scheduler: {
        total_posts: number;
        recurring_posts: number;
        pool_auto_post_enabled?: boolean;
        beat_running?: boolean;
        celery_worker_running?: boolean;
        celery_post_worker_running?: boolean;
        scheduling_paused_by_focus?: boolean;
        focus_profile?: string;
        queues?: Record<string, { length?: number; sample_tasks?: Record<string, number> }>;
      };
      bots: Record<
        string,
        {
          label: string;
          module: string;
          username?: string;
          status: string;
          adapter?: string;
        }
      >;
      stack?: {
        available?: boolean;
        enabled_up?: number;
        enabled?: number;
        profile?: string;
        services?: Array<{ id: string; title: string; running: boolean; status: string }>;
      };
      format_engine: {
        settings: SecretarySettingsEffective;
        user_contexts_total: number;
        phases: Record<string, number>;
        knowledge_chunks_active: number;
      };
    }>("/automation/overview"),
    stackStatus: () =>
      fetchApi<{
        ok?: boolean;
        available?: boolean;
        enabled_up?: number;
        enabled?: number;
        profile?: string;
        services?: Array<{ id: string; title: string; running: boolean; status: string }>;
      }>("/ops/stack-status"),
  },
  subscriptions: {
    list: (status?: string) =>
      fetchApi<Array<Record<string, unknown>>>(status ? `/subscriptions?status=${status}` : "/subscriptions"),
  },
  analytics: {
    subscriptions: () =>
      fetchApi<{
        total_subscriptions: number;
        active: number;
        expired: number;
        cancelled: number;
        revenue_stars: number;
      }>("/analytics/subscriptions"),
    incomeSummary: (opts?: { days?: number; backfill?: boolean }) => {
      const p = new URLSearchParams();
      if (opts?.days != null) p.set("days", String(opts.days));
      if (opts?.backfill === false) p.set("backfill", "false");
      const q = p.toString();
      return fetchApi<{
        ok: boolean;
        scope: string;
        range_days: number | null;
        totals: {
          usd_cents: number;
          usd: number;
          stars: number;
          entry_count: number;
          internal_usd: number;
          external_usd: number;
        };
        by_source: Array<{
          source: string;
          label: string;
          usd_cents: number;
          stars: number;
          count: number;
          category: string;
        }>;
        stars_usd_rate: number;
        latest_earned_at: string | null;
        latest_entry_at: string | null;
      }>(q ? `/analytics/income/summary?${q}` : "/analytics/income/summary");
    },
    incomeEntries: (opts?: { days?: number; source?: string; limit?: number; offset?: number }) => {
      const p = new URLSearchParams();
      if (opts?.days != null) p.set("days", String(opts.days));
      if (opts?.source) p.set("source", opts.source);
      if (opts?.limit != null) p.set("limit", String(opts.limit));
      if (opts?.offset != null) p.set("offset", String(opts.offset));
      const q = p.toString();
      return fetchApi<{
        items: Array<{
          id: number;
          source: string;
          source_label: string | null;
          amount_minor: number;
          currency: string;
          amount_usd_cents: number;
          amount_usd: number;
          earned_at: string | null;
          sync_kind: string;
          external_ref: string | null;
          created_at: string | null;
        }>;
        total: number;
        limit: number;
        offset: number;
      }>(q ? `/analytics/income/entries?${q}` : "/analytics/income/entries");
    },
    incomeManual: (body: {
      source: string;
      amount_usd: number;
      source_label?: string;
      period_key?: string;
      notes?: string;
      promo_affiliate_link_id?: number;
    }) =>
      fetchApi<{ ok: boolean; idempotent?: boolean; id?: number; error?: string }>(
        "/analytics/income/manual",
        { method: "POST", body: JSON.stringify(body) }
      ),
    incomeSync: (body?: { sources?: string[]; headed?: boolean }) =>
      fetchApi<{
        ok: boolean;
        results: Array<{
          ok?: boolean;
          source?: string;
          error?: string;
          skipped?: boolean;
          delta_usd?: number;
        }>;
        synced_at: string;
      }>("/analytics/income/sync", {
        method: "POST",
        body: JSON.stringify(body ?? {}),
      }),
    incomeAffiliates: () =>
      fetchApi<{
        ok: boolean;
        count: number;
        items: Array<{
          id: number;
          label: string;
          url: string;
          payout_kind: string;
          last_usd_cents: number;
          last_earned_at: string | null;
          last_sync_kind: string | null;
        }>;
      }>("/analytics/income/affiliates"),
    incomePollStatus: () =>
      fetchApi<{
        enabled: boolean;
        interval_hours: number;
        last_poll_at: string | null;
        last_poll_ok: boolean | null;
        last_results: Array<Record<string, unknown>>;
        beat_task: string;
        redis_error?: string;
      }>("/analytics/income/poll-status"),
    postEvents: (opts?: { limit?: number; offset?: number }) => {
      const p = new URLSearchParams();
      if (opts?.limit != null) p.set("limit", String(opts.limit));
      if (opts?.offset != null) p.set("offset", String(opts.offset));
      const q = p.toString();
      return fetchApi<{
        items: Array<{
          id: number;
          created_at: string | null;
          event_type: string;
          channel_id: number | null;
          channel_name: string | null;
          scheduled_post_id: number | null;
          pool_id: number | null;
          ok: boolean;
          error_message: string | null;
        }>;
        limit: number;
        offset: number;
      }>(q ? `/analytics/post-events?${q}` : "/analytics/post-events");
    },
    postEventsSummary: (days?: number) => {
      const q = days != null ? `?days=${days}` : "";
      return fetchApi<{
        range_days: number;
        totals: {
          scheduled_post_sent: number;
          pool_album_posted: number;
          all: number;
          ok: number;
          failed: number;
        };
        by_day: Array<{
          date: string;
          scheduled_post_sent: number;
          pool_album_posted: number;
          count: number;
        }>;
        by_channel: Array<{ channel_id: number; channel_name: string; count: number }>;
      }>(`/analytics/post-events/summary${q}`);
    },
    deliveries: (opts?: {
      days?: number;
      limit?: number;
      offset?: number;
      scheduled_post_id?: number;
      channel_id?: number;
    }) => {
      const p = new URLSearchParams();
      if (opts?.days != null) p.set("days", String(opts.days));
      if (opts?.limit != null) p.set("limit", String(opts.limit));
      if (opts?.offset != null) p.set("offset", String(opts.offset));
      if (opts?.scheduled_post_id != null) p.set("scheduled_post_id", String(opts.scheduled_post_id));
      if (opts?.channel_id != null) p.set("channel_id", String(opts.channel_id));
      const q = p.toString();
      return fetchApi<{
        range_days: number;
        total: number;
        limit: number;
        offset: number;
        timezone: string;
        items: Array<{
          id: number;
          created_at: string | null;
          event_type: string;
          channel_id: number | null;
          channel_name: string | null;
          scheduled_post_id: number | null;
          pool_id: number | null;
          scheduler_name: string | null;
          telegram_message_id: number | null;
          caption_slot_index: number | null;
          posted_hour_local: number | null;
          views_latest: number | null;
          views_peak: number | null;
          forwards_latest: number | null;
        }>;
      }>(q ? `/analytics/deliveries?${q}` : "/analytics/deliveries");
    },
    refreshDeliveryViews: (limit?: number) => {
      const q = limit != null ? `?limit=${limit}` : "";
      return fetchApi<{ ok: boolean; updated?: number; checked?: number; error?: string }>(
        `/analytics/deliveries/refresh-views${q}`,
        { method: "POST" }
      );
    },
    viewsByHour: (days?: number) => {
      const q = days != null ? `?days=${days}` : "";
      return fetchApi<{
        range_days: number;
        timezone: string;
        by_hour: Array<{
          hour_local: number;
          post_count: number;
          avg_views: number | null;
          total_views: number;
          max_views: number | null;
        }>;
        top_hours_local: number[];
        suggested_peak_hours_et: Array<{ start: number; end: number }>;
        note: string;
      }>(`/analytics/deliveries/views-by-hour${q}`);
    },
    captionSlotViews: (scheduledPostId: number, days?: number) => {
      const p = new URLSearchParams({ scheduled_post_id: String(scheduledPostId) });
      if (days != null) p.set("days", String(days));
      return fetchApi<{
        scheduled_post_id: number;
        scheduler_name: string | null;
        caption_variation_count: number;
        slots: Array<{
          caption_slot_index: number;
          send_count: number;
          avg_views: number | null;
          max_views: number | null;
        }>;
      }>(`/analytics/deliveries/caption-slots?${p}`);
    },
    growthAttributionSummary: (days?: number) => {
      const q = days != null ? `?days=${days}` : "";
      return fetchApi<{
        range_days: number;
        timezone: string;
        totals_by_type: Record<string, number>;
        subscription_stars_total: number;
        top_conversion_hours_local: Array<{ hour: number; count: number }>;
      }>(`/analytics/growth-attribution/summary${q}`);
    },
    signalsStatus: () =>
      fetchApi<{
        enabled: boolean;
        flywheel_growth_tick: boolean;
        /** @deprecated use flywheel_growth_tick */
        openclaw_growth_tick?: boolean;
        lookback_days: number;
        thresholds: Record<string, number>;
        last_tick_unix: number | null;
        last_digest: string | null;
      }>("/analytics/signals/status"),
    signals: (days?: number) => {
      const q = days != null ? `?days=${days}` : "";
      return fetchApi<{
        ok: boolean;
        signal_count: number;
        network_avg_views: number;
        timezone: string;
        signals: Array<{
          signal_type: string;
          strength: number;
          confidence: string;
          recommendation: string;
        }>;
      }>(`/analytics/signals${q}`);
    },
    signalsTick: (opts?: { refreshViews?: boolean; pushInbox?: boolean }) => {
      const p = new URLSearchParams();
      if (opts?.refreshViews === false) p.set("refresh_views", "false");
      if (opts?.pushInbox === false) p.set("push_inbox", "false");
      const q = p.toString();
      return fetchApi<{
        ok: boolean;
        digest_changed: boolean;
        markdown?: string;
        report?: { signals: unknown[] };
      }>(q ? `/analytics/signals/tick?${q}` : "/analytics/signals/tick", { method: "POST" });
    },
    tbccFlywheelTick: (opsLimit?: number) => {
      const q = opsLimit != null ? `?ops_limit=${opsLimit}` : "";
      return fetchApi<{ ok: boolean; ops?: unknown; growth?: unknown }>(
        `/analytics/tbcc-flywheel/tick${q}`,
        { method: "POST" }
      );
    },
    /** @deprecated use tbccFlywheelTick */
    openclawTick: (opsLimit?: number) => {
      const q = opsLimit != null ? `?ops_limit=${opsLimit}` : "";
      return fetchApi<{ ok: boolean; ops?: unknown; growth?: unknown }>(
        `/analytics/openclaw/tick${q}`,
        { method: "POST" }
      );
    },
    industryBenchmarks: (topicType?: string) => {
      const q = topicType ? `?topic_type=${encodeURIComponent(topicType)}` : "";
      return fetchApi<{
        items: Array<{
          id: number;
          slug: string;
          title: string;
          topic_type: string;
          summary: string;
          demand_index: number | null;
          source_url: string | null;
          source_label: string | null;
        }>;
      }>(`/analytics/industry-benchmarks${q}`);
    },
    seedIndustryIntelligence: () =>
      fetchApi<{
        benchmarks: { ok: boolean; upserted: number; error?: string };
        iui_corpus: { ok: boolean; chunks: number; error?: string };
      }>("/analytics/industry-benchmarks/seed", { method: "POST" }),
    ga4HubDeviceCountry: (days?: number) => {
      const q = days != null ? `?days=${days}` : "";
      return fetchApi<{
        ok: boolean;
        configured: boolean;
        lookback_days?: number;
        rows: Array<{
          device_category: string;
          country: string;
          sessions: number;
          active_users: number;
        }>;
        error?: string;
      }>(`/analytics/ga4/hub-device-country${q}`);
    },
    categoryDemand: (opts?: { limit?: number; gapThreshold?: number }) => {
      const p = new URLSearchParams();
      if (opts?.limit != null) p.set("limit", String(opts.limit));
      if (opts?.gapThreshold != null) p.set("gap_threshold", String(opts.gapThreshold));
      const q = p.toString();
      return fetchApi<{
        ok: boolean;
        seeded: boolean;
        message?: string;
        total_media: number;
        benchmark_count: number;
        gap_threshold: number;
        rows: Array<{
          slug: string;
          title: string;
          demand_index: number;
          supply_count: number;
          supply_pct: number;
          gap_score: number;
          status: string;
          in_clip_catalog: boolean;
          summary: string;
        }>;
        gaps: Array<{
          slug: string;
          title: string;
          demand_index: number;
          supply_count: number;
          gap_score: number;
        }>;
        top_opportunities: Array<{
          slug: string;
          title: string;
          demand_index: number;
          gap_score: number;
        }>;
      }>(q ? `/analytics/category-demand?${q}` : "/analytics/category-demand");
    },
  },
  growthSettings: {
    get: () =>
      fetchApi<{ effective: Record<string, unknown>; overrides: Record<string, unknown> }>("/growth-settings"),
    patch: (body: Record<string, unknown>) =>
      fetchApi<{ ok: boolean; effective: Record<string, unknown>; overrides: Record<string, unknown> }>(
        "/growth-settings",
        { method: "PATCH", body: JSON.stringify(body) }
      ),
    /** Queue landing bulletin now (force=True); needs Celery worker + Redis. */
    sendBulletinNow: () =>
      fetchApi<{ ok: boolean; task_id: string; message: string }>("/growth-settings/send-bulletin-now", {
        method: "POST",
      }),
  },
  growthHub: {
    status: () =>
      fetchApi<{
        bulletin_preview: string;
        bulletin_full_chars: number;
        schedulers: Array<{
          key: string;
          channel_id?: number;
          scheduler_id?: number;
          ok: boolean;
          variations?: number;
          reason?: string;
        }>;
        pinned_bulletin_id: number | null;
        storage_hub: { identifier: string; invite: string };
      }>("/growth-hub/status"),
    syncSchedulers: () =>
      fetchApi<{ ok: boolean; bulletin_has_packs: boolean; bulletin_has_goon: boolean; channels: unknown[] }>(
        "/growth-hub/sync-schedulers",
        { method: "POST" }
      ),
    syncAffiliateRotation: () =>
      fetchApi<{
        ok: boolean;
        bulletin_has_partners?: boolean;
        affiliate?: { active_rows: number; by_placement: Record<string, number>; cursors: number };
        channels?: unknown[];
      }>("/growth-hub/sync-affiliate-rotation", { method: "POST" }),
    broadcastBulletin: () =>
      fetchApi<{ ok: boolean; queued: unknown[]; count: number }>("/growth-hub/broadcast-bulletin", {
        method: "POST",
      }),
    storageDeposit: (body?: {
      limit?: number;
      topic_keys?: string[];
      media_types?: string;
      content_lanes_only?: boolean;
    }) =>
      fetchApi<{
        ok: boolean;
        limit_per_topic: number;
        jobs: Array<{ id?: number; network_key?: string; pool_name?: string; topic_title?: string }>;
        unmatched_topics: Array<{ title: string; thread_id: number }>;
        matched_count: number;
        error?: string;
      }>("/growth-hub/storage-deposit", {
        method: "POST",
        body: JSON.stringify(body ?? {}),
      }),
    livenessStatus: () =>
      fetchApi<{
        intervals: Record<string, number>;
        main_pulses: Array<{
          name: string;
          id?: number;
          interval_minutes?: number;
          variations?: number;
          installed?: boolean;
        }>;
        command_schedulers: number;
        pools_with_backup_post: number;
        subscriber_count_real: number;
        first_sub_celebrated: boolean;
      }>("/growth-hub/liveness-status"),
    applyLiveness: () =>
      fetchApi<{ ok: boolean; intervals: Record<string, number>; subscriber_count_real: number }>(
        "/growth-hub/apply-liveness",
        { method: "POST" }
      ),
    celebrateFirstSub: () =>
      fetchApi<{ ok: boolean; skipped?: boolean; post_id?: number }>("/growth-hub/celebrate-first-sub", {
        method: "POST",
      }),
    feedRhythm: () => fetchApi<Record<string, unknown>>("/growth-hub/feed-rhythm"),
    scheduleDrop: (body: { lane_key: string; drop_at: string; message_thread_id?: number }) =>
      fetchApi<{ ok: boolean; session_id?: number }>("/growth-hub/schedule-drop", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    topicMirror: (body?: { limit_per_pair?: number; topic_keys?: string[] }) =>
      fetchApi<{ ok: boolean; matched_count?: number; jobs?: unknown[] }>("/growth-hub/topic-mirror", {
        method: "POST",
        body: JSON.stringify(body ?? { limit_per_pair: 8 }),
      }),
    topicMirrorStatus: () =>
      fetchApi<{ enabled: boolean; liveness_random_topics: boolean; pairs: unknown[] }>(
        "/growth-hub/topic-mirror"
      ),
  },
  companion: {
    ops: () =>
      fetchApi<{
        bot_username: string;
        token_configured: boolean;
        image_provider: string;
        undress_balance: number | null;
        webhook_ok: boolean;
        webhook_detail: string;
        pending_jobs: number;
        llm_provider: string;
        llm_model: string;
        llm_configured: boolean;
        gate_enabled: boolean;
        free_trial_photos: number;
        stars_enabled: boolean;
        stars_per_photo: number;
      }>("/companion/ops"),
  },
  paymentBotSettings: {
    get: () =>
      fetchApi<{ effective: PaymentBotSettings; overrides: Record<string, unknown> }>("/payment-bot-settings"),
    patch: (body: Partial<PaymentBotSettings>) =>
      fetchApi<{ ok: boolean; effective: PaymentBotSettings; overrides: Record<string, unknown> }>(
        "/payment-bot-settings",
        { method: "PATCH", body: JSON.stringify(body) }
      ),
  },
  lootBotSettings: {
    get: () =>
      fetchApi<{ effective: LootBotSettingsEffective; overrides: Record<string, unknown> }>("/loot-bot-settings"),
    patch: (body: Record<string, unknown>) =>
      fetchApi<{ ok: boolean; effective: LootBotSettingsEffective; overrides: Record<string, unknown> }>(
        "/loot-bot-settings",
        { method: "PATCH", body: JSON.stringify(body) }
      ),
    triggerDailyPromo: () =>
      fetchApi<{ ok: boolean; queued: boolean; sent?: boolean; chat_id: number | null; buffer_mirror_enabled?: boolean }>(
        "/loot-bot-settings/trigger-daily-promo",
        { method: "POST" }
      ),
    bufferTestPost: (body?: { text?: string; publish_now?: boolean }) =>
      fetchApi<{ ok: boolean; mode: string; chars: number; channels: number }>(
        "/loot-bot-settings/buffer-test-post",
        { method: "POST", body: JSON.stringify(body ?? {}) }
      ),
  },
  secretary: {
    settings: {
      get: () =>
        fetchApi<{ effective: SecretarySettingsEffective; overrides: Record<string, unknown> }>(
          "/secretary-settings"
        ),
      patch: (body: Partial<SecretarySettingsEffective> & {
        llm_api_key?: string;
        clear_llm_api_key?: boolean;
        clear_system_prompt?: boolean;
      }) =>
        fetchApi<{ ok: boolean; effective: SecretarySettingsEffective; overrides: Record<string, unknown> }>(
          "/secretary-settings",
          { method: "PATCH", body: JSON.stringify(body) }
        ),
      testReply: (body: {
        message: string;
        telegram_user_id?: number | null;
        include_format_engine?: boolean;
        include_rag?: boolean;
      }) =>
        fetchApi<{
          reply: string;
          context_suffix_preview: string;
          rag_hits: Array<{ id: number; title: string | null; body: string; score: number }>;
        }>("/secretary-settings/test-reply", { method: "POST", body: JSON.stringify(body) }),
      testLlm: () =>
        fetchApi<{
          ok: boolean;
          stage?: string;
          message?: string;
          endpoint?: string;
          model?: string;
          latency_ms?: number;
          reply_preview?: string;
        }>("/secretary-settings/test-llm", { method: "POST" }),
    },
    contexts: {
      list: (params?: { q?: string; phase?: string; limit?: number; offset?: number }) => {
        const sp = new URLSearchParams();
        if (params?.q) sp.set("q", params.q);
        if (params?.phase) sp.set("phase", params.phase);
        if (params?.limit != null) sp.set("limit", String(params.limit));
        if (params?.offset != null) sp.set("offset", String(params.offset));
        const q = sp.toString();
        return fetchApi<{ total: number; items: SecretaryUserContext[] }>(
          `/secretary-contexts${q ? `?${q}` : ""}`
        );
      },
      get: (id: number, messageLimit?: number) => {
        const sp = messageLimit != null ? `?message_limit=${messageLimit}` : "";
        return fetchApi<SecretaryUserContext>(`/secretary-contexts/${id}${sp}`);
      },
      reset: (id: number) =>
        fetchApi<{ ok: boolean; context: SecretaryUserContext }>(`/secretary-contexts/${id}/reset`, {
          method: "POST",
        }),
      patchPhase: (id: number, current_phase: string) =>
        fetchApi<{ ok: boolean; context: SecretaryUserContext }>(`/secretary-contexts/${id}`, {
          method: "PATCH",
          body: JSON.stringify({ current_phase }),
        }),
    },
    knowledge: {
      list: (q?: string) => {
        const sp = q ? `?q=${encodeURIComponent(q)}` : "";
        return fetchApi<SecretaryKnowledgeEntry[]>(`/secretary-knowledge${sp}`);
      },
      create: (body: { title?: string; body: string; tags?: string; is_active?: boolean }) =>
        fetchApi<{ id: number; title: string | null }>("/secretary-knowledge", {
          method: "POST",
          body: JSON.stringify(body),
        }),
      delete: (id: number) =>
        fetchApi<{ deleted: boolean; id: number }>(`/secretary-knowledge/${id}`, { method: "DELETE" }),
      importDocs: () =>
        fetchApi<{ files: number; chunks: number; error?: string }>("/secretary-knowledge/import-docs", {
          method: "POST",
        }),
      importIuiCorpus: () =>
        fetchApi<{ ok: boolean; chunks: number; error?: string }>("/secretary-knowledge/import-iui-corpus", {
          method: "POST",
        }),
      reindexEmbeddings: () =>
        fetchApi<{ updated: number; total?: number; error?: string }>("/secretary-knowledge/reindex-embeddings", {
          method: "POST",
        }),
      search: (q: string, top_k?: number) =>
        fetchApi<{ query: string; hits: Array<{ id: number; title: string | null; body: string; score: number }> }>(
          "/secretary-knowledge/search",
          { method: "POST", body: JSON.stringify({ q, top_k }) }
        ),
    },
  },
  emojiFactory: {
    prerequisites: () =>
      fetchApi<{
        ffmpeg: boolean;
        telethon_session: boolean;
        telethon_error: string | null;
        docs: Record<string, string>;
      }>("/emoji-factory/prerequisites"),
    runSplit: (body: {
      input_path: string;
      out_dir: string;
      cols?: number;
      rows?: number;
      tile_px?: number;
      margin_pct?: number;
      loop_sec?: number;
      crf?: number;
      static?: boolean;
    }) =>
      fetchApi<{
        ok: boolean;
        manifest_path: string;
        out_dir: string;
        tile_count: number;
        over_soft_limit: number;
      }>("/emoji-factory/run-split", { method: "POST", body: JSON.stringify(body) }),
    createFromUpload: async (
      file: File,
      opts: {
        cols?: number;
        rows?: number;
        tile_px?: number;
        margin_pct?: number;
        loop_sec?: number;
        crf?: number;
        static?: boolean;
        title?: string;
        short_name?: string;
        upload_telegram?: boolean;
        dry_run?: boolean;
      }
    ) => {
      const form = new FormData();
      form.append("file", file);
      form.append("cols", String(opts.cols ?? 4));
      form.append("rows", String(opts.rows ?? 4));
      form.append("tile_px", String(opts.tile_px ?? 100));
      form.append("margin_pct", String(opts.margin_pct ?? 8));
      form.append("loop_sec", String(opts.loop_sec ?? 3));
      form.append("crf", String(opts.crf ?? 38));
      form.append("static", opts.static ? "true" : "false");
      form.append("title", opts.title ?? "TBCC emoji pack");
      form.append("short_name", opts.short_name ?? "");
      form.append("upload_telegram", opts.upload_telegram ? "true" : "false");
      form.append("dry_run", opts.dry_run ? "true" : "false");
      let res: Response;
      try {
        res = await fetch(`${API_BASE}/emoji-factory/create-from-upload`, { method: "POST", body: form });
      } catch (e) {
        const msg =
          e instanceof TypeError && e.message === "Failed to fetch"
            ? "Cannot reach backend. Is it running on http://localhost:8000?"
            : String(e);
        throw new Error(msg);
      }
      const text = await res.text();
      let data: Record<string, unknown> = {};
      try {
        data = text ? (JSON.parse(text) as Record<string, unknown>) : {};
      } catch {
        throw new Error(text || res.statusText);
      }
      if (!res.ok) {
        const detail = data.detail;
        throw new Error(
          typeof detail === "string" ? detail : Array.isArray(detail) ? JSON.stringify(detail) : text || res.statusText
        );
      }
      return data as {
        ok: boolean;
        split: Record<string, unknown>;
        upload?: Record<string, unknown>;
      };
    },
    uploadFromManifest: (body: {
      manifest_path: string;
      title: string;
      short_name: string;
      dry_run: boolean;
    }) =>
      fetchApi<Record<string, unknown>>("/emoji-factory/upload-from-manifest", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    sketchbook: {
      listPages: () =>
        fetchApi<
          Array<{
            id: number;
            sort_order: number;
            title: string | null;
            body: string;
            created_at?: string | null;
            updated_at?: string | null;
          }>
        >("/emoji-factory/sketchbook/pages"),
      createPage: (body?: { title?: string | null; body?: string }) =>
        fetchApi<{ id: number; sort_order: number; title: string | null; body: string }>(
          "/emoji-factory/sketchbook/pages",
          { method: "POST", body: JSON.stringify(body ?? {}) }
        ),
      patchPage: (pageId: number, body: { title?: string | null; body?: string }) =>
        fetchApi<{ id: number; sort_order: number; title: string | null; body: string }>(
          `/emoji-factory/sketchbook/pages/${pageId}`,
          { method: "PATCH", body: JSON.stringify(body) }
        ),
      deletePage: (pageId: number) =>
        fetchApi<{ deleted: boolean; id: number }>(`/emoji-factory/sketchbook/pages/${pageId}`, {
          method: "DELETE",
        }),
      savePreset: (pageId: number, body?: { title?: string | null; html?: string }) =>
        fetchApi<{ id: number; title: string; html_fragment: string }>(
          `/emoji-factory/sketchbook/pages/${pageId}/save-preset`,
          { method: "POST", body: JSON.stringify(body ?? {}) }
        ),
    },
    listJobs: () =>
      fetchApi<{
        jobs: Array<{
          job_id: string;
          cols: number;
          rows: number;
          row_strips?: Array<{
            row: number;
            preview_url: string;
            saved_path?: string | null;
            export_filename: string;
          }>;
        }>;
      }>("/emoji-factory/jobs"),
    saveRowDivider: (jobId: string, row: number) =>
      fetchApi<{ ok: boolean; path: string; filename: string }>(
        `/emoji-factory/jobs/${encodeURIComponent(jobId)}/rows/${row}/divider-png`,
        { method: "POST" }
      ),
    importRowDivider: (jobId: string, row: number) =>
      fetchApi<{ ok: boolean; settings: Record<string, unknown> }>(
        `/emoji-factory/jobs/${encodeURIComponent(jobId)}/rows/${row}/import-divider`,
        { method: "POST" }
      ),
  },
  telegramCustomEmoji: {
    listPresets: () => fetchApi<Array<{ id: number; title: string; html_fragment: string; source_note?: string | null }>>("/telegram-custom-emoji/presets"),
    createPreset: (body: { title: string; html_fragment: string; source_note?: string | null }) =>
      fetchApi<{ id: number; title: string; html_fragment: string }>("/telegram-custom-emoji/presets", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    deletePreset: (id: number) =>
      fetchApi<{ deleted: number }>(`/telegram-custom-emoji/presets/${id}`, { method: "DELETE" }),
    validate: (html: string) =>
      fetchApi<Record<string, unknown>>("/telegram-custom-emoji/validate", {
        method: "POST",
        body: JSON.stringify({ html }),
      }),
    buildTag: (body: { document_id: number; placeholder?: string }) =>
      fetchApi<{ tag: string }>("/telegram-custom-emoji/build-tag", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    savedMessagesRecent: (limit = 20) =>
      fetchApi<{
        peer: string;
        messages: Array<{
          message_id: number;
          preview: string;
          has_custom_emoji: boolean;
          date?: string | null;
        }>;
      }>(`/telegram-custom-emoji/saved-messages/recent?limit=${limit}`),
    installedPacks: () =>
      fetchApi<{
        count: number;
        packs: Array<{ id: number; short_name: string; title: string; count: number; access_hash?: number }>;
      }>("/telegram-custom-emoji/installed-packs"),
    packEmojis: (shortName: string) =>
      fetchApi<{
        id: number;
        short_name: string;
        title: string;
        count: number;
        emojis: Array<{ document_id: number; alt: string; placeholder: string; tag: string; free: boolean }>;
      }>(`/telegram-custom-emoji/installed-packs/${encodeURIComponent(shortName)}/emojis`),
    importMacro: (body: {
      peer?: string;
      message_id: number;
      peer_link?: string;
      title?: string | null;
      layout?: string;
      save_preset?: boolean;
      save_sketchbook?: boolean;
      send_to_saved?: boolean;
    }) =>
      fetchApi<{
        ok: boolean;
        html: string;
        preset_id: number | null;
        sketch_page_id: number | null;
        sent_to: string | null;
        custom_emoji_count: number;
      }>("/telegram-custom-emoji/import-macro", { method: "POST", body: JSON.stringify(body) }),
    extract: (body: { peer?: string; message_id?: number; peer_link?: string }) =>
      fetchApi<{
        custom_emoji_html: string;
        custom_emoji_html_with_body?: string;
        full_message_html?: string;
        plain_text?: string;
        custom_emoji_count: number;
      }>("/telegram-custom-emoji/extract-from-message", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    testSend: (body: { html: string; channel_id?: number; telegram_user_id?: number; send_silent?: boolean }) =>
      fetchApi<{ ok: boolean; sent_to: string }>("/telegram-custom-emoji/test-send", {
        method: "POST",
        body: JSON.stringify(body),
      }),
  },
  watermarkSettings: {
    get: () =>
      fetchApi<{
        effective: Record<string, unknown>;
        overrides: Record<string, unknown>;
      }>("/watermark-settings"),
    patch: (body: {
      enabled?: boolean | null;
      text_primary?: string | null;
      text_secondary?: string | null;
      text_tertiary?: string | null;
      opacity?: number | null;
      color?: string | null;
      strip_previous?: boolean | null;
      apply_on_saved_import?: boolean | null;
      apply_on_album_composer?: boolean | null;
    }) =>
      fetchApi<{ ok: boolean; effective: Record<string, unknown>; overrides: Record<string, unknown> }>(
        "/watermark-settings",
        { method: "PATCH", body: JSON.stringify(body) }
      ),
  },
  gallerySendPromo: {
    get: () =>
      fetchApi<{
        settings: {
          enabled: boolean;
          active_image_id: string | null;
          active_image: { id: string; url: string; label?: string; filename?: string } | null;
          images: Array<{ id: string; url: string; label?: string; filename?: string }>;
        };
      }>("/gallery-send-promo"),
    patch: (body: { enabled?: boolean; active_image_id?: string | null }) =>
      fetchApi<{ ok: boolean; settings: Record<string, unknown> }>("/gallery-send-promo", {
        method: "PATCH",
        body: JSON.stringify(body),
      }),
    uploadImage: (file: File, label?: string) => {
      const fd = new FormData();
      fd.append("file", file);
      if (label) fd.append("label", label);
      return fetchApi<{ ok: boolean; image: Record<string, unknown>; settings: Record<string, unknown> }>(
        "/gallery-send-promo/images",
        { method: "POST", body: fd }
      );
    },
    deleteImage: (imageId: string) =>
      fetchApi<{ ok: boolean; settings: Record<string, unknown> }>(
        `/gallery-send-promo/images/${encodeURIComponent(imageId)}`,
        { method: "DELETE" }
      ),
  },
  mainChannelDivider: {
    get: () =>
      fetchApi<{
        settings: {
          enabled: boolean;
          rotate_images: boolean;
          apply_in_topics: boolean;
          active_image_id: string | null;
          active_image: { id: string; url: string; label?: string; filename?: string } | null;
          images: Array<{ id: string; url: string; label?: string; filename?: string }>;
          main_group_identifier: string;
        };
      }>("/main-channel-divider"),
    patch: (body: {
      enabled?: boolean;
      rotate_images?: boolean;
      apply_in_topics?: boolean;
      active_image_id?: string | null;
    }) =>
      fetchApi<{ ok: boolean; settings: Record<string, unknown> }>("/main-channel-divider", {
        method: "PATCH",
        body: JSON.stringify(body),
      }),
    uploadImage: (file: File, label?: string) => {
      const fd = new FormData();
      fd.append("file", file);
      if (label) fd.append("label", label);
      return fetchApi<{ ok: boolean; image: Record<string, unknown>; settings: Record<string, unknown> }>(
        "/main-channel-divider/images",
        { method: "POST", body: fd }
      );
    },
    deleteImage: (imageId: string) =>
      fetchApi<{ ok: boolean; settings: Record<string, unknown> }>(
        `/main-channel-divider/images/${encodeURIComponent(imageId)}`,
        { method: "DELETE" }
      ),
    listEmojiFactorySources: () =>
      fetchApi<{
        jobs: Array<{
          job_id: string;
          cols: number;
          rows: number;
          tile_px?: number;
          tile_count: number;
          has_normalized: boolean;
          normalized_preview_url: string;
          tiles: Array<{
            tile: string;
            row?: number;
            col?: number;
            emoji?: string;
            preview_url: string;
          }>;
          row_strips?: Array<{
            row: number;
            preview_url: string;
            saved_path?: string | null;
            export_filename: string;
          }>;
        }>;
      }>("/main-channel-divider/emoji-factory-sources"),
    importFromEmojiFactory: (body: { job_id: string; tile?: string; row?: number; label?: string }) =>
      fetchApi<{ ok: boolean; settings: Record<string, unknown> }>("/main-channel-divider/import-from-emoji-factory", {
        method: "POST",
        body: JSON.stringify(body),
      }),
  },
  zipBundle: {
    get: () =>
      fetchApi<{
        settings: {
          enabled: boolean;
          include_text_file: boolean;
          include_image: boolean;
          text_filename: string;
          text_body: string;
          image_filename: string | null;
          image_url: string | null;
          has_image_on_disk: boolean;
        };
      }>("/zip-bundle-settings"),
    patch: (body: Record<string, unknown>) =>
      fetchApi<{ ok: boolean; settings: Record<string, unknown> }>("/zip-bundle-settings", {
        method: "PATCH",
        body: JSON.stringify(body),
      }),
    uploadPromoImage: (file: File) => {
      const fd = new FormData();
      fd.append("file", file);
      return fetchApi<{ ok: boolean; filename: string; url: string }>("/zip-bundle-settings/promo-image", {
        method: "POST",
        body: fd,
      });
    },
  },
  listeningRelay: {
    get: () =>
      fetchApi<{ settings: ListeningRelaySettings; webhook_secret?: string }>("/listening-relay-settings"),
    patch: (body: Record<string, unknown>) =>
      fetchApi<{ ok: boolean; settings: ListeningRelaySettings; webhook_secret?: string }>(
        "/listening-relay-settings",
        { method: "PATCH", body: JSON.stringify(body) }
      ),
    lastfmPreview: () => fetchApi<ListeningRelayLastfmPreview>("/listening-relay-settings/lastfm-preview"),
    testPost: () =>
      fetchApi<{ ok: boolean; queued?: boolean }>("/listening-relay-settings/test-post", { method: "POST" }),
    bufferTestPost: (body?: {
      text?: string;
      image_url?: string;
      x_only?: boolean;
      publish_now?: boolean;
    }) =>
      fetchApi<{ ok: boolean; queued?: Array<{ channel_id: string; post_id?: string }>; errors?: unknown }>(
        "/listening-relay-settings/buffer-test-post",
        { method: "POST", body: JSON.stringify(body ?? {}) }
      ),
    listAsciiArt: () =>
      fetchApi<{ entries: RelayAsciiEntry[]; max_width: number; max_lines: number }>(
        "/listening-relay-settings/ascii-art"
      ),
    uploadAsciiArt: (body: { name?: string; content: string }) =>
      fetchApi<{ ok: boolean; entry: RelayAsciiEntry }>("/listening-relay-settings/ascii-art", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    deleteAsciiArt: (id: string) =>
      fetchApi<{ ok: boolean }>(`/listening-relay-settings/ascii-art/${encodeURIComponent(id)}`, {
        method: "DELETE",
      }),
  },
  loot: {
    listModifiers: (includeInactive = true) =>
      fetchApi<LootModifier[]>(`/loot/modifiers?include_inactive=${includeInactive ? "true" : "false"}`),
    createModifier: (body: Partial<LootModifier> & { kind: string }) =>
      fetchApi<LootModifier>("/loot/modifiers", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    createModifierFromUrl: (body: {
      url: string;
      label?: string;
      kind?: string;
      source_note?: string;
    }) =>
      fetchApi<LootModifier>("/loot/modifiers/from-url", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    creatorSubmit: (body: { url: string; telegram_user_id?: number; handle?: string }) =>
      fetchApi<{ ok: boolean; modifier_id: number; label: string; target_url: string; message: string }>(
        "/loot/creator-submit",
        { method: "POST", body: JSON.stringify(body) }
      ),
    createModifiersFromUrlBatch: (items: Array<{
      url: string;
      label?: string;
      kind?: string;
      source_note?: string;
      as_zip_pack?: boolean;
    }>) =>
      fetchApi<{ ok_count: number; fail_count: number; results: Array<{ index: number; url: string; ok: boolean; modifier_id?: number; error?: string }> }>(
        "/loot/modifiers/from-url/batch",
        { method: "POST", body: JSON.stringify({ items }) }
      ),
    patchModifier: (id: number, body: Partial<LootModifier>) =>
      fetchApi<LootModifier>(`/loot/modifiers/${id}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      }),
    deleteModifier: (id: number) =>
      fetchApi<{ deleted: number }>(`/loot/modifiers/${id}`, {
        method: "DELETE",
      }),
    uploadZipModifier: (args: {
      file: File;
      label?: string;
      weight_base?: number;
      rarity_focus?: number;
      active?: boolean;
      bypass_vip?: boolean;
      source_note?: string;
    }) => {
      const params = new URLSearchParams();
      if (args.label != null) params.set("label", String(args.label));
      if (args.weight_base != null) params.set("weight_base", String(args.weight_base));
      if (args.rarity_focus != null) params.set("rarity_focus", String(args.rarity_focus));
      if (args.active != null) params.set("active", String(Boolean(args.active)));
      if (args.bypass_vip != null) params.set("bypass_vip", String(Boolean(args.bypass_vip)));
      if (args.source_note != null) params.set("source_note", String(args.source_note));
      const fd = new FormData();
      fd.append("file", args.file);
      const q = params.toString();
      return fetchApi<LootModifier>(`/loot/modifiers/upload-zip${q ? `?${q}` : ""}`, {
        method: "POST",
        body: fd,
      });
    },
    rollPreview: (args?: { telegram_user_id?: number; interval_code?: "m15" | "m30" | "m45" | "m60"; seed?: number }) => {
      const params = new URLSearchParams();
      if (args?.telegram_user_id != null) params.set("telegram_user_id", String(args.telegram_user_id));
      if (args?.interval_code) params.set("interval_code", args.interval_code);
      if (args?.seed != null) params.set("seed", String(args.seed));
      const q = params.toString();
      return fetchApi<LootRollPreview>(`/loot/roll-preview${q ? `?${q}` : ""}`);
    },
    sendPreviewDm: (args?: {
      telegram_user_id?: number;
      interval_code?: "m15" | "m30" | "m45" | "m60";
      seed?: number;
      to_telegram_user_id?: number;
    }) => {
      const params = new URLSearchParams();
      if (args?.telegram_user_id != null) params.set("telegram_user_id", String(args.telegram_user_id));
      if (args?.interval_code) params.set("interval_code", args.interval_code);
      if (args?.seed != null) params.set("seed", String(args.seed));
      if (args?.to_telegram_user_id != null) params.set("to_telegram_user_id", String(args.to_telegram_user_id));
      const q = params.toString();
      return fetchApi<{ ok: boolean; sent_to: number; preview: LootRollPreview }>(
        `/loot/send-preview-dm${q ? `?${q}` : ""}`,
        { method: "POST", body: "{}" }
      );
    },
  },
  externalPaymentOrders: {
    listPending: () =>
      fetchApi<
        Array<{
          id: number;
          telegram_user_id: number;
          plan_id: number;
          reference_code: string;
          status: string;
          created_at?: string | null;
          plan_name?: string | null;
          price_stars?: number | null;
        }>
      >("/external-payment-orders/pending"),
    markPaid: (orderId: number) =>
      fetchApi<Record<string, unknown>>(`/external-payment-orders/${orderId}/mark-paid`, {
        method: "POST",
        body: "{}",
      }),
    cancel: (orderId: number) =>
      fetchApi<Record<string, unknown>>(`/external-payment-orders/${orderId}/cancel`, {
        method: "POST",
        body: "{}",
      }),
  },
  llm: {
    status: () =>
      fetchApi<{ openai_configured: boolean; model: string }>("/llm/status"),
    suggestShopProduct: (body: {
      name: string;
      description?: string;
      product_type?: string;
      brand_voice_hint?: string;
    }) =>
      fetchApi<{
        tag_ids: number[];
        description: string | null;
        description_variations: string[];
        hook_line: string | null;
        model: string;
      }>("/llm/suggest-shop-product", { method: "POST", body: JSON.stringify(body) }),
    suggestMediaCaption: (body: { media_id: number; brand_voice_hint?: string }) =>
      fetchApi<{
        media_id: number;
        tag_ids: number[];
        tags_csv: string;
        caption: string | null;
        caption_variants: string[];
        curator_note: string | null;
        model: string;
      }>("/llm/suggest-media-caption", { method: "POST", body: JSON.stringify(body) }),
  },
  subscriptionPlans: {
    list: () => fetchApi<Array<Record<string, unknown>>>("/subscription-plans"),
    create: (body: {
      name: string;
      price_stars?: number;
      duration_days?: number;
      channel_id?: number;
      description?: string;
      is_active?: boolean;
      product_type?: string;
      bot_section?: string;
      /** @deprecated use promo_image_urls — kept for older callers */
      promo_image_url?: string;
      /** Up to 5 HTTPS URLs for Telegram promo album + invoice (first image on invoice). */
      promo_image_urls?: string[];
      /** Extra lines; bot picks randomly with `description` for invoices / pack views. */
      description_variations?: string[];
      /** tbcc_tags.id values from GET /tags */
      tag_ids?: number[];
      /** Optional fixed NOWPayments quote in USD for wallet/crypto checkout. */
      nowpayments_price_usd?: number;
      /** If true, NOWPayments checkout can offer supported currencies. */
      nowpayments_allow_any_currency?: boolean;
      /** Optional fixed NOWPayments pay currency (used when allow_any_currency is false). */
      nowpayments_pay_currency?: string;
      /** Optional metadata note for operator receiving wallet/address. */
      nowpayments_receiving_wallet?: string;
    }) =>
      fetchApi<Record<string, unknown>>("/subscription-plans", { method: "POST", body: JSON.stringify(body) }),
    update: (
      id: number,
      body: Partial<{
        name: string;
        price_stars: number;
        duration_days: number;
        channel_id: number | null;
        description: string | null;
        is_active: boolean;
        product_type: string;
        bot_section: string;
        promo_image_url: string | null;
        promo_image_urls: string[] | null;
        description_variations: string[] | null;
        tag_ids: number[] | null;
        nowpayments_price_usd: number | null;
        nowpayments_allow_any_currency: boolean;
        nowpayments_pay_currency: string | null;
        nowpayments_receiving_wallet: string | null;
      }>
    ) =>
      fetchApi<Record<string, unknown>>(`/subscription-plans/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
    delete: (id: number) =>
      fetchApi<{ deleted: number }>(`/subscription-plans/${id}`, { method: "DELETE" }),
    /** Digital bundle: append a .zip part (max ~50MB each — Telegram bot delivery limit). Call again for each split part. */
    uploadBundleZip: async (planId: number, file: File) => {
      const fd = new FormData();
      fd.append("file", file);
      const res = await fetch(`${API_BASE}/subscription-plans/${planId}/bundle-zip`, { method: "POST", body: fd });
      if (!res.ok) throw new Error(parseFastApiErrorBody(await res.text()));
      return res.json() as Promise<Record<string, unknown>>;
    },
    /** One promo image → public URL (served at GET /static/promo/… on the API host). Max 8MB. */
    uploadPromoImage: async (file: File) => {
      const fd = new FormData();
      fd.append("file", file);
      const res = await fetch(`${API_BASE}/subscription-plans/upload-promo-image`, { method: "POST", body: fd });
      if (!res.ok) throw new Error(parseFastApiErrorBody(await res.text()));
      return res.json() as Promise<{
        url: string;
        filename: string;
        telegram_reachable?: boolean;
        telegram_hint?: string | null;
      }>;
    },
    /** Omit `index` to remove all parts; otherwise 0-based part index. */
    deleteBundleZip: (planId: number, index?: number) =>
      fetchApi<{ deleted: number }>(
        `/subscription-plans/${planId}/bundle-zip${index !== undefined ? `?index=${index}` : ""}`,
        { method: "DELETE" }
      ),
  },
  jobs: {
    triggerScrape: (sourceId: number) =>
      fetchApi<{ status: string; run_id: number; celery_task_id?: string }>(`/jobs/scrape/${sourceId}`, {
        method: "POST",
      }),
    triggerMegaScrape: (body: {
      chat_id?: number;
      message_limit?: number;
      direct_only?: boolean;
      execute?: boolean;
    }) =>
      fetchApi<{ status: string; run_id: number; run_kind?: string; celery_task_id?: string }>(
        "/jobs/mega-scrape",
        { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }
      ),
    triggerPost: (poolId: number) =>
      fetchApi<{ status: string }>(`/jobs/post/${poolId}`, { method: "POST" }),
  },
   scheduledPosts: {
    list: () => fetchApi<Array<Record<string, unknown>>>("/scheduled-posts"),
    create: (body: {
      name?: string;
      channel_id?: number;
      /** Multi-channel campaign: one scheduler row per id (same caption/pool/interval). */
      channel_ids?: number[];
      /** Telegram forum topic id; omit for main chat */
      message_thread_id?: number | null;
      content: string;
      scheduled_at?: string;
      interval_minutes?: number;
      media_ids?: number[];
      pool_id?: number | null;
      pool_collective_random?: boolean;
      buttons?: Array<{ text: string; url: string }>;
      album_size?: number;
      pool_randomize?: boolean;
      pool_only_mode?: boolean;
      /** 2+ strings: captions rotate each run (e.g. hourly A, B, A, …) */
      content_variations?: string[];
      /** Dashboard promo images (/static/promo/…) — same upload as Bot Shop; not Media Library */
      attachment_urls?: string[];
      /** Per-caption albums: { attachment_urls?: string[]; media_ids?: number[] }[] */
      album_variants?: Array<{ attachment_urls?: string[]; media_ids?: number[] }>;
      album_order_mode?: "static" | "shuffle" | "carousel";
      send_silent?: boolean;
      pin_after_send?: boolean;
      /** Append payment-bot deep link button; Stars checkout opens in private chat with the bot. */
      checkout_stars_enabled?: boolean;
      checkout_stars_plan_id?: number | null;
      checkout_button_label?: string | null;
      checkout_referral_code?: string | null;
      buffer_mirror_enabled?: boolean;
      buffer_publish_now?: boolean;
      buffer_x_queue?: Array<{ text: string; image_url?: string }>;
      caption_llm_rewrite_enabled?: boolean;
      caption_llm_rewrite_mode?: "random" | "interval" | null;
      caption_llm_rewrite_interval?: number | null;
      caption_llm_rewrite_probability?: number | null;
      /** Multi-channel: each run posts to one random channel from channel_ids. */
      campaign_random_channel?: boolean;
    }) =>
      fetchApi<{ posts: Array<Record<string, unknown>>; campaign_group_id: string | null }>(
        "/scheduled-posts",
        { method: "POST", body: JSON.stringify(body) }
      ),
    update: (
      id: number,
      body: Partial<{
        name?: string;
        channel_id: number;
        /** Omit to leave unchanged; `null` = main chat */
        message_thread_id?: number | null;
        content: string;
        scheduled_at?: string | null;
        interval_minutes?: number | null;
        media_ids?: number[];
        pool_id?: number | null;
        pool_collective_random?: boolean | null;
        buttons?: Array<{ text: string; url: string }>;
        album_size?: number | null;
        pool_randomize?: boolean | null;
        pool_only_mode?: boolean | null;
        content_variations?: string[] | null;
        attachment_urls?: string[] | null;
        album_variants?: Array<{ attachment_urls?: string[]; media_ids?: number[] }> | null;
        album_order_mode?: "static" | "shuffle" | "carousel" | null;
        send_silent?: boolean | null;
        pin_after_send?: boolean | null;
        checkout_stars_enabled?: boolean | null;
        checkout_stars_plan_id?: number | null;
        checkout_button_label?: string | null;
        checkout_referral_code?: string | null;
        clear_auto_pause?: boolean;
        buffer_mirror_enabled?: boolean | null;
        buffer_publish_now?: boolean | null;
        buffer_x_queue?: Array<{ text: string; image_url?: string }> | null;
        caption_llm_rewrite_enabled?: boolean | null;
        caption_llm_rewrite_mode?: "random" | "interval" | null;
        caption_llm_rewrite_interval?: number | null;
        caption_llm_rewrite_probability?: number | null;
        campaign_random_channel?: boolean | null;
      }>
    ) =>
      fetchApi<Record<string, unknown>>(`/scheduled-posts/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
    delete: (id: number) =>
      fetchApi<{ deleted?: number; deleted_campaign?: string }>(`/scheduled-posts/${id}`, { method: "DELETE" }),
    trigger: async (id: number, options?: { reshuffle?: boolean }) =>
      throwIfBodyError(
        await fetchApi<{
          status: string;
          post_id?: number;
          campaign_group_id?: string | null;
          reshuffle?: boolean;
          error?: string;
        }>(
          `/scheduled-posts/${id}/trigger${options?.reshuffle ? "?reshuffle=true" : ""}`,
          { method: "POST" }
        )
      ),
  },
  archive: {
    list: (params?: {
      q?: string;
      tags?: string;
      kind?: "" | "url" | "username";
      username?: string;
      page?: number;
      page_size?: number;
      include_media?: boolean;
      sort?: string;
      order?: "asc" | "desc";
      sort2?: string;
      order2?: "asc" | "desc";
      status?: "approved" | "pending" | "rejected";
    }) => {
      const sp = new URLSearchParams();
      if (params?.q) sp.set("q", params.q);
      if (params?.tags) sp.set("tags", params.tags);
      if (params?.kind) sp.set("kind", params.kind);
      if (params?.username) sp.set("username", params.username);
      if (params?.status) sp.set("status", params.status);
      sp.set("page", String(params?.page ?? 1));
      sp.set("page_size", String(Math.min(100, params?.page_size ?? 100)));
      if (params?.include_media === false) sp.set("include_media", "false");
      if (params?.sort) sp.set("sort", params.sort);
      if (params?.order) sp.set("order", params.order);
      if (params?.sort2) sp.set("sort2", params.sort2);
      if (params?.order2) sp.set("order2", params.order2);
      const qs = sp.toString();
      return fetchApi<{
        items: CaptureArchiveEntry[];
        total: number;
        page: number;
        page_size: number;
        total_pages: number;
      }>(`/archive/entries?${qs}`);
    },
    syncBundle: () =>
      fetchApi<{ entries: CaptureArchiveEntry[]; total: number }>("/archive/entries/sync-bundle"),
    handles: () => fetchApi<{ handles: string[] }>("/archive/entries/handles"),
    bulk: (entries: CaptureArchiveEntryInput[], merge = true, autoTag = false) =>
      fetchApi<{ ok: boolean; added: number; total: number; auto_tag?: { enriched?: number } }>(
        "/archive/entries/bulk",
        {
          method: "POST",
          body: JSON.stringify({ entries, merge, auto_tag: autoTag }),
        }
      ),
    insertMenu: async (params?: { limit?: number; q?: string }) => {
      const limit = Math.min(params?.limit ?? 200, 500);
      const sp = new URLSearchParams();
      sp.set("limit", String(limit));
      if (params?.q) sp.set("q", params.q);
      type Row = { id: number; url: string; label: string; description?: string; tags?: string };
      try {
        return await fetchApi<{ items: Row[]; total: number }>(`/archive/entries/insert-menu?${sp.toString()}`);
      } catch {
        const items: Row[] = [];
        for (let page = 1; page <= 5 && items.length < limit; page++) {
          const list = await fetchApi<{
            items: CaptureArchiveEntry[];
            total_pages: number;
          }>(`/archive/entries?kind=url&page=${page}&page_size=100&include_media=false`);
          for (const e of list.items || []) {
            if (e.kind !== "url") continue;
            if (e.status && e.status !== "approved") continue;
            const label = String(e.description || e.summary || e.value || "").trim();
            items.push({
              id: Number(e.id) || 0,
              url: e.value,
              label: label.slice(0, 80),
              description: e.description || e.summary || "",
              tags: e.tags || "",
            });
            if (items.length >= limit) break;
          }
          if (page >= (list.total_pages || 1)) break;
        }
        return { items, total: items.length };
      }
    },
    autoTagEntry: (entryId: number, opts?: { force?: boolean; fast?: boolean }) =>
      fetchApi<{ ok: boolean; entry?: CaptureArchiveEntry }>(`/archive/entries/${entryId}/auto-tag`, {
        method: "POST",
        body: JSON.stringify(opts ?? {}),
      }),
    bulkAutoTag: (opts?: { ids?: number[]; missing_only?: boolean; limit?: number; force?: boolean }) =>
      fetchApi<{ ok: boolean; enriched: number; skipped: number; scanned: number }>(
        "/archive/entries/bulk/auto-tag",
        {
          method: "POST",
          body: JSON.stringify(opts ?? { missing_only: true }),
        }
      ),
    syncFromMedia: () =>
      fetchApi<{ ok: boolean; added: number; scanned: number }>("/archive/entries/sync-from-media", {
        method: "POST",
      }),
    clear: (confirm: string) =>
      fetchApi<{ ok: boolean; deleted: number }>(
        `/archive/entries?confirm=${encodeURIComponent(confirm)}`,
        { method: "DELETE" }
      ),
    governEntry: (entryId: number, status: "approved" | "rejected" | "pending", reviewedBy?: string) =>
      fetchApi<{ ok: boolean; entry: CaptureArchiveEntry }>(`/archive/entries/${entryId}/governance`, {
        method: "POST",
        body: JSON.stringify({ status, reviewed_by: reviewedBy }),
      }),
    pendingGovernance: () =>
      fetchApi<{ items: CaptureArchiveEntry[]; total: number }>("/archive/governance/pending"),
    exportDownloadUrl: (
      format: "json" | "csv" | "txt",
      params?: { q?: string; kind?: string; sort?: string; order?: string; sort2?: string; order2?: string }
    ) => {
      const sp = new URLSearchParams({ format });
      if (params?.q) sp.set("q", params.q);
      if (params?.kind) sp.set("kind", params.kind);
      if (params?.sort) sp.set("sort", params.sort);
      if (params?.order) sp.set("order", params.order);
      if (params?.sort2) sp.set("sort2", params.sort2);
      if (params?.order2) sp.set("order2", params.order2);
      return `${API_BASE}/archive/entries/export?${sp.toString()}`;
    },
  },
  extensionContextMenu: {
    get: () =>
      fetchApi<{ pageMenu: Record<string, boolean>; labels: Record<string, string> }>(
        "/extension/context-menu"
      ),
    patch: (pageMenu: Record<string, boolean>) =>
      fetchApi<{ pageMenu: Record<string, boolean>; labels: Record<string, string> }>(
        "/extension/context-menu",
        {
          method: "PATCH",
          body: JSON.stringify({ pageMenu }),
        }
      ),
  },
  k2s: {
    status: () =>
      fetchApi<{
        enabled: boolean;
        configured: boolean;
        mirror_enabled: boolean;
        lanes: Array<{
          lane: string;
          folder_id: string | null;
          folder_name: string | null;
          env_var: string;
          network_channel: string | null;
        }>;
      }>("/k2s/status"),
    ensureFolders: () =>
      fetchApi<{ ok: boolean; folders: Record<string, string | null>; lanes: unknown[] }>(
        "/k2s/ensure-folders",
        { method: "POST" }
      ),
    library: (lane = "packs", limit = 50, offset = 0) =>
      fetchApi<{
        lane: string;
        folder_id: string;
        count: number;
        files: Array<{
          id: string;
          name: string;
          size: number;
          is_folder: boolean;
          is_available: boolean;
          public_url: string | null;
        }>;
      }>(`/k2s/library?lane=${encodeURIComponent(lane)}&limit=${limit}&offset=${offset}`),
    checkUrl: (url: string) =>
      fetchApi<{ ok: boolean; host_kind?: string; reason?: string; file_id?: string }>(
        "/k2s/check-url",
        { method: "POST", body: JSON.stringify({ url }) }
      ),
    mirror: (modifierId: number, lane?: string) =>
      fetchApi<Record<string, unknown>>("/k2s/mirror", {
        method: "POST",
        body: JSON.stringify({ modifier_id: modifierId, lane: lane || undefined }),
      }),
  },
};
