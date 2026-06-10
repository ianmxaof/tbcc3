import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api } from "../api";
import { InfoDisclosure } from "./InfoDisclosure";

type Props = {
  /** Fits inside the 4-column scheduler composer grid. */
  compact?: boolean;
};

/** Buffer → X on the Scheduler page — not Misc. */
export function SchedulerBufferPanel({ compact = false }: Props) {
  const [msg, setMsg] = useState<string | null>(null);
  const [testPublishNow, setTestPublishNow] = useState(false);
  const test = useMutation({
    mutationFn: () =>
      api.listeningRelay.bufferTestPost({ x_only: true, publish_now: testPublishNow }),
    onSuccess: (data) => {
      const n = data.queued?.length ?? 0;
      const mode = (data as { mode?: string }).mode || (testPublishNow ? "shareNow" : "addToQueue");
      setMsg(
        n
          ? mode === "shareNow"
            ? `Published ${n} channel(s) via shareNow.`
            : `Queued ${n} in Buffer — check publish.buffer.com.`
          : "No confirmation — check API / logs."
      );
      window.setTimeout(() => setMsg(null), 14000);
    },
    onError: (e: unknown) => {
      const raw = e instanceof Error ? e.message : "Buffer test failed";
      const hint =
        raw.includes("posted that one recently") || raw.includes("buffer_errors")
          ? " Duplicate copy blocked — wait or retry."
          : "";
      setMsg(raw + hint);
      window.setTimeout(() => setMsg(null), 16000);
    },
  });

  if (compact) {
    return (
      <div className="space-y-2 text-[11px]">
        <p className="text-slate-500 leading-snug">
          Per-job <strong className="text-slate-300">Buffer → X</strong> mirrors Telegram to X.{" "}
          <InfoDisclosure>
            shareNow posts right after send; addToQueue uses Buffer&apos;s queue (Free: 10 slots/channel). Row editor
            holds up to 10 custom X captions; else TBCC mirrors Telegram. Env{" "}
            <code className="text-slate-500">TBCC_BUFFER_SCHEDULED_SHARE_NOW=1</code> defaults publish-now.
          </InfoDisclosure>
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <label className="flex items-center gap-1.5 text-slate-300">
            <input
              type="checkbox"
              checked={testPublishNow}
              onChange={(e) => setTestPublishNow(e.target.checked)}
            />
            Test publish now
          </label>
          <button
            type="button"
            className="rounded bg-emerald-700 px-2 py-1 text-[10px] text-white hover:bg-emerald-600 disabled:opacity-50"
            disabled={test.isPending}
            onClick={() => test.mutate()}
          >
            {test.isPending ? "…" : testPublishNow ? "Test shareNow" : "Test queue"}
          </button>
          <a
            href="https://publish.buffer.com"
            target="_blank"
            rel="noreferrer"
            className="text-[10px] text-cyan-400 hover:underline"
          >
            Buffer
          </a>
        </div>
        {msg ? <p className="text-[10px] text-emerald-200/90">{msg}</p> : null}
      </div>
    );
  }

  return (
    <section className="mb-8 max-w-3xl rounded-lg border border-slate-600 bg-slate-900/50 p-5">
      <h2 className="mb-1 text-lg font-medium text-slate-100">Social · Buffer</h2>
      <p className="mb-3 text-sm text-slate-400">
        With <strong className="text-slate-300">Buffer → X</strong> on a scheduled row, each successful Telegram send
        triggers one Buffer post. Use <strong className="text-slate-300">Publish now</strong> per job for Buffer{" "}
        <code className="text-slate-500">shareNow</code> (X goes live right after Telegram). Leave it off for{" "}
        <code className="text-slate-500">addToQueue</code> (Buffer&apos;s own queue timing). Pre-write up to 10 X captions
        in the row editor; otherwise TBCC mirrors the Telegram caption.
      </p>
      <ul className="mb-4 list-disc space-y-1 pl-5 text-xs text-slate-500">
        <li>
          <strong className="text-slate-400">Buffer Free:</strong> up to 10 posts waiting in queue per channel when using
          addToQueue.
        </li>
        <li>
          <strong className="text-slate-400">Global default:</strong> set{" "}
          <code className="text-slate-500">TBCC_BUFFER_SCHEDULED_SHARE_NOW=1</code> in <code className="text-slate-500">.env</code>{" "}
          to default all jobs to publish now (per-job checkbox still overrides).
        </li>
      </ul>
      <div className="flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-2 text-sm text-slate-300">
          <input type="checkbox" checked={testPublishNow} onChange={(e) => setTestPublishNow(e.target.checked)} />
          Test with publish now
        </label>
        <button
          type="button"
          className="rounded bg-emerald-700 px-3 py-2 text-sm text-white hover:bg-emerald-600 disabled:opacity-50"
          disabled={test.isPending}
          onClick={() => test.mutate()}
        >
          {test.isPending ? "Testing…" : testPublishNow ? "Test shareNow → X" : "Test addToQueue"}
        </button>
        <a
          href="https://publish.buffer.com"
          target="_blank"
          rel="noreferrer"
          className="text-sm text-cyan-400 hover:underline"
        >
          Open Buffer
        </a>
      </div>
      {msg ? <p className="mt-3 text-sm text-emerald-200">{msg}</p> : null}
    </section>
  );
}
