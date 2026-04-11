import { useMutation } from "@tanstack/react-query";
import type { Dispatch, SetStateAction } from "react";
import { api } from "../api";

const MAX = 10;

/**
 * Bot Shop–style URL rows + per-slot file upload. Uses POST /subscription-plans/upload-promo-image
 * (normalized images under /static/promo/…). Stored on scheduled posts as attachment_urls, not Media Library.
 */
export function SchedulePromoSlots({
  urls,
  setUrls,
  idPrefix,
}: {
  urls: string[];
  setUrls: Dispatch<SetStateAction<string[]>>;
  /** Prefix for stable input ids when multiple instances exist */
  idPrefix: string;
}) {
  const uploadPromo = useMutation({
    mutationFn: async ({ file, slotIndex }: { file: File; slotIndex: number }) => {
      const data = await api.subscriptionPlans.uploadPromoImage(file);
      return { ...data, slotIndex };
    },
    onSuccess: (data) => {
      setUrls((prev) => {
        const n = [...prev];
        while (n.length <= data.slotIndex) n.push("");
        n[data.slotIndex] = data.url;
        return n;
      });
    },
  });

  return (
    <div className="border border-slate-600 rounded p-2 space-y-1.5 bg-slate-900/40">
      <p
        className="text-slate-500 text-[11px] leading-snug"
        title="Same upload as Bot Shop: files stored under /static/promo/ on this server. They do not appear in the Media Library. If you also set pool picks or explicit library selections for this caption, those are sent first; promo fills in when those are empty."
      >
        Local promo → <code className="text-slate-400">/static/promo/</code> (not Media Library). Pool/picks override when
        present.
      </p>
      <div className="space-y-2">
        {urls.map((url, i) => (
          <div key={`${idPrefix}-slot-${i}`} className="flex flex-col gap-1 sm:flex-row sm:items-center">
            <input
              type="text"
              value={url}
              onChange={(e) => {
                const v = e.target.value;
                setUrls((prev) => prev.map((u, j) => (j === i ? v : u)));
              }}
              placeholder="https://… or upload below"
              className="w-full flex-1 bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200 text-sm"
            />
            <input
              type="file"
              accept="image/*"
              id={`${idPrefix}-file-${i}`}
              className="hidden"
              disabled={uploadPromo.isPending}
              onChange={(e) => {
                const input = e.currentTarget;
                const f = input.files?.[0];
                input.value = "";
                if (f) uploadPromo.mutate({ file: f, slotIndex: i });
              }}
            />
            <div className="flex flex-wrap gap-2 shrink-0">
              <label
                htmlFor={`${idPrefix}-file-${i}`}
                className={`inline-flex items-center justify-center px-3 py-2 bg-slate-600 text-white rounded hover:bg-slate-500 text-sm ${
                  uploadPromo.isPending ? "pointer-events-none opacity-50" : "cursor-pointer"
                }`}
              >
                {uploadPromo.isPending ? "Uploading…" : "Upload"}
              </label>
              <button
                type="button"
                onClick={() => setUrls((prev) => prev.filter((_, j) => j !== i))}
                className="text-sm text-red-300 hover:text-red-200 px-2 py-1"
              >
                Remove
              </button>
            </div>
          </div>
        ))}
        {urls.length < MAX && (
          <button
            type="button"
            onClick={() => setUrls((prev) => [...prev, ""])}
            className="text-sm text-cyan-400 hover:underline"
          >
            + Add URL slot
          </button>
        )}
      </div>
      {uploadPromo.isError && (
        <p className="text-red-400 text-xs">{String((uploadPromo.error as Error)?.message ?? "")}</p>
      )}
    </div>
  );
}
