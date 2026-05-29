import { Link } from "react-router-dom";
import { EmojiFactoryMaker } from "./EmojiFactoryMaker";
import { EmojiFactorySketchbook } from "./EmojiFactorySketchbook";

export function EmojiFactoryExpress() {
  return (
    <div className="space-y-6">
      <EmojiFactoryMaker variant="express" />
      <p className="text-xs text-slate-500 max-w-3xl">
        After a successful run, open <strong className="text-slate-400">Saved Messages</strong> — one message shows your
        full grid. Tap any emoji → <strong className="text-slate-400">Add emoji</strong>. For caption banners, use{" "}
        <Link to="/misc#caption-emoji-banners" className="text-violet-400 hover:underline">
          Misc → Caption banners
        </Link>{" "}
        or the{" "}
        <Link to="/misc/emoji#stage-1" className="text-violet-400 hover:underline">
          design sketchbook
        </Link>{" "}
        below.
      </p>
      <EmojiFactorySketchbook />
    </div>
  );
}
