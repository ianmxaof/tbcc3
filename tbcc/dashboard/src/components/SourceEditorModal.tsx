import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import { CronScheduleBuilder } from "./CronScheduleBuilder";
import { ScraperTelegramAuth } from "./ScraperTelegramAuth";
import { buildCronFromState, defaultScheduleState, parseCronToState } from "../utils/cronSchedule";

export type SourceRow = {
  id: number;
  name?: string;
  source_type?: string;
  identifier?: string;
  pool_id?: number;
  active?: boolean;
  schedule_cron?: string | null;
  schedule_enabled?: boolean;
  media_types?: string;
  max_messages_per_run?: number;
  last_scraped_at?: string | null;
};

const SOURCE_TYPES = [
  { value: "telegram_channel", label: "Telegram channel", supported: true },
  { value: "reddit", label: "Reddit (coming soon)", supported: false },
  { value: "manual", label: "Manual import only", supported: false },
] as const;

const MEDIA_TYPE_OPTIONS = [
  { value: "both", label: "Photos and videos" },
  { value: "photos", label: "Photos only" },
  { value: "videos", label: "Videos only" },
] as const;

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
  source: SourceRow | null;
  pools: Array<{ id: number; name?: string }>;
  onClose: () => void;
  onDeleted?: () => void;
};

export function SourceEditorModal({ source, pools, onClose, onDeleted }: Props) {
  const queryClient = useQueryClient();
  const open = source != null;

  const [name, setName] = useState("");
  const [identifier, setIdentifier] = useState("");
  const [sourceType, setSourceType] = useState("telegram_channel");
  const [poolId, setPoolId] = useState(1);
  const [active, setActive] = useState(true);
  const [scheduleCron, setScheduleCron] = useState(buildCronFromState(defaultScheduleState()));
  const [scheduleEnabled, setScheduleEnabled] = useState(false);
  const [mediaTypes, setMediaTypes] = useState<"both" | "photos" | "videos">("both");
  const [maxMessages, setMaxMessages] = useState(50);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  useEffect(() => {
    if (!source) return;
    setName(String(source.name ?? ""));
    setIdentifier(String(source.identifier ?? ""));
    setSourceType(String(source.source_type ?? "telegram_channel"));
    setPoolId(Number(source.pool_id ?? 1));
    setActive(source.active !== false);
    setScheduleCron(
      source.schedule_cron?.trim() || buildCronFromState(parseCronToState(source.schedule_cron))
    );
    setScheduleEnabled(Boolean(source.schedule_enabled));
    const mt = String(source.media_types ?? "both").toLowerCase();
    setMediaTypes(mt === "photos" || mt === "videos" ? mt : "both");
    setMaxMessages(Math.min(500, Math.max(1, Number(source.max_messages_per_run ?? 50) || 50)));
    setConfirmDelete(false);
    setFormError(null);
  }, [source]);

  useEscapeClose(onClose, open);

  const save = useMutation({
    mutationFn: () =>
      api.sources.update(source!.id, {
        name: name.trim() || "Source",
        identifier: identifier.trim(),
        source_type: sourceType,
        pool_id: poolId,
        active,
        schedule_cron: scheduleEnabled ? scheduleCron.trim() || null : null,
        schedule_enabled: scheduleEnabled,
        media_types: mediaTypes,
        max_messages_per_run: maxMessages,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sources"] });
      onClose();
    },
    onError: (e: Error) => {
      const msg = e.message || String(e);
      if (/method not allowed/i.test(msg)) {
        setFormError(
          "Backend API is outdated. Restart TBCC-Backend, then try Save again."
        );
        return;
      }
      setFormError(msg);
    },
  });

  const remove = useMutation({
    mutationFn: () => api.sources.delete(source!.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sources"] });
      onDeleted?.();
      onClose();
    },
    onError: (e: Error) => setFormError(e.message || String(e)),
  });

  if (!open || !source) return null;

  const isTelegram = sourceType === "telegram_channel";
  const typeSupported = SOURCE_TYPES.find((t) => t.value === sourceType)?.supported ?? false;

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 p-4 overflow-y-auto"
      role="dialog"
      aria-modal="true"
      aria-labelledby="source-editor-title"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className="bg-slate-800 border border-slate-600 rounded-lg shadow-xl w-full max-w-xl flex flex-col my-4 max-h-[92vh]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-2 p-4 border-b border-slate-600 shrink-0">
          <div>
            <h2 id="source-editor-title" className="text-lg font-medium text-slate-100">
              Edit source
            </h2>
            <p className="text-slate-400 text-sm mt-1">
              Source ID {source.id} · pool {poolId}
              {source.name ? (
                <>
                  {" "}
                  · <span className="text-cyan-300">{source.name}</span>
                </>
              ) : null}
            </p>
          </div>
          <button type="button" onClick={onClose} className="text-slate-400 hover:text-slate-200 px-2 py-1 text-sm">
            Close
          </button>
        </div>

        <div className="p-4 space-y-4 overflow-y-auto flex-1">
          {isTelegram ? <ScraperTelegramAuth compact /> : null}

          <label className="block">
            <span className="text-slate-400 text-xs uppercase tracking-wide">Display name</span>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="mt-1 w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200"
            />
          </label>

          <label className="block">
            <span className="text-slate-400 text-xs uppercase tracking-wide">Type</span>
            <select
              value={sourceType}
              onChange={(e) => setSourceType(e.target.value)}
              className="mt-1 w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200"
            >
              {SOURCE_TYPES.map((t) => (
                <option key={t.value} value={t.value} disabled={!t.supported && t.value !== sourceType}>
                  {t.label}
                </option>
              ))}
            </select>
          </label>

          <label className="block">
            <span className="text-slate-400 text-xs uppercase tracking-wide">
              {isTelegram ? "Channel" : "Identifier"}
            </span>
            <input
              type="text"
              value={identifier}
              onChange={(e) => setIdentifier(e.target.value)}
              placeholder={
                isTelegram
                  ? "@channel, t.me/+invite, or -100… id"
                  : "URL or id"
              }
              className="mt-1 w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200 font-mono text-sm"
            />
            {isTelegram ? (
              <span className="text-slate-500 text-xs mt-1 block">
                Join this channel with your scraper Telegram account. No extra login per channel.
              </span>
            ) : null}
          </label>

          <label className="block">
            <span className="text-slate-400 text-xs uppercase tracking-wide">Destination pool</span>
            <select
              value={poolId}
              onChange={(e) => setPoolId(Number(e.target.value))}
              className="mt-1 w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200"
            >
              {pools.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name || `Pool ${p.id}`} (id {p.id})
                </option>
              ))}
            </select>
          </label>

          {isTelegram && typeSupported ? (
            <div className="rounded border border-slate-600/80 bg-slate-900/40 p-3 space-y-3">
              <p className="text-slate-300 text-sm font-medium">Scrape settings</p>

              <label className="block">
                <span className="text-slate-400 text-xs uppercase tracking-wide">Media types</span>
                <select
                  value={mediaTypes}
                  onChange={(e) => setMediaTypes(e.target.value as "both" | "photos" | "videos")}
                  className="mt-1 w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200"
                >
                  {MEDIA_TYPE_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </label>

              <label className="block">
                <span className="text-slate-400 text-xs uppercase tracking-wide">Messages per run</span>
                <div className="mt-1 flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setMaxMessages((n) => Math.max(1, n - 5))}
                    className="h-9 w-9 rounded bg-slate-700 border border-slate-600 text-slate-200"
                  >
                    −
                  </button>
                  <input
                    type="number"
                    min={1}
                    max={500}
                    value={maxMessages}
                    onChange={(e) => setMaxMessages(Number(e.target.value))}
                    className="flex-1 bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200 text-center"
                  />
                  <button
                    type="button"
                    onClick={() => setMaxMessages((n) => Math.min(500, n + 5))}
                    className="h-9 w-9 rounded bg-slate-700 border border-slate-600 text-slate-200"
                  >
                    +
                  </button>
                </div>
              </label>

              <CronScheduleBuilder
                cron={scheduleCron}
                enabled={scheduleEnabled}
                onCronChange={setScheduleCron}
                onEnabledChange={setScheduleEnabled}
              />
            </div>
          ) : null}

          <label className="flex items-center gap-2 text-slate-300">
            <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} />
            Active
          </label>

          {formError ? <p className="text-red-300 text-sm">{formError}</p> : null}

          <div className="border-t border-slate-600 pt-4">
            {!confirmDelete ? (
              <button
                type="button"
                onClick={() => setConfirmDelete(true)}
                className="text-red-300 text-sm hover:text-red-200 underline"
              >
                Delete this source…
              </button>
            ) : (
              <div className="rounded border border-red-900/60 bg-red-950/30 p-3 space-y-2">
                <p className="text-red-200 text-sm">
                  Delete <strong>{name || source.name}</strong>? Imported media stays in the library.
                </p>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => void remove.mutate()}
                    disabled={remove.isPending}
                    className="px-3 py-1.5 bg-red-700 text-white rounded text-sm disabled:opacity-50"
                  >
                    Confirm delete
                  </button>
                  <button
                    type="button"
                    onClick={() => setConfirmDelete(false)}
                    className="px-3 py-1.5 bg-slate-600 text-slate-200 rounded text-sm"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>

        <div className="flex flex-wrap justify-end gap-2 p-4 border-t border-slate-600 shrink-0">
          <button type="button" onClick={onClose} className="px-4 py-2 bg-slate-600 text-slate-200 rounded">
            Cancel
          </button>
          <button
            type="button"
            onClick={() => {
              if (!identifier.trim() && isTelegram) {
                setFormError("Channel identifier is required.");
                return;
              }
              if (maxMessages < 1 || maxMessages > 500) {
                setFormError("Messages per run must be 1–500.");
                return;
              }
              if (scheduleEnabled && !scheduleCron.trim()) {
                setFormError("Pick a schedule or disable scheduled scrape.");
                return;
              }
              void save.mutate();
            }}
            disabled={save.isPending}
            className="px-4 py-2 bg-cyan-600 text-white rounded hover:bg-cyan-500 disabled:opacity-50"
          >
            {save.isPending ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}
