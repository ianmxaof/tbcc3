import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type PaymentBotMenuButton } from "../api";
import { QueryErrorBanner } from "../components/QueryErrorBanner";

const MENU_TEMPLATE = JSON.stringify(
  [
    [{ label: "🔑 Join the Inner Circle", action: "menu_subscribe" }],
    [
      { label: "🗝 Loot Room (24h key)", action: "menu_loot" },
      { label: "📦 Digital packs", action: "menu_packs" },
    ],
    [
      { label: "🔗 Referral", action: "menu_referral" },
      { label: "📋 Status", action: "menu_status" },
    ],
  ],
  null,
  2
);

export function PaymentBotSettingsPanel() {
  const qc = useQueryClient();
  const settingsQ = useQuery({
    queryKey: ["paymentBotSettings"],
    queryFn: () => api.paymentBotSettings.get(),
  });

  const effective = settingsQ.data?.effective;
  const [menuJson, setMenuJson] = useState("");
  const [welcomeHtml, setWelcomeHtml] = useState("");
  const [lootIntroHtml, setLootIntroHtml] = useState("");
  const [subscribeTitleMain, setSubscribeTitleMain] = useState("");
  const [subscribeTitleLoot, setSubscribeTitleLoot] = useState("");
  const [columns, setColumns] = useState(2);
  const [minStars, setMinStars] = useState(0);
  const [runtimeAdapter, setRuntimeAdapter] = useState<"local" | "command">("local");
  const [cmdStart, setCmdStart] = useState("");
  const [cmdStop, setCmdStop] = useState("");
  const [cmdRestart, setCmdRestart] = useState("");
  const [cmdReload, setCmdReload] = useState("");
  const [cmdStatus, setCmdStatus] = useState("");
  const [videoFinderEnabled, setVideoFinderEnabled] = useState(true);
  const [videoFinderMaxLinks, setVideoFinderMaxLinks] = useState(8);
  const [videoFinderSourcesJson, setVideoFinderSourcesJson] = useState("");
  const [edited, setEdited] = useState(false);

  useEffect(() => {
    if (!effective || edited) return;
    setMenuJson(JSON.stringify(effective.main_menu, null, 2));
    setWelcomeHtml(effective.welcome_html || "");
    setLootIntroHtml(effective.loot_intro_html || "");
    setSubscribeTitleMain(effective.subscribe_title_main || "");
    setSubscribeTitleLoot(effective.subscribe_title_loot || "");
    setColumns(Number(effective.subscription_catalog_columns || 2));
    setMinStars(Number(effective.min_subscription_stars || 0));
    setRuntimeAdapter((effective.runtime_adapter as "local" | "command" | null) || "local");
    setCmdStart(String(effective.runtime_cmd_start || ""));
    setCmdStop(String(effective.runtime_cmd_stop || ""));
    setCmdRestart(String(effective.runtime_cmd_restart || ""));
    setCmdReload(String(effective.runtime_cmd_reload || ""));
    setCmdStatus(String(effective.runtime_cmd_status || ""));
    setVideoFinderEnabled(effective.video_finder_enabled !== false);
    setVideoFinderMaxLinks(Number(effective.video_finder_max_links_per_source || 8));
    setVideoFinderSourcesJson(JSON.stringify(effective.video_finder_sources || [], null, 2));
  }, [effective, edited]);

  const menuParseError = useMemo(() => {
    if (!menuJson.trim()) return null;
    try {
      const parsed = JSON.parse(menuJson) as unknown;
      if (!Array.isArray(parsed)) return "Menu JSON must be an array of rows.";
      for (const row of parsed) {
        if (!Array.isArray(row)) return "Each row must be an array of buttons.";
        for (const btn of row) {
          const b = btn as Partial<PaymentBotMenuButton>;
          if (!b || typeof b !== "object") return "Each button must be an object.";
          if (!String(b.label || "").trim()) return "Each button must have a non-empty `label`.";
          if (!String(b.action || "").startsWith("menu_")) return "Each button `action` must start with `menu_`.";
        }
      }
      return null;
    } catch (e) {
      return (e as Error).message;
    }
  }, [menuJson]);
  const runtimeConfigError = null;
  const videoFinderSourcesError = useMemo(() => {
    if (!videoFinderSourcesJson.trim()) return null;
    try {
      const parsed = JSON.parse(videoFinderSourcesJson) as unknown;
      if (!Array.isArray(parsed)) return "Video finder sources must be an array.";
      for (const row of parsed) {
        if (!row || typeof row !== "object") return "Each source must be an object.";
        const r = row as { id?: unknown; name?: unknown; url?: unknown };
        if (!String(r.id || "").trim()) return "Each source needs a non-empty id.";
        if (!String(r.name || "").trim()) return "Each source needs a non-empty name.";
        const url = String(r.url || "").trim();
        if (!/^https?:\/\//i.test(url) || !url.includes("{username}")) {
          return "Each source url must be http(s) and include {username}.";
        }
      }
      return null;
    } catch (e) {
      return (e as Error).message;
    }
  }, [videoFinderSourcesJson]);

  const save = useMutation({
    mutationFn: async () => {
      const body: Record<string, unknown> = {
        welcome_html: welcomeHtml.trim() || null,
        loot_intro_html: lootIntroHtml.trim() || null,
        subscribe_title_main: subscribeTitleMain.trim() || null,
        subscribe_title_loot: subscribeTitleLoot.trim() || null,
        subscription_catalog_columns: Math.max(1, Math.min(4, Number(columns || 2))),
        min_subscription_stars: Math.max(0, Number(minStars || 0)),
        runtime_adapter: runtimeAdapter,
        runtime_cmd_start: cmdStart.trim() || null,
        runtime_cmd_stop: cmdStop.trim() || null,
        runtime_cmd_restart: cmdRestart.trim() || null,
        runtime_cmd_reload: cmdReload.trim() || null,
        runtime_cmd_status: cmdStatus.trim() || null,
        video_finder_enabled: !!videoFinderEnabled,
        video_finder_max_links_per_source: Math.max(1, Math.min(30, Number(videoFinderMaxLinks || 8))),
      };
      if (videoFinderSourcesJson.trim()) {
        body.video_finder_sources = JSON.parse(videoFinderSourcesJson);
      }
      if (menuJson.trim()) {
        body.main_menu = JSON.parse(menuJson);
      }
      return api.paymentBotSettings.patch(body);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["paymentBotSettings"] });
      setEdited(false);
    },
  });

  return (
    <div className="max-w-4xl">
      <h2 className="text-xl font-semibold mb-2">Payment bot runtime settings</h2>
      <p className="text-slate-400 text-sm mb-4">
        Controls for menu tree and copy used by `payment_bot.py`. Changes are pulled by the bot every ~30 seconds.
      </p>
      {settingsQ.isError && (
        <QueryErrorBanner
          title="Could not load payment bot settings"
          message={String((settingsQ.error as Error)?.message ?? settingsQ.error)}
          onRetry={() => void settingsQ.refetch()}
        />
      )}
      <div className="grid gap-4">
        <label className="block">
          <span className="text-slate-400 text-xs">Main menu button tree (JSON)</span>
          <textarea
            rows={12}
            value={menuJson || MENU_TEMPLATE}
            onChange={(e) => {
              setMenuJson(e.target.value);
              setEdited(true);
            }}
            className="mt-1 w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200 text-xs font-mono"
          />
          <p className="text-slate-500 text-xs mt-1">
            Allowed actions: `menu_shop`, `menu_loot`, `menu_loot_subscribe`, `menu_subscribe`, `menu_packs`, `menu_referral`, `menu_status`.
          </p>
          {menuParseError ? <p className="text-red-300 text-xs mt-1">{menuParseError}</p> : null}
        </label>

        <label className="block">
          <span className="text-slate-400 text-xs">Welcome HTML (optional override)</span>
          <textarea
            rows={5}
            value={welcomeHtml}
            onChange={(e) => {
              setWelcomeHtml(e.target.value);
              setEdited(true);
            }}
            className="mt-1 w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200 text-sm"
          />
        </label>

        <label className="block">
          <span className="text-slate-400 text-xs">Loot intro HTML (optional override)</span>
          <textarea
            rows={5}
            value={lootIntroHtml}
            onChange={(e) => {
              setLootIntroHtml(e.target.value);
              setEdited(true);
            }}
            className="mt-1 w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200 text-sm"
          />
        </label>

        <div className="grid sm:grid-cols-2 gap-3">
          <label className="block">
            <span className="text-slate-400 text-xs">Subscribe title (main)</span>
            <input
              value={subscribeTitleMain}
              onChange={(e) => {
                setSubscribeTitleMain(e.target.value);
                setEdited(true);
              }}
              className="mt-1 w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200"
            />
          </label>
          <label className="block">
            <span className="text-slate-400 text-xs">Subscribe title (loot)</span>
            <input
              value={subscribeTitleLoot}
              onChange={(e) => {
                setSubscribeTitleLoot(e.target.value);
                setEdited(true);
              }}
              className="mt-1 w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200"
            />
          </label>
          <label className="block">
            <span className="text-slate-400 text-xs">Subscription grid columns (1-4)</span>
            <input
              type="number"
              min={1}
              max={4}
              value={columns}
              onChange={(e) => {
                setColumns(Number(e.target.value) || 2);
                setEdited(true);
              }}
              className="mt-1 w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200"
            />
          </label>
          <label className="block">
            <span className="text-slate-400 text-xs">Min subscription Stars (hide lower-priced plans)</span>
            <input
              type="number"
              min={0}
              value={minStars}
              onChange={(e) => {
                setMinStars(Number(e.target.value) || 0);
                setEdited(true);
              }}
              className="mt-1 w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200"
            />
          </label>
        </div>

        <div className="border border-slate-700 rounded-lg p-3 bg-slate-900/30">
          <h3 className="text-sm font-semibold text-slate-200 mb-2">Runtime adapter</h3>
          <p className="text-xs text-slate-400 mb-3">
            On Windows, leave commands empty to delegate to TBCC Supervisor tray (<code className="text-slate-300">tbcc-stack-cli.ps1</code>).
            Override only for Docker or custom service managers.
          </p>
          <label className="block mb-3">
            <span className="text-slate-400 text-xs">Adapter</span>
            <select
              value={runtimeAdapter}
              onChange={(e) => {
                setRuntimeAdapter(e.target.value as "local" | "command");
                setEdited(true);
              }}
              className="mt-1 w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200"
            >
              <option value="local">local (API starts python process)</option>
              <option value="command">command (tray / custom scripts)</option>
            </select>
          </label>
          {runtimeAdapter === "command" ? (
            <div className="grid gap-3">
              <label className="block">
                <span className="text-slate-400 text-xs">Start command (optional on Windows — tray default)</span>
                <input
                  value={cmdStart}
                  onChange={(e) => {
                    setCmdStart(e.target.value);
                    setEdited(true);
                  }}
                  placeholder="(empty = tray Start-TbccStackService payment)"
                  className="mt-1 w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200 text-sm"
                />
              </label>
              <label className="block">
                <span className="text-slate-400 text-xs">Stop command (optional on Windows — tray default)</span>
                <input
                  value={cmdStop}
                  onChange={(e) => {
                    setCmdStop(e.target.value);
                    setEdited(true);
                  }}
                  placeholder="(empty = tray Stop-TbccStackService payment)"
                  className="mt-1 w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200 text-sm"
                />
              </label>
              <label className="block">
                <span className="text-slate-400 text-xs">Restart command (optional)</span>
                <input
                  value={cmdRestart}
                  onChange={(e) => {
                    setCmdRestart(e.target.value);
                    setEdited(true);
                  }}
                  placeholder='docker compose -f infra/docker-compose.yml restart payment_bot'
                  className="mt-1 w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200 text-sm"
                />
              </label>
              <label className="block">
                <span className="text-slate-400 text-xs">Reload command (optional)</span>
                <input
                  value={cmdReload}
                  onChange={(e) => {
                    setCmdReload(e.target.value);
                    setEdited(true);
                  }}
                  placeholder='docker compose -f infra/docker-compose.yml kill -s HUP payment_bot'
                  className="mt-1 w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200 text-sm"
                />
              </label>
              <label className="block">
                <span className="text-slate-400 text-xs">Status command (optional)</span>
                <input
                  value={cmdStatus}
                  onChange={(e) => {
                    setCmdStatus(e.target.value);
                    setEdited(true);
                  }}
                  placeholder='docker compose -f infra/docker-compose.yml ps payment_bot'
                  className="mt-1 w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200 text-sm"
                />
              </label>
            </div>
          ) : null}
        </div>

        <div className="border border-slate-700 rounded-lg p-3 bg-slate-900/30">
          <h3 className="text-sm font-semibold text-slate-200 mb-2">Macro / video search</h3>
          <p className="text-xs text-slate-400 mb-3">
            Powers <code>/macrosearch</code> and <code>/videofind</code> in the payment bot. Built-in macro
            sources come from <code>extension/model-search-sites.json</code> (same as the TBCC extension).
            Add more via Telegram <code>/macroaddsource</code> (admin) or override legacy per-source JSON below.
            Each URL must include <code>{"{username}"}</code>.
          </p>
          <label className="flex items-center gap-2 text-sm text-slate-200 mb-3">
            <input
              type="checkbox"
              checked={videoFinderEnabled}
              onChange={(e) => {
                setVideoFinderEnabled(e.target.checked);
                setEdited(true);
              }}
            />
            Enable video finder command
          </label>
          <label className="block mb-3">
            <span className="text-slate-400 text-xs">Max links per source message (1-30)</span>
            <input
              type="number"
              min={1}
              max={30}
              value={videoFinderMaxLinks}
              onChange={(e) => {
                setVideoFinderMaxLinks(Number(e.target.value) || 8);
                setEdited(true);
              }}
              className="mt-1 w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200"
            />
          </label>
          <label className="block">
            <span className="text-slate-400 text-xs">Sources JSON</span>
            <textarea
              rows={10}
              value={videoFinderSourcesJson}
              onChange={(e) => {
                setVideoFinderSourcesJson(e.target.value);
                setEdited(true);
              }}
              className="mt-1 w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200 text-xs font-mono"
            />
          </label>
          {videoFinderSourcesError ? <p className="text-red-300 text-xs mt-1">{videoFinderSourcesError}</p> : null}
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => save.mutate()}
            disabled={save.isPending || !!menuParseError || !!runtimeConfigError || !!videoFinderSourcesError}
            className="px-4 py-2 bg-cyan-600 text-white rounded hover:bg-cyan-500 disabled:opacity-50"
          >
            {save.isPending ? "Saving..." : "Save payment bot settings"}
          </button>
          {runtimeConfigError ? <p className="text-red-300 text-sm">{runtimeConfigError}</p> : null}
          {save.isError ? <p className="text-red-300 text-sm">{(save.error as Error).message}</p> : null}
          {save.isSuccess ? <p className="text-emerald-300 text-sm">Saved.</p> : null}
        </div>
      </div>
    </div>
  );
}
