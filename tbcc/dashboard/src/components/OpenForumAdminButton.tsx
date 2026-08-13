import { useCallback, useState } from "react";
import { api } from "../api";

/** Mint a short-lived URL and open AOF Forum as admin. */
export function OpenForumAdminButton() {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const openForum = useCallback(async () => {
    setBusy(true);
    setErr(null);
    try {
      const res = await api.adminBridgeMint({ destination: "forum", next_path: "/admin" });
      if (!res?.url) throw new Error("No bridge URL returned");
      window.open(res.url, "_blank", "noopener,noreferrer");
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, []);

  return (
    <button
      type="button"
      className="tbcc-header-icon-btn text-slate-400 hover:text-cyan-300 text-xs font-medium px-2"
      title={err ? `Forum admin: ${err}` : "Open AOF Forum admin (bridge)"}
      aria-label="Open AOF Forum admin"
      disabled={busy}
      onClick={() => void openForum()}
    >
      {busy ? "…" : "Forum"}
    </button>
  );
}
