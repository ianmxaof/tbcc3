"use client";

import { useState } from "react";

export function ReportButton({
  targetKind,
  targetId,
}: {
  targetKind: "media" | "gallery" | "group" | "thread" | "post" | "connect_listing";
  targetId: number;
}) {
  const [state, setState] = useState<"idle" | "sending" | "done" | "error">("idle");

  const report = async () => {
    if (state === "sending" || state === "done") return;
    const reason = window.prompt("Report reason (optional):") ?? "";
    setState("sending");
    try {
      const res = await fetch("/api/report", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ targetKind, targetId, reason: reason || undefined }),
      });
      if (!res.ok) {
        const j = await res.json().catch(() => ({}));
        throw new Error(j.error || "report failed");
      }
      setState("done");
    } catch {
      setState("error");
    }
  };

  return (
    <button type="button" className="ghost danger" onClick={() => void report()} disabled={state === "done"}>
      {state === "done" ? "Reported" : state === "error" ? "Report failed" : "Report"}
    </button>
  );
}
