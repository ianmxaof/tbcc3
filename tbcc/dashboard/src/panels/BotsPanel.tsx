import { useState } from "react";
import { BotMonitor } from "./BotMonitor";
import { BotShop } from "./BotShop";
import { Growth } from "./Growth";

type Tab = "shop" | "referrals" | "monitor";

export function BotsPanel() {
  const [tab, setTab] = useState<Tab>("shop");

  return (
    <div>
      <h1 className="text-2xl font-semibold mb-2">Bots</h1>
      <p className="text-slate-400 mb-6 max-w-2xl">
        Configure what your Telegram payment bot sells, referral &amp; landing copy, and monitor worker processes.
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
      </div>

      {tab === "shop" ? <BotShop /> : tab === "referrals" ? <Growth /> : <BotMonitor />}
    </div>
  );
}
