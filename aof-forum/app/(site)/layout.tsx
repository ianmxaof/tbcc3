import { Suspense } from "react";
import { TopBar } from "@/components/TopBar";
import { LeftNav } from "@/components/LeftNav";
import { NavProgress } from "@/components/NavProgress";
import { LeftNavSkeleton, MainPaneSkeleton, TopBarSkeleton } from "@/components/ShellSkeletons";

/**
 * Instant-nav doctrine (foundation):
 * - Chrome (topbar / leftnav / main grid) must paint immediately; wrap auth/data
 *   fetches in Suspense — never block the shell on page data.
 * - Route segments use `loading.tsx` for soft main-pane swaps.
 * - Prefer streaming over waiting; keep `force-dynamic` only when cookie/auth
 *   truth requires it — do not add it by default on new pages.
 */
export default function SiteLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="app-shell">
      <Suspense fallback={null}>
        <NavProgress />
      </Suspense>
      <Suspense fallback={<TopBarSkeleton />}>
        <TopBar />
      </Suspense>
      <Suspense fallback={<LeftNavSkeleton />}>
        <LeftNav />
      </Suspense>
      <main className="main">
        <Suspense fallback={<MainPaneSkeleton />}>{children}</Suspense>
      </main>
    </div>
  );
}
