import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api";

export function LinkScrapeDeploy() {
  const [chatId, setChatId] = useState("");
  const [limit, setLimit] = useState(40);
  const [directOnly, setDirectOnly] = useState(true);
  const [notice, setNotice] = useState<string | null>(null);

  const deploy = useMutation({
    mutationFn: () =>
      api.jobs.triggerMegaScrape({
        chat_id: chatId.trim() ? Number(chatId.trim()) : undefined,
        message_limit: limit,
        direct_only: directOnly,
        execute: true,
      }),
    onSuccess: (data) => {
      setNotice(
        `Link scrape queued (run #${data.run_id}). Watch the banner — modifiers land in Loot when done.`
      );
    },
    onError: (e: Error) => setNotice(e.message),
  });

  return (
    <div className="bg-slate-800 rounded-lg p-4 mb-6 max-w-2xl border border-violet-800/40">
      <h2 className="text-lg font-medium mb-1 text-violet-200">Link scrape (mega / paste / Sophon)</h2>
      <p className="text-slate-500 text-xs mb-3">
        Pull file-host and paste URLs from Telegram channel posts → validate → LV rewrap →{" "}
        <strong className="text-slate-400">loot modifiers</strong>. Leave channel id empty to run all{" "}
        <em>direct_host + mixed</em> sources from your curated list. LV-gated channels need bypass.vip key.
      </p>
      <div className="space-y-2">
        <input
          type="text"
          placeholder="Channel id (-100…) or empty = curated batch"
          value={chatId}
          onChange={(e) => setChatId(e.target.value)}
          className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200 font-mono text-sm"
        />
        <label className="block text-slate-400 text-xs">
          Messages per channel
          <div className="flex items-center gap-2 mt-1">
            <button
              type="button"
              onClick={() => setLimit((n) => Math.max(5, n - 5))}
              className="h-8 w-8 rounded bg-slate-700 border border-slate-600 text-slate-200"
            >
              −
            </button>
            <span className="text-slate-200 font-mono min-w-[3rem] text-center">{limit}</span>
            <button
              type="button"
              onClick={() => setLimit((n) => Math.min(200, n + 5))}
              className="h-8 w-8 rounded bg-slate-700 border border-slate-600 text-slate-200"
            >
              +
            </button>
          </div>
        </label>
        <label className="flex items-center gap-2 text-slate-300 text-sm">
          <input type="checkbox" checked={directOnly} onChange={(e) => setDirectOnly(e.target.checked)} />
          Direct / paste only (skip Linkvertise until bypass key)
        </label>
        <button
          type="button"
          onClick={() => deploy.mutate()}
          disabled={deploy.isPending}
          className="px-4 py-2 bg-violet-600 text-white rounded hover:bg-violet-500 disabled:opacity-50"
        >
          {deploy.isPending ? "Deploying…" : "Deploy link scrape"}
        </button>
        {notice ? (
          <p className={`text-sm ${notice.includes("queued") ? "text-emerald-300" : "text-amber-300"}`}>{notice}</p>
        ) : null}
      </div>
    </div>
  );
}
