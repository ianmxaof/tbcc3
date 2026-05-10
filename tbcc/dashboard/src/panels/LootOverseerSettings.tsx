import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api, type LootBotSettingsEffective, type LootModifier, type LootRollPreview } from "../api";
import { QueryErrorBanner } from "../components/QueryErrorBanner";

type Overrides = Record<string, unknown>;

export function LootOverseerSettingsPanel() {
  const qc = useQueryClient();
  const { data, isPending, isError, error, refetch } = useQuery({
    queryKey: ["lootBotSettings"],
    queryFn: () => api.lootBotSettings.get(),
  });
  const eff = data?.effective as LootBotSettingsEffective | undefined;
  const ov = (data?.overrides ?? {}) as Overrides;

  const [botUsername, setBotUsername] = useState("");
  const [inviteUrl, setInviteUrl] = useState("");
  const [chatId, setChatId] = useState("");
  const [pollSeconds, setPollSeconds] = useState("");
  const [narrativeOn, setNarrativeOn] = useState(false);
  const [narrativePrompt, setNarrativePrompt] = useState("");
  const [spoilerDefault, setSpoilerDefault] = useState(true);
  const [runtimeAdapter, setRuntimeAdapter] = useState<"" | "local" | "command">("");
  const [cmdStart, setCmdStart] = useState("");
  const [cmdStop, setCmdStop] = useState("");
  const [cmdRestart, setCmdRestart] = useState("");
  const [cmdReload, setCmdReload] = useState("");
  const [cmdStatus, setCmdStatus] = useState("");
  const [operatorNotes, setOperatorNotes] = useState("");
  const [botTokenInput, setBotTokenInput] = useState("");
  const [modKind, setModKind] = useState("telegram_group");
  const [modLabel, setModLabel] = useState("");
  const [modUrl, setModUrl] = useState("");
  const [modWeight, setModWeight] = useState("1.0");
  const [modRarityFocus, setModRarityFocus] = useState("1.0");
  const [modBypass, setModBypass] = useState(false);
  const [modActive, setModActive] = useState(true);
  const [zipFile, setZipFile] = useState<File | null>(null);
  const [previewUserId, setPreviewUserId] = useState("");
  const [previewInterval, setPreviewInterval] = useState<"m15" | "m30" | "m45" | "m60">("m30");
  const [previewSeed, setPreviewSeed] = useState("");
  const [previewSendToUserId, setPreviewSendToUserId] = useState("");
  const [rollPreview, setRollPreview] = useState<LootRollPreview | null>(null);

  const modifiersQ = useQuery({
    queryKey: ["lootModifiers"],
    queryFn: () => api.loot.listModifiers(true),
  });

  useEffect(() => {
    if (!eff && !ov) return;
    setBotUsername(String(ov.bot_username ?? eff?.bot_username ?? ""));
    setInviteUrl(String(ov.primary_loot_room_invite_url ?? eff?.primary_loot_room_invite_url ?? ""));
    const cid = ov.primary_loot_room_chat_id ?? eff?.primary_loot_room_chat_id;
    setChatId(cid != null && cid !== "" ? String(cid) : "");
    const ps = ov.config_poll_seconds ?? eff?.config_poll_seconds;
    setPollSeconds(ps != null ? String(ps) : "");
    setNarrativeOn(Boolean(ov.narrative_enabled ?? eff?.narrative_enabled));
    setNarrativePrompt(String(ov.narrative_system_prompt ?? eff?.narrative_system_prompt ?? ""));
    setSpoilerDefault(Boolean(ov.drop_spoiler_default ?? eff?.drop_spoiler_default ?? true));
    const ra = (ov.runtime_adapter ?? eff?.runtime_adapter ?? "") as string;
    setRuntimeAdapter(ra === "command" || ra === "local" ? ra : "");
    setCmdStart(String(ov.runtime_cmd_start ?? eff?.runtime_cmd_start ?? ""));
    setCmdStop(String(ov.runtime_cmd_stop ?? eff?.runtime_cmd_stop ?? ""));
    setCmdRestart(String(ov.runtime_cmd_restart ?? eff?.runtime_cmd_restart ?? ""));
    setCmdReload(String(ov.runtime_cmd_reload ?? eff?.runtime_cmd_reload ?? ""));
    setCmdStatus(String(ov.runtime_cmd_status ?? eff?.runtime_cmd_status ?? ""));
    setOperatorNotes(String(ov.operator_notes ?? eff?.operator_notes ?? ""));
  }, [eff, ov]);

  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.lootBotSettings.patch(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["lootBotSettings"] });
      setBotTokenInput("");
    },
  });
  const createModifier = useMutation({
    mutationFn: () =>
      api.loot.createModifier({
        kind: modKind,
        label: modLabel.trim() || null,
        target_url: modUrl.trim() || null,
        weight_base: Number(modWeight || "1"),
        rarity_focus: Number(modRarityFocus || "1"),
        bypass_vip: modBypass,
        active: modActive,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["lootModifiers"] });
      setModLabel("");
      setModUrl("");
      setModWeight("1.0");
      setModRarityFocus("1.0");
      setModBypass(false);
      setModActive(true);
    },
  });
  const patchModifier = useMutation({
    mutationFn: (p: { id: number; body: Partial<LootModifier> }) => api.loot.patchModifier(p.id, p.body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["lootModifiers"] }),
  });
  const deleteModifier = useMutation({
    mutationFn: (id: number) => api.loot.deleteModifier(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["lootModifiers"] }),
  });
  const runRollPreview = useMutation({
    mutationFn: () =>
      api.loot.rollPreview({
        telegram_user_id: previewUserId.trim() ? Number(previewUserId.trim()) : undefined,
        interval_code: previewInterval,
        seed: previewSeed.trim() ? Number(previewSeed.trim()) : undefined,
      }),
    onSuccess: (data) => setRollPreview(data),
  });
  const sendPreviewDm = useMutation({
    mutationFn: () =>
      api.loot.sendPreviewDm({
        telegram_user_id: previewUserId.trim() ? Number(previewUserId.trim()) : undefined,
        interval_code: previewInterval,
        seed: previewSeed.trim() ? Number(previewSeed.trim()) : undefined,
        to_telegram_user_id: previewSendToUserId.trim() ? Number(previewSendToUserId.trim()) : undefined,
      }),
    onSuccess: (data) => setRollPreview(data.preview),
  });
  const uploadZipModifier = useMutation({
    mutationFn: () => {
      if (!zipFile) throw new Error("Choose a .zip file first");
      return api.loot.uploadZipModifier({
        file: zipFile,
        label: modLabel.trim() || zipFile.name,
        weight_base: Number(modWeight || "1"),
        rarity_focus: Number(modRarityFocus || "1"),
        bypass_vip: modBypass,
        active: modActive,
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["lootModifiers"] });
      setZipFile(null);
      setModLabel("");
      setModWeight("1.0");
      setModRarityFocus("1.0");
      setModBypass(false);
      setModActive(true);
    },
  });

  const onSave = () => {
    const chatIdTrim = chatId.trim();
    const chatIdNum =
      chatIdTrim && Number.isFinite(Number(chatIdTrim)) ? Math.trunc(Number(chatIdTrim)) : null;
    const body: Record<string, unknown> = {
      bot_username: botUsername.trim() || null,
      primary_loot_room_invite_url: inviteUrl.trim() || null,
      primary_loot_room_chat_id: chatIdNum,
      config_poll_seconds: pollSeconds.trim() ? Number(pollSeconds.trim()) : null,
      narrative_enabled: narrativeOn,
      narrative_system_prompt: narrativePrompt.trim() || null,
      drop_spoiler_default: spoilerDefault,
      runtime_adapter: runtimeAdapter || null,
      runtime_cmd_start: cmdStart.trim() || null,
      runtime_cmd_stop: cmdStop.trim() || null,
      runtime_cmd_restart: cmdRestart.trim() || null,
      runtime_cmd_reload: cmdReload.trim() || null,
      runtime_cmd_status: cmdStatus.trim() || null,
      operator_notes: operatorNotes.trim() || null,
    };
    if (botTokenInput.trim()) {
      body.bot_token = botTokenInput.trim();
    }
    save.mutate(body);
  };

  const clearDashboardToken = () => {
    save.mutate({ bot_token: "" });
  };

  return (
    <div>
      <h2 className="text-xl font-semibold mb-2">Loot overseer (@aof_lootgod_bot)</h2>
      <p className="text-slate-400 mb-4 max-w-3xl">
        Runtime for <code className="text-slate-300">python -m bots.loot_bot</code>. Values here override{" "}
        <code className="text-slate-300">tbcc/.env</code> where noted. The bot polls this API for invite URL, spoiler
        defaults, and narrative flags. Assign loot-eligible media pools in the DB table{" "}
        <code className="text-slate-300">loot_pool_eligibility</code> (or add a picker UI later).
      </p>

      {isError && (
        <QueryErrorBanner
          title="Could not load loot bot settings"
          message={String((error as Error)?.message ?? error)}
          onRetry={() => void refetch()}
        />
      )}

      {isPending && !data ? (
        <p className="text-slate-500">Loading…</p>
      ) : (
        <div className="space-y-6 max-w-3xl">
          <div className="rounded-lg border border-slate-700 bg-slate-900/40 p-4 space-y-3">
            <h3 className="text-sm font-semibold text-slate-200">Identity &amp; primary room</h3>
            <label className="block text-xs text-slate-400">
              Bot username (no @)
              <input
                className="mt-1 w-full rounded border border-slate-600 bg-slate-950 px-2 py-1.5 text-sm"
                value={botUsername}
                onChange={(e) => setBotUsername(e.target.value)}
                placeholder="aof_lootgod_bot"
              />
            </label>
            <label className="block text-xs text-slate-400">
              Primary loot room invite URL
              <input
                className="mt-1 w-full rounded border border-slate-600 bg-slate-950 px-2 py-1.5 text-sm"
                value={inviteUrl}
                onChange={(e) => setInviteUrl(e.target.value)}
                placeholder="https://t.me/+…"
              />
            </label>
            <label className="block text-xs text-slate-400">
              Primary loot room Telegram chat id (optional, negative for supergroups — set once known)
              <input
                className="mt-1 w-full rounded border border-slate-600 bg-slate-950 px-2 py-1.5 text-sm"
                value={chatId}
                onChange={(e) => setChatId(e.target.value)}
                placeholder="-100…"
              />
            </label>
          </div>

          <div className="rounded-lg border border-slate-700 bg-slate-900/40 p-4 space-y-3">
            <h3 className="text-sm font-semibold text-slate-200">Token</h3>
            <p className="text-xs text-slate-500">
              Effective token is never shown in full. Prefer <code className="text-slate-400">TBCC_LOOT_BOT_TOKEN</code>{" "}
              in <code className="text-slate-400">.env</code> in production; dashboard storage is convenient if{" "}
              <code className="text-slate-400">TBCC_INTERNAL_API_KEY</code> is set so the bot can call{" "}
              <code className="text-slate-400">/loot-bot-settings/internal-runtime</code>.
            </p>
            <p className="text-xs text-slate-400">
              Masked: <strong className="text-slate-200">{eff?.bot_token_masked ?? "—"}</strong> · source:{" "}
              <strong className="text-slate-200">{eff?.bot_token_source ?? "—"}</strong>
              {ov.bot_token_set_in_dashboard ? " · dashboard override active" : ""}
            </p>
            <label className="block text-xs text-slate-400">
              Set / replace dashboard token (leave blank to keep unchanged)
              <input
                type="password"
                autoComplete="off"
                className="mt-1 w-full rounded border border-slate-600 bg-slate-950 px-2 py-1.5 text-sm"
                value={botTokenInput}
                onChange={(e) => setBotTokenInput(e.target.value)}
                placeholder="BotFather token"
              />
            </label>
            <button
              type="button"
              onClick={clearDashboardToken}
              disabled={save.isPending || !ov.bot_token_set_in_dashboard}
              className="text-xs px-2 py-1 rounded border border-amber-700/60 text-amber-200 hover:bg-amber-900/30 disabled:opacity-40"
            >
              Clear dashboard token (use env only)
            </button>
          </div>

          <div className="rounded-lg border border-slate-700 bg-slate-900/40 p-4 space-y-3">
            <h3 className="text-sm font-semibold text-slate-200">Behaviour</h3>
            <label className="block text-xs text-slate-400">
              Settings poll interval (seconds, 5–3600)
              <input
                className="mt-1 w-full rounded border border-slate-600 bg-slate-950 px-2 py-1.5 text-sm"
                value={pollSeconds}
                onChange={(e) => setPollSeconds(e.target.value)}
                placeholder="30"
              />
            </label>
            <label className="flex items-center gap-2 text-sm text-slate-300">
              <input type="checkbox" checked={spoilerDefault} onChange={(e) => setSpoilerDefault(e.target.checked)} />
              Default album media as Telegram spoilers (“unpack” feel)
            </label>
            <label className="flex items-center gap-2 text-sm text-slate-300">
              <input type="checkbox" checked={narrativeOn} onChange={(e) => setNarrativeOn(e.target.checked)} />
              Enable narrative / LLM layer (orchestrator will read this when wired)
            </label>
            <label className="block text-xs text-slate-400">
              Narrative system prompt (optional)
              <textarea
                className="mt-1 w-full rounded border border-slate-600 bg-slate-950 px-2 py-1.5 text-sm min-h-[88px]"
                value={narrativePrompt}
                onChange={(e) => setNarrativePrompt(e.target.value)}
                placeholder="Persona and tone for drop narration…"
              />
            </label>
          </div>

          <div className="rounded-lg border border-slate-700 bg-slate-900/40 p-4 space-y-3">
            <h3 className="text-sm font-semibold text-slate-200">Process monitor (optional)</h3>
            <p className="text-xs text-slate-500">
              Same pattern as the payment bot: <code className="text-slate-400">local</code> lets the API spawn{" "}
              <code className="text-slate-300">python -m bots.loot_bot</code>; <code className="text-slate-400">command</code>{" "}
              runs your Docker/systemd scripts. Per-bot commands override global env when set.
            </p>
            <label className="block text-xs text-slate-400">
              Runtime adapter override
              <select
                className="mt-1 w-full rounded border border-slate-600 bg-slate-950 px-2 py-1.5 text-sm"
                value={runtimeAdapter}
                onChange={(e) => setRuntimeAdapter(e.target.value as "" | "local" | "command")}
              >
                <option value="">(inherit — see TBCC_BOT_RUNTIME_ADAPTER in .env)</option>
                <option value="local">local</option>
                <option value="command">command</option>
              </select>
            </label>
            <label className="block text-xs text-slate-400">
              Start command
              <input
                className="mt-1 w-full rounded border border-slate-600 bg-slate-950 px-2 py-1.5 text-sm font-mono text-xs"
                value={cmdStart}
                onChange={(e) => setCmdStart(e.target.value)}
                placeholder="docker compose … up -d loot_bot"
              />
            </label>
            <label className="block text-xs text-slate-400">
              Stop command
              <input
                className="mt-1 w-full rounded border border-slate-600 bg-slate-950 px-2 py-1.5 text-sm font-mono text-xs"
                value={cmdStop}
                onChange={(e) => setCmdStop(e.target.value)}
                placeholder="docker compose … stop loot_bot"
              />
            </label>
            <label className="block text-xs text-slate-400">
              Restart command
              <input
                className="mt-1 w-full rounded border border-slate-600 bg-slate-950 px-2 py-1.5 text-sm font-mono text-xs"
                value={cmdRestart}
                onChange={(e) => setCmdRestart(e.target.value)}
                placeholder="docker compose … restart loot_bot"
              />
            </label>
            <label className="block text-xs text-slate-400">
              Reload command
              <input
                className="mt-1 w-full rounded border border-slate-600 bg-slate-950 px-2 py-1.5 text-sm font-mono text-xs"
                value={cmdReload}
                onChange={(e) => setCmdReload(e.target.value)}
                placeholder="optional — loot bot polls TBCC automatically"
              />
            </label>
            <label className="block text-xs text-slate-400">
              Status command
              <input
                className="mt-1 w-full rounded border border-slate-600 bg-slate-950 px-2 py-1.5 text-sm font-mono text-xs"
                value={cmdStatus}
                onChange={(e) => setCmdStatus(e.target.value)}
                placeholder="docker compose … ps loot_bot"
              />
            </label>
          </div>

          <div className="rounded-lg border border-slate-700 bg-slate-900/40 p-4 space-y-3">
            <h3 className="text-sm font-semibold text-slate-200">Caption modifiers (roll 0-3)</h3>
            <p className="text-xs text-slate-500">
              Add reusable modifier links (groups/channels/mega). The roll engine can attach up to 3 per drop based on
              <code className="text-slate-400"> weight_base</code> and <code className="text-slate-400"> rarity_focus</code>.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
              <label className="block text-xs text-slate-400">
                Kind
                <select
                  className="mt-1 w-full rounded border border-slate-600 bg-slate-950 px-2 py-1.5 text-sm"
                  value={modKind}
                  onChange={(e) => setModKind(e.target.value)}
                >
                  <option value="telegram_group">telegram_group</option>
                  <option value="telegram_channel">telegram_channel</option>
                  <option value="mega_pack">mega_pack</option>
                  <option value="internal_route">internal_route</option>
                  <option value="other">other</option>
                </select>
              </label>
              <label className="block text-xs text-slate-400">
                Label
                <input
                  className="mt-1 w-full rounded border border-slate-600 bg-slate-950 px-2 py-1.5 text-sm"
                  value={modLabel}
                  onChange={(e) => setModLabel(e.target.value)}
                  placeholder="Mega Pack Drop #12"
                />
              </label>
              <label className="block text-xs text-slate-400 md:col-span-2">
                Target URL
                <input
                  className="mt-1 w-full rounded border border-slate-600 bg-slate-950 px-2 py-1.5 text-sm"
                  value={modUrl}
                  onChange={(e) => setModUrl(e.target.value)}
                  placeholder="https://t.me/+... or https://mega.nz/..."
                />
              </label>
              <label className="block text-xs text-slate-400">
                Base weight
                <input
                  className="mt-1 w-full rounded border border-slate-600 bg-slate-950 px-2 py-1.5 text-sm"
                  value={modWeight}
                  onChange={(e) => setModWeight(e.target.value)}
                  placeholder="1.0"
                />
              </label>
              <label className="block text-xs text-slate-400">
                Rarity focus
                <input
                  className="mt-1 w-full rounded border border-slate-600 bg-slate-950 px-2 py-1.5 text-sm"
                  value={modRarityFocus}
                  onChange={(e) => setModRarityFocus(e.target.value)}
                  placeholder="1.0"
                />
              </label>
            </div>
            <div className="flex flex-wrap gap-3 items-center">
              <label className="flex items-center gap-2 text-sm text-slate-300">
                <input type="checkbox" checked={modBypass} onChange={(e) => setModBypass(e.target.checked)} />
                bypass.vip eligible
              </label>
              <label className="flex items-center gap-2 text-sm text-slate-300">
                <input type="checkbox" checked={modActive} onChange={(e) => setModActive(e.target.checked)} />
                active
              </label>
              <button
                type="button"
                onClick={() => createModifier.mutate()}
                disabled={createModifier.isPending || !modKind.trim()}
                className="px-3 py-1.5 rounded bg-cyan-700 text-white hover:bg-cyan-600 disabled:opacity-50"
              >
                {createModifier.isPending ? "Adding…" : "Add modifier"}
              </button>
              {createModifier.isError ? (
                <span className="text-xs text-red-300">{(createModifier.error as Error).message}</span>
              ) : null}
            </div>
            <div className="rounded border border-slate-700 p-3 space-y-2">
              <p className="text-xs text-slate-400">
                Upload local zip as a <code className="text-slate-300">local_zip_pack</code> modifier (served from
                <code className="text-slate-300"> /static/bundles/loot_modifiers/...</code>).
              </p>
              <input
                type="file"
                accept=".zip,application/zip"
                onChange={(e) => setZipFile(e.target.files?.[0] ?? null)}
                className="text-xs text-slate-300"
              />
              <button
                type="button"
                onClick={() => uploadZipModifier.mutate()}
                disabled={uploadZipModifier.isPending || !zipFile}
                className="px-3 py-1.5 rounded bg-violet-700 text-white hover:bg-violet-600 disabled:opacity-50"
              >
                {uploadZipModifier.isPending ? "Uploading…" : "Upload zip as modifier"}
              </button>
              {uploadZipModifier.isError ? (
                <span className="text-xs text-red-300 ml-2">{(uploadZipModifier.error as Error).message}</span>
              ) : null}
              {zipFile ? <p className="text-xs text-slate-500">Selected: {zipFile.name}</p> : null}
            </div>

            <div className="overflow-x-auto border border-slate-700 rounded">
              <table className="w-full text-xs">
                <thead className="bg-slate-800">
                  <tr>
                    <th className="p-2 text-left">ID</th>
                    <th className="p-2 text-left">Kind</th>
                    <th className="p-2 text-left">Label</th>
                    <th className="p-2 text-left">URL</th>
                    <th className="p-2 text-left">W</th>
                    <th className="p-2 text-left">R</th>
                    <th className="p-2 text-left">On</th>
                    <th className="p-2 text-left">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {(modifiersQ.data ?? []).map((m) => (
                    <tr key={m.id} className="border-t border-slate-700">
                      <td className="p-2">{m.id}</td>
                      <td className="p-2">{m.kind}</td>
                      <td className="p-2">{m.label || "—"}</td>
                      <td className="p-2 max-w-[260px] truncate">{m.target_url || "—"}</td>
                      <td className="p-2">{m.weight_base}</td>
                      <td className="p-2">{m.rarity_focus}</td>
                      <td className="p-2">{m.active ? "yes" : "no"}</td>
                      <td className="p-2 flex gap-1">
                        {m.target_url ? (
                          <button
                            type="button"
                            onClick={() => void navigator.clipboard?.writeText(String(m.target_url))}
                            className="px-2 py-1 rounded border border-slate-600 hover:bg-slate-800"
                          >
                            Copy URL
                          </button>
                        ) : null}
                        <button
                          type="button"
                          onClick={() => patchModifier.mutate({ id: m.id, body: { active: !m.active } })}
                          className="px-2 py-1 rounded border border-slate-600 hover:bg-slate-800"
                        >
                          {m.active ? "Disable" : "Enable"}
                        </button>
                        <button
                          type="button"
                          onClick={() => deleteModifier.mutate(m.id)}
                          className="px-2 py-1 rounded border border-red-700 text-red-200 hover:bg-red-900/30"
                        >
                          Delete
                        </button>
                      </td>
                    </tr>
                  ))}
                  {!modifiersQ.isPending && (modifiersQ.data ?? []).length === 0 ? (
                    <tr>
                      <td colSpan={8} className="p-3 text-slate-500">
                        No modifiers yet.
                      </td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>
          </div>

          <div className="rounded-lg border border-slate-700 bg-slate-900/40 p-4 space-y-3">
            <h3 className="text-sm font-semibold text-slate-200">Test roll now</h3>
            <p className="text-xs text-slate-500">
              Dry-run only: no Telegram sends and no DB drop rows. Useful to validate rarity, media picks, and caption modifiers.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
              <label className="block text-xs text-slate-400">
                Telegram user id (optional dedupe)
                <input
                  className="mt-1 w-full rounded border border-slate-600 bg-slate-950 px-2 py-1.5 text-sm"
                  value={previewUserId}
                  onChange={(e) => setPreviewUserId(e.target.value)}
                  placeholder="7787..."
                />
              </label>
              <label className="block text-xs text-slate-400">
                Interval
                <select
                  className="mt-1 w-full rounded border border-slate-600 bg-slate-950 px-2 py-1.5 text-sm"
                  value={previewInterval}
                  onChange={(e) => setPreviewInterval(e.target.value as "m15" | "m30" | "m45" | "m60")}
                >
                  <option value="m60">m60</option>
                  <option value="m45">m45</option>
                  <option value="m30">m30</option>
                  <option value="m15">m15</option>
                </select>
              </label>
              <label className="block text-xs text-slate-400">
                Seed (optional deterministic)
                <input
                  className="mt-1 w-full rounded border border-slate-600 bg-slate-950 px-2 py-1.5 text-sm"
                  value={previewSeed}
                  onChange={(e) => setPreviewSeed(e.target.value)}
                  placeholder="42"
                />
              </label>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
              <label className="block text-xs text-slate-400">
                Send preview to Telegram user id (optional; blank = ADMIN_TELEGRAM_ID)
                <input
                  className="mt-1 w-full rounded border border-slate-600 bg-slate-950 px-2 py-1.5 text-sm"
                  value={previewSendToUserId}
                  onChange={(e) => setPreviewSendToUserId(e.target.value)}
                  placeholder="7787..."
                />
              </label>
              <div className="flex items-end gap-2">
                <button
                  type="button"
                  onClick={() => runRollPreview.mutate()}
                  disabled={runRollPreview.isPending}
                  className="px-3 py-1.5 rounded bg-emerald-700 text-white hover:bg-emerald-600 disabled:opacity-50"
                >
                  {runRollPreview.isPending ? "Rolling…" : "Run dry roll"}
                </button>
                <button
                  type="button"
                  onClick={() => sendPreviewDm.mutate()}
                  disabled={sendPreviewDm.isPending}
                  className="px-3 py-1.5 rounded bg-cyan-700 text-white hover:bg-cyan-600 disabled:opacity-50"
                >
                  {sendPreviewDm.isPending ? "Sending…" : "Send preview to my DM"}
                </button>
              </div>
            </div>
            {runRollPreview.isError ? (
              <p className="text-xs text-red-300">{(runRollPreview.error as Error).message}</p>
            ) : null}
            {sendPreviewDm.isError ? (
              <p className="text-xs text-red-300">{(sendPreviewDm.error as Error).message}</p>
            ) : null}
            {sendPreviewDm.isSuccess ? (
              <p className="text-xs text-emerald-300">Sent via @aof_lootgod_bot to user id {sendPreviewDm.data.sent_to}.</p>
            ) : null}
            {rollPreview ? (
              <div className="space-y-2">
                <p className="text-xs text-slate-300">
                  Result: {rollPreview.ok ? "ok" : "failed"} · tier {rollPreview.rarity_tier ?? "-"} · album{" "}
                  {rollPreview.album_size ?? 0} · modifier slots {rollPreview.modifier_slot_count ?? 0}
                </p>
                {!rollPreview.ok ? <p className="text-xs text-amber-300">{rollPreview.reason}</p> : null}
                {rollPreview.ok ? (
                  <pre className="text-[11px] p-2 rounded bg-slate-950 border border-slate-700 overflow-x-auto whitespace-pre-wrap">
{`🎁 Loot Drop (Tier ${rollPreview.rarity_tier})
Album size: ${rollPreview.album_size}
Media IDs: ${(rollPreview.media ?? []).map((m) => m.id).join(", ") || "none"}
Modifiers:
${(rollPreview.modifiers ?? [])
  .map((m) => `- ${m.label || m.kind}${m.target_url ? ` -> ${m.target_url}` : ""}`)
  .join("\n") || "- none"}`}
                  </pre>
                ) : null}
              </div>
            ) : null}
          </div>

          <div className="rounded-lg border border-slate-700 bg-slate-900/40 p-4 space-y-2">
            <h3 className="text-sm font-semibold text-slate-200">Operator notes</h3>
            <textarea
              className="w-full rounded border border-slate-600 bg-slate-950 px-2 py-1.5 text-sm min-h-[72px]"
              value={operatorNotes}
              onChange={(e) => setOperatorNotes(e.target.value)}
              placeholder="Internal runbook / reminders…"
            />
          </div>

          <div className="flex flex-wrap gap-2 items-center">
            <button
              type="button"
              onClick={onSave}
              disabled={save.isPending}
              className="px-4 py-2 rounded bg-cyan-700 text-white hover:bg-cyan-600 disabled:opacity-50"
            >
              {save.isPending ? "Saving…" : "Save loot overseer settings"}
            </button>
            {save.isError ? <span className="text-sm text-red-300">{(save.error as Error).message}</span> : null}
            {save.isSuccess && save.data?.ok ? (
              <span className="text-sm text-emerald-400">Saved. Bot picks up public fields on the next poll.</span>
            ) : null}
          </div>
        </div>
      )}
    </div>
  );
}
