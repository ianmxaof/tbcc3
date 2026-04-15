import { type ReactNode } from "react";

type Props = {
  title?: string;
  children: ReactNode;
  className?: string;
};

export function InfoDisclosure({ title = "How it works", children, className = "" }: Props) {
  return (
    <details
      className={`text-xs text-slate-500 [&_summary]:cursor-pointer [&_summary]:select-none ${className}`.trim()}
    >
      <summary>{title}</summary>
      <div className="mt-2 pl-0.5 leading-relaxed text-slate-400">{children}</div>
    </details>
  );
}
