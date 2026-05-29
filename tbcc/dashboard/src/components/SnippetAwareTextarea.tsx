import { useRef, type TextareaHTMLAttributes } from "react";
import { useSnippetInsertBridge } from "../hooks/useSnippetInsertBridge";

type Props = Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, "value" | "onChange"> & {
  value: string;
  onChange: (next: string) => void;
};

/** Controlled textarea that receives inserts at the caret via insertSnippetAtActiveTarget when focused. */
export function SnippetAwareTextarea({ value, onChange, onFocus, onBlur, ...rest }: Props) {
  const ref = useRef<HTMLTextAreaElement>(null);
  const { onFocus: regFocus, onBlur: regBlur } = useSnippetInsertBridge(value, onChange, ref);
  return (
    <textarea
      ref={ref}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      onFocus={(e) => {
        regFocus();
        onFocus?.(e);
      }}
      onBlur={(e) => {
        regBlur();
        onBlur?.(e);
      }}
      {...rest}
    />
  );
}
