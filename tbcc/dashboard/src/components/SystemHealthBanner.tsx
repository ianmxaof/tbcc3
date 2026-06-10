import { useCallback, useEffect, useState } from "react";

type Conflict = {
  code: string;
  severity: string;
  message: string;
  action?: string;
  action_label?: string;
};

type FocusState = {
  state?: { profile?: string; reason?: string; since?: string; auto?: boolean };
  evaluation?: { suggested_profile?: string | null; lock_events?: number };
};

type SystemHealth = {
  ok?: boolean;
  conflicts?: Conflict[];
  recommendations?: string[];
  import_pipeline?: { active_jobs?: number };
  ports?: Record<string, boolean | number>;
  fixable_count?: number;
  focus?: FocusState | null;
};

const API = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

export function SystemHealthBanner() {
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [dismissed, setDismissed] = useState(false);
  const [fixing, setFixing] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const r = await fetch(`${API}/health/system`, { cache: "no-store" });
      const data = (await r.json()) as SystemHealth;
      setHealth(data);
    } catch {
      setHealth({
        ok: false,
        conflicts: [
          {
            code: "api_unreachable",
            severity: "critical",
            message: "TBCC API not reachable — restart from the TBCC tray or run start.ps1",
          },
        ],
      });
    }
  }, []);

  useEffect(() => {
    void load();
    const t = setInterval(() => void load(), 20000);
    return () => clearInterval(t);
  }, [load]);

  const applyFocus = async (profile: string) => {
    setFixing(`focus:${profile}`);
    try {
      const r = await fetch(`${API}/ops/focus`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ profile, reason: "Dashboard focus apply" }),
      });
      if (r.ok) await load();
    } catch {
      /* ignore */
    } finally {
      setFixing(null);
    }
  };

  const runRemediate = async (codes?: string[]) => {
    setFixing(codes?.join(",") ?? "all");
    try {
      const r = await fetch(`${API}/health/system/remediate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(codes?.length ? { codes } : {}),
      });
      if (r.ok) {
        const data = (await r.json()) as { health?: SystemHealth };
        if (data.health) setHealth(data.health);
        else await load();
      }
    } catch {
      /* API may be down */
    } finally {
      setFixing(null);
    }
  };

  if (dismissed || !health) return null;
  const conflicts = health.conflicts || [];
  const focusProfile = health.focus?.state?.profile || "off";
  const focusActive = focusProfile !== "off";
  if (health.ok && conflicts.length === 0 && !focusActive) return null;

  const critical = conflicts.filter((c) => c.severity === "critical");
  const fixable = conflicts.filter((c) => c.action);
  const apiDown = conflicts.some((c) => c.code === "api_unreachable");

  return (
    <div
      className={
        critical.length
          ? "bg-red-950/90 border-b border-red-700 px-4 py-2 text-sm text-red-100"
          : "bg-amber-950/80 border-b border-amber-700 px-4 py-2 text-sm text-amber-100"
      }
      role="status"
    >
      <div className="flex flex-wrap items-start gap-3">
        <div className="flex-1 min-w-[200px]">
          <strong className="font-medium">
            {critical.length ? "TBCC system issues" : "TBCC warnings"}
          </strong>
          <ul className="mt-1 space-y-2">
            {conflicts.map((c) => (
              <li key={c.code} className="flex flex-wrap items-center gap-2">
                <span className="opacity-95">
                  <span className="font-mono text-xs opacity-70">{c.code}</span> — {c.message}
                </span>
                {c.action && !apiDown ? (
                  <button
                    type="button"
                    disabled={fixing !== null}
                    onClick={() => void runRemediate([c.code])}
                    className="text-xs px-2 py-0.5 rounded bg-red-800/80 hover:bg-red-700 text-red-50 disabled:opacity-50 shrink-0"
                  >
                    {fixing === c.code ? "…" : c.action_label || "Fix"}
                  </button>
                ) : null}
              </li>
            ))}
          </ul>
          {(health.recommendations || []).length > 0 && (
            <p className="mt-2 text-xs opacity-80">
              {(health.recommendations || []).join(" · ")}
            </p>
          )}
          {typeof health.import_pipeline?.active_jobs === "number" &&
            health.import_pipeline.active_jobs > 0 && (
              <p className="mt-1 text-xs">
                Active import jobs: {health.import_pipeline.active_jobs}
              </p>
            )}
          {focusActive ? (
            <p className="mt-2 text-xs font-medium text-cyan-200/90">
              Focus profile: <span className="font-mono">{focusProfile}</span>
              {health.focus?.state?.auto ? " (auto)" : ""}
              {health.focus?.state?.reason ? ` — ${health.focus.state.reason}` : ""}
            </p>
          ) : null}
        </div>
        <div className="flex flex-col gap-1 shrink-0">
          {!apiDown ? (
            <>
              <button
                type="button"
                className="text-xs px-2 py-1 rounded bg-cyan-900/80 hover:bg-cyan-800 text-cyan-50 disabled:opacity-50"
                disabled={fixing !== null}
                onClick={() => void applyFocus("import_burst")}
              >
                Focus: import burst
              </button>
              <button
                type="button"
                className="text-xs px-2 py-1 rounded bg-cyan-900/60 hover:bg-cyan-800 text-cyan-50 disabled:opacity-50"
                disabled={fixing !== null}
                onClick={() => void applyFocus("telegram_relief")}
              >
                Focus: Telegram relief
              </button>
              {focusActive ? (
                <button
                  type="button"
                  className="text-xs px-2 py-1 rounded border border-cyan-700/60 hover:bg-cyan-950/50 disabled:opacity-50"
                  disabled={fixing !== null}
                  onClick={() => void applyFocus("off")}
                >
                  End focus (restore)
                </button>
              ) : null}
            </>
          ) : null}
          {fixable.length > 0 && !apiDown ? (
            <button
              type="button"
              className="text-xs px-2 py-1 rounded bg-red-800/80 hover:bg-red-700 text-red-50 disabled:opacity-50"
              disabled={fixing !== null}
              onClick={() => void runRemediate()}
            >
              {fixing === "all" ? "Fixing…" : `Fix all (${fixable.length})`}
            </button>
          ) : null}
          <button
            type="button"
            className="text-xs underline opacity-80 hover:opacity-100"
            onClick={() => setDismissed(true)}
          >
            Dismiss
          </button>
        </div>
      </div>
    </div>
  );
}
