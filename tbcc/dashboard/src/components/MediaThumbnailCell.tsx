import { useEffect, useRef, useState, type ReactNode } from "react";
import { api } from "../api";

/** Limit parallel thumbnail fetches so /media list + bulk approve are not starved. */
const THUMB_MAX_PARALLEL = 2;
let thumbActive = 0;
const thumbWaiters: Array<() => void> = [];

async function withThumbnailSlot<T>(fn: () => Promise<T>): Promise<T> {
  while (thumbActive >= THUMB_MAX_PARALLEL) {
    await new Promise<void>((resolve) => thumbWaiters.push(resolve));
  }
  thumbActive += 1;
  try {
    return await fn();
  } finally {
    thumbActive -= 1;
    const next = thumbWaiters.shift();
    if (next) next();
  }
}

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
  disableFetch = false,
}: {
  mediaId: number;
  mediaType: string;
  className?: string;
  disableFetch?: boolean;
}) {
  const rootRef = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const [phase, setPhase] = useState<"idle" | "loading" | "ok" | "fail">("idle");
  const revokeRef = useRef<string | null>(null);

  useEffect(() => {
    if (disableFetch) return;
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
  }, [disableFetch]);

  useEffect(() => {
    if (disableFetch) {
      setPhase("idle");
      setObjectUrl(null);
      if (revokeRef.current) {
        URL.revokeObjectURL(revokeRef.current);
        revokeRef.current = null;
      }
      return;
    }
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
      // The backend returns 503 + Retry-After while the Telegram session is busy (transient,
      // not a real failure). Back off and retry a few times — releasing the throttle slot
      // between attempts — so a busy moment doesn't leave a permanent "#id" placeholder.
      const MAX_ATTEMPTS = 4;
      const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));
      for (let attempt = 0; attempt < MAX_ATTEMPTS; attempt += 1) {
        try {
          const res = await withThumbnailSlot(() =>
            fetch(api.media.thumbnailUrl(mediaId), { signal: ac.signal })
          );
          if (res.status === 503 && attempt + 1 < MAX_ATTEMPTS) {
            const ra = Number(res.headers.get("Retry-After"));
            const delayMs = Math.min(15000, (Number.isFinite(ra) && ra > 0 ? ra : 5) * 1000);
            await sleep(delayMs);
            if (cancelled || ac.signal.aborted) return;
            continue;
          }
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
          return;
        } catch {
          if (cancelled || ac.signal.aborted) return;
          if (attempt + 1 >= MAX_ATTEMPTS) {
            setPhase("fail");
            return;
          }
          await sleep(1500);
          if (cancelled || ac.signal.aborted) return;
        }
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
  }, [visible, mediaId, disableFetch]);

  const mediaClass = className ?? "";
  const outer = `relative flex w-full h-full min-h-0 items-center justify-center bg-slate-800 text-slate-500 text-[10px] leading-tight text-center ${
    phase === "ok" && objectUrl ? "p-0 overflow-hidden" : "p-0.5"
  }`;

  let inner: ReactNode;
  if (disableFetch) {
    inner = (
      <span className="text-slate-400" title="Fast rebuild mode: thumbnail fetch disabled">
        #{mediaId}
      </span>
    );
  } else if (!visible) {
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
    // The thumbnail endpoint returns a JPEG poster frame for video too, so always render
    // an <img> (a JPEG fed to <video src> never paints). Full playback is in the lightbox.
    const isVideo = String(mediaType || "").toLowerCase() === "video";
    inner = (
      <>
        <img src={objectUrl} alt="" className={mediaClass} loading="lazy" decoding="async" />
        {isVideo && (
          <span
            className="absolute bottom-1 right-1 rounded bg-black/60 px-1 text-[10px] leading-none text-white"
            title={`Video #${mediaId}`}
          >
            ▶
          </span>
        )}
      </>
    );
  }

  return (
    <div ref={rootRef} className={outer}>
      {inner}
    </div>
  );
}
