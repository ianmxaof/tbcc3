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
  const [autoPostEnabled, setAutoPostEnabled] = useState(true);
  const [randomizeQueue, setRandomizeQueue] = useState(false);
  const [routeSlugs, setRouteSlugs] = useState("");
  const [routeNsfwTiers, setRouteNsfwTiers] = useState("");
  const [routePriority, setRoutePriority] = useState(100);
  const [editOpen, setEditOpen] = useState(false);
  const [editId, setEditId] = useState(0);
  const [editName, setEditName] = useState("");
  const [editChannelId, setEditChannelId] = useState(0);
  const [editAlbumSize, setEditAlbumSize] = useState(5);
  const [editInterval, setEditInterval] = useState(60);
  const [editAutoPostEnabled, setEditAutoPostEnabled] = useState(true);
  const [editRandomize, setEditRandomize] = useState(false);
  const [editRouteSlugs, setEditRouteSlugs] = useState("");
  const [editRouteNsfwTiers, setEditRouteNsfwTiers] = useState("");
  const [editRoutePriority, setEditRoutePriority] = useState(100);
  const [channelName, setChannelName] = useState("");
  const [channelIdentifier, setChannelIdentifier] = useState("");
  const [channelInviteLink, setChannelInviteLink] = useState("");
  const [postFeedback, setPostFeedback] = useState<{ poolId: number; msg: string } | null>(null);

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

  const deleteChannel = useMutation({
    mutationFn: (id: number) => api.channels.deleteChannel(id),
    onSuccess: (_, id) => {
      void refetchChannels();
      queryClient.invalidateQueries({ queryKey: ["pools"] });
      queryClient.invalidateQueries({ queryKey: ["media"] });
      queryClient.invalidateQueries({ queryKey: ["sources"] });
      queryClient.invalidateQueries({ queryKey: ["scheduledPosts"] });
      queryClient.invalidateQueries({ queryKey: ["subscriptionPlans"] });
      if (channelId === id) setChannelId(0);
      if (editOpen && editChannelId === id) setEditOpen(false);
    },
    onError: (err: Error) => {
      setPostFeedback({ poolId: -1, msg: `Error: ${err.message}` });
      setTimeout(() => setPostFeedback(null), 5000);
    },
  });

  const createPool = useMutation({
    mutationFn: () =>
      api.pools.create({
        name: name || "New pool",
        channel_id: channelId || 1,
        album_size: albumSize,
        interval_minutes: intervalMinutes,
        auto_post_enabled: autoPostEnabled,
        randomize_queue: randomizeQueue,
        route_match_tag_slugs: routeSlugs.trim() || undefined,
        route_nsfw_tiers: routeNsfwTiers.trim() || undefined,
        route_priority: routePriority,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["pools"] });
      setName("");
      setChannelId(0);
      setAutoPostEnabled(true);
      setRandomizeQueue(false);
      setRouteSlugs("");
      setRouteNsfwTiers("");
      setRoutePriority(100);
    },
  });

  const updatePool = useMutation({
    mutationFn: () =>
      api.pools.update(editId, {
        name: editName.trim() || undefined,
        channel_id: editChannelId || undefined,
        album_size: editAlbumSize,
        interval_minutes: editInterval,
        auto_post_enabled: editAutoPostEnabled,
        randomize_queue: editRandomize,
        route_match_tag_slugs: editRouteSlugs.trim() || null,
        route_nsfw_tiers: editRouteNsfwTiers.trim() || null,
        route_priority: editRoutePriority,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["pools"] });
      setEditOpen(false);
    },
  });

  const deletePool = useMutation({
    mutationFn: (id: number) => api.pools.deletePool(id),
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: ["pools"] });
      queryClient.invalidateQueries({ queryKey: ["media"] });
      queryClient.invalidateQueries({ queryKey: ["sources"] });
      queryClient.invalidateQueries({ queryKey: ["scheduledPosts"] });
      if (editOpen && editId === id) setEditOpen(false);
    },
    onError: (err: Error) => {
      setPostFeedback({ poolId: -1, msg: `Error: ${err.message}` });
      setTimeout(() => setPostFeedback(null), 5000);
    },
  });

  function openPoolEditor(p: Record<string, unknown>) {
    setEditId(Number(p.id));
    setEditName(String(p.name || ""));
    setEditChannelId(Number(p.channel_id || 0));
    setEditAlbumSize(Number(p.album_size ?? 5));
    setEditInterval(Number(p.interval_minutes ?? 60));
    setEditAutoPostEnabled(p.auto_post_enabled !== false);
    setEditRandomize(!!p.randomize_queue);
    setEditRouteSlugs(String(p.route_match_tag_slugs || ""));
    setEditRouteNsfwTiers(String(p.route_nsfw_tiers || ""));
    setEditRoutePriority(Number(p.route_priority ?? 100));
    setEditOpen(true);
  }

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
                <th className="pb-2 pr-4 w-[1%] whitespace-nowrap">Actions</th>
              </tr>
            </thead>
            <tbody>
              {channelsPending && !channels.length ? (
                <tr>
                  <td colSpan={5} className="py-3 text-slate-500">
                    Loading channels…
                  </td>
                </tr>
              ) : null}
              {!channelsPending && !channelsError && !(channels as Array<unknown>).length ? (
                <tr>
                  <td colSpan={5} className="py-3 text-slate-500">
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
                  <td className="py-2 pr-4 align-top">
                    <button
                      type="button"
                      onClick={() => {
                        const label = String(c.name || c.identifier || c.id);
                        if (
                          !confirm(
                            `Delete channel "${label}"? All pools that post to this channel will be removed (including their media). Scheduled text jobs for this channel will be deleted. Shop plans linked to this channel will be unlinked.`
                          )
                        ) {
                          return;
                        }
                        deleteChannel.mutate(Number(c.id));
                      }}
                      disabled={
                        deleteChannel.isPending || deletePool.isPending || createChannel.isPending
                      }
                      className="px-2 py-1 bg-red-900/70 text-red-100 rounded text-xs hover:bg-red-800/80 whitespace-nowrap"
                    >
                      Delete
                    </button>
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
                checked={autoPostEnabled}
                onChange={(e) => setAutoPostEnabled(e.target.checked)}
              />
              Auto-post by pool interval
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
          <label className="block text-xs text-slate-400">
            Auto-route tag slugs (optional)
            <input
              type="text"
              value={routeSlugs}
              onChange={(e) => setRouteSlugs(e.target.value)}
              placeholder="cosplay, outdoor — comma-separated tbcc_tags.slug"
              className="mt-1 block w-full bg-slate-700 border border-slate-600 rounded px-2 py-1.5 text-slate-200 text-sm"
              title="When TBCC_AUTO_ROUTE_POOL=1, vision auto-tag can assign this pool if any linked tag slug matches"
            />
          </label>
          <label className="block text-xs text-slate-400">
            Auto-route NSFW tiers (optional)
            <input
              type="text"
              value={routeNsfwTiers}
              onChange={(e) => setRouteNsfwTiers(e.target.value)}
              placeholder="explicit, suggestive — comma-separated; AND with slugs if both set"
              className="mt-1 block w-full bg-slate-700 border border-slate-600 rounded px-2 py-1.5 text-slate-200 text-sm"
              title="sfw | suggestive | explicit | unknown"
            />
          </label>
          <label className="flex items-center gap-2 text-slate-400 text-xs">
            Route priority (lower = tried first)
            <input
              type="number"
              min={0}
              max={9999}
              value={routePriority}
              onChange={(e) => setRoutePriority(Number(e.target.value))}
              className="w-20 bg-slate-700 border border-slate-600 rounded px-2 py-1 text-slate-200"
            />
          </label>
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
                  checked={editAutoPostEnabled}
                  onChange={(e) => setEditAutoPostEnabled(e.target.checked)}
                />
                Auto-post by pool interval
              </label>
              <label className="flex items-center gap-2 text-slate-300 text-sm">
                <input
                  type="checkbox"
                  checked={editRandomize}
                  onChange={(e) => setEditRandomize(e.target.checked)}
                />
                Randomize which approved items scheduler picks for each album
              </label>
              <label className="block text-xs text-slate-400">
                Auto-route tag slugs (optional)
                <input
                  type="text"
                  value={editRouteSlugs}
                  onChange={(e) => setEditRouteSlugs(e.target.value)}
                  placeholder="cosplay, outdoor — comma-separated tbcc_tags.slug"
                  className="mt-1 block w-full bg-slate-700 border border-slate-600 rounded px-2 py-1.5 text-slate-200 text-sm"
                  title="TBCC_AUTO_ROUTE_POOL=1: assign pool when media has any of these tag slugs (after auto-tag)"
                />
              </label>
              <label className="block text-xs text-slate-400">
                Auto-route NSFW tiers (optional)
                <input
                  type="text"
                  value={editRouteNsfwTiers}
                  onChange={(e) => setEditRouteNsfwTiers(e.target.value)}
                  placeholder="explicit, suggestive — sfw | suggestive | explicit | unknown"
                  className="mt-1 block w-full bg-slate-700 border border-slate-600 rounded px-2 py-1.5 text-slate-200 text-sm"
                  title="When set with slugs, BOTH must match. Tier alone can match without slugs."
                />
              </label>
              <label className="flex items-center gap-2 text-slate-400 text-xs">
                Route priority (lower = tried first)
                <input
                  type="number"
                  min={0}
                  max={9999}
                  value={editRoutePriority}
                  onChange={(e) => setEditRoutePriority(Number(e.target.value))}
                  className="w-20 bg-slate-700 border border-slate-600 rounded px-2 py-1 text-slate-200"
                />
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
              <th className="text-left p-3">Route</th>
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
                <td colSpan={9} className="p-4 text-slate-500">
                  Loading pools…
                </td>
              </tr>
            ) : null}
            {!poolsPending && poolsError && !pools.length ? (
              <tr>
                <td colSpan={9} className="p-4 text-red-300/90">
                  Pools list unavailable — fix the error above or check the backend.
                </td>
              </tr>
            ) : null}
            {!poolsPending && !poolsError && !pools.length ? (
              <tr>
                <td colSpan={9} className="p-4 text-slate-500">
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
                <td
                  className="p-3 text-xs text-slate-400 max-w-[220px] align-top"
                  title={[
                    p.route_match_tag_slugs ? `tags: ${p.route_match_tag_slugs}` : "",
                    p.route_nsfw_tiers ? `tiers: ${p.route_nsfw_tiers}` : "",
                  ]
                    .filter(Boolean)
                    .join("\n")}
                >
                  {p.route_match_tag_slugs ? (
                    <div className="truncate">{String(p.route_match_tag_slugs)}</div>
                  ) : null}
                  {p.route_nsfw_tiers ? (
                    <div className="text-amber-200/80 truncate">{String(p.route_nsfw_tiers)}</div>
                  ) : null}
                  {!p.route_match_tag_slugs && !p.route_nsfw_tiers ? "—" : null}
                  {p.route_priority != null && Number(p.route_priority) !== 100 ? (
                    <div className="text-slate-500">pri {String(p.route_priority)}</div>
                  ) : null}
                </td>
                <td className="p-3">{String(p.channel_id)}</td>
                <td className="p-3">
                  <span className={Number(p.approved_count ?? 0) > 0 ? "text-cyan-300" : "text-slate-500"}>
                    {String(p.approved_count ?? 0)}/{String(p.album_size ?? 5)}
                  </span>
                </td>
                <td className="p-3">{String(p.album_size)}</td>
                <td className="p-3">
                  {String(p.interval_minutes)}
                  {p.auto_post_enabled === false ? (
                    <span className="ml-2 text-xs text-rose-400" title="Pool interval auto-post disabled">
                      paused
                    </span>
                  ) : (
                    <span className="ml-2 text-xs text-emerald-400" title="Pool interval auto-post enabled">
                      auto
                    </span>
                  )}
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
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        const label = String(p.name || p.id);
                        if (
                          !confirm(
                            `Delete pool "${label}"? All media in this pool will be removed. Sources and scheduler jobs that used this pool will no longer be tied to it.`
                          )
                        ) {
                          return;
                        }
                        deletePool.mutate(Number(p.id));
                      }}
                      disabled={deletePool.isPending}
                      className="px-2 py-1 bg-red-900/70 text-red-100 rounded text-sm hover:bg-red-800/80"
                    >
                      Delete
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
