import { CaptionSnippetLibraryManageButton } from "./CaptionSnippetLibrary";
import { CustomEmojiLibraryManageButton } from "./CustomEmojiLibrary";
import { Link } from "react-router-dom";

/** Compact manage-only controls — pair with {@link TbccInsertMenu} for insertion. */
export function TbccInsertLibraryToolbar({ className }: { className?: string }) {
  return (
    <div className={`flex flex-wrap items-center gap-2 justify-end ${className ?? ""}`}>
      <Link
        to="/misc#promo-affiliate-links"
        className="text-xs text-cyan-400 hover:text-cyan-300 whitespace-nowrap px-2 py-0.5 rounded border border-slate-600/80 hover:bg-slate-700/50"
        title="Import and edit promo affiliate links (Misc → Promo affiliate links)"
      >
        Promo links…
      </Link>
      <CaptionSnippetLibraryManageButton />
      <CustomEmojiLibraryManageButton />
    </div>
  );
}
