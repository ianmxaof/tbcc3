import { useState } from "react";
import { BotMonitor } from "./BotMonitor";
import { BotShop } from "./BotShop";
import { Growth } from "./Growth";
import { WatchFolder } from "./WatchFolder";
import { PaymentBotSettingsPanel } from "./PaymentBotSettings";
import { LootOverseerSettingsPanel } from "./LootOverseerSettings";
import { SecretarySettingsPanel } from "./SecretarySettingsPanel";
import { CompanionSettingsPanel } from "./CompanionSettingsPanel";

type Tab = "shop" | "settings" | "loot" | "secretary" | "companion" | "referrals" | "monitor" | "watch";

export function BotsPanel() {
  const [tab, setTab] = useState<Tab>(() => {
    try {
      const saved = sessionStorage.getItem("tbccBotsTab");
      if (saved === "secretary" || saved === "loot" || saved === "settings" || saved === "shop" || saved === "referrals" || saved === "monitor" || saved === "watch" || saved === "companion") {
        sessionStorage.removeItem("tbccBotsTab");
        return saved as Tab;
      }
    } catch {
      /* ignore */
    }
    return "shop";
  });

  return (
    <div>
      <h1 className="text-2xl font-semibold mb-2">Bots</h1>
      <p className="text-slate-400 mb-6 max-w-2xl">
        Configure what your Telegram payment bot sells, the loot overseer bot, secretary / Format Engine, payment bot runtime behavior, referral/landing copy, and worker processes.
      </p>

      <div className="flex gap-1 mb-6 border-b border-slate-700 flex-wrap">
        <button
          type="button"
          onClick={() => setTab("shop")}
          className={`px-4 py-2 text-sm font-medium rounded-t-lg border-b-2 -mb-px transition-colors ${
            tab === "shop"
              ? "border-cyan-500 text-cyan-400 bg-slate-800/80"
              : "border-transparent text-slate-400 hover:text-slate-200"
          }`}
        >
          Shop products
        </button>
        <button
          type="button"
          onClick={() => setTab("settings")}
          className={`px-4 py-2 text-sm font-medium rounded-t-lg border-b-2 -mb-px transition-colors ${
            tab === "settings"
              ? "border-cyan-500 text-cyan-400 bg-slate-800/80"
              : "border-transparent text-slate-400 hover:text-slate-200"
          }`}
        >
          Payment bot settings
        </button>
        <button
          type="button"
          onClick={() => setTab("loot")}
          className={`px-4 py-2 text-sm font-medium rounded-t-lg border-b-2 -mb-px transition-colors ${
            tab === "loot"
              ? "border-cyan-500 text-cyan-400 bg-slate-800/80"
              : "border-transparent text-slate-400 hover:text-slate-200"
          }`}
        >
          Loot overseer
        </button>
        <button
          type="button"
          onClick={() => setTab("secretary")}
          className={`px-4 py-2 text-sm font-medium rounded-t-lg border-b-2 -mb-px transition-colors ${
            tab === "secretary"
              ? "border-cyan-500 text-cyan-400 bg-slate-800/80"
              : "border-transparent text-slate-400 hover:text-slate-200"
          }`}
        >
          Secretary / FAQ
        </button>
        <button
          type="button"
          onClick={() => setTab("companion")}
          className={`px-4 py-2 text-sm font-medium rounded-t-lg border-b-2 -mb-px transition-colors ${
            tab === "companion"
              ? "border-cyan-500 text-cyan-400 bg-slate-800/80"
              : "border-transparent text-slate-400 hover:text-slate-200"
          }`}
        >
          Companion / spicy
        </button>
        <button
          type="button"
          onClick={() => setTab("referrals")}
          className={`px-4 py-2 text-sm font-medium rounded-t-lg border-b-2 -mb-px transition-colors ${
            tab === "referrals"
              ? "border-cyan-500 text-cyan-400 bg-slate-800/80"
              : "border-transparent text-slate-400 hover:text-slate-200"
          }`}
        >
          Referrals &amp; growth
        </button>
        <button
          type="button"
          onClick={() => setTab("monitor")}
          className={`px-4 py-2 text-sm font-medium rounded-t-lg border-b-2 -mb-px transition-colors ${
            tab === "monitor"
              ? "border-cyan-500 text-cyan-400 bg-slate-800/80"
              : "border-transparent text-slate-400 hover:text-slate-200"
          }`}
        >
          Process monitor
        </button>
        <button
          type="button"
          onClick={() => setTab("watch")}
          className={`px-4 py-2 text-sm font-medium rounded-t-lg border-b-2 -mb-px transition-colors ${
            tab === "watch"
              ? "border-cyan-500 text-cyan-400 bg-slate-800/80"
              : "border-transparent text-slate-400 hover:text-slate-200"
          }`}
        >
          Watch folder
        </button>
      </div>

      {tab === "shop" ? (
        <BotShop />
      ) : tab === "settings" ? (
        <PaymentBotSettingsPanel />
      ) : tab === "loot" ? (
        <LootOverseerSettingsPanel />
      ) : tab === "secretary" ? (
        <SecretarySettingsPanel />
      ) : tab === "companion" ? (
        <CompanionSettingsPanel />
      ) : tab === "referrals" ? (
        <Growth />
      ) : tab === "watch" ? (
        <WatchFolder />
      ) : (
        <BotMonitor />
      )}
    </div>
  );
}
