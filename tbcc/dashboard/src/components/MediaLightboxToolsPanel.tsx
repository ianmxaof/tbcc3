import { useMutation, useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useState } from "react";
import { api } from "../api";

type InsetMode = "all" | "top" | "right" | "bottom" | "left";

type Props = {
  mediaId: number;
  mediaType: string;
  className?: string;
};

function blurRect(side: "top" | "bottom", percent: number) {
  const p = Math.max(1, Math.min(49, percent)) / 100;
  if (side === "top") return { x: 0, y: 0, w: 1, h: p };
  return { x: 0, y: 1 - p, w: 1, h: p };
}

export function MediaLightboxToolsPanel({ mediaId, mediaType, className = "" }: Props) {
  const mt = mediaType.toLowerCase();
  const isPhoto = mt !== "video";

  const [cropEnabled, setCropEnabled] = useState(false);
  const [insetPercent, setInsetPercent] = useState(8);
  const [insetMode, setInsetMode] = useState<InsetMode>("bottom");
  const [blurTop, setBlurTop] = useState(false);
  const [blurTopPct, setBlurTopPct] = useState(6);
  const [blurBottom, setBlurBottom] = useState(false);
  const [blurBottomPct, setBlurBottomPct] = useState(10);
  const [applyWatermark, setApplyWatermark] = useState(true);
  const [stripPrevious, setStripPrevious] = useState(true);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);

  const { data: wmSettings } = useQuery({
    queryKey: ["watermarkSettings"],
    queryFn: () => api.watermarkSettings.get(),
  });
  const effective = (wmSettings?.effective || {}) as Record<string, unknown>;

  useEffect(() => {
    setPreviewUrl(null);
    setPreviewError(null);
  }, [mediaId]);

  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  const buildCropPayload = useCallback(() => {
    if (!isPhoto) return undefined;
    const blurRegions: Array<{ x: number; y: number; w: number; h: number }> = [];
    if (blurTop) blurRegions.push(blurRect("top", blurTopPct));
    if (blurBottom) blurRegions.push(blurRect("bottom", blurBottomPct));
    const enabled = cropEnabled || blurRegions.length > 0;
    if (!enabled) return undefined;
    return {
      enabled: true,
      inset_percent: cropEnabled ? insetPercent : 0,
      inset_mode: insetMode,
      blur_regions: blurRegions,
    };
  }, [blurBottom, blurBottomPct, blurTop, blurTopPct, cropEnabled, insetMode, insetPercent, isPhoto]);

  const preview = useMutation({
    mutationFn: async () => {
      const fileRes = await fetch(api.media.fileUrl(mediaId));
      if (!fileRes.ok) throw new Error("Could not load original file from API");
      const blob = await fileRes.blob();
      const crop = buildCropPayload();
      const wm =
        applyWatermark && effective.enabled !== false
          ? { strip_previous: stripPrevious }
          : { skip: true };
      return api.import.processBytes(blob, {
        mediaType: mt || "photo",
        crop,
        watermark: wm,
        skipWatermark: !applyWatermark,
        filename: `media-${mediaId}.jpg`,
      });
    },
    onSuccess: (blob) => {
      setPreviewError(null);
      setPreviewUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return URL.createObjectURL(blob);
      });
    },
    onError: (e: Error) => setPreviewError(e.message),
  });

  const downloadProcessed = useCallback(() => {
    if (!previewUrl) return;
    const a = document.createElement("a");
    a.href = previewUrl;
    a.download = `tbcc-${mediaId}-processed.${isPhoto ? "jpg" : "mp4"}`;
    a.click();
  }, [isPhoto, mediaId, previewUrl]);

  return (
    <div className={`flex flex-col min-h-0 text-sm ${className}`}>
      <div className="p-3 border-b border-slate-700 shrink-0">
        <h3 className="text-slate-200 font-medium">Crop · blur · watermark</h3>
        <p className="text-xs text-slate-500 mt-1">
          Same pipeline as the extension gallery export. Preview runs on the server; download to save locally. Global
          watermark text comes from{" "}
          <span className="text-slate-400">{String(effective.text || "TBCC_WATERMARK_TEXT")}</span>.
        </p>
      </div>

      <div className="p-3 overflow-y-auto flex-1 min-h-0 space-y-4">
        {isPhoto ? (
          <>
            <section className="space-y-2">
              <p className="text-xs font-medium text-slate-400 uppercase tracking-wide">Crop inset</p>
              <label className="flex items-center gap-2 text-slate-300">
                <input type="checkbox" checked={cropEnabled} onChange={(e) => setCropEnabled(e.target.checked)} />
                Trim edges by percent
              </label>
              {cropEnabled && (
                <div className="flex flex-wrap gap-2 items-center pl-6">
                  <input
                    type="number"
                    min={1}
                    max={49}
                    value={insetPercent}
                    onChange={(e) => setInsetPercent(Number(e.target.value))}
                    className="w-16 bg-slate-800 border border-slate-600 rounded px-2 py-1 text-slate-200"
                  />
                  <span className="text-slate-500 text-xs">%</span>
                  <select
                    value={insetMode}
                    onChange={(e) => setInsetMode(e.target.value as InsetMode)}
                    className="bg-slate-800 border border-slate-600 rounded px-2 py-1 text-slate-200 text-xs"
                  >
                    <option value="all">all sides</option>
                    <option value="top">top</option>
                    <option value="bottom">bottom</option>
                    <option value="left">left</option>
                    <option value="right">right</option>
                  </select>
                </div>
              )}
            </section>

            <section className="space-y-2">
              <p className="text-xs font-medium text-slate-400 uppercase tracking-wide">Blur bands</p>
              <label className="flex items-center gap-2 text-slate-300">
                <input type="checkbox" checked={blurTop} onChange={(e) => setBlurTop(e.target.checked)} />
                Blur top band
                {blurTop && (
                  <input
                    type="number"
                    min={1}
                    max={49}
                    value={blurTopPct}
                    onChange={(e) => setBlurTopPct(Number(e.target.value))}
                    className="w-14 bg-slate-800 border border-slate-600 rounded px-2 py-0.5 text-slate-200 text-xs"
                  />
                )}
                {blurTop && <span className="text-slate-500 text-xs">%</span>}
              </label>
              <label className="flex items-center gap-2 text-slate-300">
                <input type="checkbox" checked={blurBottom} onChange={(e) => setBlurBottom(e.target.checked)} />
                Blur bottom band
                {blurBottom && (
                  <input
                    type="number"
                    min={1}
                    max={49}
                    value={blurBottomPct}
                    onChange={(e) => setBlurBottomPct(Number(e.target.value))}
                    className="w-14 bg-slate-800 border border-slate-600 rounded px-2 py-0.5 text-slate-200 text-xs"
                  />
                )}
                {blurBottom && <span className="text-slate-500 text-xs">%</span>}
              </label>
              <p className="text-xs text-slate-600 pl-6">Use blur bands before re-watermarking over old promo text.</p>
            </section>
          </>
        ) : (
          <p className="text-xs text-slate-500">Video: watermark only (crop/blur apply to photos).</p>
        )}

        <section className="space-y-2">
          <p className="text-xs font-medium text-slate-400 uppercase tracking-wide">Watermark</p>
          <label className="flex items-center gap-2 text-slate-300">
            <input type="checkbox" checked={applyWatermark} onChange={(e) => setApplyWatermark(e.target.checked)} />
            Apply promo watermark
          </label>
          {applyWatermark && isPhoto && (
            <label className="flex items-center gap-2 text-slate-300 pl-6">
              <input type="checkbox" checked={stripPrevious} onChange={(e) => setStripPrevious(e.target.checked)} />
              Blur edge bands before burn-in
            </label>
          )}
        </section>

        {previewError && <p className="text-red-400 text-xs">{previewError}</p>}

        {previewUrl && (
          <div className="rounded border border-slate-600 bg-black/40 p-2">
            <p className="text-xs text-slate-500 mb-2">Processed preview</p>
            {isPhoto ? (
              <img src={previewUrl} alt="Processed preview" className="max-w-full max-h-48 object-contain mx-auto" />
            ) : (
              <video src={previewUrl} controls className="max-w-full max-h-48 mx-auto" playsInline />
            )}
          </div>
        )}
      </div>

      <div className="p-3 border-t border-slate-700 flex flex-wrap gap-2 shrink-0">
        <button
          type="button"
          disabled={preview.isPending}
          onClick={() => preview.mutate()}
          className="px-3 py-1.5 rounded bg-cyan-800 text-cyan-100 text-xs hover:bg-cyan-700 disabled:opacity-50"
        >
          {preview.isPending ? "Processing…" : "Preview"}
        </button>
        <button
          type="button"
          disabled={!previewUrl}
          onClick={downloadProcessed}
          className="px-3 py-1.5 rounded bg-slate-700 text-slate-200 text-xs hover:bg-slate-600 disabled:opacity-40"
        >
          Download processed
        </button>
      </div>
    </div>
  );
}
