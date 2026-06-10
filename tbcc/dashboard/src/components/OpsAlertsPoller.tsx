import { useEffect, useRef } from "react";
import { showAlertToast, type OpsAlert } from "../utils/alertToast";

const API = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";
const POLL_MS = 45000;

export function OpsAlertsPoller() {
  const seenRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    const poll = async () => {
      try {
        const r = await fetch(`${API}/ops/alerts/poll`, { cache: "no-store" });
        if (!r.ok) return;
        const data = (await r.json()) as { alerts?: OpsAlert[]; enabled?: boolean };
        if (data.enabled === false) return;
        for (const a of data.alerts || []) {
          if (!a?.id || seenRef.current.has(a.id)) continue;
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
