import { useEffect, useRef, useState } from "react";
import { api } from "../api";

export type GalleryMediaItem = { id: number; media_type?: string };

type Props = {
  items: GalleryMediaItem[];
  openIndex: number | null;
  onClose: () => void;
  onIndexChange: (index: number) => void;
};

export function MediaGalleryModal({ items, openIndex, onClose, onIndexChange }: Props) {
  const [zoom, setZoom] = useState(1);
  const [mediaLoadError, setMediaLoadError] = useState<string | null>(null);
  const overlayRef = useRef<HTMLDivElement>(null);
  const fsWrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (openIndex != null) setZoom(1);
  }, [openIndex]);

  useEffect(() => {
    if (openIndex == null) return;
    const k = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowLeft") onIndexChange(Math.max(0, openIndex - 1));
      if (e.key === "ArrowRight") onIndexChange(Math.min(items.length - 1, openIndex + 1));
    };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [openIndex, items.length, onClose, onIndexChange]);

  useEffect(() => {
    const el = overlayRef.current;
    if (!el || openIndex == null) return;
    const wheel = (e: WheelEvent) => {
      if (e.ctrlKey) {
        e.preventDefault();
        setZoom((z) => Math.min(8, Math.max(0.25, z - e.deltaY * 0.002)));
      } else {
        e.preventDefault();
        if (e.deltaY > 0) onIndexChange(Math.min(items.length - 1, openIndex + 1));
        else onIndexChange(Math.max(0, openIndex - 1));
      }
    };
    el.addEventListener("wheel", wheel, { passive: false });
    return () => el.removeEventListener("wheel", wheel);
  }, [openIndex, items.length, onIndexChange]);

  const current = openIndex != null && items.length > 0 ? items[openIndex] : null;
  const currentId = current ? current.id : null;
  useEffect(() => {
    setMediaLoadError(null);
  }, [currentId]);
  if (!current || openIndex == null || items.length === 0) return null;

  const fileUrl = api.media.fileUrl(current.id);
  const mt = String(current.media_type || "").toLowerCase();
  const isVideo = mt === "video";

  const toggleFullscreen = () => {
    const el = fsWrapRef.current;
    if (!el) return;
    if (document.fullscreenElement) void document.exitFullscreen();
    else void el.requestFullscreen?.();
  };

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-[200] flex flex-col bg-black/90"
      role="dialog"
      aria-modal="true"
      aria-label="Media viewer"
      onClick={(e) => {
        if (e.target === overlayRef.current) onClose();
      }}
    >
      <div className="flex items-center justify-between gap-2 px-3 py-2 bg-slate-900/90 border-b border-slate-700 text-slate-200 text-sm shrink-0">
        <span>
          {openIndex + 1} / {items.length} · ID {current.id} · {current.media_type || "—"}
        </span>
        <div className="flex flex-wrap gap-2 items-center">
          <button
            type="button"
            className="px-2 py-1 rounded bg-slate-700 hover:bg-slate-600 text-xs"
            onClick={() => onIndexChange(Math.max(0, openIndex - 1))}
            disabled={openIndex <= 0}
          >
            ← Prev
          </button>
          <button
            type="button"
            className="px-2 py-1 rounded bg-slate-700 hover:bg-slate-600 text-xs"
            onClick={() => onIndexChange(Math.min(items.length - 1, openIndex + 1))}
            disabled={openIndex >= items.length - 1}
          >
            Next →
          </button>
          <button type="button" className="px-2 py-1 rounded bg-slate-700 hover:bg-slate-600 text-xs" onClick={() => setZoom(1)}>
            Reset zoom
          </button>
          <button type="button" className="px-2 py-1 rounded bg-slate-700 hover:bg-slate-600 text-xs" onClick={toggleFullscreen}>
            Full screen
          </button>
          <button type="button" className="px-2 py-1 rounded bg-red-900/80 hover:bg-red-800 text-xs" onClick={onClose}>
            Close (Esc)
          </button>
        </div>
      </div>
      <div ref={fsWrapRef} className="flex-1 min-h-0 flex items-center justify-center overflow-auto p-4" onClick={(e) => e.stopPropagation()}>
        <div
          className="max-w-full max-h-full flex items-center justify-center"
          style={{
            transform: `scale(${zoom})`,
            transformOrigin: "center center",
          }}
        >
          {isVideo ? (
            <video
              key={`video-${current.id}`}
              src={fileUrl}
              controls
              className="max-w-[min(100vw,96rem)] max-h-[85vh] rounded shadow-lg"
              playsInline
              onError={() => setMediaLoadError("Video failed to load from API")}
            />
          ) : (
            <img
              key={`img-${current.id}`}
              src={fileUrl}
              alt=""
              className="max-w-[min(100vw,96rem)] max-h-[85vh] object-contain rounded shadow-lg select-none"
              draggable={false}
              onError={() => setMediaLoadError("Image failed to load from API")}
            />
          )}
          {mediaLoadError ? (
            <div className="mt-3 text-xs text-red-300 bg-red-950/40 border border-red-800 rounded px-3 py-2">
              {mediaLoadError}. Open <a className="underline" href={fileUrl} target="_blank" rel="noreferrer">raw file</a>.
            </div>
          ) : null}
        </div>
      </div>
      <p className="text-center text-slate-500 text-xs py-2 shrink-0 bg-slate-900/80">
        Wheel: previous / next · Ctrl+wheel: zoom · ← → keys · Click backdrop to close
      </p>
    </div>
  );
}

export function canPreviewInGallery(m: Record<string, unknown>): boolean {
  const t = String(m.media_type || "").toLowerCase();
  return t === "photo" || t === "video" || t === "gif" || t === "document";
}
