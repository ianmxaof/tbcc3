export type BufferXQueueItem = { text: string; image_url?: string };

const MAX = 10;

type Props = {
  items: BufferXQueueItem[];
  onChange: (items: BufferXQueueItem[]) => void;
  disabled?: boolean;
};

export function BufferXQueueEditor({ items, onChange, disabled }: Props) {
  const add = () => {
    if (items.length >= MAX) return;
    onChange([...items, { text: "" }]);
  };
  const update = (i: number, patch: Partial<BufferXQueueItem>) => {
    onChange(items.map((x, j) => (j === i ? { ...x, ...patch } : x)));
  };
  const remove = (i: number) => onChange(items.filter((_, j) => j !== i));

  return (
    <section className="rounded border border-sky-800/40 bg-sky-950/20 p-3 space-y-3">
      <p className="text-xs text-slate-400">
        Up to <strong className="text-slate-300">{MAX}</strong> X captions stored in TBCC (not sent to Buffer until this job
        posts to Telegram). Each Telegram run uses the <strong className="text-slate-300">next</strong> caption below; when empty,
        falls back to mirroring the Telegram caption. Buffer still holds its own publish queue (max 10 slots per channel on Free).
      </p>
      {items.length === 0 ? (
        <p className="text-xs text-slate-500 italic">No pre-queued X captions — will mirror Telegram on each run.</p>
      ) : null}
      {items.map((item, i) => (
        <article key={i} className="border border-slate-600/60 rounded p-2 space-y-2 bg-slate-900/40">
          <header className="flex items-center justify-between gap-2">
            <span className="text-xs text-sky-300 font-medium">
              #{i + 1}
              {i === 0 ? " — next on Telegram send" : ""}
            </span>
            <button
              type="button"
              className="text-xs text-red-400 hover:text-red-300 disabled:opacity-40"
              disabled={disabled}
              onClick={() => remove(i)}
            >
              Remove
            </button>
          </header>
          <textarea
            value={item.text}
            onChange={(e) => update(i, { text: e.target.value })}
            disabled={disabled}
            rows={3}
            placeholder="X post text (plain or Telegram HTML)"
            className="w-full bg-slate-800 border border-slate-600 rounded px-2 py-1.5 text-slate-200 text-sm"
          />
          <input
            type="url"
            value={item.image_url || ""}
            onChange={(e) => update(i, { image_url: e.target.value })}
            disabled={disabled}
            placeholder="Optional image URL (https://…)"
            className="w-full bg-slate-800 border border-slate-600 rounded px-2 py-1.5 text-slate-200 text-sm"
          />
        </article>
      ))}
      <button
        type="button"
        className="text-sm text-cyan-400 hover:text-cyan-300 disabled:opacity-40"
        disabled={disabled || items.length >= MAX}
        onClick={add}
      >
        + Add X caption ({items.length}/{MAX})
      </button>
    </section>
  );
}
