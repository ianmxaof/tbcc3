import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api } from "../api";

type AuthStatus = {
  authorized?: boolean;
  pending_login?: boolean;
  session_file?: string;
  stale?: boolean;
  error?: string;
  user?: { first_name?: string; username?: string; phone?: string };
};

type LoginStep = "phone" | "code" | "password";

export function ScraperTelegramAuth({ compact = false }: { compact?: boolean }) {
  const queryClient = useQueryClient();
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [loginStep, setLoginStep] = useState<LoginStep>("phone");
  const [msg, setMsg] = useState<string | null>(null);

  const { data: status, isPending, isError, error } = useQuery({
    queryKey: ["scraper-auth-status"],
    queryFn: () => api.sources.scraperAuthStatus() as Promise<AuthStatus>,
    staleTime: 60_000,
    refetchInterval: (query) => {
      const d = query.state.data as AuthStatus | undefined;
      if (d?.authorized) return false;
      if (d?.pending_login) return 12_000;
      return false;
    },
    refetchOnWindowFocus: false,
  });

  const authorized = Boolean(status?.authorized);

  useEffect(() => {
    if (authorized) {
      setLoginStep("phone");
      setCode("");
      setPassword("");
    }
  }, [authorized]);

  const setStatus = (patch: Partial<{ data: AuthStatus }>) => {
    queryClient.setQueryData(["scraper-auth-status"], (old: AuthStatus | undefined) => ({
      ...(old || {}),
      ...patch.data,
    }));
  };

  const refreshStatus = () => {
    void queryClient.invalidateQueries({ queryKey: ["scraper-auth-status"] });
  };

  const sendPhone = useMutation({
    mutationFn: () => api.sources.scraperAuthPhone(phone.trim()),
    onSuccess: (r) => {
      const res = r as { already_authorized?: boolean; message?: string };
      setMsg(String(res.message ?? "Code sent."));
      if (res.already_authorized) {
        refreshStatus();
        return;
      }
      setLoginStep("code");
      setStatus({ data: { authorized: false, pending_login: true } });
    },
    onError: (e: Error) => setMsg(e.message),
  });

  const sendCode = useMutation({
    mutationFn: () => api.sources.scraperAuthCode(code.trim()),
    onSuccess: (r) => {
      const res = r as { needs_password?: boolean; message?: string };
      if (res.needs_password) {
        setLoginStep("password");
        setMsg(res.message ?? "Enter your Telegram 2FA password.");
        return;
      }
      setMsg(res.message ?? "Logged in.");
      setLoginStep("phone");
      setCode("");
      setPhone("");
      refreshStatus();
    },
    onError: (e: Error) => setMsg(e.message),
  });

  const sendPassword = useMutation({
    mutationFn: () => api.sources.scraperAuthPassword(password),
    onSuccess: (r) => {
      setMsg(String((r as { message?: string }).message ?? "Logged in."));
      setPassword("");
      setLoginStep("phone");
      refreshStatus();
    },
    onError: (e: Error) => setMsg(e.message),
  });

  const cancel = useMutation({
    mutationFn: () => api.sources.scraperAuthCancel(),
    onSuccess: () => {
      setLoginStep("phone");
      setMsg("Login cancelled.");
      setStatus({ data: { authorized: false, pending_login: false } });
    },
  });

  const showShell = status != null || !isPending;

  return (
    <div
      className={`rounded-lg border border-slate-600/80 bg-slate-900/50 ${compact ? "p-3" : "p-4"} space-y-3 min-h-[11rem]`}
    >
      <div>
        <h3 className="text-slate-200 font-medium text-sm">Telegram scraper account</h3>
        <p className="text-slate-500 text-xs mt-1 max-w-xl">
          One login covers all Telegram channel sources. Join each channel in the Telegram app with this account.
        </p>
      </div>

      {!showShell ? (
        <p className="text-slate-500 text-sm">Checking scraper session…</p>
      ) : isError && !status ? (
        <p className="text-amber-300 text-sm">
          Could not read session status: {String((error as Error)?.message ?? error)}. Restart TBCC-Backend if this
          persists.
        </p>
      ) : authorized ? (
        <p className="text-emerald-300 text-sm">
          Connected
          {status?.user?.first_name ? (
            <>
              {" "}
              as <strong>{status.user.first_name}</strong>
              {status.user.username ? ` (@${status.user.username})` : ""}
            </>
          ) : null}
          . Use <strong>Scrape now</strong> or per-source schedules below.
        </p>
      ) : (
        <>
          <p className="text-amber-300 text-sm">Not logged in — enter phone and code below.</p>
          <div className="space-y-2 max-w-md">
            {loginStep === "phone" ? (
              <>
                <label className="block">
                  <span className="text-slate-400 text-xs uppercase">Phone (international)</span>
                  <input
                    type="tel"
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                    placeholder="+15551234567"
                    className="mt-1 w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200"
                  />
                </label>
                <button
                  type="button"
                  disabled={!phone.trim() || sendPhone.isPending}
                  onClick={() => void sendPhone.mutate()}
                  className="px-3 py-1.5 bg-cyan-700 text-white rounded text-sm hover:bg-cyan-600 disabled:opacity-50"
                >
                  {sendPhone.isPending ? "Sending…" : "Send Telegram code"}
                </button>
              </>
            ) : null}

            {loginStep === "code" ? (
              <>
                <label className="block">
                  <span className="text-slate-400 text-xs uppercase">Login code</span>
                  <input
                    type="text"
                    inputMode="numeric"
                    value={code}
                    onChange={(e) => setCode(e.target.value)}
                    placeholder="12345"
                    className="mt-1 w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200"
                  />
                </label>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    disabled={!code.trim() || sendCode.isPending}
                    onClick={() => void sendCode.mutate()}
                    className="px-3 py-1.5 bg-cyan-700 text-white rounded text-sm hover:bg-cyan-600 disabled:opacity-50"
                  >
                    {sendCode.isPending ? "Verifying…" : "Submit code"}
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setLoginStep("phone");
                      void cancel.mutate();
                    }}
                    className="px-3 py-1.5 text-slate-400 text-sm underline"
                  >
                    Back
                  </button>
                </div>
              </>
            ) : null}

            {loginStep === "password" ? (
              <>
                <label className="block">
                  <span className="text-slate-400 text-xs uppercase">2FA password</span>
                  <input
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="mt-1 w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200"
                  />
                </label>
                <button
                  type="button"
                  disabled={!password || sendPassword.isPending}
                  onClick={() => void sendPassword.mutate()}
                  className="px-3 py-1.5 bg-cyan-700 text-white rounded text-sm hover:bg-cyan-600 disabled:opacity-50"
                >
                  {sendPassword.isPending ? "Signing in…" : "Submit password"}
                </button>
              </>
            ) : null}
          </div>
        </>
      )}

      {msg ? <p className="text-slate-400 text-xs">{msg}</p> : null}
      {status?.stale ? (
        <p className="text-slate-600 text-xs">Status from cache (session check briefly failed).</p>
      ) : null}
      {!compact && !authorized ? (
        <p className="text-slate-600 text-xs">Stop TBCC-Celery while logging in if you see database is locked.</p>
      ) : null}
    </div>
  );
}
