import { useMutation } from "@tanstack/react-query";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import { importMacroOptions, type ImportMacroTarget } from "../utils/customEmojiExtract";

type SavedMsg = {
  message_id: number;
  preview: string;
  has_custom_emoji: boolean;
};

const MACRO_BUTTONS: { target: ImportMacroTarget; label: string; title: string; className: string }[] = [
  {
    target: "both",
    label: "→ Library + Sketch",
    title: "Extract full message → Emoji library + new sketchbook page",
    className: "bg-emerald-800 hover:bg-emerald-700",
  },
  {
    target: "library",
    label: "→ Library",
    title: "Extract → Emoji library (Scheduler picker)",
    className: "bg-violet-800 hover:bg-violet-700",
  },
  {
    target: "sketchbook",
    label: "→ Sketch",
    title: "Extract → new sketchbook page only",
    className: "bg-cyan-900 hover:bg-cyan-800",
  },
];

export function SavedMessagesImportMacros({
  messages,
  onSketchbookImported,
  compact,
}: {
  messages: SavedMsg[];
  onSketchbookImported?: () => void;
  compact?: boolean;
}) {
  const qc = useQueryClient();
  const macroMut = useMutation({
    mutationFn: (args: { messageId: number; target: ImportMacroTarget; preview: string }) => {
      const opts = importMacroOptions(args.target);
      return api.telegramCustomEmoji.importMacro({
        peer: "me",
        message_id: args.messageId,
        title: args.preview.slice(0, 80) || `Saved #${args.messageId}`,
        layout: "full",
        ...opts,
      });
    },
    onSuccess: (data) => {
      void qc.invalidateQueries({ queryKey: ["customEmojiPresets"] });
      if (data.sketch_page_id != null) {
        void qc.invalidateQueries({ queryKey: ["emojiFactorySketchbook"] });
        onSketchbookImported?.();
      }
    },
  });

  if (!messages.length) return null;

  return (
    <ul className={`overflow-y-auto border border-slate-700 rounded text-xs ${compact ? "max-h-36" : "max-h-48"}`}>
      {messages.map((m) => (
        <li key={m.message_id} className="border-b border-slate-800/80 last:border-0 px-2 py-2">
          <div className="flex flex-wrap items-center gap-1 mb-1">
            <span className="text-violet-300 font-mono">#{m.message_id}</span>
            {m.has_custom_emoji ? <span className="text-emerald-400 text-[10px]">custom emoji</span> : null}
          </div>
          <p className="text-slate-500 truncate mb-1.5">{m.preview}</p>
          <div className="flex flex-wrap gap-1">
            {MACRO_BUTTONS.map((b) => (
              <button
                key={b.target}
                type="button"
                title={b.title}
                disabled={macroMut.isPending}
                onClick={() =>
                  macroMut.mutate({
                    messageId: m.message_id,
                    target: b.target,
                    preview: m.preview,
                  })
                }
                className={`px-1.5 py-0.5 rounded text-[10px] text-white disabled:opacity-50 ${b.className}`}
              >
                {macroMut.isPending ? "…" : b.label}
              </button>
            ))}
          </div>
        </li>
      ))}
    </ul>
  );
}
