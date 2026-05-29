import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { CopyToClipboardButton } from "./CopyToClipboardButton";
import { QueryErrorBanner } from "./QueryErrorBanner";
import { SavedMessagesImportMacros } from "./SavedMessagesImportMacros";
import { SketchbookEmojiBrowser } from "./SketchbookEmojiBrowser";
import { TelegramPostAestheticsCompendium } from "./TelegramPostAestheticsCompendium";
import { useCaptionSnippets } from "../hooks/useCaptionSnippets";
import { tbccCopyText } from "../utils/clipboardToast";
import { bodyFromTelegramExtract } from "../utils/customEmojiExtract";

export type SketchPage = {
  id: number;
  sort_order: number;
  title: string | null;
  body: string;
};

const SKETCH_QUERY_KEY = ["emojiFactorySketchbook"];

function hasCustomEmojiTags(text: string): boolean {
  return /<tg-emoji\b/i.test(text);
}

export function EmojiFactorySketchbook() {
  const qc = useQueryClient();
  const { add: addCaptionSnippet } = useCaptionSnippets();
  const pagesQ = useQuery({
    queryKey: SKETCH_QUERY_KEY,
    queryFn: () => api.emojiFactory.sketchbook.listPages(),
    refetchOnWindowFocus: false,
  });

  const savedRecentQ = useQuery({
    queryKey: ["customEmojiSavedRecent"],
    queryFn: () => api.telegramCustomEmoji.savedMessagesRecent(25),
    refetchOnWindowFocus: false,
  });

  const [pageIndex, setPageIndex] = useState(0);
  const [draftTitle, setDraftTitle] = useState("");
  const [draftBody, setDraftBody] = useState("");
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [isDirty, setIsDirty] = useState(false);
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const activePageIdRef = useRef<number | null>(null);

  const pages = pagesQ.data ?? [];
  const current = pages[pageIndex] ?? pages[0];

  useEffect(() => {
    if (!current) return;
    if (activePageIdRef.current !== current.id) {
      activePageIdRef.current = current.id;
      setDraftTitle(current.title ?? "");
      setDraftBody(current.body ?? "");
      setIsDirty(false);
      setSaveState("saved");
    }
  }, [current?.id, current?.title, current?.body]);

  const persistPage = useMutation({
    mutationFn: (args: { id: number; title: string | null; body: string }) =>
      api.emojiFactory.sketchbook.patchPage(args.id, { title: args.title, body: args.body }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: SKETCH_QUERY_KEY });
      setSaveState("saved");
      setIsDirty(false);
    },
    onError: () => setSaveState("error"),
  });

  const scheduleSave = useCallback(
    (title: string | null, body: string) => {
      if (!current) return;
      setIsDirty(true);
      setSaveState("saving");
      if (saveTimer.current) clearTimeout(saveTimer.current);
      saveTimer.current = setTimeout(() => {
        persistPage.mutate({ id: current.id, title, body });
      }, 700);
    },
    [current, persistPage]
  );

  useEffect(() => {
    return () => {
      if (saveTimer.current) clearTimeout(saveTimer.current);
    };
  }, []);

  const createPageMut = useMutation({
    mutationFn: () => api.emojiFactory.sketchbook.createPage({ title: `Page ${pages.length + 1}`, body: "" }),
    onSuccess: async () => {
      const next = await qc.fetchQuery({ queryKey: SKETCH_QUERY_KEY, queryFn: () => api.emojiFactory.sketchbook.listPages() });
      setPageIndex(Math.max(0, next.length - 1));
    },
  });

  const deletePageMut = useMutation({
    mutationFn: (id: number) => api.emojiFactory.sketchbook.deletePage(id),
    onSuccess: async () => {
      const next = await qc.fetchQuery({ queryKey: SKETCH_QUERY_KEY, queryFn: () => api.emojiFactory.sketchbook.listPages() });
      setPageIndex((i) => Math.min(i, Math.max(0, next.length - 1)));
    },
  });

  const extractMut = useMutation({
    mutationFn: (messageId: number) => api.telegramCustomEmoji.extract({ peer: "me", message_id: messageId }),
    onSuccess: (data) => {
      const text = bodyFromTelegramExtract(data);
      if (!text) return;
      const title = draftTitle.trim() || current?.title || null;
      setDraftBody(text);
      scheduleSave(title, text);
    },
  });

  const savePresetMut = useMutation({
    mutationFn: () =>
      api.emojiFactory.sketchbook.savePreset(current!.id, {
        title: draftTitle.trim() || current?.title || "Sketchbook",
        html: draftBody,
      }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["customEmojiPresets"] }),
  });

  const pageLabel = useMemo(() => {
    if (!pages.length) return "—";
    return `Page ${pageIndex + 1} of ${pages.length}`;
  }, [pageIndex, pages.length]);

  if (pagesQ.isLoading) {
    return (
      <section className="rounded-lg border border-violet-900/50 bg-violet-950/15 p-4 text-sm text-slate-500">
        Loading design sketchbook…
      </section>
    );
  }

  if (pagesQ.isError) {
    return (
      <QueryErrorBanner
        title="Sketchbook"
        message={(pagesQ.error as Error).message}
        onRetry={() => void pagesQ.refetch()}
      />
    );
  }

  return (
    <section className="rounded-lg border border-violet-900/50 bg-violet-950/15 p-4 space-y-3">
      <div>
        <h3 className="text-base font-medium text-violet-100">Design sketchbook</h3>
        <p className="text-xs text-slate-400 mt-1 max-w-3xl leading-relaxed">
          Paginated scratchpad stored in TBCC (like Saved Messages — not cleared when you refresh or finish a stage).
          Paste or import Telegram layouts, practice emoji walls, then push to{" "}
          <Link to="/scheduler" className="text-cyan-400 hover:underline">
            Scheduler
          </Link>{" "}
          via <strong className="text-slate-300">Emoji library</strong> or{" "}
          <strong className="text-slate-300">Caption library</strong>.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          disabled={pageIndex <= 0}
          onClick={() => setPageIndex((i) => Math.max(0, i - 1))}
          className="px-2 py-1 rounded bg-slate-700 text-white text-xs disabled:opacity-40"
        >
          ← Prev
        </button>
        <span className="text-xs text-slate-400 font-mono">{pageLabel}</span>
        <button
          type="button"
          disabled={pageIndex >= pages.length - 1}
          onClick={() => setPageIndex((i) => Math.min(pages.length - 1, i + 1))}
          className="px-2 py-1 rounded bg-slate-700 text-white text-xs disabled:opacity-40"
        >
          Next →
        </button>
        <button
          type="button"
          onClick={() => createPageMut.mutate()}
          disabled={createPageMut.isPending}
          className="px-2 py-1 rounded bg-violet-800 text-violet-100 text-xs hover:bg-violet-700"
        >
          + New page
        </button>
        <button
          type="button"
          disabled={pages.length <= 1 || deletePageMut.isPending || !current}
          onClick={() => {
            if (!current) return;
            if (!window.confirm(`Delete "${current.title || "this page"}"?`)) return;
            deletePageMut.mutate(current.id);
          }}
          className="px-2 py-1 rounded text-rose-400/90 text-xs hover:text-rose-300 disabled:opacity-40"
        >
          Delete page
        </button>
        <span className="text-[10px] text-slate-500 ml-auto">
          {saveState === "saving" ? "Saving…" : saveState === "error" ? "Save failed" : isDirty ? "Unsaved" : "Saved"}
        </span>
      </div>

      <label className="block text-xs text-slate-500">
        Page title
        <input
          className="mt-1 w-full max-w-md bg-slate-900 border border-slate-600 rounded px-2 py-1 text-sm"
          value={draftTitle}
          onChange={(e) => {
            const v = e.target.value;
            setDraftTitle(v);
            scheduleSave(v.trim() || null, draftBody);
          }}
        />
      </label>

      <SketchbookEmojiBrowser
        onInsert={(tag) => {
          setDraftBody((prev) => {
            const next = prev + tag;
            scheduleSave(draftTitle.trim() || null, next);
            return next;
          });
        }}
      />

      <label className="block text-xs text-slate-500">
        Design (Telegram HTML, plain text, or <code className="text-violet-300">&lt;tg-emoji&gt;</code> tags)
        <textarea
          className="mt-1 w-full rounded border border-slate-600 bg-slate-950 px-2 py-2 text-sm font-mono min-h-[220px] leading-relaxed"
          value={draftBody}
          spellCheck={false}
          onChange={(e) => {
            const v = e.target.value;
            setDraftBody(v);
            scheduleSave(draftTitle.trim() || null, v);
          }}
        />
      </label>

      <div className="flex flex-wrap gap-2 items-center">
        <CopyToClipboardButton text={draftBody} label="Copy" />
        <button
          type="button"
          className="px-2 py-1 rounded bg-slate-700 text-white text-xs"
          onClick={() => void tbccCopyText(draftBody)}
        >
          Copy + toast
        </button>
        <button
          type="button"
          disabled={!draftBody.trim() || savePresetMut.isPending}
          onClick={() => savePresetMut.mutate()}
          className="px-2 py-1 rounded bg-emerald-800 text-white text-xs disabled:opacity-40"
          title="Stores telethon-ready HTML in Emoji library for Scheduler"
        >
          {savePresetMut.isPending ? "…" : "→ Emoji library"}
        </button>
        <button
          type="button"
          disabled={!draftBody.trim()}
          onClick={() => void addCaptionSnippet(draftTitle || "Sketchbook", draftBody)}
          className="px-2 py-1 rounded bg-slate-700 text-white text-xs disabled:opacity-40"
          title="Full caption line for Scheduler snippet picker"
        >
          → Caption library
        </button>
        <Link to="/scheduler" className="text-xs text-cyan-400 hover:underline px-1">
          Open Scheduler
        </Link>
        <Link to="/misc#caption-emoji-banners" className="text-xs text-violet-400 hover:underline px-1">
          Extract tools
        </Link>
      </div>
      {savePresetMut.isError ? (
        <p className="text-xs text-amber-300">
          {(savePresetMut.error as Error).message}
          {!hasCustomEmojiTags(draftBody) ? " — plain text works via Caption library; Emoji library needs valid Telegram HTML." : null}
        </p>
      ) : null}
      {savePresetMut.isSuccess ? (
        <p className="text-xs text-emerald-300">Saved to Emoji library — insert from Scheduler with “Emoji banner…”.</p>
      ) : null}

      <TelegramPostAestheticsCompendium />

      <div className="border-t border-slate-700/80 pt-3">
        <div className="flex gap-2 items-center mb-2">
          <h4 className="text-xs font-medium text-slate-300">Import from Saved Messages</h4>
          <button
            type="button"
            onClick={() => void savedRecentQ.refetch()}
            className="px-2 py-0.5 rounded bg-slate-700 text-white text-[10px]"
          >
            Refresh
          </button>
          {extractMut.isPending ? <span className="text-[10px] text-slate-500">Extracting…</span> : null}
        </div>
        {savedRecentQ.isError ? (
          <p className="text-xs text-amber-300">Could not load Saved Messages (poster Telethon session must be logged in).</p>
        ) : savedRecentQ.data?.messages?.length ? (
          <>
            <p className="text-[10px] text-slate-500 mb-1">
              One tap: extract telethon HTML and save. Use <strong className="text-slate-400">→ Sketch</strong> to load this
              page only, or <strong className="text-slate-400">Library + Sketch</strong> for both.
            </p>
            <SavedMessagesImportMacros
              messages={savedRecentQ.data.messages}
              compact
              onSketchbookImported={() => void pagesQ.refetch()}
            />
            <button
              type="button"
              className="mt-2 text-[10px] text-slate-500 hover:text-slate-300 underline"
              onClick={() => {
                const first = savedRecentQ.data?.messages?.[0];
                if (first) extractMut.mutate(first.message_id);
              }}
            >
              Legacy: import latest into this page only
            </button>
          </>
        ) : (
          <p className="text-xs text-slate-500">No recent messages — forward a design to Saved Messages first.</p>
        )}
        {extractMut.isError ? <p className="text-xs text-red-300 mt-1">{(extractMut.error as Error).message}</p> : null}
      </div>
    </section>
  );
}
