import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import { useState, useEffect, useMemo } from "react";
import { SchedulePromoSlots } from "./SchedulePromoSlots";
import { ApprovedMediaPickerStrip } from "./ApprovedMediaPickerStrip";
import {
  formatLocalForDashboard,
  formatPtForDashboard,
  formatUtcForDashboard,
  formatUtcWithLocalHint,
} from "../utils/formatUtc";
import { CaptionSnippetInsertSelect, CaptionSnippetLibraryManageButton } from "./CaptionSnippetLibrary";
import { CaptionTelegramHtmlField } from "./CaptionTelegramHtmlField";

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

function nextRecurringRunIso(lastPostedAt: unknown, intervalMinutes: unknown): string | null {
  if (!lastPostedAt) return null;
  const mins = Number(intervalMinutes);
  if (!Number.isFinite(mins) || mins <= 0) return null;
  const raw = String(lastPostedAt).trim();
  const base = /[zZ]|[+-]\d{2}:?\d{2}$/.test(raw)
    ? new Date(raw)
    : new Date(raw.includes("T") ? `${raw}Z` : `${raw.replace(" ", "T")}Z`);
  if (Number.isNaN(base.getTime())) return null;
  const next = new Date(base.getTime() + mins * 60_000);
  return next.toISOString();
}

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

type Props = {
  /** Only show recurring (interval) jobs — e.g. on Subscriptions tab */
  compactRecurringOnly?: boolean;
};

export function ScheduledPostsList({ compactRecurringOnly }: Props) {
  const queryClient = useQueryClient();

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
  const [editButtons, setEditButtons] = useState<Array<{ text: string; url: string }>>([]);
  const [editSendSilent, setEditSendSilent] = useState(false);
  const [editPinAfterSend, setEditPinAfterSend] = useState(false);
  const [editScheduleError, setEditScheduleError] = useState<string | null>(null);
  const [triggerNotice, setTriggerNotice] = useState<{ kind: "ok" | "err"; text: string } | null>(null);

  const { data: pools = [] } = useQuery({
    queryKey: ["pools"],
    queryFn: () => api.pools.list(),
  });
  const { data: channels = [] } = useQuery({
    queryKey: ["channels"],
    queryFn: () => api.channels.list(),
  });
  const { data: scheduledPosts = [] } = useQuery({
    queryKey: ["scheduledPosts"],
    queryFn: () => api.scheduledPosts.list(),
  });
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
      editPoolId > 0
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
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["scheduledPosts"] }),
  });

  const deleteScheduledPost = useMutation({
    mutationFn: (id: number) => api.scheduledPosts.delete(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["scheduledPosts"] }),
  });

  const triggerScheduledPost = useMutation({
    mutationFn: ({ id, reshuffle }: { id: number; reshuffle?: boolean }) =>
      api.scheduledPosts.trigger(id, { reshuffle: !!reshuffle }),
    onSuccess: (data, { id }) => {
      queryClient.invalidateQueries({ queryKey: ["scheduledPosts"] });
      const cg = data?.campaign_group_id;
      const rs = data?.reshuffle;
      setTriggerNotice({
        kind: "ok",
        text: cg
          ? `Campaign queued (leader #${data.post_id ?? id})${rs ? " — album order reshuffled for this send" : ""} — Celery will send to all channels shortly.`
          : `Post #${id} queued${rs ? " — album order reshuffled for this send" : ""} — Celery will send shortly. Watch Telegram (and server logs if it fails).`,
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
    const pool = pid ? (poolMap[String(pid)] as Record<string, unknown> | undefined) : undefined;
    const poolDefaultAlbum = Number(pool?.album_size ?? 5);
    setEditAlbumSize(leader.album_size != null ? Number(leader.album_size) : poolDefaultAlbum);
    setEditRandomize(leader.pool_randomize != null ? Boolean(leader.pool_randomize) : !!pool?.randomize_queue);
    setEditPoolOnlyMode(leader.pool_only_mode != null ? Boolean(leader.pool_only_mode) : true);
    setEditMessageThreadId(
      leader.message_thread_id != null && leader.message_thread_id !== undefined
        ? Number(leader.message_thread_id)
        : null
    );
    setEditPoolId(Number.isFinite(pid) && pid > 0 ? pid : 0);
    const cap = Array.isArray(cv) && cv.length >= 2 ? cv.length : 1;
    const { variants: avFromApi, order: ordFromApi } = parseAlbumVariantsFromPost(leader);
    setEditAlbumVariants(padAlbumVariants(avFromApi, cap));
    setEditAlbumOrderMode(ordFromApi);
    setEditButtons(parseButtonsFromPost(leader));
    setEditSendSilent(Boolean(leader.send_silent));
    setEditPinAfterSend(Boolean(leader.pin_after_send));
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
    const body: Parameters<typeof api.scheduledPosts.update>[1] = {
      name: editName.trim() || undefined,
      content: trimmed[0] || "",
      channel_id: editChannelId || undefined,
      ...(isCampaignEdit ? {} : { message_thread_id: editMessageThreadId }),
      pool_id: editPoolId > 0 ? editPoolId : null,
      media_ids: [],
      album_variants: av,
      album_order_mode: editAlbumOrderMode,
      pool_only_mode: editPoolId > 0 ? editPoolOnlyMode : false,
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
    if (editPoolId > 0) {
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
    await updateScheduled.mutateAsync({ id, body });
    setEditOpen(false);
    setEditing(null);
    setEditCampaignHint(null);
  }

  type DisplayRow =
    | { kind: "campaign"; campaign_group_id: string; posts: Array<Record<string, unknown>> }
    | { kind: "single"; post: Record<string, unknown> };

  const displayRows: DisplayRow[] = useMemo(() => {
    const flat = compactRecurringOnly
      ? (scheduledPosts as Array<Record<string, unknown>>).filter((p) => !!p.interval_minutes)
      : (scheduledPosts as Array<Record<string, unknown>>);
    const byCg = new Map<string, Array<Record<string, unknown>>>();
    const singles: Array<Record<string, unknown>> = [];
    for (const p of flat) {
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
  }, [scheduledPosts, compactRecurringOnly]);

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
                  <p className="text-slate-400 text-sm">
                    Channels are fixed for this campaign. To change targets, delete the campaign and create a new one.
                  </p>
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
                  <CaptionSnippetLibraryManageButton />
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
                        <CaptionSnippetInsertSelect
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
                <div className="flex flex-col gap-2 pt-1 border-t border-slate-600/50">
                  <label className="flex items-center gap-2 text-sm text-slate-300 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={editSendSilent}
                      onChange={(e) => setEditSendSilent(e.target.checked)}
                    />
                    Silent send
                  </label>
                  <label className="flex items-center gap-2 text-sm text-slate-300 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={editPinAfterSend}
                      onChange={(e) => setEditPinAfterSend(e.target.checked)}
                    />
                    Pin after send
                  </label>
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
                <select
                  value={editPoolId}
                  onChange={(e) => {
                    setEditPoolId(Number(e.target.value));
                    setEditAlbumVariants((prev) => prev.map((v) => ({ ...v, media_ids: [] })));
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
                  Choose <strong>No pool</strong> for text-only recurring posts (links/buttons still work).
                </p>
                {editPoolId > 0 && (
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
                      editPoolId
                        ? "Imports into the selected pool as pending — approve in Media Library"
                        : "Choose a specific pool in the dropdown above first (not “All approved”)"
                    }
                    onChange={(e) => {
                      const pid = editPoolId;
                      const input = e.target as HTMLInputElement;
                      const snapshot = input.files?.length ? Array.from(input.files) : [];
                      input.value = "";
                      if (!snapshot.length) return;
                      if (!pid) {
                        setEditUploadMsg("Choose a pool above first — uploads go into that pool (not “All approved”).");
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
                {!editPoolId && (
                  <p className="text-amber-400/90 text-xs mb-2">
                    Select a pool above to enable this import (pending in Media Library until approved).
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
                  {editPoolId > 0 && editPoolOnlyMode
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
          className={`mb-3 px-3 py-2 rounded text-sm ${
            triggerNotice.kind === "ok" ? "bg-emerald-900/40 text-emerald-200" : "bg-red-900/40 text-red-200"
          }`}
        >
          {triggerNotice.text}
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="w-full border border-slate-600 rounded-lg overflow-hidden">
          <thead className="bg-slate-700">
            <tr>
              <th className="text-left p-3">Name</th>
              <th className="text-left p-3">Channel</th>
              <th className="text-left p-3">Content</th>
              <th className="text-left p-3">Schedule / last sent</th>
              <th className="text-left p-3">Pool</th>
              <th className="text-left p-3">Status</th>
              <th className="text-left p-3">Actions</th>
            </tr>
          </thead>
          <tbody>
            {displayRows.map((row) => {
              const p =
                row.kind === "campaign"
                  ? row.posts[0]
                  : row.post;
              const channelCell =
                row.kind === "campaign"
                  ? row.posts.map((x) => String(x.channel_name || x.channel_id)).join(", ")
                  : String(p.channel_name || p.channel_id);
              const rowKey =
                row.kind === "campaign" ? `campaign-${row.campaign_group_id}` : String(p.id);
              const recurring = !!p.interval_minutes;
              const lastPost = p.last_posted_at;
              const nextRecurringIso = nextRecurringRunIso(lastPost, p.interval_minutes);
              const cvRow = p.content_variations;
              const rotating = Array.isArray(cvRow) && cvRow.length >= 2;
              const textPreview = String(p.content || "").slice(0, 40);
              const preview = rotating ? `${cvRow.length} captions (rotating)` : textPreview;
              const poolId = p.pool_id != null ? Number(p.pool_id) : 0;
              const poolName = poolId
                ? String(
                    (pools as Array<Record<string, unknown>>).find((x) => Number(x.id) === poolId)?.name ||
                      poolId
                  )
                : "—";
              const attUrls = Array.isArray(p.attachment_urls)
                ? (p.attachment_urls as string[]).filter((x) => String(x).trim())
                : [];
              const btnCount = parseButtonsFromPost(p).length;
              const flags = [
                p.send_silent ? "silent" : null,
                p.pin_after_send ? "pin after" : null,
                btnCount ? `${btnCount} btn` : null,
              ].filter(Boolean);
              return (
                <tr
                  key={rowKey}
                  className="border-t border-slate-600 hover:bg-slate-800/50 cursor-pointer"
                  onClick={() => openEditor(p)}
                  title="Click row to edit schedule, caption, and pool album options"
                >
                  <td className="p-3">
                    {String(p.name || "—")}
                    {row.kind === "campaign" ? (
                      <span className="ml-2 text-xs text-cyan-400/90">({row.posts.length} ch)</span>
                    ) : null}
                  </td>
                  <td className="p-3 max-w-[12rem] truncate" title={channelCell}>
                    {channelCell}
                  </td>
                  <td className="p-3 text-slate-400 text-sm">
                    {p.message_thread_id != null && p.message_thread_id !== undefined
                      ? `#${p.message_thread_id}`
                      : "—"}
                  </td>
                  <td className="p-3 text-slate-400 text-sm max-w-xs truncate" title={rotating ? String(cvRow.join(" | ")).slice(0, 500) : String(p.content || "")}>
                    {rotating ? preview : `${textPreview}${String(p.content || "").length > 40 ? "…" : ""}`}
                  </td>
                  <td
                    className="p-3 text-slate-400 text-sm max-w-[14rem]"
                    title={
                      recurring && lastPost
                        ? formatUtcWithLocalHint(String(lastPost))
                        : !recurring && p.scheduled_at
                          ? formatUtcWithLocalHint(String(p.scheduled_at))
                          : undefined
                    }
                  >
                    {recurring ? (
                      <>
                        <span className="block">Every {Number(p.interval_minutes)} min</span>
                        {nextRecurringIso ? (
                          <>
                            <span className="block text-xs mt-0.5 text-cyan-200 font-semibold">
                              Next: {formatLocalForDashboard(nextRecurringIso)} (your time)
                            </span>
                            <span className="block text-xs text-cyan-300/90 mt-0.5">
                              PT: {formatPtForDashboard(nextRecurringIso)}
                            </span>
                            <span className="block text-[11px] text-slate-500 mt-0.5">
                              Last UTC: {formatUtcForDashboard(String(lastPost))}
                            </span>
                          </>
                        ) : (
                          <span className="block text-xs text-amber-500/90 mt-0.5">Use &quot;Post now&quot; once</span>
                        )}
                      </>
                    ) : p.scheduled_at ? (
                      formatUtcForDashboard(String(p.scheduled_at))
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="p-3 text-slate-400 text-sm">
                    {poolName}
                    {attUrls.length > 0 ? (
                      <span className="text-slate-500 text-xs ml-1">({attUrls.length} promo)</span>
                    ) : null}
                    {flags.length > 0 ? (
                      <span className="block text-slate-500 text-xs mt-1">{flags.join(" · ")}</span>
                    ) : null}
                  </td>
                  <td className="p-3">
                    {recurring ? (
                      lastPost ? (
                        <span className="text-emerald-400 text-sm">Running</span>
                      ) : (
                        <span className="text-amber-400 text-sm">Start with Post now</span>
                      )
                    ) : p.sent_at ? (
                      <span className="text-emerald-400 text-sm">Sent</span>
                    ) : (
                      <span className="text-amber-400 text-sm">Pending</span>
                    )}
                  </td>
                  <td className="p-3 flex flex-wrap gap-2" onClick={(e) => e.stopPropagation()}>
                    {(recurring || !p.sent_at) && (
                      <button
                        type="button"
                        onClick={() => triggerScheduledPost.mutate({ id: Number(p.id) })}
                        disabled={triggerScheduledPost.isPending}
                        className="px-2 py-1 bg-slate-600 text-slate-200 rounded text-sm hover:bg-slate-500"
                        title={
                          row.kind === "campaign"
                            ? "Queues one Celery run for all channels in this campaign"
                            : undefined
                        }
                      >
                        Post now
                      </button>
                    )}
                    {scheduledPostHasAlbumOrPool(p) && (
                        <button
                          type="button"
                          onClick={() => triggerScheduledPost.mutate({ id: Number(p.id), reshuffle: true })}
                          disabled={triggerScheduledPost.isPending}
                          className="px-2 py-1 bg-violet-800/90 text-violet-100 rounded text-sm hover:bg-violet-700/90"
                          title={
                            row.kind === "campaign"
                              ? "Queue send to all campaign channels with promo/media order randomized for this run only (new Telegram messages). For one-time jobs that already ran, this is how you repost."
                              : "Randomize promo/media order for this send only and queue Celery (new Telegram message). One-time jobs that already ran can only be reposted this way."
                          }
                        >
                          Repost shuffled
                        </button>
                      )}
                    <button
                      onClick={() => deleteScheduledPost.mutate(Number(p.id))}
                      disabled={deleteScheduledPost.isPending}
                      className="px-2 py-1 bg-red-800/50 text-red-200 rounded text-sm hover:bg-red-700/50"
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              );
            })}
            {displayRows.length === 0 && (
              <tr>
                <td colSpan={7} className="p-4 text-slate-500 text-center">
                  {compactRecurringOnly ? "No recurring posting jobs." : "No scheduled posts."}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}