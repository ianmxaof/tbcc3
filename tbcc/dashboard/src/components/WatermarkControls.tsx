import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useState } from "react";
import { api } from "../api";

type WatermarkEffective = {
  enabled?: boolean;
  text?: string;
  text_secondary?: string;
  text_tertiary?: string;
  opacity?: number;
  color?: string;
  strip_previous?: boolean;
  apply_on_saved_import?: boolean;
  apply_on_album_composer?: boolean;
};

type Props = {
  /** When true, shows the saved-import uptake toggle prominently */
  showSavedImportToggle?: boolean;
  /** Generic per-action apply toggle (channel/storage/upload panels) */
  showApplyToggle?: boolean;
  applyToggleLabel?: string;
  applyChecked?: boolean;
  onApplyToggleChange?: (apply: boolean) => void;
  compact?: boolean;
  onApplyChange?: (applyOnSavedImport: boolean) => void;
};

declare global {
  interface Window {
    EyeDropper?: new () => { open: () => Promise<{ sRGBHex: string }> };
  }
}

export function WatermarkControls({
  showSavedImportToggle = false,
  showApplyToggle = false,
  applyToggleLabel = "Apply on this import (download + re-upload with burn-in)",
  applyChecked = false,
  onApplyToggleChange,
  compact = false,
  onApplyChange,
}: Props) {
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["watermarkSettings"],
    queryFn: () => api.watermarkSettings.get(),
  });

  const effective = (data?.effective || {}) as WatermarkEffective;
  const overrides = (data?.overrides || {}) as Record<string, unknown>;

  const [textPrimary, setTextPrimary] = useState("");
  const [textSecondary, setTextSecondary] = useState("");
  const [textTertiary, setTextTertiary] = useState("");
  const [opacity, setOpacity] = useState(0.58);
  const [color, setColor] = useState("#ffffff");
  const [enabled, setEnabled] = useState(true);
  const [stripPrevious, setStripPrevious] = useState(true);
  const [applyOnSavedImport, setApplyOnSavedImport] = useState(false);
  const [applyOnAlbumComposer, setApplyOnAlbumComposer] = useState(true);
  useEffect(() => {
    if (!data) return;
    setTextPrimary(String(effective.text || overrides.text_primary || ""));
    setTextSecondary(String(effective.text_secondary || overrides.text_secondary || ""));
    setTextTertiary(String(effective.text_tertiary || overrides.text_tertiary || ""));
    setOpacity(Number(effective.opacity ?? overrides.opacity ?? 0.58));
    setColor(String(effective.color || overrides.color || "#ffffff"));
    setEnabled(effective.enabled !== false);
    setStripPrevious(effective.strip_previous === true);
    const savedApply = !!effective.apply_on_saved_import;
    setApplyOnSavedImport(savedApply);
    onApplyChange?.(savedApply);
    setApplyOnAlbumComposer(effective.apply_on_album_composer !== false);
  }, [data]);

  const save = useMutation({
    mutationFn: () =>
      api.watermarkSettings.patch({
        enabled,
        text_primary: textPrimary.trim() || null,
        text_secondary: textSecondary.trim() || null,
        text_tertiary: textTertiary.trim() || null,
        opacity,
        color,
        strip_previous: stripPrevious,
        apply_on_saved_import: applyOnSavedImport,
        apply_on_album_composer: applyOnAlbumComposer,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["watermarkSettings"] });
      onApplyChange?.(applyOnSavedImport);
    },
  });

  const pickScreenColor = useCallback(async () => {
    if (!window.EyeDropper) {
      window.alert("Screen eyedropper needs Chromium (Chrome/Edge). Use the color input instead.");
      return;
    }
    try {
      const dropper = new window.EyeDropper();
      const result = await dropper.open();
      if (result?.sRGBHex) setColor(result.sRGBHex);
    } catch {
      /* user cancelled */
    }
  }, []);

  if (isLoading && !data) {
    return <p className="text-xs text-slate-400">Loading watermark settings…</p>;
  }

  return (
    <div className={`space-y-2 ${compact ? "text-xs" : ""}`}>
      <label className="flex items-center gap-2 text-slate-300">
        <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
        <span>Promo watermark enabled</span>
      </label>

      <div className="grid grid-cols-1 gap-2">
        <label className="block text-slate-400">
          Primary text
          <input
            className="mt-0.5 block w-full bg-slate-900 border border-slate-600 rounded px-2 py-1 text-slate-100"
            value={textPrimary}
            onChange={(e) => setTextPrimary(e.target.value)}
            placeholder="t.me/aofmainhub"
          />
        </label>
        <label className="block text-slate-400">
          Secondary
          <input
            className="mt-0.5 block w-full bg-slate-900 border border-slate-600 rounded px-2 py-1 text-slate-100"
            value={textSecondary}
            onChange={(e) => setTextSecondary(e.target.value)}
          />
        </label>
        <label className="block text-slate-400">
          Tertiary
          <input
            className="mt-0.5 block w-full bg-slate-900 border border-slate-600 rounded px-2 py-1 text-slate-100"
            value={textTertiary}
            onChange={(e) => setTextTertiary(e.target.value)}
          />
        </label>
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <label className="block text-slate-400 min-w-[8rem]">
          Opacity {opacity.toFixed(2)}
          <input
            type="range"
            min={0.15}
            max={1}
            step={0.01}
            value={opacity}
            onChange={(e) => setOpacity(Number(e.target.value))}
            className="mt-1 block w-full"
          />
        </label>
        <label className="block text-slate-400">
          Color
          <div className="mt-0.5 flex items-center gap-2">
            <input
              type="color"
              value={color.startsWith("#") ? color : "#ffffff"}
              onChange={(e) => setColor(e.target.value)}
              className="h-8 w-10 cursor-pointer bg-transparent border-0 p-0"
              title="Pick color"
            />
            <span
              className="inline-block h-8 w-8 rounded border border-slate-500 shrink-0"
              style={{ backgroundColor: color }}
              title={color}
            />
            <input
              className="w-24 bg-slate-900 border border-slate-600 rounded px-2 py-1 text-slate-100 font-mono text-xs"
              value={color}
              onChange={(e) => setColor(e.target.value)}
            />
            <button
              type="button"
              onClick={() => void pickScreenColor()}
              className="px-2 py-1 rounded bg-slate-700 text-slate-100 text-xs hover:bg-slate-600"
              title="Pick color from anywhere on screen (Chromium)"
            >
              Eyedropper
            </button>
          </div>
        </label>
      </div>

      <label className="flex items-center gap-2 text-slate-300">
        <input type="checkbox" checked={stripPrevious} onChange={(e) => setStripPrevious(e.target.checked)} />
        <span>
          Blur edge bands before watermarking (optional — top 6%, bottom 10%, corners; for re-burning over old promo text)
        </span>
      </label>

      {showSavedImportToggle && (
        <label className="flex items-center gap-2 text-amber-200/90">
          <input
            type="checkbox"
            checked={applyOnSavedImport}
            onChange={(e) => {
              setApplyOnSavedImport(e.target.checked);
              onApplyChange?.(e.target.checked);
            }}
          />
          <span>Apply on <strong>Import from Saved</strong> (re-upload watermarked copy into pool)</span>
        </label>
      )}

      {showApplyToggle && !showSavedImportToggle && (
        <label className="flex items-center gap-2 text-amber-200/90">
          <input
            type="checkbox"
            checked={applyChecked}
            onChange={(e) => onApplyToggleChange?.(e.target.checked)}
          />
          <span>{applyToggleLabel}</span>
        </label>
      )}

      {!compact && (
        <label className="flex items-center gap-2 text-slate-300">
          <input
            type="checkbox"
            checked={applyOnAlbumComposer}
            onChange={(e) => setApplyOnAlbumComposer(e.target.checked)}
          />
          <span>Apply on Album Composer bot sends</span>
        </label>
      )}

      <button
        type="button"
        onClick={() => save.mutate()}
        disabled={save.isPending}
        className="px-3 py-1.5 rounded bg-cyan-700/90 text-white text-sm hover:bg-cyan-600 disabled:opacity-50"
      >
        {save.isPending ? "Saving…" : "Save watermark settings"}
      </button>
      {save.isError && <p className="text-red-400 text-xs">{(save.error as Error).message}</p>}
      {save.isSuccess && <p className="text-green-400 text-xs">Watermark settings saved.</p>}
    </div>
  );
}
