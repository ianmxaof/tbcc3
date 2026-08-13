"use client";

import { useEffect, useState } from "react";
import { usePathname, useSearchParams } from "next/navigation";

/**
 * Thin top accent bar during client navigations so transitions feel instant
 * even while a route segment is still streaming.
 */
export function NavProgress() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [active, setActive] = useState(false);

  useEffect(() => {
    setActive(true);
    const t = window.setTimeout(() => setActive(false), 400);
    return () => window.clearTimeout(t);
  }, [pathname, searchParams]);

  return <div className={`nav-progress${active ? " is-active" : ""}`} aria-hidden />;
}
