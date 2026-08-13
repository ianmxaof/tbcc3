/** Stable placeholders so Suspense chrome does not shift layout. */
export function TopBarSkeleton() {
  return (
    <header className="topbar topbar-skeleton" aria-hidden>
      <span className="brand">AOF Hub</span>
      <div className="search skeleton-bar" />
      <div className="spacer" />
      <nav className="actions skeleton-actions">
        <span className="skeleton-chip" />
        <span className="skeleton-chip" />
        <span className="skeleton-chip" />
      </nav>
    </header>
  );
}

export function LeftNavSkeleton() {
  return (
    <aside className="leftnav leftnav-skeleton" aria-hidden>
      <h4>Browse</h4>
      <div className="skeleton-nav-line" />
      <div className="skeleton-nav-line" />
      <div className="skeleton-nav-line" />
      <div className="skeleton-nav-line" />
      <h4>You</h4>
      <div className="skeleton-nav-line" />
    </aside>
  );
}

export function MainPaneSkeleton() {
  return (
    <div className="main-skeleton" aria-busy="true" aria-label="Loading">
      <div className="skeleton-title" />
      <div className="skeleton-grid">
        <div className="skeleton-card" />
        <div className="skeleton-card" />
        <div className="skeleton-card" />
        <div className="skeleton-card" />
        <div className="skeleton-card" />
        <div className="skeleton-card" />
      </div>
    </div>
  );
}
