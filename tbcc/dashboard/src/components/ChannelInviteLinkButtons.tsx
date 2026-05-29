/** Collapsible row of channel invite buttons (keeps the scheduler / relay UI compact). */

export function ChannelInviteLinkButtons({
  channels,
  onInsertLink,
  summaryPrefix = "Quick insert — channel invite links",
}: {
  channels: Array<Record<string, unknown>>;
  onInsertLink: (inviteUrl: string) => void;
  /** e.g. append "→ first caption" vs "→ template #1" in the summary line */
  summaryPrefix?: string;
}) {
  const withLinks = channels.filter((c) => String(c.invite_link || "").trim());
  if (withLinks.length === 0) return null;

  return (
    <details className="w-full rounded border border-slate-600/60 bg-slate-900/30 px-2 py-1.5 text-xs">
      <summary className="cursor-pointer text-slate-400 select-none hover:text-slate-300">
        {summaryPrefix} ({withLinks.length})
      </summary>
      <div className="flex flex-wrap gap-2 mt-2 pb-1">
        {withLinks.map((c) => (
          <button
            key={String(c.id)}
            type="button"
            onClick={() => {
              const link = String(c.invite_link || "").trim();
              if (link) onInsertLink(link);
            }}
            className="px-2 py-1 rounded bg-slate-700 border border-slate-600 text-xs text-cyan-300 hover:bg-slate-600"
          >
            + {String(c.name || c.identifier || c.id)} link
          </button>
        ))}
      </div>
    </details>
  );
}
