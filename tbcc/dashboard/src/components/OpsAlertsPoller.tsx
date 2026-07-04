import { useEffect, useRef } from "react";
import { showAlertToast, type OpsAlert } from "../utils/alertToast";

const API = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";
/** Fast poll so sales/pending checkout toasts feel instant. */
const POLL_MS = 5000;

export function OpsAlertsPoller() {
  const seenRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    const poll = async () => {
      try {
        const r = await fetch(`${API}/ops/alerts/poll`, { cache: "no-store" });
        if (!r.ok) return;
        const data = (await r.json()) as {
          alerts?: OpsAlert[];
          enabled?: boolean;
          hub_toast?: boolean;
          restart_grace?: { active?: boolean };
        };
        if (data.enabled === false) return;
        if (data.restart_grace?.active) return;
        for (const a of data.alerts || []) {
          if (!a?.id || seenRef.current.has(a.id)) continue;
          const kind = (a.kind || "").toLowerCase();
          const code = (a.code || "").toLowerCase();
          if (kind === "error_hub" || code === "error_hub_digest") continue;
          if (!data.hub_toast && kind === "error_hub") continue;
          seenRef.current.add(a.id);
          showAlertToast(a);
        }
        if (seenRef.current.size > 200) {
          seenRef.current = new Set([...seenRef.current].slice(-80));
        }
      } catch {
        /* API may be down */
      }
    };
    void poll();
    const t = setInterval(() => void poll(), POLL_MS);
    return () => clearInterval(t);
  }, []);

  return null;
}
