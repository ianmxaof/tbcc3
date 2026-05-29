/**
 * Last-focused caption/promo textarea registers here so "Insert" from modals can paste at the caret.
 * Falls back to clipboard-only when nothing is focused (caller handles toast).
 */
type InsertFn = (text: string) => void;

let activeInsert: InsertFn | null = null;

export function registerSnippetInsertTarget(insertAtCursor: InsertFn): () => void {
  activeInsert = insertAtCursor;
  return () => {
    if (activeInsert === insertAtCursor) activeInsert = null;
  };
}

export function insertSnippetAtActiveTarget(text: string): boolean {
  if (!activeInsert || !String(text || "").trim()) return false;
  try {
    activeInsert(text);
    return true;
  } catch {
    return false;
  }
}
