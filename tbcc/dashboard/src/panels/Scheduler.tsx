import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";
import { useState, useEffect } from "react";
import { ScheduledPostsList } from "../components/ScheduledPostsList";
import { SchedulerWeek } from "../components/SchedulerWeek";
import { SchedulePromoSlots } from "../components/SchedulePromoSlots";
import { ApprovedMediaPickerStrip } from "../components/ApprovedMediaPickerStrip";
import { formatUtcForDashboard, formatUtcWithLocalHint } from "../utils/formatUtc";
import { CaptionSnippetInsertSelect, CaptionSnippetLibraryManageButton } from "../components/CaptionSnippetLibrary";
import { CaptionTelegramHtmlField } from "../components/CaptionTelegramHtmlField";
import { InfoDisclosure } from "../components/InfoDisclosure";

const INTERVAL_OPTIONS = [15, 30, 60, 120, 180, 240, 360, 720];

type AlbumVariant = { attachment_urls: string[]; media_ids: number[] };

function padAlbumVariants(v: AlbumVariant[], n: number): AlbumVariant[] {
  const out = [...v];
  while (out.length < n) out.push({ attachment_urls: [], media_ids: [] });
  return out.slice(0, n);
}

export function Scheduler() {
  const queryClient = useQueryClient();
  const [calendarScheduleModalOpen, setCalendarScheduleModalOpen] = useState(false);
  const [name, setName] = useState("");
  /** Multi-select: same job posts to every checked channel (one shared recurring / one-time schedule). */
  const [selectedChannelIds, setSelectedChannelIds] = useState<number[]>([]);
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
  const [scheduleSendSilent, setScheduleSendSilent] = useState(false);
  const [schedulePinAfterSend, setSchedulePinAfterSend] = useState(false);
  const [pinToolChannelId, setPinToolChannelId] = useState(0);
  const [pinToolMessageId, setPinToolMessageId] = useState("");
  const [pinToolUnpin, setPinToolUnpin] = useState(false);
  const [pinToolMsg, setPinToolMsg] = useState<string | null>(null);

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
      poolId > 0
        ? api.media.list({ status: "approved", pool_id: poolId })
        : api.media.list("approved"),
  });
  const { data: scheduledPostsForWeek = [] } = useQuery({
    queryKey: ["scheduledPosts"],
    queryFn: () => api.scheduledPosts.list(),
  });
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
      const base: Parameters<typeof api.scheduledPosts.create>[0] = {
        name: name || undefined,
        channel_ids: chIds,
        ...(messageThreadId != null ? { message_thread_id: messageThreadId } : {}),
        content: trimmed[0] || "",
        media_ids: [],
        album_variants: av,
        album_order_mode: scheduleAlbumOrderMode,
        pool_id: poolId || undefined,
        buttons: buttons.some((b) => b.text.trim() && b.url.trim()) ? buttons.filter((b) => b.text.trim() && b.url.trim()) : undefined,
        scheduled_at: isRecurring ? undefined : scheduledAtIso,
        interval_minutes: isRecurring ? intervalMinutes : undefined,
        ...(poolId > 0
          ? {
              album_size: Math.min(10, Math.max(1, scheduleAlbumSize)),
              pool_randomize: schedulePoolRandomize,
              pool_only_mode: schedulePoolOnlyMode,
            }
          : {}),
        send_silent: scheduleSendSilent,
        pin_after_send: schedulePinAfterSend,
      };
      if (trimmed.length >= 2) {
        base.content_variations = trimmed;
        base.content = trimmed[0];
      }
      return api.scheduledPosts.create(base);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["scheduledPosts"] });
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

  const chartData = (pools as Array<Record<string, unknown>>).map((p) => ({
    name: String(p.name || `Pool ${p.id}`),
    interval: Number(p.interval_minutes) || 60,
    id: p.id,
  }));

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

  const renderAddScheduledPostForm = () => (
    <>
        {createScheduledPost.isError && (
          <div className="mb-3 px-3 py-2 rounded bg-red-900/50 text-red-200 text-sm">
            {createScheduledPost.error?.message}
          </div>
        )}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="space-y-2">
            <input
              type="text"
              placeholder="Name (optional)"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200"
            />
            <div className="border border-slate-600 rounded-lg p-2 bg-slate-900/40">
              <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
                <span className="text-slate-400 text-sm">Channels (one post per channel)</span>
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
              <div className="flex flex-col gap-1.5 max-h-36 overflow-y-auto">
                {(channels as Array<{ id: number; name?: string; identifier?: string }>).map((c) => (
                  <label key={c.id} className="flex items-center gap-2 text-sm text-slate-300 cursor-pointer">
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
            </div>
            {selectedChannelIds.length > 1 && (
              <p className="text-slate-500 text-xs">
                Forum topic picker is available when exactly one channel is selected; with multiple channels, leave topic
                as main chat or pick a topic after narrowing to one channel.
              </p>
            )}
            {forumTopicSourceId > 0 && (
              <div>
                <span className="text-slate-400 text-xs block mb-1">
                  Forum topic (optional — supergroups with topics enabled)
                </span>
                <select
                  value={messageThreadId === null ? "" : String(messageThreadId)}
                  onChange={(e) => {
                    const v = e.target.value;
                    setMessageThreadId(v === "" ? null : Number(v));
                  }}
                  className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200 text-sm"
                >
                  <option value="">Main chat (no topic)</option>
                  {forumTopics.map((t) => (
                    <option key={t.id} value={String(t.id)}>
                      {t.title}
                    </option>
                  ))}
                </select>
                {forumTopicsHint && (
                  <p className="text-amber-400/90 text-xs mt-1">{forumTopicsHint}</p>
                )}
                {forumTopics.length === 0 && !forumTopicsHint && (
                  <p className="text-slate-500 text-xs mt-1">
                    No topics listed — group may not be forum-enabled, or Telegram user session cannot read topics.
                  </p>
                )}
              </div>
            )}
            <label className="flex items-center gap-2 text-slate-300">
              <input
                type="checkbox"
                checked={isRecurring}
                onChange={(e) => setIsRecurring(e.target.checked)}
              />
              Recurring (post at interval)
            </label>
            {isRecurring ? (
              <div>
                <span className="text-slate-400 text-sm">Every </span>
                <select
                  value={intervalMinutes}
                  onChange={(e) => setIntervalMinutes(Number(e.target.value))}
                  className="bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200"
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
                className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200"
              />
            )}
            <div className="space-y-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-slate-400 text-sm">
                  Caption{captionVariations.length > 1 ? "s (rotate in order)" : ""}
                </span>
                <CaptionSnippetLibraryManageButton />
              </div>
              {captionVariations.map((line, i) => (
                <CaptionTelegramHtmlField
                  key={i}
                  value={line}
                  onChange={(v) => setCaptionVariations((prev) => prev.map((p, j) => (j === i ? v : p)))}
                  placeholder={i === 0 ? "Text content (caption)" : `Caption variation ${i + 1}`}
                  rows={i === 0 ? 4 : 3}
                  extraActions={
                    <>
                    <CaptionSnippetInsertSelect
                      onInsert={(t) =>
                        setCaptionVariations((prev) => prev.map((p, j) => (j === i ? t : p)))
                      }
                    />
                    {captionVariations.length > 1 && (
                      <button
                        type="button"
                        onClick={() => setCaptionVariations((prev) => prev.filter((_, j) => j !== i))}
                        className="px-2 py-1 text-red-400 hover:bg-red-900/30 rounded"
                        title="Remove this caption"
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
                onClick={() => setCaptionVariations((prev) => [...prev, ""])}
                className="text-sm text-cyan-400 hover:text-cyan-300"
              >
                + Add caption variation (enables rotation when 2+ are filled)
              </button>
            </div>
            <div className="flex flex-wrap gap-2">
              <span className="text-slate-500 text-xs w-full">Quick insert (channel invite links) → first caption:</span>
              {(channels as Array<Record<string, unknown>>).map((c) =>
                c.invite_link ? (
                  <button
                    key={String(c.id)}
                    type="button"
                    onClick={() => {
                      const link = String(c.invite_link || "").trim();
                      if (!link) return;
                      setCaptionVariations((prev) => {
                        const next = [...prev];
                        const cur = next[0] || "";
                        next[0] = cur.trim() ? `${cur.trim()}\n\n${link}` : link;
                        return next;
                      });
                    }}
                    className="px-2 py-1 rounded bg-slate-700 border border-slate-600 text-xs text-cyan-300 hover:bg-slate-600"
                  >
                    + {String(c.name || c.identifier || c.id)} link
                  </button>
                ) : null
              )}
            </div>
            <div>
              <span className="text-slate-400 text-sm block mb-1">Inline buttons (text + URL)</span>
              <p className="text-slate-500 text-xs mb-2">
                Use <code className="text-slate-400">https://</code> or <code className="text-slate-400">tg://</code>{" "}
                (e.g. link to your bot). Buttons apply to the whole album (caption sits on the first item).
              </p>
              {buttons.map((b, i) => (
                <div key={i} className="flex gap-2 mb-2">
                  <input
                    placeholder="Button text"
                    value={b.text}
                    onChange={(e) => updateButton(i, "text", e.target.value)}
                    className="flex-1 bg-slate-700 border border-slate-600 rounded px-2 py-1 text-slate-200 text-sm"
                  />
                  <input
                    placeholder="https://… or tg://…"
                    value={b.url}
                    onChange={(e) => updateButton(i, "url", e.target.value)}
                    className="flex-1 bg-slate-700 border border-slate-600 rounded px-2 py-1 text-slate-200 text-sm"
                  />
                  <button
                    type="button"
                    onClick={() => removeButton(i)}
                    className="px-2 py-1 text-red-400 hover:bg-red-900/30 rounded"
                  >
                    ✕
                  </button>
                </div>
              ))}
              <button
                type="button"
                onClick={addButton}
                className="text-sm text-cyan-400 hover:text-cyan-300"
              >
                + Add button
              </button>
              <div className="flex flex-col gap-2 pt-2 border-t border-slate-600/60 mt-2">
                <label className="flex items-center gap-2 text-sm text-slate-300 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={scheduleSendSilent}
                    onChange={(e) => setScheduleSendSilent(e.target.checked)}
                  />
                  Silent send (no notification sound for subscribers)
                </label>
                <label className="flex items-center gap-2 text-sm text-slate-300 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={schedulePinAfterSend}
                    onChange={(e) => setSchedulePinAfterSend(e.target.checked)}
                  />
                  Pin this post after send (needs pin rights; pins first album message)
                </label>
              </div>
            </div>
          </div>
          <div>
            <label className="block text-slate-400 text-xs mb-1">Album order (promo + picked media)</label>
            <select
              value={scheduleAlbumOrderMode}
              onChange={(e) =>
                setScheduleAlbumOrderMode(e.target.value as "static" | "shuffle" | "carousel")
              }
              className="w-full mb-3 bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200 text-sm"
            >
              <option value="static">Static order</option>
              <option value="shuffle">Shuffle each time</option>
              <option value="carousel">Carousel (rotate order each post)</option>
            </select>
            <p className="text-slate-500 text-xs mb-3">
              One album block per caption. Shuffle / carousel apply to that caption&apos;s combined promo + library picks.
            </p>
            <p className="text-slate-400 text-sm mb-2">
              Media pool (optional) — choosing a pool filters thumbnails. Empty caption albums fall back to the pool
              batch.
            </p>
            <select
              value={poolId}
              onChange={(e) => {
                setPoolId(Number(e.target.value));
                setScheduleAlbumVariants((prev) => prev.map((v) => ({ ...v, media_ids: [] })));
              }}
              className="w-full mb-2 bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200 text-sm"
            >
              <option value={0}>No pool (text-only unless media is explicitly picked below)</option>
              {(pools as Array<{ id: number; name?: string }>).map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name || `Pool ${p.id}`} (media + optional auto-pick)
                </option>
              ))}
            </select>
            <p className="text-slate-500 text-xs mb-2">
              Choose <strong>No pool</strong> for clean text+links recurring posts between album drops.
            </p>
            {poolId > 0 && (
              <div className="border border-slate-600 rounded p-3 mb-2 space-y-2 bg-slate-900/40">
                <p className="text-slate-400 text-xs">
                  <strong>This schedule only</strong> — album size & randomize (override the pool defaults for this job).
                </p>
                <div className="flex flex-wrap items-center gap-3">
                  <label className="flex items-center gap-2 text-sm text-slate-300">
                    <span className="text-slate-400">Album size</span>
                    <input
                      type="number"
                      min={1}
                      max={10}
                      value={scheduleAlbumSize}
                      onChange={(e) => setScheduleAlbumSize(Math.min(10, Math.max(1, Number(e.target.value) || 5)))}
                      className="w-16 bg-slate-700 border border-slate-600 rounded px-2 py-1 text-slate-200"
                    />
                  </label>
                  <label className="flex items-center gap-2 text-sm text-slate-300">
                    <input
                      type="checkbox"
                      checked={schedulePoolRandomize}
                      onChange={(e) => setSchedulePoolRandomize(e.target.checked)}
                    />
                    Randomize pool picks
                  </label>
                  <label className="flex items-center gap-2 text-sm text-slate-300">
                    <input
                      type="checkbox"
                      checked={schedulePoolOnlyMode}
                      onChange={(e) => setSchedulePoolOnlyMode(e.target.checked)}
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
                disabled={!poolId || uploadToPool.isPending}
                onChange={(e) => {
                  const pid = poolId;
                  const input = e.target as HTMLInputElement;
                  const snapshot = input.files?.length ? Array.from(input.files) : [];
                  input.value = "";
                  if (!pid || !snapshot.length) return;
                  uploadToPool.mutate({ files: snapshot, pid });
                }}
                className="text-slate-300 max-w-full"
              />
            </label>
            {uploadMsg && (
              <pre className="text-xs text-slate-300 bg-slate-900/80 rounded p-2 mb-2 whitespace-pre-wrap max-h-24 overflow-y-auto">
                {uploadMsg}
              </pre>
            )}
            {!poolId && (
              <p className="text-amber-400/90 text-xs mb-2">
                Select a pool above to enable this import (pending in Media Library until approved).
              </p>
            )}
            {captionVariations.map((_, vi) => (
              <div key={vi} className="mb-3 border border-slate-600/80 rounded-lg p-2 bg-slate-900/30">
                <p className="text-slate-300 text-xs font-medium mb-2">
                  {captionVariations.length > 1 ? `Album for caption ${vi + 1}` : "Promotional album"}
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
                <div className="mt-2 min-w-0">
                  <ApprovedMediaPickerStrip
                    rows={media as Array<Record<string, unknown>>}
                    selectedIds={scheduleAlbumVariants[vi]?.media_ids ?? []}
                    onToggle={(id) => toggleScheduleVariantMedia(vi, id)}
                    rowKeyPrefix={`scheduler-create-v${vi}`}
                  />
                </div>
              </div>
            ))}
            <p className="text-slate-500 text-xs mt-1">
              {scheduleAlbumVariants.reduce((n, v) => n + v.media_ids.length, 0)} media pick(s).{" "}
              {poolId > 0 && schedulePoolOnlyMode
                ? "Pool-only mode is ON: scheduler ignores picked media/promos and always uses pool batch."
                : "If pool is set and a caption has no picks, that run uses the pool batch."}
            </p>
          </div>
        </div>
        <button
          onClick={() => createScheduledPost.mutate()}
          disabled={
            createScheduledPost.isPending ||
            selectedChannelIds.length === 0 ||
            (!captionVariations.some((s) => s.trim()) &&
              !poolId &&
              !scheduleAlbumVariants.some(
                (v) => v.media_ids.length > 0 || v.attachment_urls.some((s) => s.trim())
              ))
          }
          className="mt-4 px-4 py-2 bg-cyan-600 text-white rounded hover:bg-cyan-500 disabled:opacity-50"
        >
          {createScheduledPost.isPending ? "Creating..." : "Schedule"}
        </button>
    </>
  );

  return (
    <div>
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

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4 mb-8 items-stretch">
        <div className="bg-slate-800 rounded-lg p-4 xl:col-span-1">
          <div className="flex items-center justify-between gap-2 mb-2">
            <h2 className="text-lg font-medium">Pool intervals</h2>
            <InfoDisclosure>
              Pool auto-posting is off. Use scheduled posts below to publish. Times are stored as UTC; tooltips show
              local and PT hints.
            </InfoDisclosure>
          </div>
          {chartData.length > 0 ? (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                <XAxis dataKey="name" stroke="#94a3b8" fontSize={12} />
                <YAxis stroke="#94a3b8" fontSize={12} />
                <Tooltip
                  contentStyle={{ backgroundColor: "#1e293b", border: "1px solid #475569" }}
                  labelStyle={{ color: "#e2e8f0" }}
                />
                <Bar dataKey="interval" radius={[4, 4, 0, 0]}>
                  {chartData.map((_, i) => (
                    <Cell key={i} fill="#06b6d4" />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-slate-500">No pools. Create pools in the Pools panel.</p>
          )}
        </div>
        <div className="overflow-x-auto xl:col-span-2 border border-slate-600 rounded-lg">
          <table className="w-full overflow-hidden">
            <thead className="bg-slate-700">
              <tr>
                <th className="text-left p-3">Pool</th>
                <th className="text-left p-3">Queued</th>
                <th className="text-left p-3">Interval (min)</th>
                <th className="text-left p-3">Last pool run (UTC)</th>
              </tr>
            </thead>
            <tbody>
              {pools.map((p: Record<string, unknown>) => (
                <tr key={String(p.id)} className="border-t border-slate-600 hover:bg-slate-800/50">
                  <td className="p-3">{String(p.name)}</td>
                  <td className="p-3">
                    <span className={Number(p.approved_count ?? 0) > 0 ? "text-cyan-300" : "text-slate-500"}>
                      {String(p.approved_count ?? 0)}/{String(p.album_size ?? 5)}
                    </span>
                  </td>
                  <td className="p-3">{String(p.interval_minutes)}</td>
                  <td
                    className="p-3 text-slate-400 text-sm"
                    title={p.last_posted ? formatUtcWithLocalHint(String(p.last_posted)) : undefined}
                  >
                    {p.last_posted ? formatUtcForDashboard(String(p.last_posted)) : "Never"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <SchedulerWeek
        posts={
          scheduledPostsForWeek as Array<{
            id: number;
            name?: string | null;
            scheduled_at?: string | null;
            interval_minutes?: number | null;
            channel_name?: string | null;
            campaign_group_id?: string | null;
          }>
        }
        onDayClick={openScheduleForCalendarDay}
      />

      <h2 className="text-xl font-semibold mb-3">Scheduled Posts</h2>
      <div className="mb-4 flex justify-end">
        <InfoDisclosure>
          Captions support Telegram HTML tags; buttons support https:// and tg:// links. Recurring schedules begin with
          <strong> Post now</strong> once if no last send exists. You can rotate captions and send one campaign to many
          channels. Recurring rows show bright <strong>Next post</strong> in local time + PT.
        </InfoDisclosure>
      </div>

      {!calendarScheduleModalOpen ? (
        <div id="scheduler-add-post" className="bg-slate-800 rounded-lg p-4 mb-6 max-w-4xl">
          <h3 className="text-lg font-medium mb-3">Add scheduled post</h3>
          {renderAddScheduledPostForm()}
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
            className="w-full max-w-4xl rounded-lg border border-slate-600 bg-slate-800 p-4 shadow-2xl mb-10"
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

      <div className="bg-slate-800 rounded-lg p-4 mb-8 max-w-2xl border border-slate-600/80">
        <div className="flex items-center justify-between gap-2 mb-2">
          <h3 className="text-lg font-medium">Pin a message in a channel</h3>
          <InfoDisclosure>
            Paste numeric message id from a message link or helper bot. Your admin Telegram session must have pin rights
            in the channel.
          </InfoDisclosure>
        </div>
        <div className="flex flex-wrap gap-3 items-end">
          <div className="flex-1 min-w-[10rem]">
            <span className="text-slate-400 text-xs block mb-1">Channel</span>
            <select
              value={pinToolChannelId}
              onChange={(e) => setPinToolChannelId(Number(e.target.value))}
              className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200 text-sm"
            >
              <option value={0}>Select channel</option>
              {(channels as Array<{ id: number; name?: string; identifier?: string }>).map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name || c.identifier || `#${c.id}`}
                </option>
              ))}
            </select>
          </div>
          <div className="w-32">
            <span className="text-slate-400 text-xs block mb-1">Message id</span>
            <input
              type="text"
              inputMode="numeric"
              value={pinToolMessageId}
              onChange={(e) => setPinToolMessageId(e.target.value)}
              placeholder="e.g. 48291"
              className="w-full bg-slate-700 border border-slate-600 rounded px-2 py-2 text-slate-200 text-sm"
            />
          </div>
          <label className="flex items-center gap-2 text-sm text-slate-300 pb-2">
            <input type="checkbox" checked={pinToolUnpin} onChange={(e) => setPinToolUnpin(e.target.checked)} />
            Unpin
          </label>
          <button
            type="button"
            onClick={() => pinToolMutation.mutate()}
            disabled={pinToolMutation.isPending}
            className="px-4 py-2 bg-slate-600 text-white rounded hover:bg-slate-500 disabled:opacity-50 text-sm"
          >
            {pinToolMutation.isPending ? "…" : pinToolUnpin ? "Unpin" : "Pin"}
          </button>
        </div>
        {pinToolMsg && (
          <p className={`text-sm mt-3 ${pinToolMsg.includes("Error") || pinToolMsg.includes("Select") ? "text-amber-300" : "text-emerald-300"}`}>
            {pinToolMsg}
          </p>
        )}
      </div>

      <h2 className="text-xl font-semibold mb-2">Scheduled posts</h2>
      <p className="text-slate-400 text-sm mb-4">
        Click a row to edit captions (including rotating variations), posting interval, or pool album options.
      </p>
      <ScheduledPostsList />
    </div>
  );
}
