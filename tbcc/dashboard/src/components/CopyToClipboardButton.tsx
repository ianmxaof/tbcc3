import { tbccCopyText } from "../utils/clipboardToast";

type Props = {
  text: string;
  label?: string;
  className?: string;
  title?: string;
};

/** Standard TBCC copy control — shows global “Copied!” tooltip on success. */
export function CopyToClipboardButton({
  text,
  label = "Copy",
  className,
  title = "Copy to clipboard",
}: Props) {
  return (
    <button
      type="button"
      title={title}
      className={
        className ??
        "text-xs text-slate-400 hover:text-slate-200 px-2 py-0.5 rounded hover:bg-slate-700/50"
      }
      onClick={(e) => {
        e.stopPropagation();
        void tbccCopyText(text, { anchor: e.currentTarget });
      }}
    >
      {label}
    </button>
  );
}
