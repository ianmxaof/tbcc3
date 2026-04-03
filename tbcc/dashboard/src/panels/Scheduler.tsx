import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";
import { useState } from "react";
import { ScheduledPostsList } from "../components/ScheduledPostsList";

const INTERVAL_OPTIONS = [15, 30, 60, 120, 360];

export function Scheduler() {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [channelId, setChannelId] = useState<number>(0);
  /** One box = single caption; 2+ non-empty = rotate in order each time the job runs */
  const [captionVariations, setCaptionVariations] = useState<string[]>([""]);
  const [scheduledAt, setScheduledAt] = useState("");
  const [isRecurring, setIsRecurring] = useState(false);
  const [intervalMinutes, setIntervalMinutes] = useState(30);
  const [selectedMediaIds, setSelectedMediaIds] = useState<number[]>([]);
  const [poolId, setPoolId] = useState<number>(0);
  const [scheduleAlbumSize, setScheduleAlbumSize] = useState(5);
  const [schedulePoolRandomize, setSchedulePoolRandomize] = useState(false);
  const [buttons, setButtons] = useState<Array<{ text: string; url: string }>>([]);
  const [uploadMsg, setUploadMsg] = useState<string | null>(null);
  /** null = post to main chat; number = Telegram forum topic id (message_thread_id) */
  const [messageThreadId, setMessageThreadId] = useState<number | null>(null);

  const { data: pools = [] } = useQuery({
    queryKey: ["pools"],
    queryFn: () => api.pools.list(),
  });
  const { data: channels = [] } = useQuery({
    queryKey: ["channels"],
    queryFn: () => api.channels.list(),
  });
  const { data: forumTopicsRes } = useQuery({
    queryKey: ["forumTopics", channelId],
    queryFn: () => api.channels.forumTopics(channelId),
    enabled: channelId > 0,
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
  const uploadToPool = useMutation({
    mutationFn: async ({ files, pid }: { files: FileList; pid: number }) => {
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
      const base: Parameters<typeof api.scheduledPosts.create>[0] = {
        name: name || undefined,
        channel_id: channelId,
        ...(messageThreadId != null ? { message_thread_id: messageThreadId } : {}),
        content: trimmed[0] || "",
        media_ids: selectedMediaIds.length > 0 ? selectedMediaIds : undefined,
        pool_id: poolId || undefined,
        buttons: buttons.some((b) => b.text.trim() && b.url.trim()) ? buttons.filter((b) => b.text.trim() && b.url.trim()) : undefined,
        scheduled_at: isRecurring ? undefined : scheduledAtIso,
        interval_minutes: isRecurring ? intervalMinutes : undefined,
        ...(poolId > 0
          ? {
              album_size: Math.min(10, Math.max(1, scheduleAlbumSize)),
              pool_randomize: schedulePoolRandomize,
            }
          : {}),
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
      setChannelId(0);
      setMessageThreadId(null);
      setCaptionVariations([""]);
      setScheduledAt("");
      setSelectedMediaIds([]);
      setPoolId(0);
      setScheduleAlbumSize(5);
      setSchedulePoolRandomize(false);
      setButtons([]);
    },
  });

  const toggleMedia = (id: number) => {
    setSelectedMediaIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  };

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

  return (
    <div>
      <h1 className="text-2xl font-semibold mb-4">Scheduler</h1>
      <p className="text-slate-400 mb-6">
        Pool posting runs every 5 minutes. Scheduled posts support one-time or recurring intervals.
        For <strong>forum supergroups</strong>, pick a <strong>topic</strong> so content goes to that subtopic (same as
        extension &quot;Forum topic&quot;).
      </p>

      <div className="bg-slate-800 rounded-lg p-4 mb-6 max-w-2xl">
        <h2 className="text-lg font-medium mb-3">Pool intervals</h2>
        {chartData.length > 0 ? (
          <ResponsiveContainer width="100%" height={200}>
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

      <div className="overflow-x-auto mb-8">
        <table className="w-full border border-slate-600 rounded-lg overflow-hidden">
          <thead className="bg-slate-700">
            <tr>
              <th className="text-left p-3">Pool</th>
              <th className="text-left p-3">Interval (min)</th>
              <th className="text-left p-3">Last posted</th>
            </tr>
          </thead>
          <tbody>
            {pools.map((p: Record<string, unknown>) => (
              <tr key={String(p.id)} className="border-t border-slate-600 hover:bg-slate-800/50">
                <td className="p-3">{String(p.name)}</td>
                <td className="p-3">{String(p.interval_minutes)}</td>
                <td className="p-3 text-slate-400 text-sm">
                  {p.last_posted ? String(p.last_posted).slice(0, 19) : "Never"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h2 className="text-xl font-semibold mb-3">Scheduled Posts</h2>
      <p className="text-slate-400 mb-4">
        Create text posts with optional media and inline buttons. One-time or recurring intervals.
        For recurring, &quot;Post now&quot; starts the cycle from the current time. Add a second caption
        box to <strong>rotate captions</strong> in order each run (e.g. every hour: caption A, then B, then A…).
      </p>

      <div className="bg-slate-800 rounded-lg p-4 mb-6 max-w-4xl">
        <h3 className="text-lg font-medium mb-3">Add scheduled post</h3>
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
            <select
              value={channelId}
              onChange={(e) => {
                setChannelId(Number(e.target.value));
                setMessageThreadId(null);
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
            {channelId > 0 && (
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
              <span className="text-slate-400 text-sm">
                Caption{captionVariations.length > 1 ? "s (rotate in order)" : ""}
              </span>
              {captionVariations.map((line, i) => (
                <div key={i} className="flex gap-2 items-start">
                  <textarea
                    placeholder={i === 0 ? "Text content (caption)" : `Caption variation ${i + 1}`}
                    value={line}
                    onChange={(e) => {
                      const v = e.target.value;
                      setCaptionVariations((prev) => prev.map((p, j) => (j === i ? v : p)));
                    }}
                    rows={i === 0 ? 4 : 3}
                    className="flex-1 bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200"
                  />
                  {captionVariations.length > 1 && (
                    <button
                      type="button"
                      onClick={() => setCaptionVariations((prev) => prev.filter((_, j) => j !== i))}
                      className="mt-1 px-2 py-1 text-red-400 hover:bg-red-900/30 rounded shrink-0"
                      title="Remove this caption"
                    >
                      ✕
                    </button>
                  )}
                </div>
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
              {buttons.map((b, i) => (
                <div key={i} className="flex gap-2 mb-2">
                  <input
                    placeholder="Button text"
                    value={b.text}
                    onChange={(e) => updateButton(i, "text", e.target.value)}
                    className="flex-1 bg-slate-700 border border-slate-600 rounded px-2 py-1 text-slate-200 text-sm"
                  />
                  <input
                    placeholder="https://..."
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
            </div>
          </div>
          <div>
            <p className="text-slate-400 text-sm mb-2">
              Media (optional) — thumbnails are from <strong>approved</strong> items. Choosing a pool filters the grid
              to that pool and sets the pool auto-pick for this schedule.
            </p>
            <select
              value={poolId}
              onChange={(e) => {
                setPoolId(Number(e.target.value));
                setSelectedMediaIds([]);
              }}
              className="w-full mb-2 bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200 text-sm"
            >
              <option value={0}>All approved (any pool)</option>
              {(pools as Array<{ id: number; name?: string }>).map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name || `Pool ${p.id}`} (media + optional auto-pick)
                </option>
              ))}
            </select>
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
                </div>
              </div>
            )}
            <label className="flex flex-wrap items-center gap-2 text-slate-400 text-xs mb-2 cursor-pointer">
              <span>Upload local files into pool:</span>
              <input
                type="file"
                accept="image/*,video/*"
                multiple
                disabled={!poolId || uploadToPool.isPending}
                onChange={(e) => {
                  const pid = poolId;
                  const fl = e.target.files;
                  e.target.value = "";
                  if (!pid || !fl?.length) return;
                  uploadToPool.mutate({ files: fl, pid });
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
                Select a pool above to enable uploads (files are imported into that pool as pending — approve in Media
                Library).
              </p>
            )}
            <div className="flex flex-wrap gap-2 max-h-64 overflow-y-auto">
              {(media as Array<Record<string, unknown>>).map((m) => {
                const id = Number(m.id);
                const sel = selectedMediaIds.includes(id);
                return (
                  <button
                    key={id}
                    type="button"
                    onClick={() => toggleMedia(id)}
                    className={`relative w-16 h-16 rounded border-2 overflow-hidden flex items-center justify-center text-xs ${
                      sel ? "border-cyan-500 bg-cyan-900/30" : "border-slate-600 bg-slate-700 hover:border-slate-500"
                    }`}
                    title={`${m.media_type || "media"} #${id}`}
                  >
                    <img
                      src={api.media.thumbnailUrl(id)}
                      alt=""
                      className="absolute inset-0 w-full h-full object-cover"
                      onError={(ev) => {
                        (ev.target as HTMLImageElement).style.display = "none";
                      }}
                    />
                    <span className="relative z-[1] drop-shadow-md opacity-90">
                      {m.media_type === "photo" ? "🖼" : m.media_type === "video" ? "🎬" : "📎"}
                    </span>
                  </button>
                );
              })}
            </div>
            <p className="text-slate-500 text-xs mt-1">
              {selectedMediaIds.length} selected. If <strong>pool</strong> is set, scheduled posts use the next batch
              from that pool unless you clear the pool (0) and rely on selected IDs only.
            </p>
          </div>
        </div>
        <button
          onClick={() => createScheduledPost.mutate()}
          disabled={
            createScheduledPost.isPending ||
            !channelId ||
            (!captionVariations.some((s) => s.trim()) && selectedMediaIds.length === 0 && !poolId)
          }
          className="mt-4 px-4 py-2 bg-cyan-600 text-white rounded hover:bg-cyan-500 disabled:opacity-50"
        >
          {createScheduledPost.isPending ? "Creating..." : "Schedule"}
        </button>
      </div>

      <h2 className="text-xl font-semibold mb-2">Scheduled posts</h2>
      <p className="text-slate-400 text-sm mb-4">
        Click a row to edit captions (including rotating variations), posting interval, or pool album options.
      </p>
      <ScheduledPostsList />
    </div>
  );
}
