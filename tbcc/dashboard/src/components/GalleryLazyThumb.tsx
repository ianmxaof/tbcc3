import { useEffect, useRef, useState } from "react";
import { api } from "../api";

/** Gallery-only throttle — one at a time so curation never starves the API. */
const GALLERY_THUMB_MAX_PARALLEL = 1;
let galleryThumbActive = 0;
const galleryThumbWaiters: Array<() => void> = [];

async function withGalleryThumbSlot<T>(fn: () => Promise<T>): Promise<T> {
  while (galleryThumbActive >= GALLERY_THUMB_MAX_PARALLEL) {
    await new Promise<void>((resolve) => galleryThumbWaiters.push(resolve));
  }
  galleryThumbActive += 1;
  try {
    return await fn();
  } finally {
    galleryThumbActive -= 1;
    const next = galleryThumbWaiters.shift();
    if (next) next();
  }
}

type Phase = "idle" | "loading" | "ok" | "uncached" | "fail";

const POLL_MS = 2000;
const MAX_POLLS = 30;

/**
 * Lazy thumbnail for pool Curate — disk cache only; polls while Celery warms on the telegram worker.
 */
export function GalleryLazyThumb({
  mediaId,
  mediaType,
  className,
  onOpen,
  fit = "contain",
}: {
  mediaId: number;
  mediaType: string;
  className?: string;
  onOpen?: () => void;
  fit?: "contain" | "cover";
}) {
  const rootRef = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const [phase, setPhase] = useState<Phase>("idle");
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
        if (entries.some((e) => e.isIntersecting)) setVisible(true);
      },
      { root: null, rootMargin: "80px 0px", threshold: 0 }
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

    const tryUrl = async (url: string): Promise<Response> =>
      withGalleryThumbSlot(() => fetch(url, { signal: ac.signal }));

    const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

    (async () => {
      const cacheUrl = api.media.thumbnailUrl(mediaId, { cacheOnly: true });
      for (let poll = 0; poll <= MAX_POLLS; poll += 1) {
        try {
          const res = await tryUrl(cacheUrl);
          if (res.ok) {
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
          }
          if (res.status === 404 && poll < MAX_POLLS) {
            setPhase(poll === 0 ? "loading" : "uncached");
            await sleep(POLL_MS);
            if (cancelled || ac.signal.aborted) return;
            continue;
          }
          if (!res.ok) throw new Error(String(res.status));
        } catch {
          if (cancelled || ac.signal.aborted) return;
          if (poll >= MAX_POLLS) break;
          await sleep(POLL_MS);
        }
      }
      if (!cancelled) setPhase("uncached");
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

  const isVideo = String(mediaType || "").toLowerCase() === "video";

  return (
    <div
      ref={rootRef}
      className={`relative flex w-full items-center justify-center bg-slate-900 text-slate-500 ${className ?? ""}`}
      onClick={onOpen}
      role={onOpen ? "button" : undefined}
      tabIndex={onOpen ? 0 : undefined}
      onKeyDown={
        onOpen
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onOpen();
              }
            }
          : undefined
      }
    >
      {phase === "ok" && objectUrl ? (
        <>
          <img
            src={objectUrl}
            alt=""
            className={`w-full h-full ${fit === "cover" ? "object-cover" : "h-auto max-h-[85vh] object-contain"}`}
            loading="lazy"
            decoding="async"
            draggable={false}
          />
          {isVideo && (
            <span className="absolute bottom-2 right-2 rounded bg-black/70 px-2 py-0.5 text-xs text-white">
              ▶ video
            </span>
          )}
        </>
      ) : phase === "loading" ? (
        <span className="animate-pulse text-slate-600 text-sm py-24">Loading…</span>
      ) : phase === "uncached" ? (
        <span className="text-slate-500 text-sm text-center px-4 py-8" title="Preview still warming — try Refresh in a moment">
          #{mediaId} — warming…
        </span>
      ) : phase === "fail" ? (
        <span className="text-slate-500 text-sm py-16">#{mediaId} — preview failed</span>
      ) : (
        <span className="text-slate-700 text-sm py-8">·</span>
      )}
    </div>
  );
}
