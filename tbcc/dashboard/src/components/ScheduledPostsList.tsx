import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import { useState } from "react";

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
  const [editAlbumSize, setEditAlbumSize] = useState(5);
  const [editRandomize, setEditRandomize] = useState(false);
  const [editMessageThreadId, setEditMessageThreadId] = useState<number | null>(null);

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
    mutationFn: (id: number) => api.scheduledPosts.trigger(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["scheduledPosts"] }),
  });

  function openEditor(p: Record<string, unknown>) {
    setEditing(p);
    setEditName(String(p.name || ""));
    const cv = p.content_variations;
    if (Array.isArray(cv) && cv.length >= 2) {
      setEditVariations(cv.map((x) => String(x ?? "")));
    } else {
      setEditVariations([String(p.content ?? "")]);
    }
    setEditChannelId(Number(p.channel_id || 0));
    setEditInterval(Number(p.interval_minutes || 30));
    setEditScheduledAt(isoToDatetimeLocal(p.scheduled_at as string | undefined));
    const pid = p.pool_id != null ? Number(p.pool_id) : 0;
    const pool = pid ? (poolMap[String(pid)] as Record<string, unknown> | undefined) : undefined;
    const poolDefaultAlbum = Number(pool?.album_size ?? 5);
    setEditAlbumSize(p.album_size != null ? Number(p.album_size) : poolDefaultAlbum);
    setEditRandomize(p.pool_randomize != null ? Boolean(p.pool_randomize) : !!pool?.randomize_queue);
    setEditMessageThreadId(
      p.message_thread_id != null && p.message_thread_id !== undefined ? Number(p.message_thread_id) : null
    );
    setEditOpen(true);
  }

  async function saveEditor() {
    if (!editing) return;
    const id = Number(editing.id);
    const recurring = !!editing.interval_minutes;
    const trimmed = editVariations.map((s) => s.trim()).filter(Boolean);
    const body: Parameters<typeof api.scheduledPosts.update>[1] = {
      name: editName.trim() || undefined,
      content: trimmed[0] || "",
      channel_id: editChannelId || undefined,
    };
    if (trimmed.length >= 2) {
      body.content_variations = trimmed;
      body.content = trimmed[0];
    } else {
      body.content_variations = [];
    }
    if (recurring) {
      body.interval_minutes = Math.max(1, editInterval);
    } else if (!editing.sent_at && editScheduledAt) {
      body.scheduled_at = datetimeLocalToIso(editScheduledAt);
    }
    const poolId = editing.pool_id != null ? Number(editing.pool_id) : 0;
    if (poolId > 0) {
      body.album_size = Math.min(10, Math.max(1, editAlbumSize));
      body.pool_randomize = editRandomize;
    }
    await updateScheduled.mutateAsync({ id, body });
    setEditOpen(false);
    setEditing(null);
  }

  const rows = compactRecurringOnly
    ? (scheduledPosts as Array<Record<string, unknown>>).filter((p) => !!p.interval_minutes)
    : (scheduledPosts as Array<Record<string, unknown>>);

  return (
    <>
      {editOpen && editing && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
          role="dialog"
          aria-labelledby="scheduled-edit-title"
          onClick={(e) => e.target === e.currentTarget && setEditOpen(false)}
        >
          <div className="bg-slate-800 border border-slate-600 rounded-lg p-6 max-w-lg w-full shadow-xl max-h-[90vh] overflow-y-auto">
            <h2 id="scheduled-edit-title" className="text-lg font-medium mb-3">
              Edit scheduled post
            </h2>
            <p className="text-slate-500 text-xs mb-3">
              {editing.interval_minutes
                ? "Recurring job — interval is how often this post runs. With 2+ caption boxes filled, captions rotate in order each run (e.g. hourly: A, B, A…). Album size / randomize apply to the linked pool’s media queue."
                : "One-time schedule — set date/time below."}
            </p>
            <div className="space-y-3 mb-4">
              <input
                type="text"
                value={editName}
                onChange={(e) => setEditName(e.target.value)}
                className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200"
                placeholder="Name (optional)"
              />
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
              <span className="block text-slate-400 text-sm">
                Caption{editVariations.length > 1 ? "s (rotate in order)" : " / text"}
              </span>
              <div className="space-y-2">
                {editVariations.map((line, i) => (
                  <div key={i} className="flex gap-2 items-start">
                    <textarea
                      value={line}
                      onChange={(e) => {
                        const v = e.target.value;
                        setEditVariations((prev) => prev.map((p, j) => (j === i ? v : p)));
                      }}
                      rows={i === 0 ? 5 : 4}
                      className="flex-1 bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200"
                      placeholder={i === 0 ? "Text content (caption)" : `Caption variation ${i + 1}`}
                    />
                    {editVariations.length > 1 && (
                      <button
                        type="button"
                        onClick={() => setEditVariations((prev) => prev.filter((_, j) => j !== i))}
                        className="mt-1 px-2 py-1 text-red-400 hover:bg-red-900/30 rounded shrink-0"
                      >
                        ✕
                      </button>
                    )}
                  </div>
                ))}
                <button
                  type="button"
                  onClick={() => setEditVariations((prev) => [...prev, ""])}
                  className="text-sm text-cyan-400 hover:text-cyan-300"
                >
                  + Add caption variation
                </button>
              </div>
              {editing.interval_minutes ? (
                <label className="flex flex-wrap items-center gap-2 text-sm">
                  <span className="text-slate-400">Post every</span>
                  <input
                    type="number"
                    min={1}
                    value={editInterval}
                    onChange={(e) => setEditInterval(Math.max(1, Number(e.target.value) || 1))}
                    className="w-24 bg-slate-700 border border-slate-600 rounded px-2 py-1 text-slate-200"
                  />
                  <span className="text-slate-500">minutes</span>
                </label>
              ) : (
                !editing.sent_at && (
                  <label className="block text-sm">
                    <span className="text-slate-400 block mb-1">Scheduled at</span>
                    <input
                      type="datetime-local"
                      value={editScheduledAt}
                      onChange={(e) => setEditScheduledAt(e.target.value)}
                      className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200"
                    />
                  </label>
                )
              )}
              {editing.pool_id != null && Number(editing.pool_id) > 0 && (
                <div className="border border-slate-600 rounded-lg p-3 space-y-2 bg-slate-900/40">
                  <p className="text-slate-400 text-xs">
                    Pool #{String(editing.pool_id)} — album size & randomize are saved on <strong>this job only</strong>{" "}
                    (override pool defaults for this cron / schedule).
                  </p>
                  <div className="flex gap-4 flex-wrap">
                    <label className="flex items-center gap-2 text-sm">
                      <span className="text-slate-400">Album size</span>
                      <input
                        type="number"
                        min={1}
                        max={10}
                        value={editAlbumSize}
                        onChange={(e) => setEditAlbumSize(Number(e.target.value))}
                        className="w-16 bg-slate-700 border border-slate-600 rounded px-2 py-1 text-slate-200"
                      />
                    </label>
                    <label className="flex items-center gap-2 text-slate-300 text-sm">
                      <input
                        type="checkbox"
                        checked={editRandomize}
                        onChange={(e) => setEditRandomize(e.target.checked)}
                      />
                      Randomize picks from pool (not consecutive queue order)
                    </label>
                  </div>
                </div>
              )}
            </div>
            {updateScheduled.isError && (
              <p className="text-red-300 text-sm mb-2">{(updateScheduled.error as Error)?.message}</p>
            )}
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setEditOpen(false)}
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

      <div className="overflow-x-auto">
        <table className="w-full border border-slate-600 rounded-lg overflow-hidden">
          <thead className="bg-slate-700">
            <tr>
              <th className="text-left p-3">Name</th>
              <th className="text-left p-3">Channel</th>
              <th className="text-left p-3">Content</th>
              <th className="text-left p-3">Schedule</th>
              <th className="text-left p-3">Pool</th>
              <th className="text-left p-3">Status</th>
              <th className="text-left p-3">Actions</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p: Record<string, unknown>) => {
              const recurring = !!p.interval_minutes;
              const lastPost = p.last_posted_at;
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
              return (
                <tr
                  key={String(p.id)}
                  className="border-t border-slate-600 hover:bg-slate-800/50 cursor-pointer"
                  onClick={() => openEditor(p)}
                  title="Click row to edit schedule, caption, and pool album options"
                >
                  <td className="p-3">{String(p.name || "—")}</td>
                  <td className="p-3">{String(p.channel_name || p.channel_id)}</td>
                  <td className="p-3 text-slate-400 text-sm">
                    {p.message_thread_id != null && p.message_thread_id !== undefined
                      ? `#${p.message_thread_id}`
                      : "—"}
                  </td>
                  <td className="p-3 text-slate-400 text-sm max-w-xs truncate" title={rotating ? String(cvRow.join(" | ")).slice(0, 500) : String(p.content || "")}>
                    {rotating ? preview : `${textPreview}${String(p.content || "").length > 40 ? "…" : ""}`}
                  </td>
                  <td className="p-3 text-slate-400 text-sm">
                    {recurring ? (
                      <>Every {p.interval_minutes} min</>
                    ) : p.scheduled_at ? (
                      String(p.scheduled_at).slice(0, 19)
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="p-3 text-slate-400 text-sm">{poolName}</td>
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
                  <td className="p-3 flex gap-2" onClick={(e) => e.stopPropagation()}>
                    {(recurring || !p.sent_at) && (
                      <button
                        onClick={() => triggerScheduledPost.mutate(Number(p.id))}
                        disabled={triggerScheduledPost.isPending}
                        className="px-2 py-1 bg-slate-600 text-slate-200 rounded text-sm hover:bg-slate-500"
                      >
                        Post now
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
            {rows.length === 0 && (
              <tr>
                <td colSpan={8} className="p-4 text-slate-500 text-center">
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
