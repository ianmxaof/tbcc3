import { useCallback, useEffect, useState } from "react";

type Conflict = {
  code: string;
  severity: string;
  message: string;
  action?: string;
  action_label?: string;
};

type SystemHealth = {
  ok?: boolean;
  conflicts?: Conflict[];
  recommendations?: string[];
  import_pipeline?: { active_jobs?: number };
  ports?: Record<string, boolean | number>;
  fixable_count?: number;
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
  if (health.ok && conflicts.length === 0) return null;

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
        </div>
        <div className="flex flex-col gap-1 shrink-0">
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
