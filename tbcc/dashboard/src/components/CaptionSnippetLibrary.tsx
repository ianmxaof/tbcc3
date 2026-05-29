import { useState } from "react";
import { captionSnippetMenuLabel, useCaptionSnippets } from "../hooks/useCaptionSnippets";
import { insertSnippetAtActiveTarget } from "../utils/snippetInsertBridge";
import { tbccCopyText } from "../utils/clipboardToast";
import { CopyToClipboardButton } from "./CopyToClipboardButton";

/** Compact dropdown: pick a saved caption → replaces target field via onInsert. */
export function CaptionSnippetInsertSelect({
  onInsert,
  disabled,
}: {
  onInsert: (text: string) => void;
  disabled?: boolean;
}) {
  const { snippets } = useCaptionSnippets();
  const [value, setValue] = useState("");

  if (snippets.length === 0) {
    return (
      <span
        className="text-[10px] text-slate-600 whitespace-nowrap"
        title="Save captions in Caption library (TBCC database) first"
      >
        —
      </span>
    );
  }

  return (
    <select
      value={value}
      disabled={disabled}
      title="Insert saved caption"
      aria-label="Insert saved caption"
      className="max-w-[7.5rem] text-[11px] bg-slate-800 border border-slate-600 rounded px-1.5 py-1 text-slate-300 shrink-0"
      onChange={(e) => {
        const id = e.target.value;
        setValue("");
        if (!id) return;
        const s = snippets.find((x) => String(x.id) === id);
        if (!s) return;
        if (!insertSnippetAtActiveTarget(s.body)) onInsert(s.body);
      }}
    >
      <option value="">Insert…</option>
      {snippets.map((s) => (
        <option key={s.id} value={String(s.id)}>
          {captionSnippetMenuLabel(s)}
        </option>
      ))}
    </select>
  );
}

/** Opens modal to add/delete saved captions (TBCC API / DB). */
export function CaptionSnippetLibraryManageButton({ className }: { className?: string }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className={
          className ??
          "text-xs text-cyan-400 hover:text-cyan-300 whitespace-nowrap px-2 py-0.5 rounded border border-slate-600/80 hover:bg-slate-700/50"
        }
      >
        Caption library…
      </button>
      <CaptionSnippetLibraryModal open={open} onClose={() => setOpen(false)} />
    </>
  );
}

function CaptionSnippetLibraryModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { snippets, add, remove, bulkImport } = useCaptionSnippets();
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [bulkJson, setBulkJson] = useState("");
  const [flash, setFlash] = useState<string | null>(null);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[120] flex items-start justify-center overflow-y-auto bg-black/70 px-3 py-10"
      role="dialog"
      aria-modal="true"
      aria-labelledby="caption-snippet-lib-title"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg rounded-lg border border-slate-600 bg-slate-800 p-4 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-2 mb-3">
          <h2 id="caption-snippet-lib-title" className="text-lg font-medium text-slate-100">
            Caption library
          </h2>
          <button
            type="button"
            className="text-sm text-slate-400 hover:text-slate-200 px-2 py-0.5 rounded"
            onClick={onClose}
          >
            Close
          </button>
        </div>
        <p className="text-slate-500 text-xs mb-4">
          Stored in the TBCC database (shared with the gallery extension). If the API was offline, entries may still
          be in this browser&apos;s <code className="text-slate-400">localStorage</code> until the next successful
          sync. Use <strong>Insert…</strong> next to each caption or relay template field to paste scheduled posts,
          listening relay templates, or gallery captions.
        </p>

        <div className="border border-slate-600 rounded-lg p-3 mb-4 bg-slate-900/40 space-y-2">
          <label className="block text-xs text-slate-400">
            Label <span className="text-slate-600">(optional)</span>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. MILF promo / pinned"
              className="mt-1 w-full bg-slate-700 border border-slate-600 rounded px-2 py-1.5 text-slate-200 text-sm"
            />
          </label>
          <label className="block text-xs text-slate-400">
            Text
            <textarea
              value={body}
              onChange={(e) => setBody(e.target.value)}
              rows={5}
              placeholder="Paste caption copy (emojis, links, line breaks)…"
              className="mt-1 w-full bg-slate-700 border border-slate-600 rounded px-2 py-1.5 text-slate-200 text-sm font-mono"
            />
          </label>
          <button
            type="button"
            className="px-3 py-1.5 rounded bg-cyan-800 text-cyan-100 text-sm hover:bg-cyan-700 disabled:opacity-50"
            disabled={!body.trim()}
            onClick={() => {
              void add(title, body).then(() => {
                setTitle("");
                setBody("");
              });
            }}
          >
            Save to library
          </button>
        </div>

        <div>
          <h3 className="text-xs font-medium text-slate-400 mb-2">Saved ({snippets.length})</h3>
          {snippets.length === 0 ? (
            <p className="text-slate-600 text-sm">Nothing saved yet.</p>
          ) : (
            <ul className="max-h-56 overflow-y-auto space-y-2 text-sm">
              {snippets.map((s) => (
                <li
                  key={s.id}
                  className="flex gap-2 items-start justify-between rounded border border-slate-600/80 bg-slate-900/30 p-2"
                >
                  <div className="min-w-0 flex-1">
                    <div className="text-slate-200 font-medium truncate">{captionSnippetMenuLabel(s)}</div>
                    <pre className="text-slate-500 text-[11px] whitespace-pre-wrap break-words max-h-20 overflow-y-auto mt-1">
                      {s.body}
                    </pre>
                  </div>
                  <div className="flex flex-col gap-1 shrink-0 items-end">
                    <button
                      type="button"
                      className="text-xs text-cyan-400 hover:text-cyan-300 px-2 py-0.5 rounded hover:bg-slate-700/50"
                      title="Paste at caret in the last-focused caption or template field"
                      onClick={() => {
                        const ok = insertSnippetAtActiveTarget(s.body);
                        setFlash(
                          ok
                            ? "Inserted at caret."
                            : "Copied to clipboard — focus the caption/template field and paste, or try again."
                        );
                        if (!ok) void tbccCopyText(s.body);
                        window.setTimeout(() => setFlash(null), 4000);
                      }}
                    >
                      Insert
                    </button>
                    <CopyToClipboardButton text={s.body} />
                    <button
                      type="button"
                      className="text-xs text-red-400 hover:text-red-300 px-2 py-0.5 rounded hover:bg-red-950/40"
                      onClick={() => void remove(s.id)}
                    >
                      Delete
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>

        {flash ? <p className="text-[11px] text-amber-400/95 mt-3">{flash}</p> : null}

        <details className="mt-4 border border-slate-600/80 rounded-lg p-3 bg-slate-900/30">
          <summary className="text-xs text-slate-400 cursor-pointer select-none">Bulk import captions (JSON)</summary>
          <p className="text-[11px] text-slate-500 mt-2 mb-2">
            POST shape:{" "}
            <code className="text-slate-400">{`{ "items": [ { "title": "optional", "body": "…" } ] }`}</code>
          </p>
          <textarea
            value={bulkJson}
            onChange={(e) => setBulkJson(e.target.value)}
            rows={4}
            placeholder='{"items":[{"title":"Easter MDH","body":"🐣 …"}]}'
            className="w-full bg-slate-700 border border-slate-600 rounded px-2 py-1.5 text-slate-200 text-[11px] font-mono"
          />
          <button
            type="button"
            className="mt-2 px-3 py-1.5 rounded bg-slate-700 text-slate-200 text-xs hover:bg-slate-600 disabled:opacity-50"
            disabled={!bulkJson.trim()}
            onClick={() => {
              try {
                const parsed = JSON.parse(bulkJson) as { items?: Array<{ title?: string | null; body?: string }> };
                const items = Array.isArray(parsed.items) ? parsed.items : [];
                void bulkImport(items).then((n) => {
                  setBulkJson("");
                  setFlash(`Imported ${n} snippet(s).`);
                  window.setTimeout(() => setFlash(null), 4000);
                });
              } catch {
                setFlash("Invalid JSON.");
                window.setTimeout(() => setFlash(null), 4000);
              }
            }}
          >
            Import to library
          </button>
        </details>
      </div>
    </div>
  );
}
