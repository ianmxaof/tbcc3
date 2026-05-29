import { useMemo, useState } from "react";
import {
  AESTHETIC_CATEGORIES,
  TELEGRAM_POST_AESTHETICS,
  type PostAestheticEntry,
} from "../lib/telegramPostAesthetics";

export function TelegramPostAestheticsCompendium() {
  const [category, setCategory] = useState<string>("all");
  const [tier, setTier] = useState<number | "">("");

  const rows = useMemo(() => {
    return TELEGRAM_POST_AESTHETICS.filter((e) => {
      if (category !== "all" && e.category !== category) return false;
      if (tier !== "" && e.tierHints && !e.tierHints.includes(tier)) return false;
      return true;
    });
  }, [category, tier]);

  return (
    <details className="rounded-lg border border-cyan-900/40 bg-cyan-950/10 p-3">
      <summary className="cursor-pointer text-sm font-medium text-cyan-100">
        Post aesthetics compendium ({TELEGRAM_POST_AESTHETICS.length} patterns)
      </summary>
      <p className="text-xs text-slate-400 mt-2 max-w-3xl leading-relaxed">
        Reference for loot overseer tier styling: album grids, file+media sequences, HTML captions, and TBCC send
        order. Your screenshot is <strong className="text-slate-300">document_then_album</strong> +{" "}
        <strong className="text-slate-300">album_2_horizontal</strong>.
      </p>
      <div className="flex flex-wrap gap-2 mt-3">
        <select
          className="text-xs bg-slate-950 border border-slate-600 rounded px-2 py-1"
          value={category}
          onChange={(e) => setCategory(e.target.value)}
        >
          <option value="all">All categories</option>
          {(Object.keys(AESTHETIC_CATEGORIES) as PostAestheticEntry["category"][]).map((k) => (
            <option key={k} value={k}>
              {AESTHETIC_CATEGORIES[k]}
            </option>
          ))}
        </select>
        <select
          className="text-xs bg-slate-950 border border-slate-600 rounded px-2 py-1"
          value={tier === "" ? "" : String(tier)}
          onChange={(e) => setTier(e.target.value ? Number(e.target.value) : "")}
        >
          <option value="">Any tier</option>
          {[1, 2, 3, 4, 5, 6, 7].map((t) => (
            <option key={t} value={t}>
              Tier {t}
            </option>
          ))}
        </select>
      </div>
      <ul className="mt-3 space-y-2 max-h-64 overflow-y-auto text-xs">
        {rows.map((e) => (
          <li key={e.id} className="border border-slate-700/80 rounded px-2 py-2 bg-slate-900/50">
            <div className="flex flex-wrap gap-2 items-baseline">
              <span className="font-mono text-cyan-400/90">{e.id}</span>
              <span className="text-slate-200 font-medium">{e.title}</span>
              {e.tierHints?.length ? (
                <span className="text-slate-500">tiers {e.tierHints.join(",")}</span>
              ) : null}
            </div>
            <p className="text-slate-400 mt-1">{e.description}</p>
            <p className="text-slate-500 mt-1">
              <span className="text-slate-400">TBCC:</span> {e.tbccNotes}
            </p>
            {e.example ? (
              <p className="text-violet-300/80 mt-1 font-mono text-[10px]">{e.example}</p>
            ) : null}
          </li>
        ))}
      </ul>
    </details>
  );
}
