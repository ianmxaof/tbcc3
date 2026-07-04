import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";

/** Header-level promo watermark on/off — persists via PATCH /watermark-settings. */
export function WatermarkGlobalToggle() {
  const queryClient = useQueryClient();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["watermarkSettings"],
    queryFn: () => api.watermarkSettings.get(),
    staleTime: 30_000,
  });

  const effective = (data?.effective || {}) as { enabled?: boolean; text?: string };
  const enabled = effective.enabled !== false;

  const toggle = useMutation({
    mutationFn: (next: boolean) => api.watermarkSettings.patch({ enabled: next }),
    onMutate: async (next) => {
      await queryClient.cancelQueries({ queryKey: ["watermarkSettings"] });
      const prev = queryClient.getQueryData(["watermarkSettings"]);
      queryClient.setQueryData(["watermarkSettings"], (old: typeof data) => {
        if (!old || typeof old !== "object") return old;
        const eff = { ...(old.effective as Record<string, unknown>), enabled: next };
        return { ...old, effective: eff };
      });
      return { prev };
    },
    onError: (_err, _next, ctx) => {
      if (ctx?.prev) queryClient.setQueryData(["watermarkSettings"], ctx.prev);
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: ["watermarkSettings"] });
    },
  });

  const busy = isLoading || toggle.isPending;
  const label = enabled ? "On" : "Off";

  return (
    <div
      className="flex items-center gap-2 mr-1"
      title={
        enabled
          ? `Promo watermark active${effective.text ? ` (${effective.text})` : ""}`
          : "Promo watermark disabled globally"
      }
    >
      <span className="text-[10px] uppercase tracking-wide text-slate-500 hidden sm:inline">Watermark</span>
      <button
        type="button"
        role="switch"
        aria-checked={enabled}
        aria-label={`Promo watermark ${label}`}
        disabled={busy || isError}
        onClick={() => toggle.mutate(!enabled)}
        className={[
          "relative inline-flex h-6 w-[3.25rem] shrink-0 items-center rounded-full border transition-colors",
          "focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500/70",
          enabled
            ? "border-emerald-500/60 bg-emerald-700/50"
            : "border-slate-600 bg-slate-800/80",
          busy || isError ? "opacity-50 cursor-not-allowed" : "cursor-pointer hover:border-slate-500",
        ].join(" ")}
      >
        <span
          className={[
            "pointer-events-none inline-block h-4 w-4 rounded-full bg-white shadow transition-transform",
            enabled ? "translate-x-[1.65rem]" : "translate-x-1",
          ].join(" ")}
        />
        <span
          className={[
            "pointer-events-none absolute text-[9px] font-semibold uppercase",
            enabled ? "left-1.5 text-emerald-100" : "right-1 text-slate-400",
          ].join(" ")}
        >
          {busy ? "…" : label}
        </span>
      </button>
    </div>
  );
}
