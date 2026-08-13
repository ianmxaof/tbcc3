import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";

/**
 * When opened via forum → dashboard bridge (?bridge=TOKEN), validate once then strip query.
 * On island the nginx proxy already injects the internal API key — bridge is SSO convenience + audit.
 */
export function AdminBridgeConsumer() {
  const navigate = useNavigate();
  const ran = useRef(false);

  useEffect(() => {
    if (ran.current) return;
    const params = new URLSearchParams(window.location.search);
    const token = params.get("bridge");
    if (!token) return;
    ran.current = true;
    const next = params.get("next") || "/";

    void (async () => {
      try {
        await api.adminBridgeConsume({
          token,
          expected_audience: "dashboard",
        });
        sessionStorage.setItem("tbcc:adminBridgeOk", String(Date.now()));
      } catch {
        sessionStorage.setItem("tbcc:adminBridgeErr", "1");
      } finally {
        const path = next.startsWith("/") ? next : `/${next}`;
        navigate(path, { replace: true });
      }
    })();
  }, [navigate]);

  return null;
}
