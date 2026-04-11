import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import { useState } from "react";
import { QueryErrorBanner } from "../components/QueryErrorBanner";

export function ContentPools() {
  const queryClient = useQueryClient();
  const {
    data: pools = [],
    isPending: poolsPending,
    isError: poolsError,
    error: poolsErr,
    refetch: refetchPools,
  } = useQuery({
    queryKey: ["pools"],
    queryFn: () => api.pools.list(),
  });
  const {
    data: channels = [],
    isPending: channelsPending,
    isError: channelsError,
    error: channelsErr,
    refetch: refetchChannels,
  } = useQuery({
    queryKey: ["channels"],
    queryFn: () => api.channels.list(),
  });
  const [name, setName] = useState("");
  const [channelId, setChannelId] = useState<number>(0);
  const [albumSize, setAlbumSize] = useState(5);
  const [intervalMinutes, setIntervalMinutes] = useState(60);
  const [randomizeQueue, setRandomizeQueue] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [editId, setEditId] = useState(0);
  const [editName, setEditName] = useState("");
  const [editChannelId, setEditChannelId] = useState(0);
  const [editAlbumSize, setEditAlbumSize] = useState(5);
  const [editInterval, setEditInterval] = useState(60);
  const [editRandomize, setEditRandomize] = useState(false);
  const [channelName, setChannelName] = useState("");
  const [channelIdentifier, setChannelIdentifier] = useState("");
  const [channelInviteLink, setChannelInviteLink] = useState("");

  const createChannel = useMutation({
    mutationFn: () =>
      api.channels.create({
        name: channelName || "New channel",
        identifier: channelIdentifier,
        invite_link: channelInviteLink || undefined,
      }),
    onSuccess: () => {
      refetchChannels();
      setChannelName("");
      setChannelIdentifier("");
      setChannelInviteLink("");
    },
  });

  const updateChannel = useMutation({
    mutationFn: (args: { id: number; invite_link?: string; webhook_url?: string }) =>
      api.channels.update(args.id, {
        ...(args.invite_link !== undefined ? { invite_link: args.invite_link } : {}),
        ...(args.webhook_url !== undefined ? { webhook_url: args.webhook_url } : {}),
      }),
    onSuccess: () => refetchChannels(),
  });

  const createPool = useMutation({
    mutationFn: () =>
      api.pools.create({
        name: name || "New pool",
        channel_id: channelId || 1,
        album_size: albumSize,
        interval_minutes: intervalMinutes,
        randomize_queue: randomizeQueue,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["pools"] });
      setName("");
      setChannelId(0);
      setRandomizeQueue(false);
    },
  });

  const updatePool = useMutation({
    mutationFn: () =>
      api.pools.update(editId, {
        name: editName.trim() || undefined,
        channel_id: editChannelId || undefined,
        album_size: editAlbumSize,
        interval_minutes: editInterval,
        randomize_queue: editRandomize,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["pools"] });
      setEditOpen(false);
    },
  });

  function openPoolEditor(p: Record<string, unknown>) {
    setEditId(Number(p.id));
    setEditName(String(p.name || ""));
    setEditChannelId(Number(p.channel_id || 0));
    setEditAlbumSize(Number(p.album_size ?? 5));
    setEditInterval(Number(p.interval_minutes ?? 60));
    setEditRandomize(!!p.randomize_queue);
    setEditOpen(true);
  }

  const [postFeedback, setPostFeedback] = useState<{ poolId: number; msg: string } | null>(null);
  const triggerPost = useMutation({
    mutationFn: (poolId: number) => api.jobs.triggerPost(poolId),
    onSuccess: (_, poolId) => {
      queryClient.invalidateQueries({ queryKey: ["pools"] });
      queryClient.invalidateQueries({ queryKey: ["media"] });
      const pool = (pools as Array<Record<string, unknown>>).find((p) => Number(p.id) === poolId);
      const approved = Number(pool?.approved_count ?? 0);
      const msg =
        approved > 0
          ? `Post queued (${approved} item${approved === 1 ? "" : "s"}). The worker will process it shortly.`
          : "Task queued but 0 approved items in this pool. Approve media in the Media Library first.";
      setPostFeedback({ poolId, msg });
      setTimeout(() => setPostFeedback(null), 5000);
    },
    onError: (err: Error) => {
      setPostFeedback({ poolId: -1, msg: `Error: ${err.message}` });
      setTimeout(() => setPostFeedback(null), 5000);
    },
  });

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-semibold">Content Pools</h1>
        <button
          onClick={() => {
            void refetchPools();
            void refetchChannels();
          }}
          className="px-3 py-1 rounded bg-slate-600 text-slate-200 hover:bg-slate-500"
        >
          Refresh
        </button>
      </div>
      {poolsError && (
        <QueryErrorBanner
          title="Could not load pools"
          message={String((poolsErr as Error)?.message ?? poolsErr)}
          onRetry={() => void refetchPools()}
        />
      )}
      {channelsError && (
        <QueryErrorBanner
          title="Could not load channels"
          message={String((channelsErr as Error)?.message ?? channelsErr)}
          onRetry={() => void refetchChannels()}
        />
      )}
      <p className="text-slate-500 text-xs mb-4 max-w-2xl">
        If this page used to hang on &quot;Loading…&quot;, the API was not returning (check TBCC backend on port 8000 and{" "}
        <code className="text-slate-400">DATABASE_URL</code>). Channels load independently of the pools table below.
      </p>
      {postFeedback && (
        <div
          className={`mb-4 px-4 py-2 rounded-lg text-sm ${
            postFeedback.msg.startsWith("Error")
              ? "bg-red-900/50 text-red-200"
              : "bg-slate-700 text-slate-200"
          }`}
        >
          {postFeedback.msg}
        </div>
      )}
      <div className="bg-slate-800 rounded-lg p-4 mb-6 max-w-2xl">
        <h2 className="text-lg font-medium mb-3">Add channel</h2>
        <div className="space-y-2 mb-4">
          <div className="flex gap-2">
            <input
              type="text"
              placeholder="Channel name"
              value={channelName}
              onChange={(e) => setChannelName(e.target.value)}
              className="flex-1 bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200"
            />
            <input
              type="text"
              placeholder="@username or -100..."
              value={channelIdentifier}
              onChange={(e) => setChannelIdentifier(e.target.value)}
              className="flex-1 bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200"
            />
          </div>
          <input
            type="text"
            placeholder="Invite link (optional) — t.me/joinchat/xxx or t.me/channel"
            value={channelInviteLink}
            onChange={(e) => setChannelInviteLink(e.target.value)}
            className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200 text-sm"
          />
          <button
            onClick={() => createChannel.mutate()}
            disabled={createChannel.isPending || !channelIdentifier}
            className="px-4 py-2 bg-slate-600 text-white rounded hover:bg-slate-500 disabled:opacity-50"
          >
            Add
          </button>
        </div>
        <h2 className="text-lg font-medium mb-3">Channels</h2>
        <div className="overflow-x-auto mb-4">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-400 border-b border-slate-600">
                <th className="pb-2 pr-4">Name</th>
                <th className="pb-2 pr-4">Identifier</th>
                <th className="pb-2 pr-4">Invite link</th>
                <th className="pb-2 pr-4 min-w-[200px]">Outbound webhook</th>
              </tr>
            </thead>
            <tbody>
              {channelsPending && !channels.length ? (
                <tr>
                  <td colSpan={3} className="py-3 text-slate-500">
                    Loading channels…
                  </td>
                </tr>
              ) : null}
              {!channelsPending && !channelsError && !(channels as Array<unknown>).length ? (
                <tr>
                  <td colSpan={3} className="py-3 text-slate-500">
                    No channels yet — add one above (name + @username or channel id).
                  </td>
                </tr>
              ) : null}
              {(channels as Array<Record<string, unknown>>).map((c) => (
                <tr key={String(c.id)} className="border-b border-slate-700/50">
                  <td className="py-2 pr-4">{String(c.name || c.identifier || c.id)}</td>
                  <td className="py-2 pr-4 font-mono text-xs">{String(c.identifier || "—")}</td>
                  <td className="py-2 pr-4">
                    <input
                      key={`${c.id}-${c.invite_link || ""}`}
                      type="text"
                      placeholder="t.me/joinchat/..."
                      defaultValue={String(c.invite_link || "")}
                      onBlur={(e) => {
                        const v = e.target.value.trim();
                        if ((c.invite_link as string) !== v) {
                          updateChannel.mutate({ id: Number(c.id), invite_link: v });
                        }
                      }}
                      className="w-full max-w-xs bg-slate-700 border border-slate-600 rounded px-2 py-1 text-slate-200 text-xs"
                    />
                  </td>
                  <td className="py-2 pr-4">
                    <input
                      key={`wh-${c.id}-${String(c.webhook_url || "")}`}
                      type="url"
                      placeholder="https://… (Discord/Zapier)"
                      defaultValue={String(c.webhook_url || "")}
                      onBlur={(e) => {
                        const v = e.target.value.trim();
                        if (String(c.webhook_url || "") !== v) {
                          updateChannel.mutate({ id: Number(c.id), webhook_url: v });
                        }
                      }}
                      className="w-full max-w-md bg-slate-700 border border-slate-600 rounded px-2 py-1 text-slate-200 text-xs"
                      title="POST JSON when a scheduled post is sent or a pool album posts to this channel"
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <h2 className="text-lg font-medium mb-3">Create pool</h2>
        <div className="space-y-2">
          <input
            type="text"
            placeholder="Name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200"
          />
          <select
            value={channelId}
            onChange={(e) => setChannelId(Number(e.target.value))}
            className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200"
          >
            <option value={0}>Select channel</option>
            {(channels as Array<{ id: number; name?: string; identifier?: string }>).map((c) => (
              <option key={c.id} value={c.id}>
                {c.name || c.identifier || `#${c.id}`}
              </option>
            ))}
          </select>
          <div className="flex gap-4">
            <label className="flex items-center gap-2">
              <span className="text-slate-400">Album size</span>
              <input
                type="number"
                min={1}
                max={10}
                value={albumSize}
                onChange={(e) => setAlbumSize(Number(e.target.value))}
                className="w-16 bg-slate-700 border border-slate-600 rounded px-2 py-1 text-slate-200"
              />
            </label>
            <label className="flex items-center gap-2">
              <span className="text-slate-400">Interval (min)</span>
              <input
                type="number"
                min={1}
                value={intervalMinutes}
                onChange={(e) => setIntervalMinutes(Number(e.target.value))}
                className="w-20 bg-slate-700 border border-slate-600 rounded px-2 py-1 text-slate-200"
              />
            </label>
            <label className="flex items-center gap-2 text-slate-300 text-sm">
              <input
                type="checkbox"
                checked={randomizeQueue}
                onChange={(e) => setRandomizeQueue(e.target.checked)}
              />
              Randomize album picks
            </label>
          </div>
          <button
            onClick={() => createPool.mutate()}
            disabled={createPool.isPending || !channelId}
            className="px-4 py-2 bg-cyan-600 text-white rounded hover:bg-cyan-500 disabled:opacity-50"
          >
            {createPool.isPending ? "Creating..." : "Create"}
          </button>
        </div>
      </div>

      {editOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" role="dialog">
          <div className="bg-slate-800 border border-slate-600 rounded-lg p-6 max-w-md w-full shadow-xl">
            <h2 className="text-lg font-medium mb-3">Edit pool</h2>
            <div className="space-y-3 mb-4">
              <input
                type="text"
                value={editName}
                onChange={(e) => setEditName(e.target.value)}
                className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200"
                placeholder="Name"
              />
              <select
                value={editChannelId}
                onChange={(e) => setEditChannelId(Number(e.target.value))}
                className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200"
              >
                <option value={0}>Select channel</option>
                {(channels as Array<{ id: number; name?: string; identifier?: string }>).map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name || c.identifier || `#${c.id}`}
                  </option>
                ))}
              </select>
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
                <label className="flex items-center gap-2 text-sm">
                  <span className="text-slate-400">Interval (min)</span>
                  <input
                    type="number"
                    min={1}
                    value={editInterval}
                    onChange={(e) => setEditInterval(Number(e.target.value))}
                    className="w-20 bg-slate-700 border border-slate-600 rounded px-2 py-1 text-slate-200"
                  />
                </label>
              </div>
              <label className="flex items-center gap-2 text-slate-300 text-sm">
                <input
                  type="checkbox"
                  checked={editRandomize}
                  onChange={(e) => setEditRandomize(e.target.checked)}
                />
                Randomize which approved items go into each album (cron / Post now)
              </label>
            </div>
            {updatePool.isError && (
              <p className="text-red-300 text-sm mb-2">{updatePool.error?.message}</p>
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
                onClick={() => updatePool.mutate()}
                disabled={updatePool.isPending || !editChannelId}
                className="px-3 py-2 rounded bg-cyan-600 text-white hover:bg-cyan-500 disabled:opacity-50"
              >
                {updatePool.isPending ? "Saving…" : "Save"}
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="w-full border border-slate-600 rounded-lg overflow-hidden">
          <thead className="bg-slate-700">
            <tr>
              <th className="text-left p-3">ID</th>
              <th className="text-left p-3">Name</th>
              <th className="text-left p-3">Channel ID</th>
              <th className="text-left p-3">Queued</th>
              <th className="text-left p-3">Album size</th>
              <th className="text-left p-3">Interval (min)</th>
              <th className="text-left p-3">Last posted</th>
              <th className="text-left p-3">Actions</th>
            </tr>
          </thead>
          <tbody>
            {poolsPending && !pools.length ? (
              <tr>
                <td colSpan={8} className="p-4 text-slate-500">
                  Loading pools…
                </td>
              </tr>
            ) : null}
            {!poolsPending && poolsError && !pools.length ? (
              <tr>
                <td colSpan={8} className="p-4 text-red-300/90">
                  Pools list unavailable — fix the error above or check the backend.
                </td>
              </tr>
            ) : null}
            {!poolsPending && !poolsError && !pools.length ? (
              <tr>
                <td colSpan={8} className="p-4 text-slate-500">
                  No pools yet — create one in the form above (requires at least one channel).
                </td>
              </tr>
            ) : null}
            {pools.map((p: Record<string, unknown>) => (
              <tr
                key={String(p.id)}
                className="border-t border-slate-600 hover:bg-slate-800/50 cursor-pointer"
                onClick={() => openPoolEditor(p)}
                title="Click row to edit pool"
              >
                <td className="p-3">{String(p.id)}</td>
                <td className="p-3">{String(p.name)}</td>
                <td className="p-3">{String(p.channel_id)}</td>
                <td className="p-3">
                  <span className={Number(p.approved_count ?? 0) > 0 ? "text-cyan-300" : "text-slate-500"}>
                    {String(p.approved_count ?? 0)}/{String(p.album_size ?? 5)}
                  </span>
                </td>
                <td className="p-3">{String(p.album_size)}</td>
                <td className="p-3">
                  {String(p.interval_minutes)}
                  {p.randomize_queue ? (
                    <span className="ml-2 text-xs text-amber-400" title="Randomize enabled">
                      shuf
                    </span>
                  ) : null}
                </td>
                <td className="p-3 text-slate-400 text-sm">
                  {p.last_posted ? String(p.last_posted).slice(0, 19) : "—"}
                </td>
                <td className="p-3">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      triggerPost.mutate(Number(p.id));
                    }}
                    disabled={triggerPost.isPending}
                    className="px-2 py-1 bg-slate-600 text-slate-200 rounded text-sm hover:bg-slate-500"
                  >
                    Post now
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
