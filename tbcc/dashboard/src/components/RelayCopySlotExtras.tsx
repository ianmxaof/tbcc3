import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import { ApprovedMediaPickerStrip } from "./ApprovedMediaPickerStrip";

export type RelaySlotExtra = {
  copy_buttons: Array<{ text: string; url: string }>;
  copy_media_ids: number[];
  copy_attachment_urls: string[];
  copy_album_order_mode: "static" | "shuffle" | "carousel";
  copy_pin_after_send: boolean;
  copy_checkout_stars_enabled: boolean;
  copy_checkout_stars_plan_id: number | null;
  copy_checkout_button_label: string | null;
  copy_checkout_referral_code: string | null;
};

export const EMPTY_RELAY_SLOT_EXTRA: RelaySlotExtra = {
  copy_buttons: [],
  copy_media_ids: [],
  copy_attachment_urls: [],
  copy_album_order_mode: "static",
  copy_pin_after_send: false,
  copy_checkout_stars_enabled: false,
  copy_checkout_stars_plan_id: null,
  copy_checkout_button_label: null,
  copy_checkout_referral_code: null,
};

/** Merge API/partial slot extras with defaults so .length / .map never hit undefined. */
export function normalizeRelaySlotExtra(x: Partial<RelaySlotExtra> | null | undefined): RelaySlotExtra {
  if (!x || typeof x !== "object") {
    return { ...EMPTY_RELAY_SLOT_EXTRA };
  }
  return {
    ...EMPTY_RELAY_SLOT_EXTRA,
    copy_buttons: Array.isArray(x.copy_buttons)
      ? x.copy_buttons.filter((b) => b && typeof b === "object")
      : [],
    copy_media_ids: Array.isArray(x.copy_media_ids)
      ? x.copy_media_ids.map((id) => Number(id)).filter((id) => Number.isFinite(id))
      : [],
    copy_attachment_urls: Array.isArray(x.copy_attachment_urls)
      ? x.copy_attachment_urls.map(String).filter((u) => u.trim())
      : [],
    copy_album_order_mode:
      x.copy_album_order_mode === "shuffle" || x.copy_album_order_mode === "carousel"
        ? x.copy_album_order_mode
        : "static",
    copy_pin_after_send: Boolean(x.copy_pin_after_send),
    copy_checkout_stars_enabled: Boolean(x.copy_checkout_stars_enabled),
    copy_checkout_stars_plan_id:
      x.copy_checkout_stars_plan_id != null && Number.isFinite(Number(x.copy_checkout_stars_plan_id))
        ? Number(x.copy_checkout_stars_plan_id)
        : null,
    copy_checkout_button_label:
      typeof x.copy_checkout_button_label === "string" ? x.copy_checkout_button_label : null,
    copy_checkout_referral_code:
      typeof x.copy_checkout_referral_code === "string" ? x.copy_checkout_referral_code : null,
  };
}

type PlanOpt = { id: number; name?: string; price_stars?: number; product_type?: string };

export function RelayCopySlotExtras({
  slotIndex,
  extra,
  onChange,
  salablePlans,
}: {
  slotIndex: number;
  extra: RelaySlotExtra;
  onChange: (next: RelaySlotExtra) => void;
  salablePlans: PlanOpt[];
}) {
  const slot = normalizeRelaySlotExtra(extra);
  const { data: approvedMedia = [] } = useQuery({
    queryKey: ["media", "approved", "relay-copy"],
    queryFn: () => api.media.list("approved"),
  });

  const patch = (part: Partial<RelaySlotExtra>) => onChange(normalizeRelaySlotExtra({ ...slot, ...part }));

  const updateBtn = (i: number, field: "text" | "url", v: string) => {
    const btns = [...slot.copy_buttons];
    while (btns.length <= i) btns.push({ text: "", url: "" });
    btns[i] = { ...btns[i], [field]: v };
    patch({ copy_buttons: btns });
  };

  const promoLines = slot.copy_attachment_urls.join("\n");

  return (
    <div className="mt-2 rounded border border-slate-700/80 bg-slate-950/60 p-2 space-y-2">
      <p className="text-[10px] text-cyan-400/90 font-medium">
        Copy panel extras (slot {slotIndex + 1}) — posts under Last.fm preview; supports albums, promo URLs, buttons
      </p>
      <div>
        <span className="text-[10px] text-slate-500 block mb-1">Inline buttons</span>
        {slot.copy_buttons.map((b, i) => (
          <div key={i} className="flex gap-1 mb-1">
            <input
              placeholder="Label"
              value={b.text}
              onChange={(e) => updateBtn(i, "text", e.target.value)}
              className="flex-1 bg-slate-800 border border-slate-600 rounded px-2 py-1 text-xs text-slate-200"
            />
            <input
              placeholder="https://…"
              value={b.url}
              onChange={(e) => updateBtn(i, "url", e.target.value)}
              className="flex-1 bg-slate-800 border border-slate-600 rounded px-2 py-1 text-xs text-slate-200"
            />
            <button
              type="button"
              className="text-red-400 text-xs px-1"
              onClick={() => patch({ copy_buttons: slot.copy_buttons.filter((_, j) => j !== i) })}
            >
              ✕
            </button>
          </div>
        ))}
        <button
          type="button"
          className="text-[10px] text-cyan-400"
          onClick={() => patch({ copy_buttons: [...extra.copy_buttons, { text: "", url: "" }] })}
        >
          + button
        </button>
      </div>
      <label className="flex items-center gap-2 text-[10px] text-slate-400 cursor-pointer">
        <input
          type="checkbox"
          checked={slot.copy_checkout_stars_enabled}
          onChange={(e) =>
            patch({
              copy_checkout_stars_enabled: e.target.checked,
              copy_checkout_stars_plan_id: e.target.checked ? slot.copy_checkout_stars_plan_id : null,
            })
          }
        />
        Stars checkout button on copy panel
      </label>
      {slot.copy_checkout_stars_enabled ? (
        <select
          value={slot.copy_checkout_stars_plan_id ?? ""}
          onChange={(e) => patch({ copy_checkout_stars_plan_id: Number(e.target.value) || null })}
          className="w-full bg-slate-800 border border-slate-600 rounded px-2 py-1 text-xs text-slate-200"
        >
          <option value="">Plan…</option>
          {salablePlans.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name || `Plan ${p.id}`} — {p.price_stars ?? 0}⭐
            </option>
          ))}
        </select>
      ) : null}
      <div>
        <span className="text-[10px] text-slate-500 block mb-1">Promo image URLs (/static/promo/…)</span>
        <textarea
          rows={2}
          value={promoLines}
          onChange={(e) =>
            patch({
              copy_attachment_urls: e.target.value
                .split("\n")
                .map((s) => s.trim())
                .filter(Boolean)
                .slice(0, 10),
            })
          }
          placeholder="One URL per line"
          className="w-full bg-slate-800 border border-slate-600 rounded px-2 py-1 text-xs text-slate-200 font-mono"
        />
      </div>
      <ApprovedMediaPickerStrip
        rows={approvedMedia as Array<Record<string, unknown>>}
        selectedIds={slot.copy_media_ids}
        onToggle={(id) => {
          const mids = slot.copy_media_ids.includes(id)
            ? slot.copy_media_ids.filter((x) => x !== id)
            : [...slot.copy_media_ids, id].slice(0, 10);
          patch({ copy_media_ids: mids });
        }}
        rowKeyPrefix={`relay-copy-s${slotIndex}`}
      />
      <div className="flex flex-wrap gap-3 text-[10px] text-slate-400">
        <label className="flex items-center gap-1">
          Album order
          <select
            value={slot.copy_album_order_mode}
            onChange={(e) =>
              patch({
                copy_album_order_mode: e.target.value as RelaySlotExtra["copy_album_order_mode"],
              })
            }
            className="bg-slate-800 border border-slate-600 rounded px-1 py-0.5 text-slate-200"
          >
            <option value="static">static</option>
            <option value="shuffle">shuffle</option>
            <option value="carousel">carousel</option>
          </select>
        </label>
        <label className="flex items-center gap-1 cursor-pointer">
          <input
            type="checkbox"
            checked={slot.copy_pin_after_send}
            onChange={(e) => patch({ copy_pin_after_send: e.target.checked })}
          />
          Pin copy panel after send
        </label>
      </div>
    </div>
  );
}
