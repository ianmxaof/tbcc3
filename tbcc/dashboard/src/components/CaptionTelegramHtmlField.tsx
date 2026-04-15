import { useLayoutEffect, useRef, type ReactNode } from "react";

type Props = {
  value: string;
  onChange: (next: string) => void;
  placeholder?: string;
  rows?: number;
  className?: string;
  /** Snippet picker + remove variation, etc. */
  extraActions?: ReactNode;
};

/**
 * Caption textarea with Telegram Bot-API-style HTML helpers (<b>, <i>, <u>, …).
 * Selection is preserved after wrapping when possible.
 */
export function CaptionTelegramHtmlField({
  value,
  onChange,
  placeholder,
  rows = 4,
  className = "",
  extraActions,
}: Props) {
  const taRef = useRef<HTMLTextAreaElement>(null);
  const selRestore = useRef<{ start: number; end: number } | null>(null);

  useLayoutEffect(() => {
    const el = taRef.current;
    const p = selRestore.current;
    if (!el || !p) return;
    selRestore.current = null;
    const len = value.length;
    const a = Math.max(0, Math.min(p.start, len));
    const b = Math.max(0, Math.min(p.end, len));
    el.setSelectionRange(a, b);
  }, [value]);

  const wrap = (open: string, close: string) => {
    const ta = taRef.current;
    if (!ta) return;
    const start = ta.selectionStart;
    const end = ta.selectionEnd;
    const sel = value.slice(start, end);
    const next = value.slice(0, start) + open + sel + close + value.slice(end);
    selRestore.current = { start: start + open.length, end: start + open.length + sel.length };
    onChange(next);
  };

  const btn =
    "px-2 py-0.5 rounded border border-slate-500 bg-slate-700/90 text-slate-200 text-xs font-medium hover:bg-slate-600 disabled:opacity-40";

  return (
    <div className="flex gap-2 items-start">
      <div className={`flex-1 min-w-0 flex flex-col gap-1 ${className}`}>
        <div className="flex flex-wrap items-center gap-1">
          <span className="text-slate-500 text-[10px] uppercase tracking-wide mr-1">Format</span>
          <button type="button" className={btn} onClick={() => wrap("<b>", "</b>")} title="Bold">
            B
          </button>
          <button type="button" className={btn} onClick={() => wrap("<i>", "</i>")} title="Italic">
            I
          </button>
          <button type="button" className={btn} onClick={() => wrap("<u>", "</u>")} title="Underline">
            U
          </button>
          <button type="button" className={btn} onClick={() => wrap("<s>", "</s>")} title="Strikethrough">
            S
          </button>
          <button
            type="button"
            className={btn}
            onClick={() => wrap("<tg-spoiler>", "</tg-spoiler>")}
            title="Spoiler (tap to reveal)"
          >
            Spoiler
          </button>
          <button type="button" className={btn} onClick={() => wrap("<code>", "</code>")} title="Monospace">
            Mono
          </button>
        </div>
        <textarea
          ref={taRef}
          placeholder={placeholder}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          rows={rows}
          className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200 min-w-0"
        />
        <p className="text-slate-500 text-[10px] leading-snug">
          Sent as Telegram HTML. For a different &quot;font&quot;, use Unicode stylers outside TBCC or the Mono tag. In text,
          use <code className="text-slate-400">&amp;lt;</code> only for tags you intend — raw{" "}
          <code className="text-slate-400">&amp;</code> should be <code className="text-slate-400">&amp;amp;</code>.
        </p>
      </div>
      {extraActions ? <div className="flex flex-col gap-1 shrink-0 items-end pt-0.5">{extraActions}</div> : null}
    </div>
  );
}
