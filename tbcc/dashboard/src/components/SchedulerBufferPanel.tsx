import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api } from "../api";

/** Buffer → X on the Scheduler page — not Misc. */
export function SchedulerBufferPanel() {
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
            ? `Published ${n} channel(s) via Buffer shareNow. Check X shortly.`
            : `Queued ${n} item(s) in Buffer. Open publish.buffer.com → Queue.`
          : "No confirmation from Buffer — check API / backend logs."
      );
      window.setTimeout(() => setMsg(null), 14000);
    },
    onError: (e: unknown) => {
      const raw = e instanceof Error ? e.message : "Buffer test failed";
      const hint =
        raw.includes("posted that one recently") || raw.includes("buffer_errors")
          ? " Buffer blocks duplicate copy — wait a few minutes or retry (test text is timestamped)."
          : "";
      setMsg(raw + hint);
      window.setTimeout(() => setMsg(null), 16000);
    },
  });

  return (
    <section className="mb-8 max-w-3xl border border-slate-600 rounded-lg p-5 bg-slate-900/50">
      <h2 className="text-lg font-medium text-slate-100 mb-1">Social · Buffer</h2>
      <p className="text-slate-400 text-sm mb-3">
        With <strong className="text-slate-300">Buffer → X</strong> on a scheduled row, each successful Telegram send
        triggers one Buffer post. Use <strong className="text-slate-300">Publish now</strong> per job for Buffer{" "}
        <code className="text-slate-500">shareNow</code> (X goes live right after Telegram). Leave it off for{" "}
        <code className="text-slate-500">addToQueue</code> (Buffer&apos;s own queue timing). Pre-write up to 10 X captions
        in the row editor; otherwise TBCC mirrors the Telegram caption.
      </p>
      <ul className="text-xs text-slate-500 mb-4 list-disc pl-5 space-y-1">
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
          <input
            type="checkbox"
            checked={testPublishNow}
            onChange={(e) => setTestPublishNow(e.target.checked)}
          />
          Test with publish now
        </label>
        <button
          type="button"
          className="px-3 py-2 rounded bg-emerald-700 text-white text-sm hover:bg-emerald-600 disabled:opacity-50"
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
      {msg ? <p className="text-sm text-emerald-200 mt-3">{msg}</p> : null}
    </section>
  );
}
