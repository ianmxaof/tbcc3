import { useEffect, useRef, useState, type ReactNode } from "react";
import { api } from "../api";

/**
 * Loads preview bytes via fetch (same path as <img src> but reliable through Vite /api proxy)
 * and shows a numeric fallback if the request fails (instead of an empty box).
 * Thumbnails load only when the cell is near the viewport so bulk approve is not starved by
 * many parallel Telegram downloads + SQLite contention.
 */
export function MediaThumbnailCell({
  mediaId,
  mediaType,
  className,
}: {
  mediaId: number;
  mediaType: string;
  className?: string;
}) {
  const rootRef = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const [phase, setPhase] = useState<"idle" | "loading" | "ok" | "fail">("idle");
  const revokeRef = useRef<string | null>(null);

  useEffect(() => {
    const el = rootRef.current;
    if (!el) return;
    if (typeof IntersectionObserver === "undefined") {
      setVisible(true);
      return;
    }
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setVisible(true);
        }
      },
      { root: null, rootMargin: "80px", threshold: 0 }
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  useEffect(() => {
    if (!visible) return;
    let cancelled = false;
    const ac = new AbortController();
    setPhase("loading");
    setObjectUrl(null);
    if (revokeRef.current) {
      URL.revokeObjectURL(revokeRef.current);
      revokeRef.current = null;
    }

    (async () => {
      try {
        const res = await fetch(api.media.thumbnailUrl(mediaId), { signal: ac.signal });
        if (!res.ok) throw new Error(String(res.status));
        const blob = await res.blob();
        const u = URL.createObjectURL(blob);
        if (cancelled) {
          URL.revokeObjectURL(u);
          return;
        }
        revokeRef.current = u;
        setObjectUrl(u);
        setPhase("ok");
      } catch {
        if (!cancelled) setPhase("fail");
      }
    })();

    return () => {
      cancelled = true;
      ac.abort();
      if (revokeRef.current) {
        URL.revokeObjectURL(revokeRef.current);
        revokeRef.current = null;
      }
    };
  }, [visible, mediaId]);

  const mediaClass = className ?? "";
  const outer = `flex w-full h-full min-h-0 items-center justify-center bg-slate-800 text-slate-500 text-[10px] leading-tight text-center ${
    phase === "ok" && objectUrl ? "p-0 overflow-hidden" : "p-0.5"
  }`;

  let inner: ReactNode;
  if (!visible) {
    inner = (
      <span className="text-slate-600" title="Scroll into view to load preview">
        ·
      </span>
    );
  } else if (phase === "fail") {
    inner = (
      <span title="Preview failed — check API / Telegram session">#{mediaId}</span>
    );
  } else if (phase === "loading" || !objectUrl) {
    inner = (
      <span className="animate-pulse text-slate-600" title="Loading preview…">
        …
      </span>
    );
  } else {
    const mt = String(mediaType || "").toLowerCase();
    if (mt === "video") {
      inner = (
        <video
          src={objectUrl}
          className={mediaClass}
          muted
          playsInline
          preload="metadata"
          title={`Video #${mediaId}`}
        />
      );
    } else {
      inner = <img src={objectUrl} alt="" className={mediaClass} loading="lazy" decoding="async" />;
    }
  }

  return (
    <div ref={rootRef} className={outer}>
      {inner}
    </div>
  );
}
