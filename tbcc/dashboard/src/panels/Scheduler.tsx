import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import { useState, useEffect } from "react";
import { ScheduledPostsList } from "../components/ScheduledPostsList";
import { SchedulePromoSlots } from "../components/SchedulePromoSlots";
import { ApprovedMediaPickerStrip } from "../components/ApprovedMediaPickerStrip";
import { CaptionTelegramHtmlField } from "../components/CaptionTelegramHtmlField";
import { TbccInsertMenu } from "../components/TbccInsertMenu";
import { TbccInsertLibraryToolbar } from "../components/TbccInsertLibraryToolbar";
import { InfoDisclosure } from "../components/InfoDisclosure";
import { SchedulerGrowthHub } from "../components/SchedulerGrowthHub";
import { SchedulerBufferPanel } from "../components/SchedulerBufferPanel";
import { SchedulerComposerCard } from "../components/SchedulerComposerCard";
import { CaptionLlmRewriteFields } from "../components/CaptionLlmRewriteFields";
import { MediaPoolSelect } from "../components/MediaPoolSelect";
import {
  poolSelectToApi,
  poolSelectUsesPool,
  poolSelectUsesSpecificPool,
  poolAlbumDefaultsFromMap,
} from "../utils/mediaPoolSelect";
import {
  SilentTelegramSendOption,
  readSendSilentPreference,
  writeSendSilentPreference,
} from "../components/SilentTelegramSendOption";

const INTERVAL_OPTIONS = [15, 30, 60, 120, 180, 240, 360, 720];
/** Fixed-height composer tiles (matches overview band density). */
const COMPOSER_TILE_H = "h-[8.25rem]";
const COMPOSER_BODY_H = "h-full space-y-1.5";
/** Tall post-body column for readable captions (left pane in bottom row). */
const POST_BODY_PANEL_H = "min-h-[22rem] xl:min-h-[26rem]";
const POST_BODY_EDITOR_H = "min-h-[14rem] flex-1";
type ComposerDetailTab = "caption" | "buttons" | "delivery";

type AlbumVariant = { attachment_urls: string[]; media_ids: number[] };

function padAlbumVariants(v: AlbumVariant[], n: number): AlbumVariant[] {
  const out = [...v];
  while (out.length < n) out.push({ attachment_urls: [], media_ids: [] });
  return out.slice(0, n);
}

export function Scheduler({ embedded = false }: { embedded?: boolean }) {
  const queryClient = useQueryClient();
  const [calendarScheduleModalOpen, setCalendarScheduleModalOpen] = useState(false);
  const [name, setName] = useState("");
  /** Multi-select: same job posts to every checked channel (one shared recurring / one-time schedule). */
  const [selectedChannelIds, setSelectedChannelIds] = useState<number[]>([]);
  /** Multi-channel: each interval posts to one random checked channel instead of all. */
  const [campaignRandomChannel, setCampaignRandomChannel] = useState(false);
  /** One box = single caption; 2+ non-empty = rotate in order each time the job runs */
  const [captionVariations, setCaptionVariations] = useState<string[]>([""]);
  const [scheduledAt, setScheduledAt] = useState("");
  const [isRecurring, setIsRecurring] = useState(false);
  const [intervalMinutes, setIntervalMinutes] = useState(30);
  const [poolId, setPoolId] = useState<number>(0);
  const [scheduleAlbumSize, setScheduleAlbumSize] = useState(5);
  const [schedulePoolRandomize, setSchedulePoolRandomize] = useState(false);
  const [schedulePoolOnlyMode, setSchedulePoolOnlyMode] = useState(true);
  const [buttons, setButtons] = useState<Array<{ text: string; url: string }>>([]);
  const [uploadMsg, setUploadMsg] = useState<string | null>(null);
  /** null = post to main chat; number = Telegram forum topic id (message_thread_id) */
  const [messageThreadId, setMessageThreadId] = useState<number | null>(null);
  /** One album per caption variation */
  const [scheduleAlbumVariants, setScheduleAlbumVariants] = useState<AlbumVariant[]>([
    { attachment_urls: [], media_ids: [] },
  ]);
  const [scheduleAlbumOrderMode, setScheduleAlbumOrderMode] = useState<"static" | "shuffle" | "carousel">("static");
  const [scheduleSendSilent, setScheduleSendSilent] = useState(readSendSilentPreference);
  const [schedulePinAfterSend, setSchedulePinAfterSend] = useState(false);
  const [scheduleBufferMirror, setScheduleBufferMirror] = useState(false);
  const [scheduleBufferPublishNow, setScheduleBufferPublishNow] = useState(false);
  const [scheduleLlmRewrite, setScheduleLlmRewrite] = useState(false);
  const [scheduleLlmMode, setScheduleLlmMode] = useState<"" | "random" | "interval">("interval");
  const [scheduleLlmInterval, setScheduleLlmInterval] = useState(3);
  const [scheduleLlmProb, setScheduleLlmProb] = useState(0.25);
  const [scheduleCheckoutStars, setScheduleCheckoutStars] = useState(false);
  const [scheduleCheckoutPlanId, setScheduleCheckoutPlanId] = useState(0);
  const [scheduleCheckoutButtonLabel, setScheduleCheckoutButtonLabel] = useState("");
  const [scheduleCheckoutReferralCode, setScheduleCheckoutReferralCode] = useState("");
  const [pinToolChannelId, setPinToolChannelId] = useState(0);
  const [pinToolMessageId, setPinToolMessageId] = useState("");
  const [pinToolUnpin, setPinToolUnpin] = useState(false);
  const [pinToolMsg, setPinToolMsg] = useState<string | null>(null);
  const [composerDetailTab, setComposerDetailTab] = useState<ComposerDetailTab>("caption");

  const { data: pools = [] } = useQuery({
    queryKey: ["pools"],
    queryFn: () => api.pools.list(),
  });
  const { data: channels = [] } = useQuery({
    queryKey: ["channels"],
    queryFn: () => api.channels.list(),
  });
  const forumTopicSourceId = selectedChannelIds.length === 1 ? selectedChannelIds[0] : 0;
  const { data: forumTopicsRes } = useQuery({
    queryKey: ["forumTopics", forumTopicSourceId],
    queryFn: () => api.channels.forumTopics(forumTopicSourceId),
    enabled: forumTopicSourceId > 0,
  });
  const forumTopics = forumTopicsRes?.topics ?? [];
  const forumTopicsHint = forumTopicsRes?.error;
  const { data: media = [] } = useQuery({
    queryKey: ["media", "approved", poolId],
    queryFn: () =>
      poolSelectUsesSpecificPool(poolId)
        ? api.media.list({ status: "approved", pool_id: poolId })
        : api.media.list("approved"),
  });
  const { data: scheduledPostsForWeek = [] } = useQuery({
    queryKey: ["scheduledPosts"],
    queryFn: () => api.scheduledPosts.list(),
  });
  const { data: subscriptionPlansRaw = [] } = useQuery({
    queryKey: ["subscriptionPlans"],
    queryFn: () => api.subscriptionPlans.list(),
  });
  const salablePlans = (subscriptionPlansRaw as Array<Record<string, unknown>>).filter(
    (p) => p.is_active !== false && Number(p.price_stars || 0) > 0
  );
  const poolMap = Object.fromEntries(
    (pools as Array<Record<string, unknown>>).map((p) => [String(p.id), p])
  );
  useEffect(() => {
    setScheduleAlbumVariants((prev) => padAlbumVariants(prev, captionVariations.length));
  }, [captionVariations.length]);

  const uploadToPool = useMutation({
    mutationFn: async ({ files, pid }: { files: File[]; pid: number }) => {
      const out: string[] = [];
      for (let i = 0; i < files.length; i++) {
        const f = files[i];
        const r = await api.import.bytes(f, pid, "dashboard:scheduler");
        if (r.error) out.push(`${f.name}: ${r.error}`);
        else if (r.status === "imported") out.push(`${f.name}: imported`);
        else out.push(`${f.name}: ${String(r.status || "skipped")}`);
      }
      return out.join("\n");
    },
    onSuccess: (msg) => {
      setUploadMsg(msg);
      queryClient.invalidateQueries({ queryKey: ["media"] });
      setTimeout(() => setUploadMsg(null), 8000);
    },
    onError: (e: Error) => setUploadMsg(e.message),
  });

  const createScheduledPost = useMutation({
    mutationFn: () => {
      const raw = scheduledAt || new Date().toISOString().slice(0, 16);
      const scheduledAtIso = raw.length <= 16 ? `${raw}:00` : raw;
      const trimmed = captionVariations.map((s) => s.trim()).filter(Boolean);
      const capCount = Math.max(trimmed.length, 1);
      const av = padAlbumVariants(scheduleAlbumVariants, capCount).map((v) => ({
        attachment_urls: v.attachment_urls.map((s) => s.trim()).filter(Boolean),
        media_ids: v.media_ids,
      }));
      const chIds = [...new Set(selectedChannelIds.filter((x) => x > 0))].sort((a, b) => a - b);
      if (chIds.length === 0) throw new Error("Select at least one channel");
      const poolApi = poolSelectToApi(poolId);
      const base: Parameters<typeof api.scheduledPosts.create>[0] = {
        name: name || undefined,
        channel_ids: chIds,
        ...(messageThreadId != null ? { message_thread_id: messageThreadId } : {}),
        content: trimmed[0] || "",
        media_ids: [],
        album_variants: av,
        album_order_mode: scheduleAlbumOrderMode,
        ...poolApi,
        buttons: buttons.some((b) => b.text.trim() && b.url.trim()) ? buttons.filter((b) => b.text.trim() && b.url.trim()) : undefined,
        scheduled_at: isRecurring ? undefined : scheduledAtIso,
        interval_minutes: isRecurring ? intervalMinutes : undefined,
        ...(poolSelectUsesPool(poolId)
          ? {
              album_size: Math.min(10, Math.max(1, scheduleAlbumSize)),
              pool_randomize: schedulePoolRandomize,
              pool_only_mode: schedulePoolOnlyMode,
            }
          : {}),
        send_silent: scheduleSendSilent,
        pin_after_send: schedulePinAfterSend,
        buffer_mirror_enabled: scheduleBufferMirror,
        buffer_publish_now: scheduleBufferMirror && scheduleBufferPublishNow,
        caption_llm_rewrite_enabled: scheduleLlmRewrite,
        caption_llm_rewrite_mode: scheduleLlmRewrite && scheduleLlmMode ? scheduleLlmMode : null,
        caption_llm_rewrite_interval:
          scheduleLlmRewrite && scheduleLlmMode === "interval" ? scheduleLlmInterval : null,
        caption_llm_rewrite_probability:
          scheduleLlmRewrite && scheduleLlmMode === "random" ? scheduleLlmProb : null,
        checkout_stars_enabled: scheduleCheckoutStars,
        checkout_stars_plan_id:
          scheduleCheckoutStars && scheduleCheckoutPlanId > 0 ? scheduleCheckoutPlanId : null,
        checkout_button_label: scheduleCheckoutButtonLabel.trim() || null,
        checkout_referral_code: scheduleCheckoutReferralCode.trim().toUpperCase() || null,
        ...(chIds.length > 1 ? { campaign_random_channel: campaignRandomChannel } : {}),
      };
      if (trimmed.length >= 2) {
        base.content_variations = trimmed;
        base.content = trimmed[0];
      }
      return api.scheduledPosts.create(base);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["scheduledPosts"] });
      queryClient.invalidateQueries({ queryKey: ["pools"] });
      setName("");
      setSelectedChannelIds([]);
      setMessageThreadId(null);
      setCaptionVariations([""]);
      setScheduledAt("");
      setPoolId(0);
      setScheduleAlbumSize(5);
      setSchedulePoolRandomize(false);
      setSchedulePoolOnlyMode(true);
      setButtons([]);
      setScheduleAlbumVariants([{ attachment_urls: [], media_ids: [] }]);
      setScheduleAlbumOrderMode("static");
      setScheduleSendSilent(false);
      setSchedulePinAfterSend(false);
      setScheduleBufferMirror(false);
      setScheduleBufferPublishNow(false);
      setScheduleLlmRewrite(false);
      setScheduleLlmMode("interval");
      setScheduleLlmInterval(3);
      setScheduleLlmProb(0.25);
      setScheduleCheckoutStars(false);
      setScheduleCheckoutPlanId(0);
      setScheduleCheckoutButtonLabel("");
      setScheduleCheckoutReferralCode("");
      setCalendarScheduleModalOpen(false);
    },
  });

  const pinToolMutation = useMutation({
    mutationFn: async () => {
      const mid = parseInt(pinToolMessageId.trim(), 10);
      if (!pinToolChannelId || !Number.isFinite(mid) || mid <= 0) {
        throw new Error("Select a channel and enter a valid Telegram message id.");
      }
      return api.channels.pinMessage(pinToolChannelId, { message_id: mid, unpin: pinToolUnpin });
    },
    onSuccess: () => {
      setPinToolMsg(pinToolUnpin ? "Unpin request sent." : "Pin request sent.");
      setTimeout(() => setPinToolMsg(null), 6000);
    },
    onError: (e: Error) => setPinToolMsg(e.message),
  });

  function toggleScheduleVariantMedia(variantIdx: number, id: number) {
    setScheduleAlbumVariants((prev) => {
      const next = [...prev];
      while (next.length <= variantIdx) next.push({ attachment_urls: [], media_ids: [] });
      const cur = next[variantIdx];
      const mids = cur.media_ids.includes(id) ? cur.media_ids.filter((x) => x !== id) : [...cur.media_ids, id];
      next[variantIdx] = { ...cur, media_ids: mids };
      return next;
    });
  }

  const addButton = () => setButtons((prev) => [...prev, { text: "", url: "" }]);
  const updateButton = (i: number, field: "text" | "url", val: string) => {
    setButtons((prev) => prev.map((b, j) => (j === i ? { ...b, [field]: val } : b)));
  };
  const removeButton = (i: number) => setButtons((prev) => prev.filter((_, j) => j !== i));

  const openScheduleForCalendarDay = (iso: string) => {
    setScheduledAt(`${iso}T12:00`);
    setIsRecurring(false);
    setCalendarScheduleModalOpen(true);
  };

  useEffect(() => {
    if (!calendarScheduleModalOpen) return;
    const k = (e: KeyboardEvent) => {
      if (e.key === "Escape") setCalendarScheduleModalOpen(false);
    };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [calendarScheduleModalOpen]);

  const inputSm =
    "w-full bg-slate-700 border border-slate-600 rounded px-2 py-1.5 text-slate-200 text-sm";

  const renderAddScheduledPostForm = () => (
    <>
        {createScheduledPost.isError && (
          <div className="mb-2 px-2 py-1.5 rounded bg-red-900/50 text-red-200 text-xs">
            {createScheduledPost.error?.message}
          </div>
        )}

        <div className="mb-2 grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-4 xl:items-stretch">
          <SchedulerComposerCard title="Destinations" className={COMPOSER_TILE_H} bodyClassName={COMPOSER_BODY_H}>
            <input
              type="text"
              placeholder="Name (optional)"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className={inputSm}
            />
            <div className="rounded border border-slate-600/80 bg-slate-950/30 p-1.5">
              <div className="mb-1 flex flex-wrap items-center justify-between gap-1">
                <span className="text-[11px] text-slate-400">
                  Channels{campaignRandomChannel ? " · random/run" : " · all selected"}
                </span>
                <div className="flex gap-2">
                  <button
                    type="button"
                    className="text-xs text-cyan-400 hover:text-cyan-300"
                    onClick={() =>
                      setSelectedChannelIds(
                        (channels as Array<{ id: number }>).map((c) => c.id).sort((a, b) => a - b)
                      )
                    }
                  >
                    All
                  </button>
                  <button
                    type="button"
                    className="text-xs text-slate-500 hover:text-slate-300"
                    onClick={() => setSelectedChannelIds([])}
                  >
                    Clear
                  </button>
                </div>
              </div>
              <div className="flex max-h-[3.25rem] flex-col gap-1 overflow-y-auto">
                {(channels as Array<{ id: number; name?: string; identifier?: string }>).map((c) => (
                  <label key={c.id} className="flex cursor-pointer items-center gap-1.5 text-[11px] text-slate-300">
                    <input
                      type="checkbox"
                      checked={selectedChannelIds.includes(c.id)}
                      onChange={() => {
                        setSelectedChannelIds((prev) =>
                          prev.includes(c.id)
                            ? prev.filter((x) => x !== c.id)
                            : [...prev, c.id].sort((a, b) => a - b)
                        );
                        setMessageThreadId(null);
                      }}
                    />
                    {c.name || c.identifier || `#${c.id}`}
                  </label>
                ))}
              </div>
              {selectedChannelIds.length > 1 ? (
                <label className="mt-1.5 flex cursor-pointer items-start gap-1.5 border-t border-slate-700/80 pt-1.5 text-[11px] text-slate-300">
                  <input
                    type="checkbox"
                    className="mt-0.5"
                    checked={campaignRandomChannel}
                    onChange={(e) => setCampaignRandomChannel(e.target.checked)}
                  />
                  <span>
                    <strong className="text-amber-300">Random channel / run</strong>
                    <span className="mt-0.5 block text-[10px] text-slate-500">One channel per interval, not all at once.</span>
                  </span>
                </label>
              ) : null}
            </div>
            {selectedChannelIds.length > 1 ? (
              <p className="text-[10px] text-slate-500">Forum topic: pick one channel first.</p>
            ) : null}
            {forumTopicSourceId > 0 && (
              <div>
                <span className="mb-0.5 block text-[10px] text-slate-500">Forum topic</span>
                <select
                  value={messageThreadId === null ? "" : String(messageThreadId)}
                  onChange={(e) => {
                    const v = e.target.value;
                    setMessageThreadId(v === "" ? null : Number(v));
                  }}
                  className={inputSm}
                >
                  <option value="">Main chat</option>
                  {forumTopics.map((t) => (
                    <option key={t.id} value={String(t.id)}>
                      {t.title}
                    </option>
                  ))}
                </select>
                {forumTopicsHint ? <p className="mt-0.5 text-[10px] text-amber-400/90">{forumTopicsHint}</p> : null}
              </div>
            )}
            <label className="flex items-center gap-1.5 text-[11px] text-slate-300">
              <input
                type="checkbox"
                checked={isRecurring}
                onChange={(e) => setIsRecurring(e.target.checked)}
              />
              Recurring
            </label>
            {isRecurring ? (
              <div className="flex items-center gap-1.5 text-[11px]">
                <span className="text-slate-500">Every</span>
                <select
                  value={intervalMinutes}
                  onChange={(e) => setIntervalMinutes(Number(e.target.value))}
                  className="rounded border border-slate-600 bg-slate-700 px-2 py-1 text-slate-200"
                >
                  {INTERVAL_OPTIONS.map((m) => (
                    <option key={m} value={m}>
                      {m} min
                    </option>
                  ))}
                </select>
              </div>
            ) : (
              <input
                type="datetime-local"
                value={scheduledAt}
                onChange={(e) => setScheduledAt(e.target.value)}
                className={inputSm}
              />
            )}
          </SchedulerComposerCard>

          <SchedulerComposerCard title="Social · Buffer" className={COMPOSER_TILE_H} bodyClassName={COMPOSER_BODY_H}>
            <label className="flex cursor-pointer items-start gap-1.5 text-[11px] text-slate-300">
              <input
                type="checkbox"
                className="mt-0.5"
                checked={scheduleBufferMirror}
                onChange={(e) => {
                  setScheduleBufferMirror(e.target.checked);
                  if (!e.target.checked) setScheduleBufferPublishNow(false);
                }}
              />
              <span>
                <strong className="text-sky-300">Buffer → X</strong> after Telegram send
                <span className="mt-0.5 block text-[10px] text-slate-500">Needs https promo URLs for images.</span>
              </span>
            </label>
            {scheduleBufferMirror ? (
              <label className="ml-4 flex cursor-pointer items-start gap-1.5 text-[11px] text-slate-300">
                <input
                  type="checkbox"
                  className="mt-0.5"
                  checked={scheduleBufferPublishNow}
                  onChange={(e) => setScheduleBufferPublishNow(e.target.checked)}
                />
                <span>
                  <strong className="text-emerald-300">Publish now</strong> (shareNow)
                  <span className="mt-0.5 block text-[10px] text-slate-500">Off = Buffer queue.</span>
                </span>
              </label>
            ) : null}
            <SchedulerBufferPanel compact />
          </SchedulerComposerCard>

          <SchedulerComposerCard title="Album & media" className={COMPOSER_TILE_H} bodyClassName={`${COMPOSER_BODY_H} text-[11px]`}>
            <div className="flex flex-wrap items-center gap-1">
              <span className="text-slate-500">Order</span>
              <select
                value={scheduleAlbumOrderMode}
                onChange={(e) =>
                  setScheduleAlbumOrderMode(e.target.value as "static" | "shuffle" | "carousel")
                }
                className="min-w-0 flex-1 rounded border border-slate-600 bg-slate-700 px-1.5 py-1 text-slate-200"
              >
                <option value="static">Static</option>
                <option value="shuffle">Shuffle</option>
                <option value="carousel">Carousel</option>
              </select>
              <InfoDisclosure>
                One album per caption. Shuffle/carousel apply to promo + library picks for that caption.
              </InfoDisclosure>
            </div>
            <MediaPoolSelect
              value={poolId}
              onChange={(next) => {
                setPoolId(next);
                setScheduleAlbumVariants((prev) => prev.map((v) => ({ ...v, media_ids: [] })));
                const defs = poolAlbumDefaultsFromMap(next, poolMap);
                setScheduleAlbumSize(defs.albumSize);
                setSchedulePoolRandomize(defs.randomize);
              }}
              pools={pools as Array<{ id: number; name?: string }>}
              className={inputSm}
              variant="compact"
            />
            {poolSelectUsesPool(poolId) ? (
              <div className="space-y-1 rounded border border-slate-600/60 bg-slate-950/40 p-1.5">
                <p className="text-[10px] text-slate-500 leading-snug">
                  {poolSelectUsesSpecificPool(poolId)
                    ? "Album size & randomize sync with the pool editor."
                    : "All pools (random): settings apply to this job only."}
                </p>
                <div className="flex flex-wrap items-center gap-2">
                  <label className="flex items-center gap-1 text-slate-300">
                    <span className="text-slate-500">Size</span>
                    <input
                      type="number"
                      min={1}
                      max={10}
                      value={scheduleAlbumSize}
                      onChange={(e) => setScheduleAlbumSize(Math.min(10, Math.max(1, Number(e.target.value) || 5)))}
                      className="w-10 rounded border border-slate-600 bg-slate-700 px-1 py-0.5 text-slate-200"
                    />
                  </label>
                  <label className="flex items-center gap-1 text-slate-300">
                    <input
                      type="checkbox"
                      checked={schedulePoolRandomize}
                      onChange={(e) => setSchedulePoolRandomize(e.target.checked)}
                    />
                    Random
                  </label>
                  <label className="flex items-center gap-1 text-slate-300">
                    <input
                      type="checkbox"
                      checked={schedulePoolOnlyMode}
                      onChange={(e) => setSchedulePoolOnlyMode(e.target.checked)}
                    />
                    Pool-only
                  </label>
                </div>
              </div>
            ) : null}
            <label className="flex cursor-pointer flex-wrap items-center gap-1 text-[10px] text-slate-500">
              <span>Import to pool:</span>
              <input
                type="file"
                accept="image/*,video/*"
                multiple
                disabled={!poolSelectUsesSpecificPool(poolId) || uploadToPool.isPending}
                onChange={(e) => {
                  const pid = poolId;
                  const input = e.target as HTMLInputElement;
                  const snapshot = input.files?.length ? Array.from(input.files) : [];
                  input.value = "";
                  if (!poolSelectUsesSpecificPool(pid) || !snapshot.length) return;
                  uploadToPool.mutate({ files: snapshot, pid });
                }}
                className="max-w-full text-slate-400"
              />
            </label>
            {uploadMsg ? (
              <pre className="max-h-16 overflow-y-auto whitespace-pre-wrap rounded bg-slate-950/80 p-1 text-[10px] text-slate-400">
                {uploadMsg}
              </pre>
            ) : null}
            {captionVariations.map((_, vi) => (
              <div key={vi} className="rounded border border-slate-600/70 bg-slate-950/30 p-1.5">
                <p className="mb-1 text-[10px] font-medium text-slate-400">
                  {captionVariations.length > 1 ? `Album · cap ${vi + 1}` : "Promo + picks"}
                </p>
                <SchedulePromoSlots
                  urls={scheduleAlbumVariants[vi]?.attachment_urls ?? []}
                  setUrls={(fn) => {
                    setScheduleAlbumVariants((prev) => {
                      const next = [...prev];
                      while (next.length <= vi) next.push({ attachment_urls: [], media_ids: [] });
                      const cur = next[vi];
                      const urls =
                        typeof fn === "function" ? fn(cur.attachment_urls) : (fn as string[]);
                      next[vi] = { ...cur, attachment_urls: urls };
                      return next;
                    });
                  }}
                  idPrefix={`scheduler-create-v${vi}`}
                />
                <div className="mt-1 min-w-0">
                  <ApprovedMediaPickerStrip
                    rows={media as Array<Record<string, unknown>>}
                    selectedIds={scheduleAlbumVariants[vi]?.media_ids ?? []}
                    onToggle={(id) => toggleScheduleVariantMedia(vi, id)}
                    rowKeyPrefix={`scheduler-create-v${vi}`}
                  />
                </div>
              </div>
            ))}
            <p className="text-[10px] text-slate-500">
              {scheduleAlbumVariants.reduce((n, v) => n + v.media_ids.length, 0)} pick(s)
              {poolSelectUsesPool(poolId) && schedulePoolOnlyMode ? " · pool-only ignores picks" : ""}
            </p>
          </SchedulerComposerCard>

          <SchedulerComposerCard title="Pin message" className={COMPOSER_TILE_H} bodyClassName={COMPOSER_BODY_H}>
            <InfoDisclosure>
              Message id from a Telegram link or helper bot. Admin session needs pin rights in the channel.
            </InfoDisclosure>
            <div className="space-y-1.5">
              <select
                value={pinToolChannelId}
                onChange={(e) => setPinToolChannelId(Number(e.target.value))}
                className={inputSm}
              >
                <option value={0}>Channel…</option>
                {(channels as Array<{ id: number; name?: string; identifier?: string }>).map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name || c.identifier || `#${c.id}`}
                  </option>
                ))}
              </select>
              <input
                type="text"
                inputMode="numeric"
                value={pinToolMessageId}
                onChange={(e) => setPinToolMessageId(e.target.value)}
                placeholder="Message id"
                className={inputSm}
              />
              <div className="flex flex-wrap items-center gap-2">
                <label className="flex items-center gap-1.5 text-[11px] text-slate-300">
                  <input type="checkbox" checked={pinToolUnpin} onChange={(e) => setPinToolUnpin(e.target.checked)} />
                  Unpin
                </label>
                <button
                  type="button"
                  onClick={() => pinToolMutation.mutate()}
                  disabled={pinToolMutation.isPending}
                  className="rounded bg-slate-600 px-2.5 py-1 text-[11px] text-white hover:bg-slate-500 disabled:opacity-50"
                >
                  {pinToolMutation.isPending ? "…" : pinToolUnpin ? "Unpin" : "Pin"}
                </button>
              </div>
              {pinToolMsg ? (
                <p
                  className={`text-[10px] ${
                    pinToolMsg.includes("Error") || pinToolMsg.includes("Select") ? "text-amber-300" : "text-emerald-300"
                  }`}
                >
                  {pinToolMsg}
                </p>
              ) : null}
            </div>
          </SchedulerComposerCard>
        </div>

        <SchedulerComposerCard
          title="Post body"
          className={`flex flex-col ${POST_BODY_PANEL_H}`}
          bodyClassName="flex min-h-0 flex-1 flex-col"
          headerRight={
            <button
              type="button"
              onClick={() => createScheduledPost.mutate()}
              disabled={
                createScheduledPost.isPending ||
                selectedChannelIds.length === 0 ||
                (scheduleCheckoutStars && scheduleCheckoutPlanId <= 0) ||
                (!captionVariations.some((s) => s.trim()) &&
                  !poolSelectUsesPool(poolId) &&
                  !scheduleAlbumVariants.some(
                    (v) => v.media_ids.length > 0 || v.attachment_urls.some((s) => s.trim())
                  ))
              }
              className="rounded bg-cyan-600 px-2.5 py-0.5 text-[10px] font-medium text-white hover:bg-cyan-500 disabled:opacity-50"
            >
              {createScheduledPost.isPending ? "…" : "Schedule"}
            </button>
          }
        >
          <div className="mb-1 flex gap-px border-b border-slate-700/80">
            {(
              [
                ["caption", "Caption"],
                ["buttons", "Buttons"],
                ["delivery", "Delivery"],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                type="button"
                onClick={() => setComposerDetailTab(id)}
                className={`px-2 py-0.5 text-[10px] font-medium border-b-2 -mb-px transition-colors ${
                  composerDetailTab === id
                    ? "border-cyan-500 text-cyan-300"
                    : "border-transparent text-slate-500 hover:text-slate-300"
                }`}
              >
                {label}
                {id === "caption" && captionVariations.length > 1 ? ` (${captionVariations.length})` : ""}
              </button>
            ))}
            <div className="ml-auto flex items-center">
              <TbccInsertLibraryToolbar />
            </div>
          </div>
          <div className={`${POST_BODY_EDITOR_H} overflow-y-auto pr-0.5 text-[11px]`}>
            {composerDetailTab === "caption" ? (
              <div className="flex h-full flex-col space-y-1">
                {captionVariations.map((line, i) => (
                  <CaptionTelegramHtmlField
                    key={i}
                    className="w-full min-w-0 flex-1"
                    value={line}
                    onChange={(v) => setCaptionVariations((prev) => prev.map((p, j) => (j === i ? v : p)))}
                    placeholder={i === 0 ? "Caption (Telegram HTML)" : `Variation ${i + 1}`}
                    rows={captionVariations.length > 1 ? 4 : 10}
                    extraActions={
                      <>
                        <TbccInsertMenu
                          channels={channels as Array<Record<string, unknown>>}
                          pools={pools as Array<Record<string, unknown>>}
                          onInsert={(t) =>
                            setCaptionVariations((prev) => prev.map((p, j) => (j === i ? t : p)))
                          }
                        />
                        {captionVariations.length > 1 ? (
                          <button
                            type="button"
                            onClick={() => setCaptionVariations((prev) => prev.filter((_, j) => j !== i))}
                            className="rounded px-1.5 py-0.5 text-red-400 hover:bg-red-900/30"
                            title="Remove caption"
                          >
                            ✕
                          </button>
                        ) : null}
                      </>
                    }
                  />
                ))}
                <button
                  type="button"
                  onClick={() => setCaptionVariations((prev) => [...prev, ""])}
                  className="text-[10px] text-cyan-400 hover:text-cyan-300"
                >
                  + Rotate caption
                </button>
              </div>
            ) : null}
            {composerDetailTab === "buttons" ? (
              <div className="space-y-1">
                {scheduleCheckoutStars ? (
                  <p className="text-[10px] text-amber-200/90 mb-1">
                    Stars checkout on: <strong>Pay ⭐</strong> button is added at send (invoice link) — not stored here.
                    {scheduleCheckoutButtonLabel.trim() ? ` Label: ${scheduleCheckoutButtonLabel.trim()}` : ""}
                  </p>
                ) : null}
                {buttons.length === 0 && !scheduleCheckoutStars ? (
                  <p className="text-[10px] text-slate-500">
                    <code>https://</code> or <code>tg://</code> on the album row.
                  </p>
                ) : null}
                {buttons.map((b, i) => (
                  <div key={i} className="flex gap-1">
                    <input
                      placeholder="Label"
                      value={b.text}
                      onChange={(e) => updateButton(i, "text", e.target.value)}
                      className="min-w-0 flex-1 rounded border border-slate-600 bg-slate-700 px-1.5 py-0.5 text-slate-200"
                    />
                    <input
                      placeholder="URL"
                      value={b.url}
                      onChange={(e) => updateButton(i, "url", e.target.value)}
                      className="min-w-0 flex-[2] rounded border border-slate-600 bg-slate-700 px-1.5 py-0.5 text-slate-200"
                    />
                    <button
                      type="button"
                      onClick={() => removeButton(i)}
                      className="px-1 text-red-400 hover:bg-red-900/30"
                    >
                      ✕
                    </button>
                  </div>
                ))}
                <button type="button" onClick={addButton} className="text-[10px] text-cyan-400 hover:text-cyan-300">
                  + Button
                </button>
              </div>
            ) : null}
            {composerDetailTab === "delivery" ? (
              <div className="space-y-1.5">
                <SilentTelegramSendOption
                  checked={scheduleSendSilent}
                  onChange={(v) => {
                    setScheduleSendSilent(v);
                    writeSendSilentPreference(v);
                  }}
                />
                <label className="flex cursor-pointer items-center gap-1.5 text-slate-300">
                  <input
                    type="checkbox"
                    checked={schedulePinAfterSend}
                    onChange={(e) => setSchedulePinAfterSend(e.target.checked)}
                  />
                  Pin after send
                </label>
                <label className="flex cursor-pointer items-center gap-1.5 text-slate-300">
                  <input
                    type="checkbox"
                    checked={scheduleCheckoutStars}
                    onChange={(e) => {
                      setScheduleCheckoutStars(e.target.checked);
                      if (!e.target.checked) setScheduleCheckoutPlanId(0);
                    }}
                  />
                  Stars checkout
                </label>
                {scheduleCheckoutStars ? (
                  <select
                    value={scheduleCheckoutPlanId || ""}
                    onChange={(e) => setScheduleCheckoutPlanId(Number(e.target.value) || 0)}
                    className={inputSm}
                  >
                    <option value="">Commerce plan…</option>
                    {salablePlans.map((p) => (
                      <option key={String(p.id)} value={Number(p.id)}>
                        {String(p.name || `Plan ${p.id}`)} — {Number(p.price_stars || 0)}⭐
                      </option>
                    ))}
                  </select>
                ) : null}
                {scheduleCheckoutStars ? (
                  <div className="grid grid-cols-2 gap-1">
                    <input
                      type="text"
                      value={scheduleCheckoutButtonLabel}
                      onChange={(e) => setScheduleCheckoutButtonLabel(e.target.value)}
                      placeholder="Button label"
                      maxLength={64}
                      className={inputSm}
                    />
                    <input
                      type="text"
                      value={scheduleCheckoutReferralCode}
                      onChange={(e) => setScheduleCheckoutReferralCode(e.target.value.replace(/[^a-zA-Z0-9]/g, ""))}
                      placeholder="Referral"
                      maxLength={16}
                      className={inputSm}
                    />
                  </div>
                ) : null}
                <CaptionLlmRewriteFields
                  enabled={scheduleLlmRewrite}
                  onEnabledChange={setScheduleLlmRewrite}
                  mode={scheduleLlmMode}
                  onModeChange={setScheduleLlmMode}
                  interval={scheduleLlmInterval}
                  onIntervalChange={setScheduleLlmInterval}
                  probability={scheduleLlmProb}
                  onProbabilityChange={setScheduleLlmProb}
                  disabled={createScheduledPost.isPending}
                />
              </div>
            ) : null}
          </div>
        </SchedulerComposerCard>
    </>
  );

  return (
    <div>
      {!embedded ? (
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold">Scheduler</h1>
            <p className="text-slate-400 text-sm mt-1">
              One-time + recurring posting with captions, media, links, and campaign fan-out.
            </p>
          </div>
          <InfoDisclosure>
            For forum supergroups, choose a topic to post into that subtopic. Timing strategy: test 2-3 windows, compare
            results, and stagger channels by 5-15 minutes to reduce notification overlap.
          </InfoDisclosure>
        </div>
      ) : null}

      {!calendarScheduleModalOpen ? (
        <div className="mb-4 max-w-full">
          <div className="mb-1.5 flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
            <h2 className="text-sm font-semibold tracking-tight text-slate-100">Scheduled posts</h2>
            <span className="text-[10px] text-slate-500">
              Overview · jobs · <strong className="text-slate-400">Post now</strong> → Celery
            </span>
            <InfoDisclosure>
              Captions support Telegram HTML. Recurring jobs fire <strong>Post now</strong> once if never sent.
            </InfoDisclosure>
          </div>
          <ScheduledPostsList
            weekPosts={
              scheduledPostsForWeek as Array<{
                id: number;
                name?: string | null;
                scheduled_at?: string | null;
                interval_minutes?: number | null;
                channel_name?: string | null;
                campaign_group_id?: string | null;
              }>
            }
            onWeekDayClick={openScheduleForCalendarDay}
          />
        </div>
      ) : null}

      {!calendarScheduleModalOpen ? (
        <div className="mb-3 grid grid-cols-1 gap-3 xl:grid-cols-2 xl:items-stretch">
          <div
            id="scheduler-add-post"
            className="tbcc-panel max-w-full rounded-md border border-slate-700/80 bg-slate-800/90 p-2"
          >
            {renderAddScheduledPostForm()}
          </div>
          <SchedulerGrowthHub className="mb-0 h-full min-h-[22rem] xl:min-h-[26rem]" />
        </div>
      ) : null}

      {calendarScheduleModalOpen ? (
        <div
          className="fixed inset-0 z-[100] flex items-start justify-center overflow-y-auto bg-slate-950/85 px-3 py-6 sm:py-10"
          role="dialog"
          aria-modal="true"
          aria-labelledby="scheduler-calendar-modal-title"
          onClick={() => setCalendarScheduleModalOpen(false)}
        >
          <div
            className="w-full max-w-[min(96rem,100%)] rounded-lg border border-slate-600 bg-slate-800 p-4 shadow-2xl mb-10"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex flex-wrap items-start justify-between gap-2 mb-2">
              <h3 id="scheduler-calendar-modal-title" className="text-lg font-medium text-slate-100 pr-2">
                Schedule from calendar
                {scheduledAt?.length >= 10 ? (
                  <span className="text-slate-400 font-normal text-sm block sm:inline sm:ml-2">
                    ({scheduledAt.slice(0, 10)})
                  </span>
                ) : null}
              </h3>
              <button
                type="button"
                className="shrink-0 px-3 py-1 rounded bg-slate-700 text-slate-200 text-sm hover:bg-slate-600"
                onClick={() => setCalendarScheduleModalOpen(false)}
              >
                Close
              </button>
            </div>
            <p className="text-slate-500 text-xs mb-3">
              Same options as the <strong>Add scheduled post</strong> card (hidden while this is open). Set a one-time{" "}
              <strong>date/time</strong> or enable <strong>recurring</strong> for interval-based runs. Click outside, Esc, or Close to
              dismiss.
            </p>
            {renderAddScheduledPostForm()}
          </div>
        </div>
      ) : null}

    </div>
  );
}
