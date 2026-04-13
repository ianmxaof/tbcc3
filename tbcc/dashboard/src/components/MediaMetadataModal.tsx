import { useEffect } from "react";
import { MediaItemEditorPanel } from "./MediaItemEditorPanel";

function useEscapeClose(onClose: () => void, enabled: boolean) {
  useEffect(() => {
    if (!enabled) return;
    const k = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [enabled, onClose]);
}

type Props = {
  mediaId: number | null;
  onClose: () => void;
};

export function MediaMetadataModal({ mediaId, onClose }: Props) {
  useEscapeClose(onClose, mediaId != null);
  if (mediaId == null) return null;

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 p-4 overflow-y-auto"
      role="dialog"
      aria-modal="true"
      aria-labelledby="media-meta-title"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className="bg-slate-800 border border-slate-600 rounded-lg shadow-xl w-full max-w-lg max-h-[min(90vh,800px)] flex flex-col my-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-2 p-4 border-b border-slate-600 shrink-0">
          <h2 id="media-meta-title" className="text-lg font-medium text-slate-100">
            Media metadata
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="text-slate-400 hover:text-slate-200 px-2 py-1 rounded text-sm"
          >
            Close
          </button>
        </div>
        <MediaItemEditorPanel mediaId={mediaId} showPreviewThumb onCancel={onClose} className="flex-1 min-h-0" />
      </div>
    </div>
  );
}
