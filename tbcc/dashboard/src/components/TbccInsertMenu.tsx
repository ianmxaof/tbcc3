import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import { captionSnippetMenuLabel, useCaptionSnippets } from "../hooks/useCaptionSnippets";
import { customEmojiPresetLabel, useCustomEmojiPresets } from "../hooks/useCustomEmojiPresets";
import { insertSnippetAtActiveTarget } from "../utils/snippetInsertBridge";

function promoInsertUrl(r: { url: string; short_url?: string | null }) {
  const s = (r.short_url || "").trim();
  return s || r.url;
}

function applyInsert(text: string, onInsert: (t: string) => void) {
  const chunk = String(text || "").trim();
  if (!chunk) return;
  if (!insertSnippetAtActiveTarget(chunk)) onInsert(chunk);
}

type ChannelRow = Record<string, unknown>;
type PoolRow = Record<string, unknown>;

function channelLabel(c: ChannelRow): string {
  return String(c.name || c.identifier || `#${c.id}`);
}

function Section({
  title,
  children,
  bordered,
}: {
  title: string;
  children: ReactNode;
  bordered?: boolean;
}) {
  return (
    <div className={bordered ? "border-t border-slate-600/80 pt-1.5 mt-1.5" : ""}>
      <div className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-slate-500">{title}</div>
      <div className="max-h-36 overflow-y-auto">{children}</div>
    </div>
  );
}

function ItemButton({ label, title, onClick }: { label: string; title?: string; onClick: () => void }) {
  return (
    <button
      type="button"
      title={title || label}
      className="block w-full text-left px-2 py-1.5 text-[11px] text-slate-200 hover:bg-slate-700/80 rounded truncate"
      onClick={onClick}
    >
      {label}
    </button>
  );
}

function archiveInsertLabel(row: { label?: string; description?: string; url: string }): string {
  const label = String(row.label || row.description || "").trim();
  if (label) return label.length > 56 ? `${label.slice(0, 56)}…` : label;
  try {
    return new URL(row.url).hostname.replace(/^www\./, "");
  } catch {
    return row.url.slice(0, 56);
  }
}

/**
 * Unified Insert dropdown: channel invites (pools), promo links, archive URLs, captions, ASCII art, emoji banners.
 * Inserts at the caret in the last-focused caption field when registered; otherwise calls onInsert.
 */
export function TbccInsertMenu({
  onInsert,
  disabled,
  channels = [],
  pools = [],
  className,
  buttonLabel = "Insert…",
}: {
  onInsert: (text: string) => void;
  disabled?: boolean;
  channels?: ChannelRow[];
  pools?: PoolRow[];
  className?: string;
  buttonLabel?: string;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const { snippets } = useCaptionSnippets();
  const { presets, isLoading: emojiLoading } = useCustomEmojiPresets();

  const promoQ = useQuery({
    queryKey: ["promoAffiliateLinks", "insert-menu"],
    queryFn: () => api.promoAffiliateLinks.list({ sort: "priority_asc", active_only: true }),
    enabled: open,
    staleTime: 60_000,
  });

  const asciiQ = useQuery({
    queryKey: ["listeningRelayAscii", "insert-menu"],
    queryFn: () => api.listeningRelay.listAsciiArt(),
    enabled: open,
    staleTime: 120_000,
  });

  const archiveQ = useQuery({
    queryKey: ["archiveInsertMenu", "insert-menu"],
    queryFn: () => api.archive.insertMenu({ limit: 200 }),
    enabled: open,
    staleTime: 60_000,
  });

  const channelIdsWithPools = useMemo(() => {
    const ids = new Set<number>();
    for (const p of pools) {
      const cid = Number(p.channel_id);
      if (Number.isFinite(cid) && cid > 0) ids.add(cid);
    }
    return ids;
  }, [pools]);

  const poolChannels = useMemo(() => {
    return channels.filter((c) => {
      const id = Number(c.id);
      const link = String(c.invite_link || "").trim();
      return link && channelIdsWithPools.has(id);
    });
  }, [channels, channelIdsWithPools]);

  const promoRows = promoQ.data ?? [];
  const asciiEntries = asciiQ.data?.entries ?? [];
  const archiveRows = archiveQ.data?.items ?? [];

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  const pick = (text: string) => {
    applyInsert(text, onInsert);
    setOpen(false);
  };

  const hasAny =
    poolChannels.length > 0 ||
    snippets.length > 0 ||
    promoRows.length > 0 ||
    archiveRows.length > 0 ||
    asciiEntries.length > 0 ||
    presets.length > 0;

  return (
    <div ref={rootRef} className={`relative inline-block text-left ${className ?? ""}`}>
      <button
        type="button"
        disabled={disabled}
        title="Insert channel link, promo URL, archive link, caption, ASCII art, or emoji banner at cursor"
        aria-expanded={open}
        aria-haspopup="listbox"
        className="text-[11px] bg-slate-800 border border-slate-600 rounded px-2 py-1 text-cyan-300 hover:bg-slate-700/80 disabled:opacity-40 whitespace-nowrap"
        onClick={() => setOpen((v) => !v)}
      >
        {buttonLabel}
      </button>
      {open ? (
        <div
          role="listbox"
          className="absolute right-0 top-full z-[118] mt-1 w-[min(100vw-1.5rem,20rem)] max-h-[min(70vh,22rem)] overflow-y-auto rounded-lg border border-slate-600 bg-slate-900 shadow-xl py-1"
        >
          {!hasAny && !promoQ.isLoading && !asciiQ.isLoading && !archiveQ.isLoading && !emojiLoading ? (
            <p className="px-2 py-2 text-[11px] text-slate-500">
              Nothing saved yet. Use libraries (Misc) to add promo links, captions, emoji, or ASCII art. Archive URLs
              from Master archive (Approved tab) appear here automatically.
            </p>
          ) : null}

          {poolChannels.length > 0 ? (
            <Section title="Channel invites">
              {poolChannels.map((c) => {
                const link = String(c.invite_link || "").trim();
                return (
                  <ItemButton
                    key={String(c.id)}
                    label={channelLabel(c)}
                    title={`Insert invite link for ${channelLabel(c)}`}
                    onClick={() => pick(link)}
                  />
                );
              })}
            </Section>
          ) : null}

          {promoQ.isLoading ? (
            <Section title="Promo links" bordered={poolChannels.length > 0}>
              <p className="px-2 py-1 text-[11px] text-slate-500">Loading…</p>
            </Section>
          ) : promoRows.length > 0 ? (
            <Section title="Promo links" bordered={poolChannels.length > 0}>
              {promoRows.map((r) => (
                <ItemButton
                  key={r.id}
                  label={r.label}
                  title={promoInsertUrl(r)}
                  onClick={() => pick(promoInsertUrl(r))}
                />
              ))}
            </Section>
          ) : null}

          {archiveQ.isLoading ? (
            <Section title="Archive links" bordered={poolChannels.length > 0 || promoRows.length > 0}>
              <p className="px-2 py-1 text-[11px] text-slate-500">Loading…</p>
            </Section>
          ) : archiveRows.length > 0 ? (
            <Section title="Archive links" bordered={poolChannels.length > 0 || promoRows.length > 0}>
              {archiveRows.map((r) => {
                const label = archiveInsertLabel(r);
                const title = [r.description || r.label, r.tags ? `tags: ${r.tags}` : "", r.url]
                  .filter(Boolean)
                  .join(" · ");
                return (
                  <ItemButton key={r.id} label={label} title={title} onClick={() => pick(r.url)} />
                );
              })}
            </Section>
          ) : null}

          {snippets.length > 0 ? (
            <Section
              title="Captions"
              bordered={poolChannels.length > 0 || promoRows.length > 0 || archiveRows.length > 0}
            >
              {snippets.map((s) => (
                <ItemButton
                  key={String(s.id)}
                  label={captionSnippetMenuLabel(s)}
                  onClick={() => pick(s.body)}
                />
              ))}
            </Section>
          ) : null}

          {asciiQ.isLoading ? (
            <Section
              title="ASCII art"
              bordered={
                poolChannels.length > 0 || promoRows.length > 0 || snippets.length > 0 || archiveRows.length > 0
              }
            >
              <p className="px-2 py-1 text-[11px] text-slate-500">Loading…</p>
            </Section>
          ) : asciiEntries.length > 0 ? (
            <Section
              title="ASCII art"
              bordered={
                poolChannels.length > 0 || promoRows.length > 0 || snippets.length > 0 || archiveRows.length > 0
              }
            >
              {asciiEntries.map((e) => (
                <ItemButton
                  key={e.id}
                  label={e.name || "Untitled"}
                  title={e.content.slice(0, 120)}
                  onClick={() => pick(e.content)}
                />
              ))}
            </Section>
          ) : null}

          {emojiLoading ? (
            <Section
              title="Emoji banners"
              bordered={
                poolChannels.length > 0 ||
                promoRows.length > 0 ||
                snippets.length > 0 ||
                archiveRows.length > 0 ||
                asciiEntries.length > 0
              }
            >
              <p className="px-2 py-1 text-[11px] text-slate-500">Loading…</p>
            </Section>
          ) : presets.length > 0 ? (
            <Section
              title="Emoji banners"
              bordered={
                poolChannels.length > 0 ||
                promoRows.length > 0 ||
                snippets.length > 0 ||
                archiveRows.length > 0 ||
                asciiEntries.length > 0
              }
            >
              {presets.map((p) => (
                <ItemButton
                  key={p.id}
                  label={customEmojiPresetLabel(p)}
                  onClick={() => pick(p.html_fragment.trim())}
                />
              ))}
            </Section>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
