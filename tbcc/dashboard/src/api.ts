/**
 * Default `/api` is rewritten by Vite to the TBCC backend (see vite.config.ts).
 * For static hosting without a proxy, set e.g. `VITE_API_BASE=http://127.0.0.1:8000` at build time.
 */
const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, "") || "/api";

/** Avoid infinite “Loading…” if the backend or DB never responds (default fetch has no timeout). */
const FETCH_TIMEOUT_MS = 30_000;
/** Bulk writes can wait behind SQLite + many parallel thumbnail reads — allow longer per chunk. */
const BULK_PATCH_TIMEOUT_MS = 300_000;
const BULK_MEDIA_CHUNK_SIZE = 15;
/** Yield between chunks so thumbnail / other API traffic can finish and release SQLite locks. */
const BULK_CHUNK_GAP_MS = 200;

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
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...fetchInit,
      signal: fetchInit.signal ?? timeoutSignal(timeoutMs),
      headers: { "Content-Type": "application/json", ...fetchInit.headers },
    });
  } catch (e) {
    const msg =
      e instanceof DOMException && e.name === "AbortError"
        ? `Request timed out after ${timeoutMs / 1000}s. Is the API up (port 8000) and the database reachable? If you bulk-approved many items, try again (requests are now sent in smaller batches).`
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

export const api = {
  health: () => fetchApi<{ status: string }>("/health"),
  healthDb: () =>
    fetchApi<{ status?: string; database?: string; error?: string; detail?: string }>("/health/db"),
  media: {
    list: (
      statusOrOpts?: string | { status?: string; pool_id?: number; tag?: string; tag_slug?: string }
    ) => {
      const opts = typeof statusOrOpts === "string" ? { status: statusOrOpts } : statusOrOpts;
      const params = new URLSearchParams();
      if (opts?.status) params.set("status", opts.status);
      if (opts?.pool_id != null) params.set("pool_id", String(opts.pool_id));
      if (opts?.tag) params.set("tag", opts.tag);
      if (opts?.tag_slug) params.set("tag_slug", opts.tag_slug);
      const q = params.toString();
      return fetchApi<Array<Record<string, unknown>>>(q ? `/media?${q}` : "/media");
    },
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
      for (let i = 0; i < ids.length; i += BULK_MEDIA_CHUNK_SIZE) {
        if (i > 0) {
          await new Promise((r) => setTimeout(r, BULK_CHUNK_GAP_MS));
        }
        const slice = ids.slice(i, i + BULK_MEDIA_CHUNK_SIZE);
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
      if (ids.length === 0) return { updated: 0, skipped_duplicate_in_target_pool: 0 };
      let updated = 0;
      let skipped = 0;
      for (let i = 0; i < ids.length; i += BULK_MEDIA_CHUNK_SIZE) {
        if (i > 0) {
          await new Promise((r) => setTimeout(r, BULK_CHUNK_GAP_MS));
        }
        const slice = ids.slice(i, i + BULK_MEDIA_CHUNK_SIZE);
        const r = await fetchApi<{
          updated: number;
          error?: string;
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
    thumbnailUrl: (id: number) => `${API_BASE}/media/${id}/thumbnail`,
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
  pools: {
    list: () => fetchApi<Array<Record<string, unknown>>>("/pools"),
    create: (body: {
      name: string;
      channel_id: number;
      album_size?: number;
      interval_minutes?: number;
      auto_post_enabled?: boolean;
      randomize_queue?: boolean;
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
      }>
    ) =>
      fetchApi<Record<string, unknown>>(`/pools/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
    deletePool: (id: number) =>
      fetchApi<{ deleted: number }>(`/pools/${id}`, { method: "DELETE" }),
  },
  forum: {
    postAlbum: (body: {
      channel_id: number;
      message_thread_id?: number | null;
      media_ids: number[];
      caption?: string;
      mark_posted?: boolean;
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
      opts?: { savedOnly?: boolean; caption?: string }
    ) => {
      const form = new FormData();
      form.append("file", file);
      form.append("pool_id", String(poolId));
      form.append("saved_only", opts?.savedOnly ? "true" : "false");
      form.append("source", source || "dashboard:upload");
      if (opts?.caption?.trim()) form.append("caption", opts.caption.trim());
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
    fromSaved: (poolId: number, limit?: number) =>
      fetchApi<{
        status?: string;
        indexed?: number;
        skipped_duplicates_or_unsupported?: number;
        messages_scanned?: number;
        error?: string;
      }>("/import/from-saved", {
        method: "POST",
        body: JSON.stringify({ pool_id: poolId, limit: limit ?? 50 }),
      }),
  },
  sources: {
    list: () => fetchApi<Array<Record<string, unknown>>>("/sources"),
    create: (body: { name: string; source_type?: string; identifier: string; pool_id: number; active?: boolean }) =>
      fetchApi<Record<string, unknown>>("/sources", { method: "POST", body: JSON.stringify(body) }),
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
  },
  bots: { list: () => fetchApi<Array<Record<string, unknown>>>("/bots") },
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
      /** @deprecated use promo_image_urls — kept for older callers */
      promo_image_url?: string;
      /** Up to 5 HTTPS URLs for Telegram promo album + invoice (first image on invoice). */
      promo_image_urls?: string[];
      /** Extra lines; bot picks randomly with `description` for invoices / pack views. */
      description_variations?: string[];
      /** tbcc_tags.id values from GET /tags */
      tag_ids?: number[];
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
        promo_image_url: string | null;
        promo_image_urls: string[] | null;
        description_variations: string[] | null;
        tag_ids: number[] | null;
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
      fetchApi<{ status: string }>(`/jobs/scrape/${sourceId}`, { method: "POST" }),
    triggerPost: (poolId: number) =>
      fetchApi<{ status: string }>(`/jobs/post/${poolId}`, { method: "POST" }),
  },
  scheduledPosts: {
    list: () => fetchApi<Array<Record<string, unknown>>>("/scheduled-posts"),
    create: (body: {
      name?: string;
      channel_id: number;
      /** Telegram forum topic id; omit for main chat */
      message_thread_id?: number | null;
      content: string;
      scheduled_at?: string;
      interval_minutes?: number;
      media_ids?: number[];
      pool_id?: number;
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
    }) =>
      fetchApi<Record<string, unknown>>("/scheduled-posts", { method: "POST", body: JSON.stringify(body) }),
    update: (
      id: number,
      body: Partial<{
        name?: string;
        channel_id: number;
        /** Omit to leave unchanged; `null` = main chat */
        message_thread_id?: number | null;
        content: string;
        scheduled_at?: string;
        interval_minutes?: number;
        media_ids?: number[];
        pool_id?: number | null;
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
      }>
    ) =>
      fetchApi<Record<string, unknown>>(`/scheduled-posts/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
    delete: (id: number) => fetchApi<{ deleted: number }>(`/scheduled-posts/${id}`, { method: "DELETE" }),
    trigger: (id: number) => fetchApi<{ status: string }>(`/scheduled-posts/${id}/trigger`, { method: "POST" }),
  },
};
