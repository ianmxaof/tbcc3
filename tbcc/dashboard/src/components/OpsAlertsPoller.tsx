import { useEffect, useRef } from "react";
import { api } from "../api";
import { useApiTarget } from "../context/ApiTargetContext";
import { showAlertToast, type OpsAlert } from "../utils/alertToast";

/** Fast poll so sales/pending checkout toasts feel instant. */
const POLL_MS = 5000;

export function OpsAlertsPoller() {
  const { target } = useApiTarget();
  const seenRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    seenRef.current = new Set();
    const poll = async () => {
      try {
        const data = await api.opsAlertsPoll();
        if (data.enabled === false) return;
        if (data.restart_grace?.active) return;
        for (const a of data.alerts || []) {
          if (!a?.id || seenRef.current.has(a.id)) continue;
          const kind = (a.kind || "").toLowerCase();
          const code = (a.code || "").toLowerCase();
          if (kind === "error_hub" || code === "error_hub_digest") continue;
          if (!data.hub_toast && kind === "error_hub") continue;
          seenRef.current.add(a.id);
          showAlertToast(a as OpsAlert);
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
  }, [target]);

  return null;
}
