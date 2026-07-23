import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import { useApiTarget } from "../context/ApiTargetContext";
import { useState, useEffect, useMemo } from "react";
import { SchedulePromoSlots } from "./SchedulePromoSlots";
import { ApprovedMediaPickerStrip } from "./ApprovedMediaPickerStrip";
import {
  formatPtForDashboard,
  formatUtcForDashboard,
  formatUtcWithLocalHint,
} from "../utils/formatUtc";
import { CaptionTelegramHtmlField } from "./CaptionTelegramHtmlField";
import { TbccInsertMenu } from "./TbccInsertMenu";
import { TbccInsertLibraryToolbar } from "./TbccInsertLibraryToolbar";
import { BufferXQueueEditor, type BufferXQueueItem } from "./BufferXQueueEditor";
import { CaptionLlmRewriteFields } from "./CaptionLlmRewriteFields";
import { SilentTelegramSendOption } from "./SilentTelegramSendOption";
import { SchedulerOverviewBand } from "./SchedulerOverviewBand";
import { SchedulerIntervalCountdown, useSchedulerClock } from "./SchedulerIntervalCountdown";
import {
  classifySchedulerPost,
  computeTransportStats,
  HIDE_SENT_STORAGE_KEY,
  inferSchedulerGroup,
  isSentOneShot,
  LIST_MODE_STORAGE_KEY,
  matchesStatusFilter,
  readHideSentOneShots,
  readSchedulerListMode,
  SCHEDULER_GROUP_DEFAULT_EXPANDED,
  SCHEDULER_GROUP_LABELS,
  SCHEDULER_GROUP_ORDER,
  shouldUseFastSchedulerPoll,
  type SchedulerGroupId,
  type SchedulerListMode,
  type SchedulerStatusFilter,
} from "../utils/schedulerPostStatus";
import { SchedulerTransportBar } from "./SchedulerTransportBar";
import { SchedulerGroupSection } from "./SchedulerGroupSection";
import { SchedulerPostStatusCell } from "./SchedulerPostStatusCell";
import { MediaPoolSelect } from "./MediaPoolSelect";
import {
  poolSelectFromPost,
  poolSelectLabel,
  poolSelectToApi,
  poolSelectUsesPool,
  poolSelectUsesSpecificPool,
  poolAlbumDefaultsFromMap,
} from "../utils/mediaPoolSelect";

type AlbumVariant = { attachment_urls: string[]; media_ids: number[] };

function parseAlbumVariantsFromPost(p: Record<string, unknown>): {
  variants: AlbumVariant[];
  order: "static" | "shuffle" | "carousel";
} {
  const av = p.album_variants;
  const om = String(p.album_order_mode || "static");
  const order: "static" | "shuffle" | "carousel" =
    om === "shuffle" || om === "carousel" ? om : "static";
  if (Array.isArray(av) && av.length > 0) {
    return {
      variants: av.map((x: Record<string, unknown>) => ({
        attachment_urls: Array.isArray(x.attachment_urls)
          ? x.attachment_urls.map((u) => String(u ?? ""))
          : [],
        media_ids: Array.isArray(x.media_ids)
          ? x.media_ids.map((n) => Number(n)).filter((n) => Number.isFinite(n))
          : [],
      })),
      order,
    };
  }
  const mids = parseScheduledMediaIds(p);
  const att = p.attachment_urls;
  const urls = Array.isArray(att) ? att.map((x) => String(x ?? "")) : [];
  return { variants: [{ attachment_urls: urls, media_ids: mids }], order };
}

function padAlbumVariants(v: AlbumVariant[], n: number): AlbumVariant[] {
  const out = [...v];
  while (out.length < n) out.push({ attachment_urls: [], media_ids: [] });
  return out.slice(0, n);
}

function parseScheduledMediaIds(p: Record<string, unknown>): number[] {
  const raw = p.media_ids;
  if (Array.isArray(raw)) return raw.map((x) => Number(x)).filter((n) => Number.isFinite(n));
  if (typeof raw === "string") {
    try {
      const j = JSON.parse(raw) as unknown;
      if (Array.isArray(j)) return j.map((x) => Number(x)).filter((n) => Number.isFinite(n));
    } catch {
      /* ignore */
    }
  }
  return [];
}

/** Pool, promo URLs, or picked media — something that can be reshuffled / reposted as an album. */
function scheduledPostHasAlbumOrPool(p: Record<string, unknown>): boolean {
  if (Boolean(p.pool_collective_random)) return true;
  const pid = p.pool_id != null ? Number(p.pool_id) : 0;
  if (Number.isFinite(pid) && pid > 0) return true;
  const { variants } = parseAlbumVariantsFromPost(p);
  for (const v of variants) {
    if (v.media_ids.length > 0) return true;
    if (v.attachment_urls.some((u) => String(u).trim())) return true;
  }
  if (parseScheduledMediaIds(p).length > 0) return true;
  const att = p.attachment_urls;
  if (Array.isArray(att) && att.some((x) => String(x ?? "").trim())) return true;
  return false;
}

function isoToDatetimeLocal(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(String(iso));
  if (isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function datetimeLocalToIso(local: string): string {
  if (!local || local.length < 16) return new Date().toISOString();
  const d = new Date(local.length <= 16 ? `${local}:00` : local);
  return d.toISOString();
}

const SCHED_COLS = 9;

/** Match Scheduler.tsx interval presets for edit modal */
const EDIT_INTERVAL_OPTIONS = [15, 30, 60, 120, 180, 240, 360, 720];

function parseButtonsFromPost(p: Record<string, unknown>): Array<{ text: string; url: string }> {
  const b = p.buttons;
  const fromArr = (arr: unknown[]) =>
    arr
      .filter((x): x is Record<string, unknown> => typeof x === "object" && x != null)
      .map((o) => ({ text: String(o.text ?? "").trim(), url: String(o.url ?? "").trim() }))
      .filter((x) => x.text && x.url);
  if (Array.isArray(b)) return fromArr(b);
  if (typeof b === "string" && b.trim()) {
    try {
      const j = JSON.parse(b) as unknown;
      if (Array.isArray(j)) return fromArr(j);
    } catch {
      /* ignore */
    }
  }
  return [];
}

type WeekPost = {
  id: number;
  name?: string | null;
  scheduled_at?: string | null;
  interval_minutes?: number | null;
  channel_name?: string | null;
  campaign_group_id?: string | null;
};

type Props = {
  /** Only show recurring (interval) jobs — e.g. on Subscriptions tab */
  compactRecurringOnly?: boolean;
  weekPosts?: WeekPost[];
  onWeekDayClick?: (isoDate: string) => void;
};

export function ScheduledPostsList({ compactRecurringOnly, weekPosts = [], onWeekDayClick }: Props) {
  const queryClient = useQueryClient();
  const { target } = useApiTarget();

  const [editOpen, setEditOpen] = useState(false);
  const [editing, setEditing] = useState<Record<string, unknown> | null>(null);
  const [editName, setEditName] = useState("");
  /** 2+ filled = rotating captions */
  const [editVariations, setEditVariations] = useState<string[]>([""]);
  const [editChannelId, setEditChannelId] = useState(0);
  const [editInterval, setEditInterval] = useState(30);
  const [editScheduledAt, setEditScheduledAt] = useState("");
  /** Editable schedule mode (independent of original row until save) */
  const [editScheduleRecurring, setEditScheduleRecurring] = useState(false);
  const [editAlbumSize, setEditAlbumSize] = useState(5);
  const [editRandomize, setEditRandomize] = useState(false);
  const [editPoolOnlyMode, setEditPoolOnlyMode] = useState(true);
  const [editMessageThreadId, setEditMessageThreadId] = useState<number | null>(null);
  /** Pool for media picker + uploads (0 = any pool / no pool auto-pick) */
  const [editPoolId, setEditPoolId] = useState(0);
  const [editUploadMsg, setEditUploadMsg] = useState<string | null>(null);
  /** One entry per caption variation (or length 1 for single caption) */
  const [editAlbumVariants, setEditAlbumVariants] = useState<AlbumVariant[]>([
    { attachment_urls: [], media_ids: [] },
  ]);
  const [editAlbumOrderMode, setEditAlbumOrderMode] = useState<"static" | "shuffle" | "carousel">("static");
  /** Set when editing a grouped multi-channel row */
  const [editCampaignHint, setEditCampaignHint] = useState<string | null>(null);
  const [editCampaignRandomChannel, setEditCampaignRandomChannel] = useState(false);
  const [editButtons, setEditButtons] = useState<Array<{ text: string; url: string }>>([]);
  const [editSendSilent, setEditSendSilent] = useState(false);
  const [editPinAfterSend, setEditPinAfterSend] = useState(false);
  const [editBufferMirror, setEditBufferMirror] = useState(false);
  const [editBufferPublishNow, setEditBufferPublishNow] = useState(false);
  const [editBufferXQueue, setEditBufferXQueue] = useState<BufferXQueueItem[]>([]);
  const [editLlmRewrite, setEditLlmRewrite] = useState(false);
  const [editLlmMode, setEditLlmMode] = useState<"" | "random" | "interval">("interval");
  const [editLlmInterval, setEditLlmInterval] = useState(3);
  const [editLlmProb, setEditLlmProb] = useState(0.25);
  const [editCheckoutStarsEnabled, setEditCheckoutStarsEnabled] = useState(false);
  const [editCheckoutPlanId, setEditCheckoutPlanId] = useState(0);
  const [editCheckoutButtonLabel, setEditCheckoutButtonLabel] = useState("");
  const [editCheckoutReferralCode, setEditCheckoutReferralCode] = useState("");
  const [editScheduleError, setEditScheduleError] = useState<string | null>(null);
  const [triggerNotice, setTriggerNotice] = useState<{ kind: "ok" | "err"; text: string } | null>(null);
  const [listMode, setListMode] = useState<SchedulerListMode>(() => readSchedulerListMode());
  const [hideSentOneShots, setHideSentOneShots] = useState(() => readHideSentOneShots(readSchedulerListMode()));
  const [statusFilter, setStatusFilter] = useState<SchedulerStatusFilter>("all");

  const { data: pools = [] } = useQuery({
    queryKey: ["pools"],
    queryFn: () => api.pools.list(),
  });
  const { data: channels = [] } = useQuery({
    queryKey: ["channels"],
    queryFn: () => api.channels.list(),
  });
  const { data: schedulingHealth } = useQuery({
    queryKey: ["health", "scheduling", target],
    queryFn: () => api.healthScheduling(),
    refetchInterval: 15_000,
  });
  const schedulerNowMs = useSchedulerClock();
  const [postsPollMs, setPostsPollMs] = useState(30_000);
  const { data: scheduledPosts = [] } = useQuery({
    queryKey: ["scheduledPosts"],
    queryFn: () => api.scheduledPosts.list(),
    refetchInterval: postsPollMs,
  });
  const transportStats = useMemo(
    () => computeTransportStats(scheduledPosts as Array<Record<string, unknown>>, schedulingHealth, schedulerNowMs),
    [scheduledPosts, schedulingHealth, schedulerNowMs]
  );
  useEffect(() => {
    const next = compactRecurringOnly
      ? 30_000
      : shouldUseFastSchedulerPoll(transportStats, schedulingHealth)
        ? 15_000
        : 30_000;
    setPostsPollMs((prev) => (prev === next ? prev : next));
  }, [compactRecurringOnly, transportStats, schedulingHealth]);

  useEffect(() => {
    try {
      localStorage.setItem(LIST_MODE_STORAGE_KEY, listMode);
    } catch {
      /* ignore */
    }
  }, [listMode]);

  useEffect(() => {
    try {
      localStorage.setItem(HIDE_SENT_STORAGE_KEY, hideSentOneShots ? "1" : "0");
    } catch {
      /* ignore */
    }
  }, [hideSentOneShots]);
  const { data: subscriptionPlansRaw = [] } = useQuery({
    queryKey: ["subscriptionPlans"],
    queryFn: () => api.subscriptionPlans.list(),
  });
  const salablePlans = (subscriptionPlansRaw as Array<Record<string, unknown>>).filter(
    (p) => p.is_active !== false && Number(p.price_stars || 0) > 0
  );
  const { data: editForumTopicsRes } = useQuery({
    queryKey: ["forumTopics", editChannelId],
    queryFn: () => api.channels.forumTopics(editChannelId),
    enabled: editOpen && editChannelId > 0,
  });
  const editForumTopics = editForumTopicsRes?.topics ?? [];
  const editForumTopicsHint = editForumTopicsRes?.error;

  const { data: editMedia = [] } = useQuery({
    queryKey: ["media", "approved", "scheduled-edit", editPoolId],
    queryFn: () =>
      poolSelectUsesSpecificPool(editPoolId)
        ? api.media.list({ status: "approved", pool_id: editPoolId })
        : api.media.list("approved"),
    enabled: editOpen,
  });

  const poolMap = Object.fromEntries(
    (pools as Array<Record<string, unknown>>).map((p) => [String(p.id), p])
  );

  const updateScheduled = useMutation({
    mutationFn: ({
      id,
      body,
    }: {
      id: number;
      body: Parameters<typeof api.scheduledPosts.update>[1];
    }) => api.scheduledPosts.update(id, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["scheduledPosts"] });
      queryClient.invalidateQueries({ queryKey: ["pools"] });
    },
  });

  const deleteScheduledPost = useMutation({
    mutationFn: (id: number) => api.scheduledPosts.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["scheduledPosts"] });
      queryClient.invalidateQueries({ queryKey: ["pools"] });
    },
  });

  const triggerScheduledPost = useMutation({
    mutationFn: ({ id, reshuffle }: { id: number; reshuffle?: boolean }) =>
      api.scheduledPosts.trigger(id, { reshuffle: !!reshuffle }),
    onSuccess: (data, { id }) => {
      queryClient.invalidateQueries({ queryKey: ["scheduledPosts"] });
      const cg = data?.campaign_group_id;
      const rs = data?.reshuffle;
      const all =
        (queryClient.getQueryData(["scheduledPosts"]) as Array<Record<string, unknown>> | undefined) || [];
      const leaderId = cg ? Number(data.post_id ?? id) : id;
      const post = all.find((x) => Number(x.id) === leaderId);
      const bufHint = post?.buffer_mirror_enabled
        ? post?.buffer_publish_now
          ? " Buffer → X (publish now) runs right after Telegram — check X in a few seconds."
          : " Buffer → X queued after Telegram — check publish.buffer.com."
        : "";
      setTriggerNotice({
        kind: "ok",
        text: cg
          ? `Campaign queued (leader #${data.post_id ?? id})${rs ? " — album order reshuffled for this send" : ""} — Celery will send to all channels shortly.${bufHint}`
          : `Post #${id} queued${rs ? " — album order reshuffled for this send" : ""} — Celery will send shortly.${bufHint}`,
      });
    },
    onError: (e: Error, { id }) => {
      setTriggerNotice({ kind: "err", text: `Post #${id}: ${e.message}` });
    },
  });

  const uploadToPoolEdit = useMutation({
    mutationFn: async ({ files, pid }: { files: File[]; pid: number }) => {
      const out: string[] = [];
      for (let i = 0; i < files.length; i++) {
        const f = files[i];
        const r = await api.import.bytes(f, pid, "dashboard:scheduled-post-edit");
        if (r.error) out.push(`${f.name}: ${r.error}`);
        else if (r.status === "imported") out.push(`${f.name}: imported`);
        else out.push(`${f.name}: ${String(r.status || "skipped")}`);
      }
      return out.join("\n");
    },
    onSuccess: (msg) => {
      setEditUploadMsg(msg);
      void queryClient.invalidateQueries({ queryKey: ["media"] });
      setTimeout(() => setEditUploadMsg(null), 8000);
    },
    onError: (e: Error) => setEditUploadMsg(e.message),
  });

  function toggleVariantMedia(variantIdx: number, id: number) {
    setEditAlbumVariants((prev) => {
      const next = [...prev];
      while (next.length <= variantIdx) next.push({ attachment_urls: [], media_ids: [] });
      const cur = next[variantIdx];
      const mids = cur.media_ids.includes(id) ? cur.media_ids.filter((x) => x !== id) : [...cur.media_ids, id];
      next[variantIdx] = { ...cur, media_ids: mids };
      return next;
    });
  }

  useEffect(() => {
    if (!editOpen) return;
    setEditAlbumVariants((prev) => padAlbumVariants(prev, editVariations.length));
  }, [editOpen, editVariations.length]);

  useEffect(() => {
    if (!triggerNotice) return;
    const t = setTimeout(() => setTriggerNotice(null), 8000);
    return () => clearTimeout(t);
  }, [triggerNotice]);

  function openEditor(p: Record<string, unknown>) {
    const cg = p.campaign_group_id as string | undefined;
    const cohort =
      cg && typeof cg === "string"
        ? [...(scheduledPosts as Array<Record<string, unknown>>)]
            .filter((x) => x.campaign_group_id === cg)
            .sort((a, b) => Number(a.id) - Number(b.id))
        : [p];
    const leader = cohort[0] ?? p;
    setEditing(leader);
    setEditCampaignHint(
      cg && cohort.length > 1
        ? `Campaign (${cohort.length} channels): ${cohort.map((x) => String(x.channel_name || x.channel_id)).join(", ")}`
        : null
    );
    setEditName(String(leader.name || ""));
    const cv = leader.content_variations;
    if (Array.isArray(cv) && cv.length >= 2) {
      setEditVariations(cv.map((x) => String(x ?? "")));
    } else {
      setEditVariations([String(leader.content ?? "")]);
    }
    setEditChannelId(Number(leader.channel_id || 0));
    setEditInterval(Number(leader.interval_minutes || 240));
    setEditScheduledAt(isoToDatetimeLocal(leader.scheduled_at as string | undefined));
    setEditScheduleRecurring(!!leader.interval_minutes);
    const pid = leader.pool_id != null ? Number(leader.pool_id) : 0;
    const pool = pid > 0 ? (poolMap[String(pid)] as Record<string, unknown> | undefined) : undefined;
    const poolDefaultAlbum = Number(pool?.album_size ?? 5);
    setEditAlbumSize(
      leader.album_size != null
        ? Number(leader.album_size)
        : Boolean(leader.pool_collective_random)
          ? 5
          : poolDefaultAlbum
    );
    setEditRandomize(
      leader.pool_randomize != null
        ? Boolean(leader.pool_randomize)
        : Boolean(leader.pool_collective_random) || !!pool?.randomize_queue
    );
    setEditPoolOnlyMode(leader.pool_only_mode != null ? Boolean(leader.pool_only_mode) : true);
    setEditMessageThreadId(
      leader.message_thread_id != null && leader.message_thread_id !== undefined
        ? Number(leader.message_thread_id)
        : null
    );
    setEditPoolId(poolSelectFromPost(leader));
    const cap = Array.isArray(cv) && cv.length >= 2 ? cv.length : 1;
    const { variants: avFromApi, order: ordFromApi } = parseAlbumVariantsFromPost(leader);
    setEditAlbumVariants(padAlbumVariants(avFromApi, cap));
    setEditAlbumOrderMode(ordFromApi);
    setEditButtons(parseButtonsFromPost(leader));
    setEditSendSilent(Boolean(leader.send_silent));
    setEditPinAfterSend(Boolean(leader.pin_after_send));
    setEditBufferMirror(Boolean(leader.buffer_mirror_enabled));
    setEditBufferPublishNow(Boolean(leader.buffer_publish_now));
    setEditLlmRewrite(Boolean(leader.caption_llm_rewrite_enabled));
    const lm = String(leader.caption_llm_rewrite_mode || "").toLowerCase();
    setEditLlmMode(lm === "random" || lm === "interval" ? lm : "interval");
    setEditLlmInterval(Math.max(1, Number(leader.caption_llm_rewrite_interval) || 3));
    setEditLlmProb(
      leader.caption_llm_rewrite_probability != null
        ? Number(leader.caption_llm_rewrite_probability)
        : 0.25
    );
    const bq = leader.buffer_x_queue;
    setEditBufferXQueue(
      Array.isArray(bq)
        ? bq
            .filter((x): x is Record<string, unknown> => x != null && typeof x === "object")
            .map((x) => ({
              text: String(x.text || ""),
              image_url: x.image_url ? String(x.image_url) : undefined,
            }))
        : []
    );
    setEditCheckoutStarsEnabled(Boolean(leader.checkout_stars_enabled));
    const cop = leader.checkout_stars_plan_id != null ? Number(leader.checkout_stars_plan_id) : 0;
    setEditCheckoutPlanId(Number.isFinite(cop) && cop > 0 ? cop : 0);
    setEditCheckoutButtonLabel(String(leader.checkout_button_label || ""));
    setEditCheckoutReferralCode(String(leader.checkout_referral_code || ""));
    setEditCampaignRandomChannel(Boolean(leader.campaign_random_channel));
    setEditUploadMsg(null);
    setEditScheduleError(null);
    setEditOpen(true);
  }

  async function saveEditor() {
    if (!editing) return;
    setEditScheduleError(null);
    const id = Number(editing.id);
    const trimmed = editVariations.map((s) => s.trim()).filter(Boolean);
    const capCount = Math.max(trimmed.length, 1);
    const av = padAlbumVariants(editAlbumVariants, capCount).map((v) => ({
      attachment_urls: v.attachment_urls.map((s) => s.trim()).filter(Boolean),
      media_ids: v.media_ids,
    }));
    const isCampaignEdit = Boolean(editing.campaign_group_id);
    const poolApi = poolSelectToApi(editPoolId);
    const body: Parameters<typeof api.scheduledPosts.update>[1] = {
      name: editName.trim() || undefined,
      content: trimmed[0] || "",
      channel_id: editChannelId || undefined,
      ...(isCampaignEdit ? {} : { message_thread_id: editMessageThreadId }),
      ...poolApi,
      media_ids: [],
      album_variants: av,
      album_order_mode: editAlbumOrderMode,
      pool_only_mode: poolSelectUsesPool(editPoolId) ? editPoolOnlyMode : false,
    };
    if (trimmed.length >= 2) {
      body.content_variations = trimmed;
      body.content = trimmed[0];
    } else {
      body.content_variations = [];
    }
    const oneTimeAlreadySent = !editing.interval_minutes && !!editing.sent_at;
    if (!oneTimeAlreadySent) {
      if (editScheduleRecurring) {
        body.interval_minutes = Math.max(1, editInterval);
        body.scheduled_at = null;
      } else {
        body.interval_minutes = null;
        if (editScheduledAt.trim()) {
          body.scheduled_at = datetimeLocalToIso(editScheduledAt);
        } else {
          setEditScheduleError("Set a date and time for one-time schedule, or enable recurring.");
          return;
        }
      }
    }
    if (poolSelectUsesPool(editPoolId)) {
      body.album_size = Math.min(10, Math.max(1, editAlbumSize));
      body.pool_randomize = editRandomize;
    } else {
      body.album_size = null;
      body.pool_randomize = null;
    }
    body.buttons = editButtons.some((b) => b.text.trim() && b.url.trim())
      ? editButtons.filter((b) => b.text.trim() && b.url.trim())
      : [];
    body.send_silent = editSendSilent;
    body.pin_after_send = editPinAfterSend;
    body.buffer_mirror_enabled = editBufferMirror;
    body.buffer_publish_now = editBufferMirror && editBufferPublishNow;
    body.caption_llm_rewrite_enabled = editLlmRewrite;
    body.caption_llm_rewrite_mode = editLlmRewrite && editLlmMode ? editLlmMode : null;
    body.caption_llm_rewrite_interval = editLlmRewrite && editLlmMode === "interval" ? editLlmInterval : null;
    body.caption_llm_rewrite_probability =
      editLlmRewrite && editLlmMode === "random" ? editLlmProb : null;
    body.buffer_x_queue = editBufferXQueue
      .map((x) => ({
        text: x.text.trim(),
        ...(x.image_url?.trim().startsWith("https://") ? { image_url: x.image_url.trim() } : {}),
      }))
      .filter((x) => x.text.length > 0);
    body.checkout_stars_enabled = editCheckoutStarsEnabled;
    body.checkout_stars_plan_id =
      editCheckoutStarsEnabled && editCheckoutPlanId > 0 ? editCheckoutPlanId : null;
    body.checkout_button_label = editCheckoutButtonLabel.trim() || null;
    body.checkout_referral_code = editCheckoutReferralCode.trim().toUpperCase() || null;
    if (editCheckoutStarsEnabled && (!editCheckoutPlanId || editCheckoutPlanId <= 0)) {
      setEditScheduleError("Stars checkout requires a Commerce product with a Stars price.");
      return;
    }
    if (isCampaignEdit) {
      body.campaign_random_channel = editCampaignRandomChannel;
    }
    await updateScheduled.mutateAsync({ id, body });
    setEditOpen(false);
    setEditing(null);
    setEditCampaignHint(null);
  }

  type DisplayRow =
    | { kind: "campaign"; campaign_group_id: string; posts: Array<Record<string, unknown>> }
    | { kind: "single"; post: Record<string, unknown> };

  const visiblePosts = useMemo(() => {
    let flat = compactRecurringOnly
      ? (scheduledPosts as Array<Record<string, unknown>>).filter((p) => !!p.interval_minutes)
      : (scheduledPosts as Array<Record<string, unknown>>);
    if (hideSentOneShots) flat = flat.filter((p) => !isSentOneShot(p));
    if (statusFilter !== "all") {
      flat = flat.filter((p) =>
        matchesStatusFilter(classifySchedulerPost(p, schedulingHealth, schedulerNowMs), statusFilter)
      );
    }
    return flat;
  }, [scheduledPosts, compactRecurringOnly, hideSentOneShots, statusFilter, schedulingHealth, schedulerNowMs]);

  const displayRows: DisplayRow[] = useMemo(() => {
    const byCg = new Map<string, Array<Record<string, unknown>>>();
    const singles: Array<Record<string, unknown>> = [];
    for (const p of visiblePosts) {
      const cg = p.campaign_group_id as string | null | undefined;
      if (cg && typeof cg === "string") {
        const arr = byCg.get(cg) ?? [];
        arr.push(p);
        byCg.set(cg, arr);
      } else {
        singles.push(p);
      }
    }
    const out: DisplayRow[] = [];
    for (const [cg, posts] of byCg.entries()) {
      const sorted = [...posts].sort((a, b) => Number(a.id) - Number(b.id));
      if (sorted.length > 1) {
        out.push({ kind: "campaign", campaign_group_id: cg, posts: sorted });
      } else if (sorted.length === 1) {
        out.push({ kind: "single", post: sorted[0] });
      }
    }
    for (const p of singles) {
      out.push({ kind: "single", post: p });
    }
    out.sort((a, b) => {
      const idA = a.kind === "campaign" ? Number(a.posts[0]?.id) : Number(a.post.id);
      const idB = b.kind === "campaign" ? Number(b.posts[0]?.id) : Number(b.post.id);
      return idA - idB;
    });
    return out;
  }, [visiblePosts]);

  const leanGroupedRows = useMemo(() => {
    if (listMode !== "lean") return null;
    const buckets = new Map<SchedulerGroupId, DisplayRow[]>();
    for (const gid of SCHEDULER_GROUP_ORDER) buckets.set(gid, []);
    for (const row of displayRows) {
      const p = row.kind === "campaign" ? row.posts[0] : row.post;
      const gid = inferSchedulerGroup(p.name, p.scheduler_category);
      buckets.get(gid)?.push(row);
    }
    return buckets;
  }, [displayRows, listMode]);

  const thCell = "text-left px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-slate-400 whitespace-nowrap";
  const tdCell = "px-2 py-1 text-[11px] leading-snug text-slate-300";
  const tdCellTop = "px-2 py-1 text-[11px] leading-snug text-slate-300 align-top";
  const btnSm =
    "px-1.5 py-0.5 rounded text-[10px] leading-tight font-medium whitespace-nowrap disabled:opacity-50";

  const renderDisplayRow = (row: DisplayRow) => {
    const p = row.kind === "campaign" ? row.posts[0] : row.post;
    const channelCell =
      row.kind === "campaign"
        ? row.posts.map((x) => String(x.channel_name || x.channel_id)).join(", ")
        : String(p.channel_name || p.channel_id);
    const rowKey = row.kind === "campaign" ? `campaign-${row.campaign_group_id}` : String(p.id);
    const recurring = !!p.interval_minutes;
    const lastPost = p.last_posted_at;
    const cvRow = p.content_variations;
    const rotating = Array.isArray(cvRow) && cvRow.length >= 2;
    const textPreview = String(p.content || "").slice(0, 40);
    const preview = rotating ? `${cvRow.length} captions (rotating)` : textPreview;
    const poolSelectId = poolSelectFromPost(p);
    const poolId = p.pool_id != null ? Number(p.pool_id) : 0;
    const poolRec = poolId > 0 ? poolMap[String(poolId)] : undefined;
    const poolName = poolSelectLabel(poolSelectId, poolRec ? String(poolRec?.name || poolId) : undefined);
    const poolApproved = poolRec != null ? Number(poolRec.approved_count ?? 0) : 0;
    const poolAlbumSize = poolRec != null ? Number(poolRec.album_size ?? 5) : 0;
    const poolLastRun = poolRec?.last_posted ? String(poolRec.last_posted) : "";
    const attUrls = Array.isArray(p.attachment_urls)
      ? (p.attachment_urls as string[]).filter((x) => String(x).trim())
      : [];
    const btnCount = parseButtonsFromPost(p).length;
    const bufferMirror = Boolean(p.buffer_mirror_enabled);
    const bufferPublishNow = Boolean(p.buffer_publish_now);
    const bufferQueueLen = Array.isArray(p.buffer_x_queue) ? p.buffer_x_queue.length : 0;
    const llmRewrite = Boolean(p.caption_llm_rewrite_enabled);
    const llmMode = String(p.caption_llm_rewrite_mode || "");
    const flags = [
      p.send_silent ? "silent" : null,
      p.pin_after_send ? "pin after" : null,
      btnCount ? `${btnCount} btn` : null,
    ].filter(Boolean);
    const hasAlbumOrPool = scheduledPostHasAlbumOrPool(p);

    return (
      <tr
        key={rowKey}
        className="border-t border-slate-700/60 hover:bg-slate-800/40 cursor-pointer"
        onClick={() => openEditor(p)}
        title="Click row to edit schedule, caption, and pool album options"
      >
        <td className={tdCell}>
          {String(p.name || "—")}
          {row.kind === "campaign" ? (
            <span className="ml-1 text-[10px] text-cyan-400/90">
              ({row.posts.length} ch
              {row.posts[0]?.campaign_random_channel ? " · random" : ""})
            </span>
          ) : null}
        </td>
        <td
          className={`${tdCell} max-w-[10rem]`}
          title={
            p.message_thread_id != null && p.message_thread_id !== undefined
              ? `${channelCell} · Topic #${p.message_thread_id}`
              : channelCell
          }
        >
          <div className="truncate text-slate-200">
            {channelCell}
            {p.message_thread_id != null && p.message_thread_id !== undefined ? (
              <span className="text-slate-500 font-normal"> · #{String(p.message_thread_id)}</span>
            ) : null}
          </div>
        </td>
        <td className={tdCellTop}>
          <div className="flex flex-col gap-0.5">
            <span className="text-slate-400 text-[10px]">Telegram</span>
            {bufferMirror ? (
              <span
                className="inline-flex w-fit items-center rounded px-1 py-px text-[10px] font-medium bg-sky-900/60 text-sky-300 border border-sky-700/50"
                title={
                  bufferQueueLen > 0
                    ? `${bufferQueueLen} TBCC-stored X caption(s); next Telegram send uses #1, then Buffer queue`
                    : "Mirrors Telegram caption to Buffer on each send"
                }
              >
                Buffer → X
                {bufferPublishNow ? " · instant" : " · buffer queue"}
                {bufferQueueLen > 0 ? ` · ${bufferQueueLen} TBCC` : bufferPublishNow ? "" : " · mirror TG"}
              </span>
            ) : (
              <span className="text-slate-600 text-xs">—</span>
            )}
            {llmRewrite ? (
              <span
                className="inline-flex w-fit items-center rounded px-1 py-px text-[10px] font-medium bg-violet-900/50 text-violet-300 border border-violet-700/50"
                title={
                  llmMode === "random"
                    ? "LLM may rephrase caption on random sends"
                    : `LLM rephrase every ${Number(p.caption_llm_rewrite_interval) || "?"} send(s)`
                }
              >
                LLM rewrite · {llmMode === "random" ? "random" : `every ${Number(p.caption_llm_rewrite_interval) || "?"}`}
              </span>
            ) : null}
          </div>
        </td>
        <td
          className={`${tdCell} max-w-[9rem] truncate text-slate-400`}
          title={rotating ? String(cvRow.join(" | ")).slice(0, 500) : String(p.content || "")}
        >
          {rotating ? preview : `${textPreview}${String(p.content || "").length > 40 ? "…" : ""}`}
        </td>
        <td className={`${tdCellTop} w-[6.5rem]`} onClick={(e) => e.stopPropagation()}>
          <SchedulerIntervalCountdown
            lastPostedAt={lastPost}
            intervalMinutes={p.interval_minutes}
            scheduledAt={p.scheduled_at}
            sentAt={p.sent_at}
            autoPausedAt={p.posting_auto_paused_at}
            scheduling={schedulingHealth ?? undefined}
            nowMs={schedulerNowMs}
          />
        </td>
        <td className={`${tdCellTop} max-w-[5.5rem] text-slate-400`} onClick={(e) => e.stopPropagation()}>
          {recurring ? (
            <span className="text-[10px] text-slate-400">
              Every {Number(p.interval_minutes)} min
              {lastPost ? (
                <span className="block text-slate-500 mt-0.5 truncate" title={formatUtcWithLocalHint(String(lastPost))}>
                  Last {formatPtForDashboard(String(lastPost))} PT
                </span>
              ) : (
                <span className="block text-amber-500/90 mt-0.5">Awaiting first post</span>
              )}
            </span>
          ) : p.scheduled_at ? (
            <span className="text-[10px]" title={formatUtcWithLocalHint(String(p.scheduled_at))}>
              {formatPtForDashboard(String(p.scheduled_at))} PT
            </span>
          ) : (
            "—"
          )}
        </td>
        <td
          className={`${tdCell} max-w-[8rem] border-l border-slate-700/50`}
          title={[
            poolSelectUsesPool(poolSelectId)
              ? poolSelectUsesSpecificPool(poolSelectId)
                ? `${poolName} · ${poolApproved}/${poolAlbumSize}`
                : poolName
              : poolName,
            poolLastRun && poolSelectUsesSpecificPool(poolSelectId)
              ? `Pool run ${formatUtcForDashboard(poolLastRun)}`
              : null,
            attUrls.length ? `${attUrls.length} promo` : null,
            flags.join(" · "),
          ]
            .filter(Boolean)
            .join(" · ")}
        >
          {poolSelectUsesPool(poolSelectId) ? (
            <span className="block min-w-0 truncate">
              <span className="text-slate-200">{poolName}</span>
              {poolSelectUsesSpecificPool(poolSelectId) ? (
                <span className={`tabular-nums ${poolApproved > 0 ? "text-cyan-400" : "text-slate-500"}`}>
                  {" "}
                  · {poolApproved}/{poolAlbumSize}
                </span>
              ) : null}
            </span>
          ) : (
            <span className="text-slate-600">—</span>
          )}
          {attUrls.length > 0 || flags.length > 0 ? (
            <span className="text-[10px] text-slate-500 block truncate">
              {[attUrls.length ? `${attUrls.length} promo` : null, ...flags].filter(Boolean).join(" · ")}
            </span>
          ) : null}
        </td>
        <td className={tdCell}>
          <SchedulerPostStatusCell
            post={p}
            scheduling={schedulingHealth}
            nowMs={schedulerNowMs}
            showTroubleDetail={statusFilter !== "all"}
          />
        </td>
        <td className={`${tdCell} flex flex-wrap gap-1`} onClick={(e) => e.stopPropagation()}>
          {(recurring || !p.sent_at) && (
            <button
              type="button"
              onClick={() => triggerScheduledPost.mutate({ id: Number(p.id) })}
              disabled={triggerScheduledPost.isPending}
              className={`${btnSm} bg-slate-600 text-slate-200 hover:bg-slate-500`}
              title={
                row.kind === "campaign"
                  ? row.posts[0]?.campaign_random_channel
                    ? "Queues one send to a random channel in this campaign"
                    : "Queues one Celery run for all channels in this campaign"
                  : undefined
              }
            >
              Post now
            </button>
          )}
          {hasAlbumOrPool && (
            <button
              type="button"
              onClick={() => triggerScheduledPost.mutate({ id: Number(p.id), reshuffle: true })}
              disabled={triggerScheduledPost.isPending}
              className={`${btnSm} bg-violet-800/90 text-violet-100 hover:bg-violet-700/90`}
              title={
                hasAlbumOrPool
                  ? row.kind === "campaign"
                    ? "Queue send with shuffled album/pool order (requires pool, promo URLs, or picked media)"
                    : "Randomize promo/media order for this send (requires pool, promo URLs, or picked media)"
                  : "Only available when job has a pool, promo URLs, or picked media"
              }
            >
              Repost shuffled
            </button>
          )}
          <button
            onClick={() => deleteScheduledPost.mutate(Number(p.id))}
            disabled={deleteScheduledPost.isPending}
            className={`${btnSm} bg-red-900/60 text-red-200/90 hover:bg-red-800/60`}
          >
            Delete
          </button>
        </td>
      </tr>
    );
  };

  return (
    <>
      {editOpen && editing && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
          role="dialog"
          aria-labelledby="scheduled-edit-title"
          onClick={(e) => {
            if (e.target === e.currentTarget) {
              setEditOpen(false);
              setEditCampaignHint(null);
            }
          }}
        >
          <div className="bg-slate-800 border border-slate-600 rounded-lg p-6 max-w-4xl w-full shadow-xl max-h-[90vh] overflow-y-auto">
            <h2 id="scheduled-edit-title" className="text-lg font-medium mb-3">
              Schedule editor
            </h2>
            {editCampaignHint && (
              <p className="text-amber-200/90 text-sm mb-2 border border-amber-700/50 rounded px-2 py-1.5 bg-amber-950/30">
                {editCampaignHint}. Saving updates every channel in this campaign (same schedule, caption, and pool
                options).
              </p>
            )}
            <p className="text-slate-500 text-xs mb-3">
              {editScheduleRecurring
                ? "Recurring — runs every N minutes. Use Trigger / Post now on the row to start the first cycle if last sent is empty. With 2+ captions, they rotate each run."
                : "One-time — posts once at the date/time below (if not already sent)."}
            </p>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-4">
              <div className="space-y-3 min-w-0">
                <input
                  type="text"
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200"
                  placeholder="Name (optional)"
                />
                {editCampaignHint ? (
                  <div className="space-y-2">
                    <p className="text-slate-400 text-sm">
                      Channels are fixed for this campaign. To change targets, delete the campaign and create a new one.
                    </p>
                    <label className="flex items-start gap-2 text-sm text-slate-300 cursor-pointer">
                      <input
                        type="checkbox"
                        className="mt-0.5"
                        checked={editCampaignRandomChannel}
                        onChange={(e) => setEditCampaignRandomChannel(e.target.checked)}
                      />
                      <span>
                        <strong className="text-amber-300">Random channel per interval</strong>
                        <span className="block text-xs text-slate-500 mt-0.5">
                          Each run posts to one randomly chosen channel in this campaign, not all at once.
                        </span>
                      </span>
                    </label>
                  </div>
                ) : (
                  <>
                    <select
                      value={editChannelId}
                      onChange={(e) => {
                        setEditChannelId(Number(e.target.value));
                        setEditMessageThreadId(null);
                      }}
                      className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200"
                    >
                      <option value={0}>Select channel</option>
                      {(channels as Array<{ id: number; name?: string; identifier?: string }>).map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.name || c.identifier || `#${c.id}`}
                        </option>
                      ))}
                    </select>
                    {editChannelId > 0 && (
                      <div>
                        <span className="text-slate-400 text-xs block mb-1">Forum topic (optional)</span>
                        <select
                          value={editMessageThreadId === null ? "" : String(editMessageThreadId)}
                          onChange={(e) => {
                            const v = e.target.value;
                            setEditMessageThreadId(v === "" ? null : Number(v));
                          }}
                          className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200 text-sm"
                        >
                          <option value="">Main chat (no topic)</option>
                          {editForumTopics.map((t) => (
                            <option key={t.id} value={String(t.id)}>
                              {t.title}
                            </option>
                          ))}
                        </select>
                        {editForumTopicsHint && (
                          <p className="text-amber-400/90 text-xs mt-1">{editForumTopicsHint}</p>
                        )}
                      </div>
                    )}
                  </>
                )}
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="block text-slate-400 text-sm">
                    Caption{editVariations.length > 1 ? "s (rotate in order)" : " / text"}
                  </span>
                  <TbccInsertLibraryToolbar />
                </div>
                <div className="space-y-2">
                  {editVariations.map((line, i) => (
                    <CaptionTelegramHtmlField
                      key={i}
                      value={line}
                      onChange={(v) => setEditVariations((prev) => prev.map((p, j) => (j === i ? v : p)))}
                      placeholder={i === 0 ? "Text content (caption)" : `Caption variation ${i + 1}`}
                      rows={i === 0 ? 5 : 4}
                      extraActions={
                        <>
                        <TbccInsertMenu
                          channels={channels as Array<Record<string, unknown>>}
                          pools={pools as Array<Record<string, unknown>>}
                          onInsert={(t) =>
                            setEditVariations((prev) => prev.map((p, j) => (j === i ? t : p)))
                          }
                        />
                        {editVariations.length > 1 && (
                          <button
                            type="button"
                            onClick={() => setEditVariations((prev) => prev.filter((_, j) => j !== i))}
                            className="px-2 py-1 text-red-400 hover:bg-red-900/30 rounded"
                          >
                            ✕
                          </button>
                        )}
                        </>
                      }
                    />
                  ))}
                  <button
                    type="button"
                    onClick={() => setEditVariations((prev) => [...prev, ""])}
                    className="text-sm text-cyan-400 hover:text-cyan-300"
                  >
                    + Add caption variation
                  </button>
                </div>
                {!editing.interval_minutes && editing.sent_at ? (
                  <p className="text-slate-500 text-sm border border-slate-600 rounded px-3 py-2 bg-slate-900/40">
                    This one-time post was already sent — schedule cannot be changed.
                  </p>
                ) : (
                  <div className="space-y-2 border border-slate-600/80 rounded-lg p-3 bg-slate-900/30">
                    <label className="flex items-center gap-2 text-sm text-slate-300 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={editScheduleRecurring}
                        onChange={(e) => {
                          const on = e.target.checked;
                          setEditScheduleRecurring(on);
                          setEditScheduleError(null);
                          if (!on && !editScheduledAt.trim()) {
                            setEditScheduledAt(isoToDatetimeLocal(new Date().toISOString()));
                          }
                        }}
                      />
                      Recurring (post at interval)
                    </label>
                    {editScheduleRecurring ? (
                      <div className="flex flex-wrap items-center gap-2 text-sm">
                        <span className="text-slate-400">Every</span>
                        <select
                          value={editInterval}
                          onChange={(e) => setEditInterval(Number(e.target.value))}
                          className="bg-slate-700 border border-slate-600 rounded px-2 py-1.5 text-slate-200"
                        >
                          {!EDIT_INTERVAL_OPTIONS.includes(editInterval) && editInterval > 0 ? (
                            <option value={editInterval}>
                              {editInterval} min (current)
                            </option>
                          ) : null}
                          {EDIT_INTERVAL_OPTIONS.map((m) => (
                            <option key={m} value={m}>
                              {m} min
                            </option>
                          ))}
                        </select>
                        <span className="text-slate-500 text-xs">Saves as interval job; clears one-time date.</span>
                      </div>
                    ) : (
                      <label className="block text-sm">
                        <span className="text-slate-400 block mb-1">Scheduled at (one-time)</span>
                        <input
                          type="datetime-local"
                          value={editScheduledAt}
                          onChange={(e) => {
                            setEditScheduledAt(e.target.value);
                            setEditScheduleError(null);
                          }}
                          className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200"
                        />
                      </label>
                    )}
                    {editScheduleError && (
                      <p className="text-amber-300 text-xs">{editScheduleError}</p>
                    )}
                  </div>
                )}
                <div>
                  <span className="text-slate-400 text-sm block mb-1">Inline buttons (https or tg://)</span>
                  {editButtons.map((b, i) => (
                    <div key={i} className="flex gap-2 mb-2">
                      <input
                        placeholder="Label"
                        value={b.text}
                        onChange={(e) =>
                          setEditButtons((prev) => prev.map((x, j) => (j === i ? { ...x, text: e.target.value } : x)))
                        }
                        className="flex-1 bg-slate-700 border border-slate-600 rounded px-2 py-1 text-slate-200 text-sm"
                      />
                      <input
                        placeholder="URL"
                        value={b.url}
                        onChange={(e) =>
                          setEditButtons((prev) => prev.map((x, j) => (j === i ? { ...x, url: e.target.value } : x)))
                        }
                        className="flex-1 bg-slate-700 border border-slate-600 rounded px-2 py-1 text-slate-200 text-sm"
                      />
                      <button
                        type="button"
                        onClick={() => setEditButtons((prev) => prev.filter((_, j) => j !== i))}
                        className="px-2 py-1 text-red-400 hover:bg-red-900/30 rounded"
                      >
                        ×
                      </button>
                    </div>
                  ))}
                  <button
                    type="button"
                    onClick={() => setEditButtons((prev) => [...prev, { text: "", url: "" }])}
                    className="text-sm text-cyan-400 hover:text-cyan-300"
                  >
                    + Add button
                  </button>
                </div>
                <div className="mt-3 pt-3 border-t border-slate-600/50 space-y-2">
                  <label className="flex items-center gap-2 text-sm text-slate-300 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={editCheckoutStarsEnabled}
                      onChange={(e) => {
                        setEditCheckoutStarsEnabled(e.target.checked);
                        if (!e.target.checked) setEditCheckoutPlanId(0);
                      }}
                    />
                    Stars checkout button (payment bot)
                  </label>
                  <p className="text-slate-500 text-xs pl-6">
                    Appends a button linking to your payment bot; the Telegram Stars invoice opens in private chat (same
                    as Commerce /subscribe).
                  </p>
                  {editCheckoutStarsEnabled && (
                    <div className="pl-6 space-y-2 border-l border-slate-600/80 ml-1">
                      <label className="block text-xs text-slate-400">
                        Commerce product
                        <select
                          value={editCheckoutPlanId || ""}
                          onChange={(e) => setEditCheckoutPlanId(Number(e.target.value) || 0)}
                          className="mt-1 w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200 text-sm"
                        >
                          <option value="">Select plan…</option>
                          {salablePlans.map((p) => (
                            <option key={String(p.id)} value={Number(p.id)}>
                              {String(p.name || `Plan ${p.id}`)} — {Number(p.price_stars || 0)}⭐ (
                              {String(p.product_type || "subscription")})
                            </option>
                          ))}
                        </select>
                      </label>
                      <label className="block text-xs text-slate-400">
                        Button label (optional)
                        <input
                          type="text"
                          value={editCheckoutButtonLabel}
                          onChange={(e) => setEditCheckoutButtonLabel(e.target.value)}
                          placeholder="Default: plan name + ⭐ price"
                          maxLength={64}
                          className="mt-1 w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200 text-sm"
                        />
                      </label>
                      <label className="block text-xs text-slate-400">
                        Referral code (optional)
                        <input
                          type="text"
                          value={editCheckoutReferralCode}
                          onChange={(e) =>
                            setEditCheckoutReferralCode(e.target.value.replace(/[^a-zA-Z0-9]/g, ""))
                          }
                          placeholder="1–16 letters or digits"
                          maxLength={16}
                          className="mt-1 w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200 text-sm"
                        />
                      </label>
                    </div>
                  )}
                </div>
                <div className="flex flex-col gap-2 pt-1 border-t border-slate-600/50">
                  <SilentTelegramSendOption checked={editSendSilent} onChange={setEditSendSilent} />
                  <label className="flex items-center gap-2 text-sm text-slate-300 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={editPinAfterSend}
                      onChange={(e) => setEditPinAfterSend(e.target.checked)}
                    />
                    Pin after send
                  </label>
                  <label className="flex items-center gap-2 text-sm text-slate-300 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={editBufferMirror}
                      onChange={(e) => {
                        setEditBufferMirror(e.target.checked);
                        if (!e.target.checked) setEditBufferPublishNow(false);
                      }}
                    />
                    <strong className="text-sky-300">Buffer → X</strong> after Telegram send (campaign: leader row only)
                  </label>
                  {editBufferMirror ? (
                    <label className="flex items-start gap-2 text-sm text-slate-300 cursor-pointer ml-4">
                      <input
                        type="checkbox"
                        className="mt-0.5"
                        checked={editBufferPublishNow}
                        onChange={(e) => setEditBufferPublishNow(e.target.checked)}
                      />
                      <span>
                        <strong className="text-emerald-300">Publish now</strong> (Buffer shareNow → X when Telegram sends)
                      </span>
                    </label>
                  ) : null}
                  {editBufferMirror ? (
                    <BufferXQueueEditor
                      items={editBufferXQueue}
                      onChange={setEditBufferXQueue}
                      disabled={updateScheduled.isPending}
                    />
                  ) : null}
                  <CaptionLlmRewriteFields
                    enabled={editLlmRewrite}
                    onEnabledChange={setEditLlmRewrite}
                    mode={editLlmMode}
                    onModeChange={setEditLlmMode}
                    interval={editLlmInterval}
                    onIntervalChange={setEditLlmInterval}
                    probability={editLlmProb}
                    onProbabilityChange={setEditLlmProb}
                    sendCount={
                      editing?.caption_llm_send_count != null
                        ? Number(editing.caption_llm_send_count)
                        : undefined
                    }
                    disabled={updateScheduled.isPending}
                  />
                </div>
              </div>
              <div className="space-y-2 min-w-0">
                <label className="block text-slate-400 text-xs mb-1">Album order (promo + picked media)</label>
                <select
                  value={editAlbumOrderMode}
                  onChange={(e) =>
                    setEditAlbumOrderMode(e.target.value as "static" | "shuffle" | "carousel")
                  }
                  className="w-full mb-3 bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200 text-sm"
                >
                  <option value="static">Static order</option>
                  <option value="shuffle">Shuffle each time</option>
                  <option value="carousel">Carousel (rotate order each post)</option>
                </select>
                <p className="text-slate-500 text-xs mb-3">
                  With multiple caption variations, add a matching album per caption (same rotation index). Shuffle
                  reorders on every send; carousel rotates the starting item each time.
                </p>
                <p className="text-slate-400 text-sm mb-2">
                  Media pool (optional) — thumbnails are from <strong>approved</strong> items. Choosing a pool filters the
                  grid. When a caption&apos;s album has no explicit picks, the job uses the next batch from this pool.
                </p>
                <MediaPoolSelect
                  value={editPoolId}
                  onChange={(next) => {
                    setEditPoolId(next);
                    setEditAlbumVariants((prev) => prev.map((v) => ({ ...v, media_ids: [] })));
                    const defs = poolAlbumDefaultsFromMap(next, poolMap);
                    setEditAlbumSize(defs.albumSize);
                    setEditRandomize(defs.randomize);
                  }}
                  pools={pools as Array<{ id: number; name?: string }>}
                  className="w-full mb-2 bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200 text-sm"
                />
                <p className="text-slate-500 text-xs mb-2">
                  Choose <strong>No pool</strong> for text-only recurring posts (links/buttons still work).
                </p>
                {poolSelectUsesPool(editPoolId) && (
                  <div className="border border-slate-600 rounded p-3 mb-2 space-y-2 bg-slate-900/40">
                    <p className="text-slate-400 text-xs leading-relaxed">
                      {poolSelectUsesSpecificPool(editPoolId) ? (
                        <>
                          <strong>Album settings</strong> — shared with the pool editor for{" "}
                          <strong>{String(poolMap[String(editPoolId)]?.name || `Pool ${editPoolId}`)}</strong>. Changing
                          size or randomize here updates the pool and every Scheduler job using it.
                        </>
                      ) : (
                        <>
                          <strong>Album settings</strong> for &quot;All pools (random)&quot; — apply to this job only
                          (no single pool to sync). Each send still picks one pool at random, then builds the album.
                        </>
                      )}
                    </p>
                    <div className="flex flex-wrap items-center gap-3">
                      <label className="flex items-center gap-2 text-sm text-slate-300">
                        <span className="text-slate-400">Album size</span>
                        <input
                          type="number"
                          min={1}
                          max={10}
                          value={editAlbumSize}
                          onChange={(e) =>
                            setEditAlbumSize(Math.min(10, Math.max(1, Number(e.target.value) || 5)))
                          }
                          className="w-16 bg-slate-700 border border-slate-600 rounded px-2 py-1 text-slate-200"
                        />
                      </label>
                      <label className="flex items-center gap-2 text-sm text-slate-300">
                        <input
                          type="checkbox"
                          checked={editRandomize}
                          onChange={(e) => setEditRandomize(e.target.checked)}
                        />
                        Randomize pool picks
                      </label>
                      <label className="flex items-center gap-2 text-sm text-slate-300">
                        <input
                          type="checkbox"
                          checked={editPoolOnlyMode}
                          onChange={(e) => setEditPoolOnlyMode(e.target.checked)}
                        />
                        Pool-only mode (ignore picked media/promos)
                      </label>
                    </div>
                  </div>
                )}
                <label className="flex flex-wrap items-center gap-2 text-slate-400 text-xs mb-2 cursor-pointer">
                  <span>Import into pool (Telegram Saved Messages — needs API session):</span>
                  <input
                    type="file"
                    accept="image/*,video/*"
                    multiple
                    disabled={uploadToPoolEdit.isPending}
                    title={
                      poolSelectUsesSpecificPool(editPoolId)
                        ? "Imports into the selected pool as pending — approve in Media Library"
                        : "Choose a specific pool in the dropdown above first (not “All pools (random)”)"
                    }
                    onChange={(e) => {
                      const pid = editPoolId;
                      const input = e.target as HTMLInputElement;
                      const snapshot = input.files?.length ? Array.from(input.files) : [];
                      input.value = "";
                      if (!snapshot.length) return;
                      if (!poolSelectUsesSpecificPool(pid)) {
                        setEditUploadMsg("Choose a specific pool above first — uploads need a target pool.");
                        setTimeout(() => setEditUploadMsg(null), 6000);
                        return;
                      }
                      uploadToPoolEdit.mutate({ files: snapshot, pid });
                    }}
                    className="text-slate-300 max-w-full"
                  />
                </label>
                {editUploadMsg && (
                  <pre className="text-xs text-slate-300 bg-slate-900/80 rounded p-2 mb-2 whitespace-pre-wrap max-h-24 overflow-y-auto">
                    {editUploadMsg}
                  </pre>
                )}
                {!poolSelectUsesSpecificPool(editPoolId) && (
                  <p className="text-amber-400/90 text-xs mb-2">
                    Select a specific pool above to enable import (pending in Media Library until approved).
                  </p>
                )}
                {editVariations.map((_, vi) => (
                  <div key={vi} className="mb-3 border border-slate-600/80 rounded-lg p-2 bg-slate-900/30">
                    <p className="text-slate-300 text-xs font-medium mb-2">
                      {editVariations.length > 1 ? `Album for caption ${vi + 1}` : "Promotional album"}
                    </p>
                    <SchedulePromoSlots
                      urls={editAlbumVariants[vi]?.attachment_urls ?? []}
                      setUrls={(fn) => {
                        setEditAlbumVariants((prev) => {
                          const next = [...prev];
                          while (next.length <= vi) next.push({ attachment_urls: [], media_ids: [] });
                          const cur = next[vi];
                          const urls =
                            typeof fn === "function"
                              ? fn(cur.attachment_urls)
                              : (fn as string[]);
                          next[vi] = { ...cur, attachment_urls: urls };
                          return next;
                        });
                      }}
                      idPrefix={`scheduled-edit-v${vi}`}
                    />
                    <div className="mt-2 min-w-0">
                      <ApprovedMediaPickerStrip
                        rows={editMedia as Array<Record<string, unknown>>}
                        selectedIds={editAlbumVariants[vi]?.media_ids ?? []}
                        onToggle={(id) => toggleVariantMedia(vi, id)}
                        rowKeyPrefix={`scheduled-edit-v${vi}`}
                      />
                    </div>
                  </div>
                ))}
                <p className="text-slate-500 text-xs mt-1">
                  {editAlbumVariants.reduce((n, v) => n + v.media_ids.length, 0)} media pick(s) across caption(s). If{" "}
                  <strong>pool</strong> is set
                  {poolSelectUsesPool(editPoolId) && editPoolOnlyMode
                    ? ", pool-only mode is ON and this job always uses pool batch."
                    : " and a caption has no picks, that run uses the pool batch."}
                </p>
              </div>
            </div>
            {updateScheduled.isError && (
              <p className="text-red-300 text-sm mb-2">{(updateScheduled.error as Error)?.message}</p>
            )}
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => {
                  setEditOpen(false);
                  setEditCampaignHint(null);
                }}
                className="px-3 py-2 rounded bg-slate-600 text-slate-200 hover:bg-slate-500"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => void saveEditor()}
                disabled={updateScheduled.isPending || !editChannelId}
                className="px-3 py-2 rounded bg-cyan-600 text-white hover:bg-cyan-500 disabled:opacity-50"
              >
                {updateScheduled.isPending ? "Saving…" : "Save"}
              </button>
            </div>
          </div>
        </div>
      )}

      {triggerNotice && (
        <div
          className={`mb-2 px-2 py-1 rounded text-[11px] ${
            triggerNotice.kind === "ok" ? "bg-emerald-900/40 text-emerald-200" : "bg-red-900/40 text-red-200"
          }`}
        >
          {triggerNotice.text}
        </div>
      )}

      {!compactRecurringOnly && (
        <SchedulerOverviewBand
          pools={pools as Array<Record<string, unknown>>}
          scheduledPosts={scheduledPosts as Array<Record<string, unknown>>}
          poolMap={poolMap}
          weekPosts={weekPosts}
          onWeekDayClick={onWeekDayClick}
        />
      )}

      {!compactRecurringOnly ? (
        <SchedulerTransportBar
          stats={transportStats}
          scheduling={schedulingHealth}
          statusFilter={statusFilter}
          onStatusFilterChange={setStatusFilter}
        />
      ) : null}

      {!compactRecurringOnly ? (
        <div className="mb-2 flex flex-wrap items-center gap-3 text-[11px]">
          <span className="text-slate-500 uppercase tracking-wide text-[10px] font-semibold">View</span>
          <div className="inline-flex rounded border border-slate-600 overflow-hidden">
            <button
              type="button"
              className={`px-2.5 py-1 ${listMode === "lean" ? "bg-cyan-900/50 text-cyan-200" : "bg-slate-800 text-slate-400 hover:bg-slate-700"}`}
              onClick={() => setListMode("lean")}
            >
              Lean
            </button>
            <button
              type="button"
              className={`px-2.5 py-1 border-l border-slate-600 ${listMode === "details" ? "bg-cyan-900/50 text-cyan-200" : "bg-slate-800 text-slate-400 hover:bg-slate-700"}`}
              onClick={() => setListMode("details")}
            >
              Details
            </button>
          </div>
          <label className="inline-flex items-center gap-1.5 text-slate-400 cursor-pointer">
            <input
              type="checkbox"
              className="rounded border-slate-500"
              checked={hideSentOneShots}
              onChange={(e) => setHideSentOneShots(e.target.checked)}
            />
            Hide sent one-shots
          </label>
        </div>
      ) : null}

      <div className="tbcc-panel overflow-x-auto rounded-lg border border-slate-600/90">
        <table className="w-full text-[11px] border-collapse">
          <thead>
            <tr className="bg-slate-700/95 border-b border-slate-600">
              <th className={thCell}>Name</th>
              <th className={thCell}>Channel</th>
              <th className={`${thCell} min-w-[6.5rem]`}>Destinations</th>
              <th className={thCell}>Content</th>
              <th className={`${thCell} w-[6.5rem]`}>Timer</th>
              <th className={`${thCell} min-w-[5.5rem]`}>Schedule</th>
              <th className={`${thCell} min-w-[7rem] border-l border-slate-600/50`}>Pool</th>
              <th className={thCell}>Status</th>
              <th className={`${thCell} min-w-[7.5rem]`}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {listMode === "lean" && leanGroupedRows && !compactRecurringOnly
              ? SCHEDULER_GROUP_ORDER.flatMap((gid) => {
                  const rows = leanGroupedRows.get(gid) ?? [];
                  if (!rows.length) return [];
                  const postsInGroup = rows.flatMap((r) => (r.kind === "campaign" ? r.posts : [r.post]));
                  return [
                    <SchedulerGroupSection
                      key={gid}
                      title={SCHEDULER_GROUP_LABELS[gid]}
                      posts={postsInGroup}
                      defaultExpanded={SCHEDULER_GROUP_DEFAULT_EXPANDED[gid]}
                      scheduling={schedulingHealth}
                      nowMs={schedulerNowMs}
                    >
                      {rows.map((row) => renderDisplayRow(row))}
                    </SchedulerGroupSection>,
                  ];
                })
              : displayRows.map((row) => renderDisplayRow(row))}
            {displayRows.length === 0 && (
              <tr>
                <td colSpan={SCHED_COLS} className="px-2 py-3 text-[11px] text-slate-500 text-center">
                  {compactRecurringOnly
                    ? "No recurring posting jobs."
                    : statusFilter !== "all"
                      ? "No jobs match this filter."
                      : "No scheduled posts."}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}