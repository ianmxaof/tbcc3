import { useCallback, useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type CaptureArchiveEntry } from "../api";
import { QueryErrorBanner } from "../components/QueryErrorBanner";
import { InfoDisclosure } from "../components/InfoDisclosure";
import { showCopiedToast } from "../utils/clipboardToast";

const PAGE_SIZE = 100;

type ArchiveSortField = "added_at" | "value" | "host" | "source" | "kind" | "summary";
type ArchiveSortOrder = "asc" | "desc";

const SORT_FIELD_OPTIONS: { value: ArchiveSortField; label: string }[] = [
  { value: "added_at", label: "Date added" },
  { value: "value", label: "URL / username" },
  { value: "host", label: "Site (host)" },
  { value: "source", label: "Source" },
  { value: "kind", label: "Type" },
  { value: "summary", label: "Title" },
];

function entryKey(e: CaptureArchiveEntry): string {
  return `${e.kind}|${e.value.toLowerCase()}`;
}

function formatMeta(e: CaptureArchiveEntry): string {
  const parts: string[] = [];
  if (e.source) parts.push(e.source);
  if (e.origin && e.origin !== e.source) parts.push(e.origin);
  if (e.status && e.status !== "approved") parts.push(`status: ${e.status}`);
  if (e.submitted_by) parts.push(`by tg:${e.submitted_by}`);
  if (e.tags) parts.push(`tags: ${e.tags}`);
  if (e.ref) parts.push(`ref: ${e.ref.slice(0, 120)}`);
  if (e.added_at) {
    try {
      parts.push(new Date(e.added_at).toLocaleString());
    } catch {
      /* ignore */
    }
  }
  return parts.join(" · ");
}

function parseUrlsFromPaste(text: string): CaptureArchiveEntry[] {
  const lines = text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  const out: CaptureArchiveEntry[] = [];
  const seen = new Set<string>();
  for (const line of lines) {
    const m = line.match(/https?:\/\/[^\s<>"']+/gi);
    if (m) {
      for (const url of m) {
        const v = url.replace(/[),.;]+$/, "");
        const k = v.toLowerCase();
        if (seen.has(k)) continue;
        seen.add(k);
        out.push({ kind: "url", value: v, id: null });
      }
      continue;
    }
    if (/^https?:\/\//i.test(line)) {
      const k = line.toLowerCase();
      if (!seen.has(k)) {
        seen.add(k);
        out.push({ kind: "url", value: line, id: null });
      }
    }
  }
  return out;
}

export function MasterArchivePanel() {
  const qc = useQueryClient();
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const [tags, setTags] = useState("");
  const [kind, setKind] = useState<"" | "url" | "username">("");
  const [sort, setSort] = useState<ArchiveSortField>("added_at");
  const [order, setOrder] = useState<ArchiveSortOrder>("desc");
  const [sort2, setSort2] = useState<"" | ArchiveSortField>("");
  const [order2, setOrder2] = useState<ArchiveSortOrder>("asc");
  const [usernameTab, setUsernameTab] = useState("");
  const [viewMode, setViewMode] = useState<"archive" | "pending">("archive");
  const [pasteText, setPasteText] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [status, setStatus] = useState("");
  const [clearConfirm, setClearConfirm] = useState("");
  const [isDangerZoneOpen, setIsDangerZoneOpen] = useState(false);

  const handlesQ = useQuery({
    queryKey: ["archive", "handles"],
    queryFn: () => api.archive.handles(),
  });

  const listQ = useQuery({
    queryKey: ["archive", "entries", page, q, tags, kind, usernameTab, sort, order, sort2, order2, viewMode],
    queryFn: () =>
      api.archive.list({
        page,
        page_size: PAGE_SIZE,
        q: q.trim() || undefined,
        tags: tags.trim() || undefined,
        kind: kind || undefined,
        username: usernameTab || undefined,
        include_media: viewMode === "archive",
        status: viewMode === "pending" ? "pending" : undefined,
        sort,
        order,
        sort2: sort2 || undefined,
        order2,
      }),
  });

  const governEntry = useMutation({
    mutationFn: ({ id, status }: { id: number; status: "approved" | "rejected" }) =>
      api.archive.governEntry(id, status),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["archive"] });
    },
    onError: (e) => setStatus(String(e)),
  });

  const syncMedia = useMutation({
    mutationFn: () => api.archive.syncFromMedia(),
    onSuccess: (r) => {
      setStatus(`Synced ${r.added} new URL(s) from media library (${r.scanned} scanned). Does not delete anything.`);
      void qc.invalidateQueries({ queryKey: ["archive"] });
    },
    onError: (e) => setStatus(String(e)),
  });

  const clearArchive = useMutation({
    mutationFn: () => api.archive.clear("DELETE ARCHIVE"),
    onSuccess: (r) => {
      setStatus(
        `Server table cleared (${r.deleted} rows). Extension local archive unchanged. Media source URLs may still appear until removed from Media.`
      );
      setClearConfirm("");
      setSelected(new Set());
      void qc.invalidateQueries({ queryKey: ["archive"] });
    },
    onError: (e) => setStatus(String(e)),
  });

  const pasteImport = useMutation({
    mutationFn: async (text: string) => {
      const parsed = parseUrlsFromPaste(text);
      if (!parsed.length) throw new Error("No http(s) URLs found in paste.");
      return api.archive.bulk(parsed, true, true);
    },
    onSuccess: (r) => {
      const tagged = r.auto_tag?.enriched;
      setStatus(
        `Added ${r.added} new URL(s) from clipboard paste` +
          (tagged != null ? ` · auto-tagged ${tagged}` : "") +
          "."
      );
      setPasteText("");
      void qc.invalidateQueries({ queryKey: ["archive"] });
    },
    onError: (e) => setStatus(String(e)),
  });

  const bulkAutoTag = useMutation({
    mutationFn: (opts: { ids?: number[]; missing_only?: boolean; limit?: number; force?: boolean }) =>
      api.archive.bulkAutoTag(opts),
    onSuccess: (r) => {
      setStatus(`Auto-tagged ${r.enriched} URL(s) (${r.skipped} skipped, ${r.scanned} scanned).`);
      void qc.invalidateQueries({ queryKey: ["archive"] });
    },
    onError: (e) => setStatus(String(e)),
  });

  const items = listQ.data?.items ?? [];
  const total = listQ.data?.total ?? 0;
  const totalPages = listQ.data?.total_pages ?? 1;

  const modelTabs = handlesQ.data?.handles ?? [];

  const searchSuggestions = useMemo(() => {
    const ql = q.trim().toLowerCase();
    if (ql.length < 2) return [];
    const pool = new Set<string>();
    for (const e of items) {
      if (e.kind === "username") pool.add(e.value);
      const host = e.kind === "url" ? (() => {
        try {
          return new URL(e.value).hostname.replace(/^www\./, "");
        } catch {
          return "";
        }
      })() : "";
      if (host && host.includes(ql)) pool.add(host);
      if (e.value.toLowerCase().includes(ql)) pool.add(e.value.slice(0, 80));
    }
    return [...pool].slice(0, 12);
  }, [items, q]);

  const defaultSelectPage = useCallback(() => {
    const next = new Set<string>();
    for (const e of items) {
      if (e.kind === "url") next.add(entryKey(e));
    }
    setSelected(next);
  }, [items]);

  useEffect(() => {
    defaultSelectPage();
  }, [items, page, defaultSelectPage]);

  const toggle = (e: CaptureArchiveEntry) => {
    const k = entryKey(e);
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(k)) next.delete(k);
      else next.add(k);
      return next;
    });
  };

  const copyCheckedUrls = async () => {
    const lines = items
      .filter((e) => e.kind === "url" && selected.has(entryKey(e)))
      .map((e) => e.value);
    if (!lines.length) {
      setStatus("No URLs selected on this page.");
      return;
    }
    try {
      await navigator.clipboard.writeText(lines.join("\n"));
      showCopiedToast({ message: `Copied ${lines.length} URL(s)` });
      setStatus(`Copied ${lines.length} URL(s) from page ${page} (export for full list).`);
    } catch {
      setStatus("Clipboard failed.");
    }
  };

  const onImportFile = async (file: File) => {
    const text = await file.text();
    let parsed: CaptureArchiveEntry[] = [];
    try {
      const j = JSON.parse(text) as unknown;
      const arr = Array.isArray(j) ? j : (j as { entries?: unknown[] }).entries;
      if (Array.isArray(arr)) {
        parsed = arr.map((x) => {
          if (typeof x === "string") return { kind: "url" as const, value: x, id: null };
          const o = x as Record<string, unknown>;
          return {
            id: null,
            kind: (o.kind === "username" ? "username" : "url") as "url" | "username",
            value: String(o.value || o.url || ""),
            source: o.source ? String(o.source) : undefined,
            ref: o.ref ? String(o.ref) : undefined,
            note: o.note ? String(o.note) : undefined,
          };
        });
      }
    } catch {
      parsed = parseUrlsFromPaste(text);
    }
    const r = await api.archive.bulk(parsed, true, true);
    const tagged = r.auto_tag?.enriched;
    setStatus(
      `Imported ${r.added} new entr${r.added === 1 ? "y" : "ies"} to server archive` +
        (tagged != null ? ` · auto-tagged ${tagged}` : "") +
        "."
    );
    void qc.invalidateQueries({ queryKey: ["archive"] });
  };

  const autoTagSelected = () => {
    const ids = items
      .filter((e) => e.kind === "url" && e.id != null && selected.has(entryKey(e)))
      .map((e) => e.id as number);
    if (!ids.length) {
      setStatus("Select URL rows on this page to auto-tag (needs server row id).");
      return;
    }
    bulkAutoTag.mutate({ ids, missing_only: false, limit: ids.length });
  };

  const autoTagMissing = () => {
    bulkAutoTag.mutate({ missing_only: true, limit: 24 });
  };

  return (
    <div className="max-w-5xl space-y-4">
      <h1 className="text-2xl font-semibold text-slate-100">Master archive</h1>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          className={`tbcc-btn-secondary text-sm ${viewMode === "archive" ? "ring-1 ring-emerald-500/60" : ""}`}
          onClick={() => {
            setViewMode("archive");
            setPage(1);
          }}
        >
          Approved archive
        </button>
        <button
          type="button"
          className={`tbcc-btn-secondary text-sm ${viewMode === "pending" ? "ring-1 ring-amber-500/60" : ""}`}
          onClick={() => {
            setViewMode("pending");
            setPage(1);
          }}
        >
          Pending review (Telegram)
        </button>
      </div>
      {viewMode === "pending" && (
        <p className="text-sm text-amber-200/90 max-w-3xl">
          Community submissions from the Erome/Bunkr forum topic and macro search bot. Approve to publish into the
          master archive (extension sync, loot modifier, import pipeline).
        </p>
      )}
      <p className="text-sm text-slate-400 max-w-3xl">
        Merged server history: extension sync, clipboard paste, manual import, and media-library source URLs.
        Each URL can get a short <strong className="text-slate-200">auto-tag description</strong> (page semantic sweep +
        tags) — use <strong className="text-slate-200">Auto-tag missing</strong> or select rows and re-run. URLs on the{" "}
        <strong className="text-slate-200">Approved archive</strong> tab appear automatically in the global{" "}
        <strong className="text-slate-200">Insert…</strong> menu (no extra approve step — only{" "}
        <strong className="text-slate-200">Pending review (Telegram)</strong> submissions need Approve/Reject). Lists{" "}
        <strong className="text-slate-200">{PAGE_SIZE}</strong> entries per page — export for the full set. The browser
        extension keeps a local copy; use <strong className="text-slate-200">Sync from server</strong> in the gallery
        Master archive sheet to match this list.
      </p>

      <InfoDisclosure title="What sync &amp; clear do">
        <ul className="list-disc pl-4 space-y-1 text-sm text-slate-400">
          <li>
            <strong className="text-slate-300">Sync from media library</strong> adds distinct{" "}
            <code className="text-cyan-300/90">Media.source_channel</code> URLs into the server table. It does not delete
            anything. Routing a URL to a content pool still records it in the master archive when captured via the
            extension.
          </li>
          <li>
            <strong className="text-slate-300">Clear server archive</strong> only deletes rows in the database table —
            not extension storage. URLs may still appear from the media-library merge until you remove them from Media.
          </li>
          <li>
            The sidebar <strong className="text-slate-300">URL inbox</strong> is a separate import queue (
            <code className="text-cyan-300/90">tbccSavedVideoUrls</code>). Master archive is the permanent capture log.
          </li>
        </ul>
      </InfoDisclosure>

      {listQ.isError && (
        <QueryErrorBanner
          title="Could not load master archive"
          message={String((listQ.error as Error)?.message ?? listQ.error)}
          onRetry={() => void listQ.refetch()}
        />
      )}

      <section className="rounded-lg border border-cyan-800/50 bg-cyan-950/20 p-4 space-y-2">
        <h2 className="text-sm font-medium text-cyan-100">Add links from clipboard</h2>
        <p className="text-xs text-slate-500">
          Paste one or many URLs (newline-separated). Non-URL lines are scanned for http(s) links.
        </p>
        <textarea
          value={pasteText}
          onChange={(e) => setPasteText(e.target.value)}
          rows={4}
          className="w-full bg-slate-900 border border-slate-600 rounded px-3 py-2 text-slate-100 text-sm font-mono"
          placeholder="https://…&#10;https://…"
        />
        <button
          type="button"
          className="px-4 py-2 rounded bg-cyan-700 text-cyan-50 text-sm hover:bg-cyan-600 disabled:opacity-50"
          disabled={!pasteText.trim() || pasteImport.isPending}
          onClick={() => pasteImport.mutate(pasteText)}
        >
          {pasteImport.isPending ? "Importing…" : "Import pasted URLs"}
        </button>
      </section>

      {modelTabs.length > 0 ? (
        <div className="flex flex-wrap gap-1.5 items-center">
          <span className="text-xs text-slate-500 mr-1">Models:</span>
          <button
            type="button"
            className={`px-2 py-0.5 rounded text-xs ${!usernameTab ? "bg-fuchsia-800 text-fuchsia-100" : "bg-slate-700 text-slate-300"}`}
            onClick={() => {
              setUsernameTab("");
              setPage(1);
            }}
          >
            All
          </button>
          {modelTabs.map((h) => (
            <button
              key={h}
              type="button"
              className={`px-2 py-0.5 rounded text-xs ${usernameTab === h ? "bg-fuchsia-800 text-fuchsia-100" : "bg-slate-700 text-slate-300"}`}
              onClick={() => {
                setUsernameTab(h);
                setPage(1);
              }}
            >
              @{h}
            </button>
          ))}
        </div>
      ) : null}

      <div className="flex flex-wrap gap-2 items-end">
        <label className="flex flex-col gap-1 text-xs text-slate-400">
          Search
          <input
            type="search"
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setPage(1);
            }}
            list="archive-search-suggestions"
            className="bg-slate-800 border border-slate-600 rounded px-2 py-1.5 text-slate-100 min-w-[200px]"
            placeholder="URL, host, username, note…"
          />
          <datalist id="archive-search-suggestions">
            {searchSuggestions.map((s) => (
              <option key={s} value={s} />
            ))}
          </datalist>
        </label>
        <label className="flex flex-col gap-1 text-xs text-slate-400">
          Tags
          <input
            type="text"
            value={tags}
            onChange={(e) => {
              setTags(e.target.value);
              setPage(1);
            }}
            placeholder="erome, staging"
            className="bg-slate-800 border border-slate-600 rounded px-2 py-1.5 text-slate-100 min-w-[140px]"
          />
        </label>
        <label className="flex flex-col gap-1 text-xs text-slate-400">
          Type
          <select
            value={kind}
            onChange={(e) => {
              setKind(e.target.value as "" | "url" | "username");
              setPage(1);
            }}
            className="bg-slate-800 border border-slate-600 rounded px-2 py-1.5 text-slate-100"
          >
            <option value="">All</option>
            <option value="url">URLs</option>
            <option value="username">Usernames</option>
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs text-slate-400">
          Sort by
          <select
            value={sort}
            onChange={(e) => {
              setSort(e.target.value as ArchiveSortField);
              setPage(1);
            }}
            className="bg-slate-800 border border-slate-600 rounded px-2 py-1.5 text-slate-100"
          >
            {SORT_FIELD_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs text-slate-400">
          Order
          <select
            value={order}
            onChange={(e) => {
              setOrder(e.target.value as ArchiveSortOrder);
              setPage(1);
            }}
            className="bg-slate-800 border border-slate-600 rounded px-2 py-1.5 text-slate-100"
          >
            <option value="desc">Newest / Z-A</option>
            <option value="asc">Oldest / A-Z</option>
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs text-slate-400">
          Then by
          <select
            value={sort2}
            onChange={(e) => {
              setSort2(e.target.value as "" | ArchiveSortField);
              setPage(1);
            }}
            className="bg-slate-800 border border-slate-600 rounded px-2 py-1.5 text-slate-100"
          >
            <option value="">—</option>
            {SORT_FIELD_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs text-slate-400">
          2nd order
          <select
            value={order2}
            onChange={(e) => {
              setOrder2(e.target.value as ArchiveSortOrder);
              setPage(1);
            }}
            disabled={!sort2}
            className="bg-slate-800 border border-slate-600 rounded px-2 py-1.5 text-slate-100 disabled:opacity-40"
          >
            <option value="asc">A-Z / oldest</option>
            <option value="desc">Z-A / newest</option>
          </select>
        </label>
        <button
          type="button"
          className="px-3 py-1.5 rounded bg-slate-700 text-slate-100 text-sm hover:bg-slate-600"
          onClick={() => defaultSelectPage()}
        >
          Select all
        </button>
        <button
          type="button"
          className="px-3 py-1.5 rounded bg-slate-700 text-slate-100 text-sm hover:bg-slate-600"
          onClick={() => setSelected(new Set())}
        >
          Deselect all
        </button>
        <button
          type="button"
          className="px-3 py-1.5 rounded bg-fuchsia-900/60 text-fuchsia-100 text-sm hover:bg-fuchsia-800/70 border border-fuchsia-800/50"
          onClick={() => autoTagMissing()}
          disabled={bulkAutoTag.isPending || viewMode !== "archive"}
          title="Semantic page sweep for URLs missing a description (up to 24)"
        >
          {bulkAutoTag.isPending ? "Auto-tagging…" : "Auto-tag missing"}
        </button>
        <button
          type="button"
          className="px-3 py-1.5 rounded bg-fuchsia-900/40 text-fuchsia-100 text-sm hover:bg-fuchsia-800/60 border border-fuchsia-900/40"
          onClick={() => autoTagSelected()}
          disabled={bulkAutoTag.isPending || viewMode !== "archive"}
          title="Re-run auto-tag for checked URLs on this page"
        >
          Auto-tag selected
        </button>
        <button
          type="button"
          className="px-3 py-1.5 rounded bg-slate-700 text-slate-100 text-sm hover:bg-slate-600"
          onClick={() => void copyCheckedUrls()}
        >
          Copy URLs (page)
        </button>
        <a
          href={api.archive.exportDownloadUrl("json", {
            q: q || undefined,
            kind: kind || undefined,
            sort,
            order,
            sort2: sort2 || undefined,
            order2,
          })}
          className="px-3 py-1.5 rounded bg-slate-700 text-slate-100 text-sm hover:bg-slate-600 no-underline"
          download
        >
          Export JSON
        </a>
        <a
          href={api.archive.exportDownloadUrl("csv", {
            q: q || undefined,
            kind: kind || undefined,
            sort,
            order,
            sort2: sort2 || undefined,
            order2,
          })}
          className="px-3 py-1.5 rounded bg-slate-700 text-slate-100 text-sm hover:bg-slate-600 no-underline"
          download
        >
          Export CSV
        </a>
        <a
          href={api.archive.exportDownloadUrl("txt", {
            q: q || undefined,
            kind: kind || undefined,
            sort,
            order,
            sort2: sort2 || undefined,
            order2,
          })}
          className="px-3 py-1.5 rounded bg-slate-700 text-slate-100 text-sm hover:bg-slate-600 no-underline"
          download
        >
          Export URLs
        </a>
        <label className="px-3 py-1.5 rounded bg-slate-700 text-slate-100 text-sm hover:bg-slate-600 cursor-pointer">
          Import file…
          <input
            type="file"
            accept=".json,.csv,.txt"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              e.target.value = "";
              if (f) void onImportFile(f).catch((err) => setStatus(String(err)));
            }}
          />
        </label>
        <button
          type="button"
          className="px-3 py-1.5 rounded bg-cyan-800 text-cyan-100 text-sm hover:bg-cyan-700"
          onClick={() => syncMedia.mutate()}
          disabled={syncMedia.isPending}
        >
          Sync from media library
        </button>
      </div>

      {status ? (
        <p className="text-sm text-slate-300" role="status">
          {status}
        </p>
      ) : null}

      <p className="text-xs text-slate-500">
        {total} entr{total === 1 ? "y" : "ies"}
        {totalPages > 1 ? ` · page ${page} / ${totalPages}` : ""}
        {usernameTab ? ` · filter @${usernameTab}` : ""}
      </p>

      {totalPages > 1 ? (
        <div className="flex gap-2 items-center justify-center text-sm">
          <button
            type="button"
            disabled={page <= 1}
            className="px-3 py-1 rounded bg-slate-700 text-slate-200 disabled:opacity-40"
            onClick={() => setPage((p) => Math.max(1, p - 1))}
          >
            ← Prev
          </button>
          <span className="text-slate-400">
            Page {page} / {totalPages}
          </span>
          <button
            type="button"
            disabled={page >= totalPages}
            className="px-3 py-1 rounded bg-slate-700 text-slate-200 disabled:opacity-40"
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
          >
            Next →
          </button>
        </div>
      ) : null}

      <div className="border border-slate-700 rounded-lg divide-y divide-slate-800 max-h-[min(70vh,640px)] overflow-auto">
        {listQ.isLoading ? (
          <p className="p-4 text-slate-400 text-sm">Loading…</p>
        ) : !items.length ? (
          <p className="p-4 text-slate-400 text-sm">No entries match.</p>
        ) : (
          items.map((e) => (
            <div key={entryKey(e)} className="flex gap-3 p-3 text-sm">
              <input
                type="checkbox"
                className="mt-1"
                checked={e.kind === "url" && selected.has(entryKey(e))}
                disabled={e.kind !== "url"}
                onChange={() => toggle(e)}
              />
              <div className="min-w-0 flex-1">
                <div className="flex gap-2 items-start">
                  <span className="text-[10px] uppercase tracking-wide text-fuchsia-300/90 shrink-0">{e.kind}</span>
                  {e.kind === "url" ? (
                    <a
                      href={e.value}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-sky-300 hover:text-sky-200 break-all underline underline-offset-2"
                    >
                      {e.value}
                    </a>
                  ) : (
                    <span className="text-slate-100">@{e.value}</span>
                  )}
                </div>
                {e.summary ? <p className="text-xs text-slate-300 mt-1">{e.summary}</p> : null}
                {e.description && e.note && !String(e.note).startsWith("ref:") ? (
                  <p className="text-xs text-slate-500 mt-0.5">Note: {e.note}</p>
                ) : null}
                <p className="text-xs text-slate-500 mt-1">{formatMeta(e)}</p>
                {viewMode === "pending" && e.id != null ? (
                  <div className="flex gap-2 mt-2">
                    <button
                      type="button"
                      className="px-2 py-0.5 rounded text-xs bg-emerald-900/50 text-emerald-200 border border-emerald-800/60"
                      disabled={governEntry.isPending}
                      onClick={() => governEntry.mutate({ id: e.id as number, status: "approved" })}
                    >
                      Approve
                    </button>
                    <button
                      type="button"
                      className="px-2 py-0.5 rounded text-xs bg-red-900/40 text-red-200 border border-red-900/50"
                      disabled={governEntry.isPending}
                      onClick={() => governEntry.mutate({ id: e.id as number, status: "rejected" })}
                    >
                      Reject
                    </button>
                  </div>
                ) : null}
              </div>
            </div>
          ))
        )}
      </div>

      <section className="rounded-lg border border-red-900/40 bg-red-950/10 p-4 mt-8">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-sm font-medium text-red-200">Danger zone</h2>
          <button
            type="button"
            className="px-2.5 py-1 rounded border border-red-900/70 text-xs text-red-200 hover:bg-red-950/60"
            onClick={() => setIsDangerZoneOpen((v) => !v)}
            aria-expanded={isDangerZoneOpen}
          >
            {isDangerZoneOpen ? "Hide" : "Expand"}
          </button>
        </div>
        {isDangerZoneOpen ? (
          <div className="space-y-2 mt-3">
            <p className="text-xs text-slate-500">
              Deletes only the server database table. Extension local master archive and inbox are not touched. Export first.
            </p>
            <label className="flex flex-col gap-1 text-xs text-slate-400 max-w-md">
              Type <code className="text-red-300">DELETE ARCHIVE</code> to confirm
              <input
                type="text"
                value={clearConfirm}
                onChange={(e) => setClearConfirm(e.target.value)}
                className="bg-slate-900 border border-red-900/60 rounded px-2 py-1.5 text-slate-100"
                autoComplete="off"
              />
            </label>
            <button
              type="button"
              className="px-3 py-1.5 rounded bg-red-950 text-red-200 text-sm border border-red-800 hover:bg-red-900 disabled:opacity-40"
              disabled={clearConfirm !== "DELETE ARCHIVE" || clearArchive.isPending}
              onClick={() => clearArchive.mutate()}
            >
              {clearArchive.isPending ? "Clearing…" : "Clear server archive table"}
            </button>
          </div>
        ) : null}
      </section>
    </div>
  );
}
