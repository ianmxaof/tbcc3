import { Link } from "react-router-dom";
import { EMOJI_PACK_VS_CAPTION_NOTE } from "../lib/emojiFactoryWorkflow";

type Variant = "banner" | "inline";

export function EmojiPackWayfinding({ variant = "banner" }: { variant?: Variant }) {
  if (variant === "inline") {
    return (
      <span className="text-xs text-slate-500">
        Building a split-grid pack?{" "}
        <Link to="/misc/emoji" className="text-cyan-400 hover:underline">
          Emoji packs workflow
        </Link>
        . {EMOJI_PACK_VS_CAPTION_NOTE}
      </span>
    );
  }

  return (
    <div className="rounded-lg border border-cyan-800/50 bg-cyan-950/25 px-4 py-3 mb-6 flex flex-col sm:flex-row sm:items-center gap-3">
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-cyan-100">Split-grid emoji packs</p>
        <p className="text-xs text-slate-400 mt-1 leading-relaxed">
          Design → export → factory → upload. Step-by-step checklist and gates.{" "}
          <span className="text-slate-500">{EMOJI_PACK_VS_CAPTION_NOTE}</span>
        </p>
      </div>
      <Link
        to="/misc/emoji"
        className="shrink-0 px-3 py-2 rounded bg-cyan-700 hover:bg-cyan-600 text-white text-sm font-medium text-center"
      >
        Open pack workflow
      </Link>
    </div>
  );
}
