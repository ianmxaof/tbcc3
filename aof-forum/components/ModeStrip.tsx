import Link from "next/link";

/**
 * Hub launcher: the four surfaces the operator wants top billing on first paint
 * (Live / Tube / Galleries / Upload), rendered as a strip above the feed rather
 * than a separate "/" mission-control route — see
 * docs/handoffs/2026-08-10_aof-hub-frontier-plan-ask_report.md §2.1.
 */
export function ModeStrip() {
  return (
    <nav className="mode-strip" aria-label="Hub sections">
      <Link href="/live" className="mode-tile live">
        <span className="icon">
          <span className="live-dot" />🔴
        </span>
        <span className="label">Live</span>
        <span className="desc">Cam models, online now</span>
      </Link>
      <Link href="/" className="mode-tile">
        <span className="icon">🎬</span>
        <span className="label">Tube</span>
        <span className="desc">Hot / New / For You</span>
      </Link>
      <Link href="/g" className="mode-tile">
        <span className="icon">🖼</span>
        <span className="label">Galleries</span>
        <span className="desc">Browse curated collections</span>
      </Link>
      <Link href="/connect" className="mode-tile connect">
        <span className="icon">💌</span>
        <span className="label">Connect</span>
        <span className="desc">Snap &amp; Telegram listings</span>
      </Link>
      <Link href="/upload" className="mode-tile">
        <span className="icon">⬆</span>
        <span className="label">Upload</span>
        <span className="desc">Build your own gallery</span>
      </Link>
    </nav>
  );
}
