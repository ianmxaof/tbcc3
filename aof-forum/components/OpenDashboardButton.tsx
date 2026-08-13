"use client";

import { useCallback, useState } from "react";

/** Mint bridge URL and open TBCC dashboard. */
export function OpenDashboardButton() {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const open = useCallback(async () => {
    setBusy(true);
    setErr(null);
    try {
      const res = await fetch("/api/admin/bridge/dashboard", { method: "POST" });
      const data = (await res.json()) as { ok?: boolean; url?: string; error?: string };
      if (!res.ok || !data.url) throw new Error(data.error || `HTTP ${res.status}`);
      window.open(data.url, "_blank", "noopener,noreferrer");
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, []);

  return (
    <button type="button" onClick={() => void open()} disabled={busy}>
      {busy ? "Opening…" : "Open TBCC dashboard"}
      {err ? ` (${err})` : ""}
    </button>
  );
}
