const API_BASE = "/api";

/** Avoid infinite “Loading…” if the backend or DB never responds (default fetch has no timeout). */
const FETCH_TIMEOUT_MS = 30_000;

function timeoutSignal(ms: number): AbortSignal {
  if (typeof AbortSignal !== "undefined" && typeof AbortSignal.timeout === "function") {
    return AbortSignal.timeout(ms);
  }
  const c = new AbortController();
  setTimeout(() => c.abort(), ms);
  return c.signal;
}

async function fetchApi<T>(path: string, options?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...options,
      signal: options?.signal ?? timeoutSignal(FETCH_TIMEOUT_MS),
      headers: { "Content-Type": "application/json", ...options?.headers },
    });
  } catch (e) {
    const msg =
      e instanceof DOMException && e.name === "AbortError"
        ? `Request timed out after ${FETCH_TIMEOUT_MS / 1000}s. Is the API up (port 8000) and the database reachable?`
        : e instanceof TypeError && e.message === "Failed to fetch"
          ? "Cannot reach backend. Is it running on http://localhost:8000?"
          : String(e);
    throw new Error(msg);
  }
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export const api = {
  health: () => fetchApi<{ status: string }>("/health"),
  media: {
    list: (statusOrOpts?: string | { status?: string; pool_id?: number }) => {
      const opts = typeof statusOrOpts === "string" ? { status: statusOrOpts } : statusOrOpts;
      const params = new URLSearchParams();
      if (opts?.status) params.set("status", opts.status);
      if (opts?.pool_id != null) params.set("pool_id", String(opts.pool_id));
      const q = params.toString();
      return fetchApi<Array<Record<string, unknown>>>(q ? `/media?${q}` : "/media");
    },
    updateStatus: (mediaId: number, status: string) =>
      fetchApi<Record<string, unknown>>(`/media/${mediaId}`, {
        method: "PATCH",
        body: JSON.stringify({ status }),
      }),
    updateStatusBulk: (ids: number[], status: string) =>
      fetchApi<{ updated: number }>(`/media/bulk`, {
        method: "PATCH",
        body: JSON.stringify({ ids, status }),
      }),
    thumbnailUrl: (id: number) => `${API_BASE}/media/${id}/thumbnail`,
    /** Full bytes (Telegram download or URL proxy) — use in lightbox / video src. */
    fileUrl: (id: number) => `${API_BASE}/media/${id}/file`,
  },
  pools: {
    list: () => fetchApi<Array<Record<string, unknown>>>("/pools"),
    create: (body: {
      name: string;
      channel_id: number;
      album_size?: number;
      interval_minutes?: number;
      randomize_queue?: boolean;
    }) => fetchApi<Record<string, unknown>>("/pools", { method: "POST", body: JSON.stringify(body) }),
    update: (
      id: number,
      body: Partial<{
        name: string;
        channel_id: number;
        album_size: number;
        interval_minutes: number;
        randomize_queue: boolean;
      }>
    ) =>
      fetchApi<Record<string, unknown>>(`/pools/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  },
  import: {
    bytes: async (file: File, poolId: number, source?: string) => {
      const form = new FormData();
      form.append("file", file);
      form.append("pool_id", String(poolId));
      form.append("saved_only", "false");
      form.append("source", source || "dashboard:upload");
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
    update: (id: number, body: Partial<{ name: string; identifier: string; invite_link: string | null }>) =>
      fetchApi<Record<string, unknown>>(`/channels/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
    /** Forum-enabled supergroups only — topic `id` is message_thread_id for scheduled posts */
    forumTopics: (channelId: number) =>
      fetchApi<{ topics: Array<{ id: number; title: string }>; error?: string | null }>(
        `/channels/${channelId}/forum-topics`
      ),
  },
  bots: { list: () => fetchApi<Array<Record<string, unknown>>>("/bots") },
  subscriptions: {
    list: (status?: string) =>
      fetchApi<Array<Record<string, unknown>>>(status ? `/subscriptions?status=${status}` : "/subscriptions"),
  },
  analytics: {
    subscriptions: () => fetchApi<{ total_subscriptions: number; active: number; expired: number; cancelled: number; revenue_stars: number }>("/analytics/subscriptions"),
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
      promo_image_url?: string;
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
      }>
    ) =>
      fetchApi<Record<string, unknown>>(`/subscription-plans/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
    delete: (id: number) =>
      fetchApi<{ deleted: number }>(`/subscription-plans/${id}`, { method: "DELETE" }),
    /** Digital bundle: upload a .zip (max ~50MB — Telegram bot delivery limit). */
    uploadBundleZip: async (planId: number, file: File) => {
      const fd = new FormData();
      fd.append("file", file);
      const res = await fetch(`${API_BASE}/subscription-plans/${planId}/bundle-zip`, { method: "POST", body: fd });
      if (!res.ok) throw new Error(await res.text());
      return res.json() as Promise<Record<string, unknown>>;
    },
    /** One promo image → public URL (served at GET /static/promo/… on the API host). Max 8MB. */
    uploadPromoImage: async (file: File) => {
      const fd = new FormData();
      fd.append("file", file);
      const res = await fetch(`${API_BASE}/subscription-plans/upload-promo-image`, { method: "POST", body: fd });
      if (!res.ok) throw new Error(await res.text());
      return res.json() as Promise<{
        url: string;
        filename: string;
        telegram_reachable?: boolean;
        telegram_hint?: string | null;
      }>;
    },
    deleteBundleZip: (planId: number) =>
      fetchApi<{ deleted: number }>(`/subscription-plans/${planId}/bundle-zip`, { method: "DELETE" }),
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
      /** 2+ strings: captions rotate each run (e.g. hourly A, B, A, …) */
      content_variations?: string[];
    }) =>
      fetchApi<Record<string, unknown>>("/scheduled-posts", { method: "POST", body: JSON.stringify(body) }),
    update: (
      id: number,
      body: Partial<{
        name?: string;
        channel_id: number;
        message_thread_id?: number | null;
        content: string;
        scheduled_at?: string;
        interval_minutes?: number;
        media_ids?: number[];
        pool_id?: number;
        buttons?: Array<{ text: string; url: string }>;
        album_size?: number | null;
        pool_randomize?: boolean | null;
        content_variations?: string[] | null;
      }>
    ) =>
      fetchApi<Record<string, unknown>>(`/scheduled-posts/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
    delete: (id: number) => fetchApi<{ deleted: number }>(`/scheduled-posts/${id}`, { method: "DELETE" }),
    trigger: (id: number) => fetchApi<{ status: string }>(`/scheduled-posts/${id}/trigger`, { method: "POST" }),
  },
};
