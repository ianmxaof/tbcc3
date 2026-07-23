import { useCallback, useEffect, useState } from "react";
import { api, type SystemHealth, type SystemHealthConflict } from "../api";
import { useApiTarget } from "../context/ApiTargetContext";
import { calmToastStyle, type ToastSeverityKind } from "../utils/severityToastColors";

const DISMISS_KEY = "tbcc:dismissedHealthFingerprint";

function conflictFingerprint(conflicts: SystemHealthConflict[]): string {
  return conflicts
    .map((c) => c.code)
    .sort()
    .join("|");
}

function readDismissedFingerprint(): string | null {
  try {
    return sessionStorage.getItem(DISMISS_KEY);
  } catch {
    return null;
  }
}

function writeDismissedFingerprint(fp: string) {
  try {
    sessionStorage.setItem(DISMISS_KEY, fp);
  } catch {
    /* ignore */
  }
}

function clearDismissedFingerprint() {
  try {
    sessionStorage.removeItem(DISMISS_KEY);
  } catch {
    /* ignore */
  }
}

function bannerSeverityKind(criticalCount: number, total: number): ToastSeverityKind {
  if (total <= 0) return "info";
  if (criticalCount > 0) return "critical";
  return "warning";
}

export function SystemHealthBanner() {
  const { target } = useApiTarget();
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [dismissedFingerprint, setDismissedFingerprint] = useState<string | null>(() =>
    readDismissedFingerprint()
  );
  const [fixing, setFixing] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await api.healthSystem();
      setHealth(data);
      const fp = conflictFingerprint(data.conflicts || []);
      if (data.ok && (data.conflicts || []).length === 0) {
        clearDismissedFingerprint();
        setDismissedFingerprint(null);
      } else if (fp && fp === readDismissedFingerprint()) {
        setDismissedFingerprint(fp);
      }
    } catch {
      setHealth({
        ok: false,
        conflicts: [
          {
            code: "api_unreachable",
            severity: "critical",
            message:
              target === "island"
                ? "Island API not reachable — check api.powercore.app and TBCC_INTERNAL_API_KEY in tbcc/.env"
                : "TBCC API not reachable — restart from the TBCC tray or run start.ps1",
          },
        ],
      });
    }
  }, [target]);

  useEffect(() => {
    void load();
    const t = setInterval(() => void load(), 20000);
    return () => clearInterval(t);
  }, [load]);

  const applyFocus = async (profile: string) => {
    setFixing(`focus:${profile}`);
    try {
      await api.opsFocus(profile);
      await load();
    } catch {
      /* ignore */
    } finally {
      setFixing(null);
    }
  };

  const runRemediate = async (codes?: string[]) => {
    setFixing(codes?.join(",") ?? "all");
    try {
      const data = await api.healthSystemRemediate(codes);
      if (data.health) {
        setHealth(data.health);
        const fp = conflictFingerprint(data.health.conflicts || []);
        if (data.health.ok && (data.health.conflicts || []).length === 0) {
          clearDismissedFingerprint();
          setDismissedFingerprint(null);
        } else if (fp && fp === readDismissedFingerprint()) {
          setDismissedFingerprint(fp);
        }
      } else await load();
    } catch {
      /* API may be down */
    } finally {
      setFixing(null);
    }
  };

  if (!health) return null;
  const conflicts = health.conflicts || [];
  const fingerprint = conflictFingerprint(conflicts);
  const dismissed =
    dismissedFingerprint !== null &&
    fingerprint.length > 0 &&
    dismissedFingerprint === fingerprint;
  const focusProfile = health.focus?.state?.profile || "off";
  const focusActive = focusProfile !== "off";
  if (dismissed || (health.ok && conflicts.length === 0 && !focusActive)) return null;

  const critical = conflicts.filter((c) => c.severity === "critical");
  const fixable = conflicts.filter((c) => c.action);
  const apiDown = conflicts.some((c) => c.code === "api_unreachable");
  const calm = calmToastStyle(bannerSeverityKind(critical.length, conflicts.length));

  return (
    <div
      className="border-b px-4 py-2 text-sm text-[var(--tbcc-text-primary,#cdd6f4)] bg-[var(--tbcc-bg-surface,rgba(30,30,46,0.92))]"
      style={{
        borderBottomColor: calm.accentBorder,
        boxShadow: `inset 0 3px 0 0 ${calm.accentBorder}`,
      }}
      role="status"
    >
      <div className="flex flex-wrap items-start gap-3">
        <div className="flex-1 min-w-[200px]">
          <strong className="font-medium">
            <span className="mr-1.5" aria-hidden>
              {calm.emoji}
            </span>
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
                    className="text-xs px-2 py-0.5 rounded border border-[var(--tbcc-bg-elevated,#45475a)] bg-transparent hover:bg-white/5 disabled:opacity-50 shrink-0"
                    style={{ borderColor: calm.accentBorder }}
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
          <p className="mt-1 text-[10px] opacity-60">
            TBCC auto-remediate runs every ~25s when the API is up (queue backlog, down workers, focus when imports
            are not processing). Import burst stays on while imports actively run.
          </p>
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
              className="text-xs px-2 py-1 rounded border disabled:opacity-50"
              style={{ borderColor: calm.accentBorder }}
              disabled={fixing !== null}
              onClick={() => void runRemediate()}
            >
              {fixing === "all" ? "Fixing…" : `Fix all (${fixable.length})`}
            </button>
          ) : null}
          <button
            type="button"
            className="text-xs underline opacity-80 hover:opacity-100"
            onClick={() => {
              writeDismissedFingerprint(fingerprint);
              setDismissedFingerprint(fingerprint);
            }}
          >
            Dismiss
          </button>
        </div>
      </div>
    </div>
  );
}
