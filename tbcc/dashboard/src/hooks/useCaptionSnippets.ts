import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import {
  CAPTION_SNIPPETS_STORAGE_KEY,
  type CaptionSnippet,
  loadCaptionSnippets,
  saveCaptionSnippets,
  snippetMenuLabel,
} from "../utils/captionSnippetsStorage";

const SNIPPETS_CHANGED = "tbcc:caption-snippets-changed";

function notifySnippetsChanged() {
  window.dispatchEvent(new Event(SNIPPETS_CHANGED));
}

/** Server-backed row; negative id = offline fallback index into localStorage order. */
export type CaptionSnippetRow = {
  id: number;
  title: string | null;
  body: string;
};

export function captionSnippetMenuLabel(s: CaptionSnippetRow): string {
  return snippetMenuLabel({
    id: String(s.id),
    title: s.title ?? "",
    body: s.body,
    createdAt: 0,
  });
}

export function useCaptionSnippets() {
  const [snippets, setSnippets] = useState<CaptionSnippetRow[]>([]);

  const refresh = useCallback(async () => {
    try {
      let rows = await api.captionSnippets.list();
      if (rows.length === 0) {
        const local = loadCaptionSnippets();
        if (local.length > 0) {
          for (const s of local) {
            try {
              await api.captionSnippets.create({ title: s.title || undefined, body: s.body });
            } catch {
              /* continue migrating other rows */
            }
          }
          saveCaptionSnippets([]);
          notifySnippetsChanged();
          rows = await api.captionSnippets.list();
        }
      }
      setSnippets(rows);
    } catch {
      const local = loadCaptionSnippets();
      setSnippets(
        local.map((s, i) => ({
          id: -(i + 1),
          title: s.title || null,
          body: s.body,
        }))
      );
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key === null || e.key === CAPTION_SNIPPETS_STORAGE_KEY) void refresh();
    };
    const onCustom = () => void refresh();
    window.addEventListener("storage", onStorage);
    window.addEventListener(SNIPPETS_CHANGED, onCustom);
    return () => {
      window.removeEventListener("storage", onStorage);
      window.removeEventListener(SNIPPETS_CHANGED, onCustom);
    };
  }, [refresh]);

  const add = useCallback(
    async (title: string, body: string) => {
      const trimmed = body.trim();
      if (!trimmed) return;
      try {
        await api.captionSnippets.create({ title: title.trim() || null, body: trimmed });
        await refresh();
      } catch {
        const id =
          typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
            ? crypto.randomUUID()
            : `s_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
        const s: CaptionSnippet = {
          id,
          title: title.trim(),
          body: trimmed,
          createdAt: Date.now(),
        };
        const next = [s, ...loadCaptionSnippets()];
        saveCaptionSnippets(next);
        notifySnippetsChanged();
        setSnippets(
          next.map((x, i) => ({
            id: -(i + 1),
            title: x.title || null,
            body: x.body,
          }))
        );
      }
    },
    [refresh]
  );

  const remove = useCallback(
    async (id: number) => {
      if (id < 0) {
        const idx = Math.abs(id) - 1;
        const local = loadCaptionSnippets();
        const next = local.filter((_, i) => i !== idx);
        saveCaptionSnippets(next);
        notifySnippetsChanged();
        setSnippets(
          next.map((x, i) => ({
            id: -(i + 1),
            title: x.title || null,
            body: x.body,
          }))
        );
        return;
      }
      try {
        await api.captionSnippets.delete(id);
        await refresh();
      } catch {
        /* ignore */
      }
    },
    [refresh]
  );

  const update = useCallback(
    async (id: number, title: string, body: string) => {
      const trimmed = body.trim();
      if (!trimmed || id < 0) return;
      try {
        await api.captionSnippets.patch(id, { title: title.trim() || null, body: trimmed });
        await refresh();
      } catch {
        /* ignore */
      }
    },
    [refresh]
  );

  const bulkImport = useCallback(
    async (items: Array<{ title?: string | null; body?: string }>) => {
      const cleaned = items
        .map((it) => ({
          title: it.title != null ? String(it.title).trim() || null : null,
          body: String(it.body || "").trim(),
        }))
        .filter((it) => it.body.length > 0);
      if (!cleaned.length) return 0;
      try {
        const res = await api.captionSnippets.bulk({ items: cleaned });
        await refresh();
        return res.created;
      } catch {
        return 0;
      }
    },
    [refresh]
  );

  return { snippets, add, update, remove, bulkImport };
}
