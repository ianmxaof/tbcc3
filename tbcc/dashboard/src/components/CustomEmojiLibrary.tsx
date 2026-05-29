import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api";
import { customEmojiPresetLabel, useCustomEmojiPresets, type CustomEmojiPreset } from "../hooks/useCustomEmojiPresets";
import { insertSnippetAtActiveTarget } from "../utils/snippetInsertBridge";
import { tbccCopyText } from "../utils/clipboardToast";
import { CopyToClipboardButton } from "./CopyToClipboardButton";

function insertBanner(fragment: string, onInsert: (text: string) => void): void {
  const chunk = String(fragment || "").trim();
  if (!chunk) return;
  if (!insertSnippetAtActiveTarget(chunk)) onInsert(chunk);
}

/** Dropdown: insert a saved custom-emoji banner at the caret in the last-focused field. */
export function CustomEmojiInsertSelect({
  onInsert,
  disabled,
}: {
  onInsert: (text: string) => void;
  disabled?: boolean;
}) {
  const { presets, isLoading } = useCustomEmojiPresets();
  const [value, setValue] = useState("");

  if (isLoading) {
    return <span className="text-[10px] text-slate-600">…</span>;
  }
  if (presets.length === 0) {
    return (
      <span
        className="text-[10px] text-slate-600 whitespace-nowrap"
        title="Save banners in Emoji library (Misc → extract, then save preset)"
      >
        —
      </span>
    );
  }

  return (
    <select
      value={value}
      disabled={disabled}
      title="Insert saved custom-emoji banner"
      aria-label="Insert custom emoji banner"
      className="max-w-[8.5rem] text-[11px] bg-slate-800 border border-violet-700/60 rounded px-1.5 py-1 text-violet-200 shrink-0"
      onChange={(e) => {
        const id = e.target.value;
        setValue("");
        if (!id) return;
        const p = presets.find((x) => String(x.id) === id);
        if (!p) return;
        insertBanner(p.html_fragment, onInsert);
      }}
    >
      <option value="">Emoji banner…</option>
      {presets.map((p) => (
        <option key={p.id} value={String(p.id)}>
          {customEmojiPresetLabel(p)}
        </option>
      ))}
    </select>
  );
}

export function CustomEmojiLibraryManageButton({ className }: { className?: string }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className={
          className ??
          "text-xs text-violet-300 hover:text-violet-200 whitespace-nowrap px-2 py-0.5 rounded border border-violet-800/70 hover:bg-violet-950/40"
        }
      >
        Emoji library…
      </button>
      <CustomEmojiLibraryModal open={open} onClose={() => setOpen(false)} />
    </>
  );
}

function PresetRow({
  p,
  onFlash,
  onDelete,
}: {
  p: CustomEmojiPreset;
  onFlash: (msg: string) => void;
  onDelete: () => void;
}) {
  const testSend = useMutation({
    mutationFn: () => api.telegramCustomEmoji.testSend({ html: p.html_fragment.trim() }),
    onSuccess: (data) => {
      onFlash(`Test sent to ${data.sent_to}`);
      window.setTimeout(() => onFlash(""), 5000);
    },
    onError: (e: Error) => {
      onFlash(e.message);
      window.setTimeout(() => onFlash(""), 6000);
    },
  });

  const frag = p.html_fragment;
  const preview = frag.length > 320 ? `${frag.slice(0, 320)}…` : frag;

  return (
    <li className="flex gap-2 items-start justify-between rounded border border-violet-900/50 bg-slate-900/40 p-2">
      <PresetInfo p={p} preview={preview} />
      <div className="flex flex-col gap-1 shrink-0 items-end">
        <button
          type="button"
          className="text-xs text-violet-300 hover:text-violet-200 px-2 py-0.5 rounded hover:bg-slate-700/50"
          title="Paste at caret in the last-focused caption or template field"
          onClick={() => {
            const ok = insertSnippetAtActiveTarget(p.html_fragment.trim());
            onFlash(
              ok ? "Inserted at caret." : "Copied to clipboard — focus a caption field and paste, or try again."
            );
            if (!ok) void tbccCopyText(p.html_fragment.trim());
            window.setTimeout(() => onFlash(""), 4000);
          }}
        >
          Insert
        </button>
        <button
          type="button"
          className="text-xs text-cyan-400 hover:text-cyan-300 px-2 py-0.5 rounded hover:bg-slate-700/50 disabled:opacity-50"
          disabled={testSend.isPending}
          onClick={() => testSend.mutate()}
        >
          Test send
        </button>
        <CopyToClipboardButton text={p.html_fragment.trim()} title="Copy HTML to clipboard" />
        <button
          type="button"
          className="text-xs text-red-400 hover:text-red-300 px-2 py-0.5 rounded hover:bg-red-950/40"
          onClick={onDelete}
        >
          Delete
        </button>
      </div>
    </li>
  );
}

function PresetInfo({ p, preview }: { p: CustomEmojiPreset; preview: string }) {
  return (
    <div className="min-w-0 flex-1">
      <div className="text-slate-200 font-medium truncate">{customEmojiPresetLabel(p)}</div>
      {p.source_note?.trim() ? <p className="text-[10px] text-slate-500 mt-0.5">{p.source_note}</p> : null}
      <pre className="text-slate-500 text-[10px] whitespace-pre-wrap break-all max-h-16 overflow-y-auto mt-1 font-mono">
        {preview}
      </pre>
    </div>
  );
}

function CustomEmojiLibraryModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { presets, remove } = useCustomEmojiPresets();
  const [flash, setFlash] = useState<string | null>(null);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[120] flex items-start justify-center overflow-y-auto bg-black/70 px-3 py-10"
      role="dialog"
      aria-modal="true"
      aria-labelledby="custom-emoji-lib-title"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg rounded-lg border border-violet-900/60 bg-slate-800 p-4 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-2 mb-3">
          <h2 id="custom-emoji-lib-title" className="text-lg font-medium text-violet-100">
            Custom emoji library
          </h2>
          <button type="button" className="text-sm text-slate-400 hover:text-slate-200 px-2 py-0.5 rounded" onClick={onClose}>
            Close
          </button>
        </div>
        <p className="text-slate-500 text-xs mb-4">
          Banners are <strong className="text-slate-400">emoji HTML only</strong> (no form body). Extract from a
          reference message in <strong className="text-slate-400">Misc → Caption banners</strong>, validate, test send, then
          save preset. Use <strong className="text-slate-400">Emoji banner…</strong> or Insert below to paste at the caret
          in Scheduler captions, listening relay templates, or any focused caption field — then type your body text in
          TBCC.
        </p>

        {presets.length === 0 ? (
          <p className="text-slate-600 text-sm mb-4">No presets yet. Extract and save one in Misc → Caption banners.</p>
        ) : (
          <ul className="max-h-72 overflow-y-auto space-y-2 text-sm mb-4">
            {presets.map((p) => (
              <PresetRow
                key={p.id}
                p={p}
                onFlash={setFlash}
                onDelete={() => void remove.mutateAsync(p.id)}
              />
            ))}
          </ul>
        )}

        {flash ? <p className="text-[11px] text-amber-400/95 mb-3">{flash}</p> : null}

        <button
          type="button"
          className="text-xs text-slate-400 hover:text-slate-200"
          onClick={() => {
            onClose();
            document.getElementById("caption-emoji-banners")?.scrollIntoView({ behavior: "smooth" });
          }}
        >
          Go to Misc → Caption banners to extract a new banner
        </button>
      </div>
    </div>
  );
}
