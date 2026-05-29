import { useCallback, useEffect, useRef, type RefObject } from "react";
import { registerSnippetInsertTarget } from "../utils/snippetInsertBridge";

/** Registers a textarea as the insert target while focused (with blur delay so toolbar/modal clicks still work). */
export function useSnippetInsertBridge(
  value: string,
  onChange: (next: string) => void,
  textAreaRef: RefObject<HTMLTextAreaElement | null>
) {
  const valueRef = useRef(value);
  valueRef.current = value;
  const disposeRef = useRef<(() => void) | null>(null);

  const onFocus = useCallback(() => {
    disposeRef.current?.();
    disposeRef.current = registerSnippetInsertTarget((chunk) => {
      const el = textAreaRef.current;
      if (!el) return;
      const v = valueRef.current;
      const start = el.selectionStart ?? v.length;
      const end = el.selectionEnd ?? start;
      const next = v.slice(0, start) + chunk + v.slice(end);
      onChange(next);
      const pos = start + chunk.length;
      requestAnimationFrame(() => {
        try {
          el.focus();
          el.setSelectionRange(pos, pos);
        } catch {
          /* ignore */
        }
      });
    });
  }, [onChange, textAreaRef]);

  const onBlur = useCallback(() => {
    window.setTimeout(() => {
      disposeRef.current?.();
      disposeRef.current = null;
    }, 280);
  }, []);

  useEffect(() => () => disposeRef.current?.(), []);

  return { onFocus, onBlur };
}
