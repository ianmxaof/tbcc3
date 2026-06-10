import type { ReactNode } from "react";

/** Compact bordered tile for the scheduler composer grid. */
export function SchedulerComposerCard({
  title,
  children,
  className = "",
  bodyClassName = "",
  headerRight,
}: {
  title: string;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
  headerRight?: ReactNode;
}) {
  return (
    <section
      className={`tbcc-panel flex min-h-0 flex-col rounded-md border border-slate-600/80 bg-slate-900/50 p-2 ${className}`}
    >
      <div className="mb-1 flex shrink-0 items-center justify-between gap-1">
        <h4 className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">{title}</h4>
        {headerRight}
      </div>
      <div className={`min-h-0 flex-1 overflow-y-auto overflow-x-hidden ${bodyClassName}`}>{children}</div>
    </section>
  );
}
