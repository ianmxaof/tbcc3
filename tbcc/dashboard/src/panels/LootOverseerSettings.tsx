import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api, type LootBotSettingsEffective, type LootModifier, type LootRollPreview } from "../api";
import { QueryErrorBanner } from "../components/QueryErrorBanner";
import { tbccCopyText } from "../utils/clipboardToast";

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
  const [aofGroupChatId, setAofGroupChatId] = useState("");
  const [aofGroupThreadId, setAofGroupThreadId] = useState("");
  const [dailyPromoEnabled, setDailyPromoEnabled] = useState(false);
  const [dailyPromoHourUtc, setDailyPromoHourUtc] = useState("18");
  const [dailyPromoIntro, setDailyPromoIntro] = useState("");
  const [bufferMirror, setBufferMirror] = useState(false);
  const [bufferPublishNow, setBufferPublishNow] = useState(true);
  const [bufferXQueueText, setBufferXQueueText] = useState("");
  const [pollSeconds, setPollSeconds] = useState("");
  const [narrativeOn, setNarrativeOn] = useState(false);
  const [narrativePrompt, setNarrativePrompt] = useState("");
  const [lootReferralOn, setLootReferralOn] = useState(true);
  const [referralBonusPulls, setReferralBonusPulls] = useState("");
  const [creatorOfUrl, setCreatorOfUrl] = useState("");
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
    const aofCid = ov.aof_group_chat_id ?? eff?.aof_group_chat_id;
    setAofGroupChatId(aofCid != null && aofCid !== "" ? String(aofCid) : "");
    const aofTid = ov.aof_group_message_thread_id ?? eff?.aof_group_message_thread_id;
    setAofGroupThreadId(aofTid != null && aofTid !== "" ? String(aofTid) : "");
    setDailyPromoEnabled(Boolean(ov.daily_promo_enabled ?? eff?.daily_promo_enabled));
    const ph = ov.daily_promo_hour_utc ?? eff?.daily_promo_hour_utc;
    setDailyPromoHourUtc(ph != null ? String(ph) : "18");
    setDailyPromoIntro(String(ov.daily_promo_intro_html ?? eff?.daily_promo_intro_html ?? ""));
    setBufferMirror(Boolean(ov.buffer_mirror_enabled ?? eff?.buffer_mirror_enabled));
    setBufferPublishNow(Boolean(ov.buffer_publish_now ?? eff?.buffer_publish_now ?? true));
    const q = (ov.buffer_x_queue ?? eff?.buffer_x_queue) as Array<{ text?: string }> | undefined;
    if (Array.isArray(q) && q.length > 0) {
      setBufferXQueueText(q.map((x) => String(x.text ?? "").trim()).filter(Boolean).join("\n---\n"));
    } else {
      setBufferXQueueText("");
    }
    const ps = ov.config_poll_seconds ?? eff?.config_poll_seconds;
    setPollSeconds(ps != null ? String(ps) : "");
    setNarrativeOn(Boolean(ov.narrative_enabled ?? eff?.narrative_enabled));
    setNarrativePrompt(String(ov.narrative_system_prompt ?? eff?.narrative_system_prompt ?? ""));
    setLootReferralOn(Boolean(ov.loot_referral_enabled ?? eff?.loot_referral_enabled ?? true));
    const rbp = ov.referral_bonus_pulls ?? eff?.referral_bonus_pulls;
    setReferralBonusPulls(rbp != null && rbp !== "" ? String(rbp) : "");
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
  const creatorSubmit = useMutation({
    mutationFn: () => api.loot.creatorSubmit({ url: creatorOfUrl.trim() }),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["lootModifiers"] });
      setCreatorOfUrl("");
      window.alert(data.message || "Added to modifier pool");
    },
    onError: (e: Error) => window.alert(e.message || "Submit failed"),
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
  const triggerDailyPromo = useMutation({
    mutationFn: () => api.lootBotSettings.triggerDailyPromo(),
  });
  const bufferTest = useMutation({
    mutationFn: () =>
      api.lootBotSettings.bufferTestPost({
        publish_now: bufferPublishNow,
      }),
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
    const aofTrim = aofGroupChatId.trim();
    const aofNum = aofTrim && Number.isFinite(Number(aofTrim)) ? Math.trunc(Number(aofTrim)) : null;
    const threadTrim = aofGroupThreadId.trim();
    const threadNum =
      threadTrim && Number.isFinite(Number(threadTrim)) ? Math.trunc(Number(threadTrim)) : null;
    const body: Record<string, unknown> = {
      bot_username: botUsername.trim() || null,
      primary_loot_room_invite_url: inviteUrl.trim() || null,
      primary_loot_room_chat_id: chatIdNum,
      aof_group_chat_id: aofNum,
      aof_group_message_thread_id: threadNum,
      daily_promo_enabled: dailyPromoEnabled,
      daily_promo_hour_utc: dailyPromoHourUtc.trim() ? Math.min(23, Math.max(0, Number(dailyPromoHourUtc.trim()))) : null,
      daily_promo_intro_html: dailyPromoIntro.trim() || null,
      buffer_mirror_enabled: bufferMirror,
      buffer_publish_now: bufferMirror && bufferPublishNow,
      buffer_x_queue: bufferXQueueText
        .split(/\n---\n/)
        .map((t) => t.trim())
        .filter(Boolean)
        .slice(0, 10)
        .map((text) => ({ text: text.slice(0, 2800) })),
      config_poll_seconds: pollSeconds.trim() ? Number(pollSeconds.trim()) : null,
      narrative_enabled: narrativeOn,
      narrative_system_prompt: narrativePrompt.trim() || null,
      loot_referral_enabled: lootReferralOn,
      referral_bonus_pulls: referralBonusPulls.trim()
        ? Math.min(20, Math.max(0, Number(referralBonusPulls.trim())))
        : null,
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
        <code className="text-slate-300">tbcc/.env</code> where noted. Daily Loot Room ads post to your{" "}
        <strong className="text-slate-300">main AOF group</strong> from this bot (not Dashboard → Growth — that is a
        separate referral bulletin on the payment bot). Assign loot pools in{" "}
        <code className="text-slate-300">loot_pool_eligibility</code>.
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

          <div className="rounded-lg border border-cyan-900/50 bg-slate-900/40 p-4 space-y-3">
            <h3 className="text-sm font-semibold text-slate-200">Main AOF group — daily Loot Room promo</h3>
            <p className="text-xs text-slate-500">
              @aof_lootgod_bot posts here once per day (UTC hour below). Celery Beat task{" "}
              <code className="text-slate-400">loot-daily-promo</code> runs hourly and sends when the hour matches.
              Add the loot bot as admin in the group with permission to post.
            </p>
            <label className="block text-xs text-slate-400">
              Main AOF group chat id (required for promos)
              <input
                className="mt-1 w-full rounded border border-slate-600 bg-slate-950 px-2 py-1.5 text-sm"
                value={aofGroupChatId}
                onChange={(e) => setAofGroupChatId(e.target.value)}
                placeholder="-100… (same id you use for the public AOF group)"
              />
            </label>
            <label className="block text-xs text-slate-400">
              Forum topic id (optional)
              <input
                className="mt-1 w-full rounded border border-slate-600 bg-slate-950 px-2 py-1.5 text-sm"
                value={aofGroupThreadId}
                onChange={(e) => setAofGroupThreadId(e.target.value)}
                placeholder="e.g. 42"
              />
            </label>
            <label className="flex items-center gap-2 text-sm text-slate-300">
              <input
                type="checkbox"
                checked={dailyPromoEnabled}
                onChange={(e) => setDailyPromoEnabled(e.target.checked)}
              />
              Enable daily promo (off at first — turn on when ready)
            </label>
            <label className="block text-xs text-slate-400">
              Send hour (UTC, 0–23)
              <input
                type="number"
                min={0}
                max={23}
                className="mt-1 w-24 rounded border border-slate-600 bg-slate-950 px-2 py-1.5 text-sm"
                value={dailyPromoHourUtc}
                onChange={(e) => setDailyPromoHourUtc(e.target.value)}
              />
            </label>
            <label className="block text-xs text-slate-400">
              Promo message HTML (optional — blank uses default release copy)
              <textarea
                className="mt-1 w-full rounded border border-slate-600 bg-slate-950 px-2 py-1.5 text-sm min-h-[80px]"
                value={dailyPromoIntro}
                onChange={(e) => setDailyPromoIntro(e.target.value)}
                placeholder="<b>Loot Room — open.</b> Tiered pulls…"
              />
            </label>
            <div className="flex flex-wrap gap-2 items-center">
              <button
                type="button"
                onClick={() => triggerDailyPromo.mutate()}
                disabled={triggerDailyPromo.isPending || !aofGroupChatId.trim()}
                className="px-3 py-1.5 rounded bg-cyan-800 text-white hover:bg-cyan-700 disabled:opacity-50 text-sm"
              >
                {triggerDailyPromo.isPending ? "Sending…" : "Post promo now (Telegram + X if enabled)"}
              </button>
              {triggerDailyPromo.isSuccess ? (
                <span className="text-xs text-emerald-400">
                  Sent to Telegram
                  {triggerDailyPromo.data?.buffer_mirror_enabled ? " · Buffer mirror enabled" : ""}.
                </span>
              ) : null}
              {triggerDailyPromo.isError ? (
                <span className="text-xs text-red-300">{(triggerDailyPromo.error as Error).message}</span>
              ) : null}
            </div>

            <div className="rounded border border-sky-900/40 bg-slate-950/50 p-3 space-y-2 mt-2">
              <h4 className="text-xs font-semibold text-sky-200 uppercase tracking-wide">Buffer → X (with each promo)</h4>
              <p className="text-xs text-slate-500">
                Same wiring as Scheduler jobs: after a successful Telegram promo, TBCC posts to your Buffer X channel
                (≤280 chars). Needs <code className="text-slate-400">TBCC_BUFFER_API_KEY</code> and{" "}
                <code className="text-slate-400">TBCC_BUFFER_CHANNEL_ID_PRIMARY</code> in .env.
              </p>
              <label className="flex items-center gap-2 text-sm text-slate-300">
                <input
                  type="checkbox"
                  checked={bufferMirror}
                  onChange={(e) => {
                    setBufferMirror(e.target.checked);
                    if (!e.target.checked) setBufferPublishNow(false);
                  }}
                />
                Mirror daily promo to Buffer → X
              </label>
              {bufferMirror ? (
                <label className="flex items-center gap-2 text-sm text-slate-300 ml-5">
                  <input
                    type="checkbox"
                    checked={bufferPublishNow}
                    onChange={(e) => setBufferPublishNow(e.target.checked)}
                  />
                  Publish now on X (<code className="text-xs text-slate-500">shareNow</code> — same moment as Telegram)
                </label>
              ) : null}
              <label className="block text-xs text-slate-400">
                Optional X captions (one per block, separated by a line with only <code>---</code>). Blank = auto from
                Telegram promo text + button links, trimmed to 280.
                <textarea
                  className="mt-1 w-full rounded border border-slate-600 bg-slate-950 px-2 py-1.5 text-sm min-h-[72px] font-mono"
                  value={bufferXQueueText}
                  onChange={(e) => setBufferXQueueText(e.target.value)}
                  placeholder={"Loot Room is open. Free pulls in DM — @aof_lootgod_bot\n---\nNext week caption…"}
                />
              </label>
              <div className="flex flex-wrap gap-2 items-center">
                <button
                  type="button"
                  className="px-3 py-1.5 rounded bg-emerald-800 text-white hover:bg-emerald-700 disabled:opacity-50 text-sm"
                  disabled={bufferTest.isPending}
                  onClick={() => bufferTest.mutate()}
                >
                  {bufferTest.isPending ? "Testing…" : bufferPublishNow ? "Test X post now" : "Test X addToQueue"}
                </button>
                {bufferTest.isSuccess ? (
                  <span className="text-xs text-emerald-400">
                    X {bufferTest.data?.mode} · {bufferTest.data?.chars} chars
                  </span>
                ) : null}
                {bufferTest.isError ? (
                  <span className="text-xs text-red-300">{(bufferTest.error as Error).message}</span>
                ) : null}
              </div>
            </div>
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
              Overseer LLM chat (DM the bot; uses TBCC_OPENAI_API_KEY or Ollama)
            </label>
            <label className="block text-xs text-slate-400">
              Narrative system prompt (optional)
              <textarea
                className="mt-1 w-full rounded border border-slate-600 bg-slate-950 px-2 py-1.5 text-sm min-h-[88px]"
                value={narrativePrompt}
                onChange={(e) => setNarrativePrompt(e.target.value)}
                placeholder="Extra persona notes appended to the default Loot Overseer voice…"
              />
            </label>
            <label className="flex items-center gap-2 text-sm text-slate-300">
              <input type="checkbox" checked={lootReferralOn} onChange={(e) => setLootReferralOn(e.target.checked)} />
              Loot referrals (bonus free pulls via lootref_ deep links)
            </label>
            <label className="block text-xs text-slate-400">
              Bonus pulls per referred friend (0–20, blank = env default)
              <input
                className="mt-1 w-full rounded border border-slate-600 bg-slate-950 px-2 py-1.5 text-sm"
                value={referralBonusPulls}
                onChange={(e) => setReferralBonusPulls(e.target.value)}
                placeholder="1"
              />
            </label>
          </div>

          <div className="rounded-lg border border-slate-700 bg-slate-900/40 p-4 space-y-3">
            <h3 className="text-sm font-semibold text-slate-200">Creator / OnlyFans pool</h3>
            <p className="text-xs text-slate-500">
              Same as bot <code className="text-slate-400">/model</code> — profile URL becomes an active modifier on tier 5+ rolls.
            </p>
            <label className="block text-xs text-slate-400">
              OnlyFans profile URL
              <input
                className="mt-1 w-full rounded border border-slate-600 bg-slate-950 px-2 py-1.5 text-sm"
                value={creatorOfUrl}
                onChange={(e) => setCreatorOfUrl(e.target.value)}
                placeholder="https://onlyfans.com/handle"
              />
            </label>
            <button
              type="button"
              disabled={creatorSubmit.isPending || !creatorOfUrl.trim()}
              onClick={() => creatorSubmit.mutate()}
              className="text-xs px-3 py-1.5 rounded bg-violet-700/80 text-white hover:bg-violet-600 disabled:opacity-40"
            >
              {creatorSubmit.isPending ? "Adding…" : "Add to modifier pool"}
            </button>
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
                            onClick={(e) =>
                              void tbccCopyText(String(m.target_url), { anchor: e.currentTarget })
                            }
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
              Dry-run does not save drop rows. <strong className="text-slate-300">Send preview to my DM</strong> delivers
              the real album (from Saved Messages) plus zip modifiers via @aof_lootgod_bot. Pools must be listed in{" "}
              <code className="text-slate-400">loot_pool_eligibility</code> (FLOOR / SPOTLIGHT / VAULT).
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
                  {sendPreviewDm.isPending ? "Sending…" : "Send visual preview to DM"}
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
