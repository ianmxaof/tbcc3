import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import { insertSnippetAtActiveTarget } from "../utils/snippetInsertBridge";
import { tbccCopyText } from "../utils/clipboardToast";

function promoInsertUrl(r: { url: string; short_url?: string | null }) {
  const s = (r.short_url || "").trim();
  return s || r.url;
}

const SORT_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "priority_asc", label: "Sort: Priority tier ↑" },
  { value: "priority_desc", label: "Sort: Priority tier ↓" },
  { value: "name_asc", label: "Sort: Name A–Z" },
  { value: "name_desc", label: "Sort: Name Z–A" },
  { value: "expires_asc", label: "Sort: Expires soonest" },
  { value: "expires_desc", label: "Sort: Expires latest" },
  { value: "created_desc", label: "Sort: Newest added" },
  { value: "created_asc", label: "Sort: Oldest added" },
];

export function PromoAffiliateLinksPopover({
  buttonLabel = "Promo links…",
  className,
  /** When true, panel opens above the button (or fixed near bottom) — use at page footers. */
  dropUp = false,
}: {
  buttonLabel?: string;
  className?: string;
  dropUp?: boolean;
}) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [sort, setSort] = useState("priority_asc");
  const [activeOnly, setActiveOnly] = useState(true);
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<Set<number>>(() => new Set());
  const [flash, setFlash] = useState<string | null>(null);

  const listQ = useQuery({
    queryKey: ["promoAffiliateLinks", sort, activeOnly],
    queryFn: () => api.promoAffiliateLinks.list({ sort, active_only: activeOnly }),
    enabled: open,
  });

  const delM = useMutation({
    mutationFn: (id: number) => api.promoAffiliateLinks.delete(id),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["promoAffiliateLinks"] }),
  });

  const shortenM = useMutation({
    mutationFn: (id: number) => api.promoAffiliateLinks.shorten(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["promoAffiliateLinks"] });
      setFlash("Short URL saved on row.");
      window.setTimeout(() => setFlash(null), 4500);
    },
    onError: (err: unknown) => {
      const msg =
        err instanceof Error
          ? err.message
          : typeof err === "object" && err && "message" in err
            ? String((err as { message?: string }).message)
            : "Shorten failed";
      setFlash(msg);
      window.setTimeout(() => setFlash(null), 6500);
    },
  });

  const rows = listQ.data ?? [];
  const filtered = useMemo(() => {
    const s = q.trim().toLowerCase();
    if (!s) return rows;
    return rows.filter((r) => r.label.toLowerCase().includes(s) || r.url.toLowerCase().includes(s));
  }, [rows, q]);

  const toggle = (id: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const insertUrls = (urls: string[]) => {
    const chunk = urls.map((u) => u.trim()).filter(Boolean).join("\n\n");
    if (!chunk) return;
    const ok = insertSnippetAtActiveTarget(chunk);
    setFlash(ok ? "Inserted at caret." : "Copied — focus a caption field and paste (Ctrl+V).");
    if (!ok) void tbccCopyText(chunk);
    window.setTimeout(() => setFlash(null), 4500);
  };

  return (
    <div className={`relative inline-block text-left ${className ?? ""}`}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="text-xs text-cyan-400 hover:text-cyan-300 whitespace-nowrap px-2 py-0.5 rounded border border-slate-600/80 hover:bg-slate-700/50"
      >
        {buttonLabel}
      </button>
      {open ? (
        <>
          <button
            type="button"
            className="fixed inset-0 z-[115] cursor-default bg-transparent"
            aria-label="Dismiss promo links panel"
            onClick={() => setOpen(false)}
          />
          <div
            className={
              dropUp
                ? "fixed z-[200] left-4 right-4 bottom-4 sm:left-auto sm:right-6 sm:w-[min(26rem,calc(100vw-2rem))] max-h-[min(70vh,28rem)] flex flex-col rounded-lg border border-slate-600 bg-slate-900 shadow-2xl p-3 space-y-2"
                : "absolute right-0 top-full z-[116] mt-1 w-[min(100vw-1.5rem,26rem)] rounded-lg border border-slate-600 bg-slate-900 shadow-xl p-3 space-y-2"
            }
          >
            <div className="flex flex-wrap gap-2 items-center">
              <select
                value={sort}
                onChange={(e) => setSort(e.target.value)}
                className="flex-1 min-w-[10rem] text-[11px] bg-slate-800 border border-slate-600 rounded px-2 py-1 text-slate-200"
                aria-label="Sort promo links"
              >
                {SORT_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
              <label className="flex items-center gap-1 text-[11px] text-slate-400 shrink-0 whitespace-nowrap">
                <input type="checkbox" checked={activeOnly} onChange={(e) => setActiveOnly(e.target.checked)} />
                Active only
              </label>
            </div>
            <input
              type="search"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Filter label / URL / short…"
              className="w-full text-[11px] bg-slate-800 border border-slate-600 rounded px-2 py-1 text-slate-200"
            />
            <div
              className={`overflow-y-auto space-y-1 border border-slate-700/80 rounded-md p-1 bg-slate-950/40 ${
                dropUp ? "flex-1 min-h-0 max-h-none" : "max-h-52"
              }`}
            >
              {listQ.isLoading ? (
                <p className="text-[11px] text-slate-500 px-1 py-2">Loading…</p>
              ) : listQ.isError ? (
                <p className="text-[11px] text-red-400 px-1 py-2">Could not load promo links.</p>
              ) : filtered.length === 0 ? (
                <p className="text-[11px] text-slate-500 px-1 py-2">No rows (import JSON under Misc → Promo).</p>
              ) : (
                filtered.map((r) => (
                  <div
                    key={r.id}
                    className="flex gap-1 items-start rounded px-1 py-1 hover:bg-slate-800/80 text-[11px]"
                  >
                    <input
                      type="checkbox"
                      className="mt-0.5 shrink-0"
                      checked={selected.has(r.id)}
                      onChange={() => toggle(r.id)}
                      aria-label={`Select ${r.label}`}
                    />
                    <div className="min-w-0 flex-1">
                      <div className="text-slate-200 font-medium leading-snug break-words">{r.label}</div>
                      {r.short_url ? (
                        <div className="text-emerald-500/90 truncate text-[10px]" title={r.short_url}>
                          short: {r.short_url}
                        </div>
                      ) : null}
                      <div className="text-slate-500 truncate" title={r.url}>
                        {r.url}
                      </div>
                      <div className="text-slate-600 flex flex-wrap gap-x-2 gap-y-0">
                        <span>{r.payout_kind}</span>
                        {r.payout_detail ? <span>{r.payout_detail}</span> : null}
                        <span>tier {r.priority_tier}</span>
                      </div>
                    </div>
                    <div className="flex flex-col gap-0.5 shrink-0 items-end">
                      <button
                        type="button"
                        className="text-cyan-400 hover:text-cyan-300 px-1"
                        title="Insert short URL when set, else full tracking URL"
                        onClick={() => insertUrls([promoInsertUrl(r)])}
                      >
                        Insert
                      </button>
                      <button
                        type="button"
                        className="text-[10px] text-slate-400 hover:text-amber-300/95 px-1 leading-tight text-right max-w-[5rem]"
                        title="API: POST …/shorten — set TBCC_PROMO_SHORTEN_PROVIDER (isgd | tinyurl | pixeldrain) + token/key (see .env.example)"
                        disabled={shortenM.isPending}
                        onClick={() => shortenM.mutate(r.id)}
                      >
                        Shorten
                      </button>
                      <button
                        type="button"
                        className="text-red-400 hover:text-red-300 px-1 leading-none"
                        title="Remove from library"
                        disabled={delM.isPending}
                        onClick={() => {
                          if (!window.confirm(`Delete “${r.label}”?`)) return;
                          delM.mutate(r.id);
                          setSelected((prev) => {
                            const next = new Set(prev);
                            next.delete(r.id);
                            return next;
                          });
                        }}
                      >
                        ×
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>
            <div className="flex flex-wrap gap-2 items-center justify-between">
              <button
                type="button"
                disabled={selected.size === 0}
                className="text-[11px] px-2 py-1 rounded bg-cyan-800 text-cyan-100 hover:bg-cyan-700 disabled:opacity-40"
                onClick={() => {
                  const urls = filtered.filter((r) => selected.has(r.id)).map((r) => promoInsertUrl(r));
                  insertUrls(urls);
                }}
              >
                Insert checked ({selected.size})
              </button>
              <button
                type="button"
                className="text-[11px] text-slate-400 hover:text-slate-200"
                onClick={() => setSelected(new Set())}
              >
                Clear selection
              </button>
            </div>
            {flash ? <p className="text-[10px] text-amber-400/95">{flash}</p> : null}
          </div>
        </>
      ) : null}
    </div>
  );
}
