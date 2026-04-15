import { useCallback, useEffect, useState } from "react";
import {
  CAPTION_SNIPPETS_STORAGE_KEY,
  type CaptionSnippet,
  loadCaptionSnippets,
  saveCaptionSnippets,
} from "../utils/captionSnippetsStorage";

const SNIPPETS_CHANGED = "tbcc:caption-snippets-changed";

function notifySnippetsChanged() {
  window.dispatchEvent(new Event(SNIPPETS_CHANGED));
}

export function useCaptionSnippets() {
  const [snippets, setSnippets] = useState<CaptionSnippet[]>(() => loadCaptionSnippets());

  useEffect(() => {
    const refresh = () => setSnippets(loadCaptionSnippets());
    const onStorage = (e: StorageEvent) => {
      if (e.key === null || e.key === CAPTION_SNIPPETS_STORAGE_KEY) refresh();
    };
    window.addEventListener("storage", onStorage);
    window.addEventListener(SNIPPETS_CHANGED, refresh);
    return () => {
      window.removeEventListener("storage", onStorage);
      window.removeEventListener(SNIPPETS_CHANGED, refresh);
    };
  }, []);

  const add = useCallback((title: string, body: string) => {
    const trimmed = body.trim();
    if (!trimmed) return;
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
    setSnippets((prev) => {
      const next = [s, ...prev];
      saveCaptionSnippets(next);
      notifySnippetsChanged();
      return next;
    });
  }, []);

  const remove = useCallback((id: string) => {
    setSnippets((prev) => {
      const next = prev.filter((x) => x.id !== id);
      saveCaptionSnippets(next);
      notifySnippetsChanged();
      return next;
    });
  }, []);

  return { snippets, add, remove };
}
