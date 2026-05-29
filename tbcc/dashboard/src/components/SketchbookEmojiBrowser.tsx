import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { api } from "../api";
import { tbccCopyText } from "../utils/clipboardToast";

type Pack = { id: number; short_name: string; title: string; count: number };
type EmojiRow = { document_id: number; alt: string; placeholder: string; tag: string };

export function SketchbookEmojiBrowser({
  onInsert,
}: {
  onInsert: (chunk: string) => void;
}) {
  const [packSn, setPackSn] = useState("");
  const [filter, setFilter] = useState("");

  const packsQ = useQuery({
    queryKey: ["customEmojiInstalledPacks"],
    queryFn: () => api.telegramCustomEmoji.installedPacks(),
    refetchOnWindowFocus: false,
    retry: 1,
  });

  const packs = packsQ.data?.packs ?? [];

  const activeSn = packSn || packs[0]?.short_name || "";

  const emojisQ = useQuery({
    queryKey: ["customEmojiPack", activeSn],
    queryFn: () => api.telegramCustomEmoji.packEmojis(activeSn),
    enabled: Boolean(activeSn),
    refetchOnWindowFocus: false,
  });

  const filtered = useMemo(() => {
    const list = emojisQ.data?.emojis ?? [];
    const q = filter.trim().toLowerCase();
    if (!q) return list;
    return list.filter(
      (e: EmojiRow) =>
        String(e.alt || "").toLowerCase().includes(q) ||
        String(e.document_id).includes(q)
    );
  }, [emojisQ.data?.emojis, filter]);

  if (packsQ.isLoading) {
    return <p className="text-xs text-slate-500">Loading your installed emoji packs…</p>;
  }

  if (packsQ.isError) {
    return (
      <p className="text-xs text-amber-300">
        Could not load emoji packs — is the poster Telethon session logged in? Install packs on the same account as{" "}
        <code className="text-slate-400">admin_poster</code>.
      </p>
    );
  }

  if (!packs.length) {
    return (
      <p className="text-xs text-slate-500">
        No custom emoji packs on this account. Install packs in Telegram, then click Refresh.
      </p>
    );
  }

  return (
    <div className="rounded-lg border border-violet-800/50 bg-slate-900/40 p-3 space-y-2">
      <div className="flex flex-wrap gap-2 items-center">
        <h4 className="text-sm font-medium text-violet-100">Your emoji libraries</h4>
        <button
          type="button"
          className="text-[10px] px-2 py-0.5 rounded bg-slate-700 text-white"
          onClick={() => void packsQ.refetch()}
        >
          Refresh packs
        </button>
        <span className="text-[10px] text-slate-500">{packs.length} pack(s)</span>
      </div>
      <div className="flex flex-wrap gap-2">
        <select
          className="flex-1 min-w-[12rem] text-xs bg-slate-950 border border-slate-600 rounded px-2 py-1 text-violet-100"
          value={activeSn}
          onChange={(e) => setPackSn(e.target.value)}
        >
          {packs.map((p: Pack) => (
            <option key={p.short_name} value={p.short_name}>
              {p.title || p.short_name} ({p.count})
            </option>
          ))}
        </select>
        <input
          className="w-32 text-xs bg-slate-950 border border-slate-600 rounded px-2 py-1"
          placeholder="Filter alt…"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
      </div>
      {emojisQ.isLoading ? (
        <p className="text-xs text-slate-500">Loading emojis…</p>
      ) : (
        <div className="max-h-40 overflow-y-auto grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-1">
          {filtered.map((e: EmojiRow) => (
            <button
              key={e.document_id}
              type="button"
              title={`Insert ${e.document_id} · alt: ${e.alt || e.placeholder}`}
              className="text-left text-[10px] px-2 py-1.5 rounded border border-slate-700 hover:border-violet-600 hover:bg-violet-950/40 text-slate-300 truncate"
              onClick={() => onInsert(e.tag)}
              onContextMenu={(ev) => {
                ev.preventDefault();
                void tbccCopyText(e.tag);
              }}
            >
              <span className="text-violet-300 font-mono">{e.placeholder}</span>
              <span className="block text-slate-500 truncate">{e.alt || `#${e.document_id}`}</span>
            </button>
          ))}
        </div>
      )}
      <p className="text-[10px] text-slate-500">
        Click inserts <code className="text-violet-300">&lt;tg-emoji&gt;</code> at end of sketch. Right-click copies tag.
      </p>
    </div>
  );
}
