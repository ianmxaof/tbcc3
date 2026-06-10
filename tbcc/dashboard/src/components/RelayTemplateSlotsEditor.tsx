import { useEffect, useState } from "react";
import { SnippetAwareTextarea } from "./SnippetAwareTextarea";
import { TbccInsertMenu } from "./TbccInsertMenu";
import { TbccInsertLibraryToolbar } from "./TbccInsertLibraryToolbar";
import {
  EMPTY_RELAY_SLOT_EXTRA,
  RelayCopySlotExtras,
  normalizeRelaySlotExtra,
  type RelaySlotExtra,
} from "./RelayCopySlotExtras";

const LAYOUT_KEY = "tbcc_relay_template_layout";
const COLS_KEY = "tbcc_relay_template_cols";

export const RELAY_TEMPLATE_SLOTS_MAX = 160;
export const RELAY_TEMPLATE_PAGE_SIZE = 16;

type LayoutMode = "grid" | "stack";
type GridCols = 2 | 3 | 4;

function readLayout(): LayoutMode {
  try {
    return localStorage.getItem(LAYOUT_KEY) === "stack" ? "stack" : "grid";
  } catch {
    return "grid";
  }
}

function readCols(): GridCols {
  try {
    const v = localStorage.getItem(COLS_KEY);
    if (v === "2" || v === "4") return Number(v) as GridCols;
  } catch {
    /* ignore */
  }
  return 3;
}

function stripHtmlPreview(s: string, max = 72): string {
  const t = String(s || "")
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  if (!t) return "(empty)";
  return t.length > max ? `${t.slice(0, max)}…` : t;
}

/** First sentence across main / promo / copy — used as the card title for quick scanning. */
function firstSentenceSnippet(...parts: string[]): string {
  for (const raw of parts) {
    const t = stripHtmlPreview(raw, 280);
    if (t === "(empty)") continue;
    const m = t.match(/^[^.!?\n]+(?:[.!?]|$)/);
    const sentence = (m ? m[0] : t).trim();
    if (sentence) return sentence.length > 76 ? `${sentence.slice(0, 76)}…` : sentence;
  }
  return "(empty slot)";
}

function excerptLine(label: string, html: string, max = 54): string | null {
  const t = stripHtmlPreview(html, max + 24);
  if (t === "(empty)") return null;
  const clipped = t.length > max ? `${t.slice(0, max)}…` : t;
  return `${label}: ${clipped}`;
}

function slotFilterChips(footer: string, copy: string): string[] {
  const chips: string[] = [];
  if (String(footer).trim()) chips.push("PROMO");
  if (String(copy).trim()) chips.push("COPY");
  return chips;
}

function slotCardMetaLines(
  tpl: string,
  footer: string,
  copy: string,
  extra: RelaySlotExtra
): string[] {
  const slot = normalizeRelaySlotExtra(extra);
  const lines: string[] = [];
  const mainEx = excerptLine("Main", tpl, 58);
  if (mainEx) lines.push(mainEx);
  const promoEx = excerptLine("Promo", footer, 50);
  if (promoEx) lines.push(promoEx);
  const copyEx = excerptLine("Copy", copy, 50);
  if (copyEx) lines.push(copyEx);
  const hasCopyPanel =
    String(copy).trim() ||
    slot.copy_buttons.length ||
    slot.copy_media_ids.length ||
    slot.copy_attachment_urls.length;
  if (hasCopyPanel) lines.push(slot.copy_pin_after_send ? "Pin copy: yes" : "Pin copy: no");
  if (slot.copy_checkout_stars_enabled) {
    lines.push(
      slot.copy_checkout_stars_plan_id != null
        ? `Stars checkout (plan #${slot.copy_checkout_stars_plan_id})`
        : "Stars checkout"
    );
  }
  if (slot.copy_buttons.length) {
    const first = slot.copy_buttons[0];
    const hint = first && first.text ? ` — “${stripHtmlPreview(first.text, 28)}”` : "";
    lines.push(
      `${slot.copy_buttons.length} button${slot.copy_buttons.length > 1 ? "s" : ""}${hint}`
    );
  }
  if (slot.copy_media_ids.length) lines.push(`${slot.copy_media_ids.length} approved media`);
  if (slot.copy_attachment_urls.length) lines.push(`${slot.copy_attachment_urls.length} promo URL(s)`);
  if (slot.copy_album_order_mode !== "static") lines.push(`Album: ${slot.copy_album_order_mode}`);
  return lines.slice(0, 2);
}

function slotDetailBadges(tpl: string, footer: string, copy: string, extra: RelaySlotExtra) {
  const badges: string[] = [];
  if (String(tpl).trim()) badges.push("main");
  const slot = normalizeRelaySlotExtra(extra);
  if (slot.copy_buttons.length) badges.push(`${slot.copy_buttons.length} btn`);
  if (slot.copy_media_ids.length) badges.push(`${slot.copy_media_ids.length} media`);
  if (slot.copy_attachment_urls.length) badges.push("URLs");
  if (slot.copy_checkout_stars_enabled) badges.push("Stars");
  if (slot.copy_pin_after_send) badges.push("pinned");
  void footer;
  void copy;
  return badges;
}

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

type SlotEditorFieldsProps = {
  slotIndex: number;
  template: string;
  footer: string;
  copyBlock: string;
  extra: RelaySlotExtra;
  canRemove: boolean;
  salablePlans: Array<{ id: number; name?: string; price_stars?: number; product_type?: string }>;
  channels?: Array<Record<string, unknown>>;
  pools?: Array<Record<string, unknown>>;
  onTemplateChange: (v: string) => void;
  onFooterChange: (v: string) => void;
  onCopyBlockChange: (v: string) => void;
  onExtraChange: (next: RelaySlotExtra) => void;
  onRemove: () => void;
};

function RelayTemplateSlotEditorFields({
  slotIndex,
  template,
  footer,
  copyBlock,
  extra,
  canRemove,
  salablePlans,
  channels = [],
  pools = [],
  onTemplateChange,
  onFooterChange,
  onCopyBlockChange,
  onExtraChange,
  onRemove,
}: SlotEditorFieldsProps) {
  const i = slotIndex;
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-sm font-medium text-slate-200">Template {i + 1}</span>
        <div className="flex flex-wrap items-center gap-2 shrink-0">
          <TbccInsertMenu channels={channels} pools={pools} onInsert={onTemplateChange} />
          {canRemove ? (
            <button type="button" className="text-xs text-red-400 hover:text-red-300" onClick={onRemove}>
              Remove slot
            </button>
          ) : null}
        </div>
      </div>
      <SnippetAwareTextarea
        className="w-full min-h-[88px] bg-slate-800 border border-slate-600 rounded px-3 py-2 text-slate-100 font-mono text-sm"
        value={template}
        onChange={onTemplateChange}
        placeholder={
          i === 0 ? "Leave empty for built-in default, or use placeholders." : `Variation ${i + 1} (rotation)`
        }
      />
      <div className="flex flex-wrap items-start justify-between gap-2">
        <span className="block text-[11px] text-slate-500">
          Flavor / promo caption (first message, above Last.fm preview — HTML)
        </span>
        <TbccInsertMenu channels={channels} pools={pools} onInsert={onFooterChange} />
      </div>
      <SnippetAwareTextarea
        className="w-full min-h-[52px] bg-slate-900 border border-slate-700 rounded px-3 py-2 text-slate-200 font-mono text-xs"
        value={footer}
        onChange={onFooterChange}
        placeholder="Italic flavor text, links, etc."
        rows={3}
      />
      <div className="flex flex-wrap items-start justify-between gap-2">
        <span className="block text-[11px] text-slate-500">
          Copy block — tap-to-copy panel under the Last.fm card (second message)
        </span>
        <div className="flex flex-wrap items-center gap-1 shrink-0">
          <TbccInsertMenu channels={channels} pools={pools} onInsert={onCopyBlockChange} />
          <button
            type="button"
            className="text-[10px] px-2 py-0.5 rounded border border-slate-600 bg-slate-800 text-slate-300 hover:bg-slate-700"
            onClick={() => {
              const body = copyBlock.trim();
              onCopyBlockChange(body.startsWith("<pre") ? body : `<pre>${body}</pre>`);
            }}
          >
            Wrap &lt;pre&gt;
          </button>
        </div>
      </div>
      <SnippetAwareTextarea
        className="w-full min-h-[48px] bg-slate-950 border border-slate-700 rounded px-3 py-2 text-slate-200 font-mono text-xs"
        value={copyBlock}
        onChange={onCopyBlockChange}
        placeholder="Invite link, ref code, wallet address…"
        rows={2}
      />
      <RelayCopySlotExtras
        slotIndex={i}
        extra={normalizeRelaySlotExtra(extra)}
        salablePlans={salablePlans}
        onChange={onExtraChange}
      />
    </div>
  );
}

function RelayTemplateSlotModal({
  slotIndex,
  onClose,
  ...fields
}: SlotEditorFieldsProps & { onClose: () => void }) {
  useEscapeClose(onClose, true);
  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/65 p-4 overflow-y-auto"
      role="dialog"
      aria-modal="true"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className="bg-slate-900 border border-slate-600 rounded-lg shadow-xl w-full max-w-2xl max-h-[min(92vh,900px)] flex flex-col my-2"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-2 p-4 border-b border-slate-700 shrink-0">
          <h3 className="text-base font-medium text-slate-100">Edit relay slot {slotIndex + 1}</h3>
          <button
            type="button"
            onClick={onClose}
            className="text-slate-400 hover:text-slate-200 px-3 py-1 rounded text-sm border border-slate-600"
          >
            Done
          </button>
        </div>
        <div className="p-4 overflow-y-auto flex-1 min-h-0">
          <RelayTemplateSlotEditorFields {...fields} slotIndex={slotIndex} />
        </div>
      </div>
    </div>
  );
}

export type RelayTemplateSlotsEditorProps = {
  templateHint: string;
  rotationActive: boolean;
  templateVariants: string[];
  footerVariants: string[];
  copyBlockVariants: string[];
  slotExtras: RelaySlotExtra[];
  templatePage: number;
  onTemplatePageChange: (page: number) => void;
  salablePlans: Array<{ id: number; name?: string; price_stars?: number; product_type?: string }>;
  channels?: Array<Record<string, unknown>>;
  pools?: Array<Record<string, unknown>>;
  onEdited: () => void;
  onTemplateVariantsChange: (fn: (prev: string[]) => string[]) => void;
  onFooterVariantsChange: (fn: (prev: string[]) => string[]) => void;
  onCopyBlockVariantsChange: (fn: (prev: string[]) => string[]) => void;
  onSlotExtrasChange: (fn: (prev: RelaySlotExtra[]) => RelaySlotExtra[]) => void;
};

export function RelayTemplateSlotsEditor({
  templateHint,
  rotationActive,
  templateVariants,
  footerVariants,
  copyBlockVariants,
  slotExtras,
  templatePage,
  onTemplatePageChange,
  salablePlans,
  channels = [],
  pools = [],
  onEdited,
  onTemplateVariantsChange,
  onFooterVariantsChange,
  onCopyBlockVariantsChange,
  onSlotExtrasChange,
}: RelayTemplateSlotsEditorProps) {
  const [layout, setLayout] = useState<LayoutMode>(readLayout);
  const [gridCols, setGridCols] = useState<GridCols>(readCols);
  const [editingSlot, setEditingSlot] = useState<number | null>(null);

  const relayTotalPages = Math.max(1, Math.ceil(templateVariants.length / RELAY_TEMPLATE_PAGE_SIZE));
  const pageStart = templatePage * RELAY_TEMPLATE_PAGE_SIZE;
  const pageSlots = templateVariants.slice(pageStart, pageStart + RELAY_TEMPLATE_PAGE_SIZE);

  const persistLayout = (mode: LayoutMode) => {
    setLayout(mode);
    try {
      localStorage.setItem(LAYOUT_KEY, mode);
    } catch {
      /* ignore */
    }
  };

  const persistCols = (cols: GridCols) => {
    setGridCols(cols);
    try {
      localStorage.setItem(COLS_KEY, String(cols));
    } catch {
      /* ignore */
    }
  };

  const gridClass =
    gridCols === 2
      ? "grid grid-cols-1 sm:grid-cols-2 gap-3"
      : gridCols === 4
        ? "grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3"
        : "grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3";

  const removeSlot = (i: number) => {
    onEdited();
    onTemplateVariantsChange((prev) => prev.filter((_, j) => j !== i));
    onFooterVariantsChange((prev) => prev.filter((_, j) => j !== i));
    onCopyBlockVariantsChange((prev) => prev.filter((_, j) => j !== i));
    onSlotExtrasChange((prev) => prev.filter((_, j) => j !== i));
    if (editingSlot === i) setEditingSlot(null);
  };

  const appendBlankSlots = (count: number) => {
    if (count < 1 || templateVariants.length >= RELAY_TEMPLATE_SLOTS_MAX) return;
    const room = RELAY_TEMPLATE_SLOTS_MAX - templateVariants.length;
    const n = Math.min(count, room);
    onEdited();
    onTemplateVariantsChange((prev) => [...prev, ...Array(n).fill("")]);
    onFooterVariantsChange((prev) => [...prev, ...Array(n).fill("")]);
    onCopyBlockVariantsChange((prev) => [...prev, ...Array(n).fill("")]);
    onSlotExtrasChange((prev) => [...prev, ...Array(n).fill({ ...EMPTY_RELAY_SLOT_EXTRA })]);
    const newPage = Math.floor((templateVariants.length + n - 1) / RELAY_TEMPLATE_PAGE_SIZE);
    onTemplatePageChange(newPage);
  };

  const editorPropsFor = (i: number): SlotEditorFieldsProps => ({
    slotIndex: i,
    template: templateVariants[i] ?? "",
    footer: footerVariants[i] ?? "",
    copyBlock: copyBlockVariants[i] ?? "",
    extra: slotExtras[i] ?? { ...EMPTY_RELAY_SLOT_EXTRA },
    canRemove: templateVariants.length > 1,
    salablePlans,
    channels,
    pools,
    onTemplateChange: (v) => {
      onEdited();
      onTemplateVariantsChange((prev) => prev.map((p, j) => (j === i ? v : p)));
    },
    onFooterChange: (v) => {
      onEdited();
      onFooterVariantsChange((prev) => {
        const next = [...prev];
        while (next.length <= i) next.push("");
        next[i] = v;
        return next;
      });
    },
    onCopyBlockChange: (v) => {
      onEdited();
      onCopyBlockVariantsChange((prev) => {
        const next = [...prev];
        while (next.length <= i) next.push("");
        next[i] = v;
        return next;
      });
    },
    onExtraChange: (next) => {
      onEdited();
      onSlotExtrasChange((prev) => {
        const copy = [...prev];
        while (copy.length <= i) copy.push({ ...EMPTY_RELAY_SLOT_EXTRA });
        copy[i] = next;
        return copy;
      });
    },
    onRemove: () => removeSlot(i),
  });

  return (
    <div className="border-t border-slate-700 pt-4">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
        <h3 className="text-sm font-medium text-slate-200">Message templates (HTML)</h3>
        <TbccInsertLibraryToolbar />
      </div>
      <div className="flex flex-wrap items-center justify-end gap-2 mb-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[11px] text-slate-500">Layout</span>
          <select
            className="bg-slate-800 border border-slate-600 rounded px-2 py-1 text-xs text-slate-200"
            value={layout}
            onChange={(e) => persistLayout(e.target.value === "stack" ? "stack" : "grid")}
          >
            <option value="grid">Grid + modal</option>
            <option value="stack">Stacked (classic)</option>
          </select>
          {layout === "grid" ? (
            <>
              <span className="text-[11px] text-slate-500">Columns</span>
              <select
                className="bg-slate-800 border border-slate-600 rounded px-2 py-1 text-xs text-slate-200"
                value={String(gridCols)}
                onChange={(e) => persistCols(Number(e.target.value) as GridCols)}
              >
                <option value="2">2×</option>
                <option value="3">3×</option>
                <option value="4">4×</option>
              </select>
            </>
          ) : null}
        </div>
      </div>
      <p className="text-xs text-slate-500 mb-2 whitespace-pre-wrap max-w-4xl">{templateHint}</p>
      {rotationActive ? (
        <p className="text-xs text-cyan-400/90 mb-2">
          Rotation active: templates cycle in order on each new listening post (Last.fm or webhook).
        </p>
      ) : null}
      {templateVariants.length > RELAY_TEMPLATE_PAGE_SIZE ? (
        <div className="flex flex-wrap items-center gap-2 mb-3">
          <span className="text-xs text-slate-500 shrink-0">Slot pages ({RELAY_TEMPLATE_PAGE_SIZE} each):</span>
          <div className="flex flex-wrap gap-1">
            {Array.from({ length: relayTotalPages }, (_, pi) => {
              const from = pi * RELAY_TEMPLATE_PAGE_SIZE + 1;
              const to = Math.min((pi + 1) * RELAY_TEMPLATE_PAGE_SIZE, templateVariants.length);
              const active = pi === templatePage;
              return (
                <button
                  key={pi}
                  type="button"
                  className={`text-[11px] px-2 py-0.5 rounded border ${
                    active
                      ? "border-cyan-500 bg-cyan-950/50 text-cyan-200"
                      : "border-slate-600 bg-slate-800/80 text-slate-400 hover:border-slate-500"
                  }`}
                  onClick={() => onTemplatePageChange(pi)}
                >
                  {from}–{to}
                </button>
              );
            })}
          </div>
        </div>
      ) : null}

      {layout === "grid" ? (
        <div className={gridClass}>
          {pageSlots.map((line, localIdx) => {
            const i = pageStart + localIdx;
            const footer = footerVariants[i] ?? "";
            const copy = copyBlockVariants[i] ?? "";
            const extra = slotExtras[i] ?? { ...EMPTY_RELAY_SLOT_EXTRA };
            const filterChips = slotFilterChips(footer, copy);
            const detailBadges = slotDetailBadges(line, footer, copy, extra);
            const metaLines = slotCardMetaLines(line, footer, copy, extra);
            const title = firstSentenceSnippet(line, footer, copy);
            const filled =
              filterChips.length > 0 || detailBadges.length > 0 || title !== "(empty slot)";
            return (
              <button
                key={i}
                type="button"
                className={`text-left rounded-lg border p-2 transition-colors min-h-[84px] flex flex-col gap-1 ${
                  editingSlot === i
                    ? "border-cyan-500 bg-cyan-950/30 ring-1 ring-cyan-500/40"
                    : filled
                      ? "border-slate-600 bg-slate-800/60 hover:border-cyan-600/60 hover:bg-slate-800"
                      : "border-dashed border-slate-600 bg-slate-900/40 hover:border-slate-500"
                }`}
                onClick={() => setEditingSlot(i)}
              >
                <div className="flex items-start justify-between gap-1 min-h-[1.25rem]">
                  <span
                    className="text-[10px] font-medium text-slate-200 line-clamp-1 leading-snug flex-1"
                    title={title}
                  >
                    {title}
                  </span>
                  <span className="text-[9px] text-slate-500 shrink-0 tabular-nums">#{i + 1}</span>
                  {templateVariants.length > 1 ? (
                    <span
                      role="button"
                      tabIndex={0}
                      className="text-[10px] text-red-400/90 hover:text-red-300 px-1 shrink-0"
                      onClick={(e) => {
                        e.stopPropagation();
                        removeSlot(i);
                      }}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          e.stopPropagation();
                          removeSlot(i);
                        }
                      }}
                    >
                      ✕
                    </span>
                  ) : null}
                </div>
                <div className="flex-1 flex flex-col gap-0.5 min-h-0">
                  {metaLines.length ? (
                    metaLines.map((ln) => (
                      <p key={ln} className="text-[9px] text-slate-500 line-clamp-1 leading-tight">
                        {ln}
                      </p>
                    ))
                  ) : (
                    <p className="text-[9px] text-slate-600 italic">Click to edit</p>
                  )}
                </div>
                {(filterChips.length > 0 || detailBadges.length > 0) ? (
                <div className="flex flex-wrap gap-0.5 mt-auto pt-0.5">
                  {filterChips.map((b) => (
                    <span
                      key={b}
                      className="text-[9px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded border border-slate-500/60 bg-slate-700/90 text-slate-300"
                    >
                      {b}
                    </span>
                  ))}
                  {detailBadges.map((b) => (
                    <span
                      key={b}
                      className="text-[9px] uppercase tracking-wide px-1.5 py-0.5 rounded bg-slate-800/90 text-slate-500"
                    >
                      {b}
                    </span>
                  ))}
                </div>
                ) : null}
              </button>
            );
          })}
        </div>
      ) : (
        <div className="space-y-3">
          {pageSlots.map((line, localIdx) => {
            const i = pageStart + localIdx;
            return (
              <div key={i} className="rounded-lg border border-slate-700 bg-slate-900/30 p-3">
                <RelayTemplateSlotEditorFields {...editorPropsFor(i)} template={line} />
              </div>
            );
          })}
        </div>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button
          type="button"
          className="px-3 py-1.5 rounded bg-cyan-800/90 text-cyan-100 text-sm hover:bg-cyan-700 disabled:opacity-40 border border-cyan-700/60"
          disabled={templateVariants.length >= RELAY_TEMPLATE_SLOTS_MAX}
          onClick={() => appendBlankSlots(1)}
        >
          + Add slot ({templateVariants.length}/{RELAY_TEMPLATE_SLOTS_MAX})
        </button>
        <button
          type="button"
          className="px-3 py-1.5 rounded bg-slate-700 text-slate-200 text-sm hover:bg-slate-600 disabled:opacity-40 border border-slate-600"
          disabled={templateVariants.length + RELAY_TEMPLATE_PAGE_SIZE > RELAY_TEMPLATE_SLOTS_MAX}
          onClick={() => appendBlankSlots(RELAY_TEMPLATE_PAGE_SIZE)}
        >
          Add page ({RELAY_TEMPLATE_PAGE_SIZE} blank slots)
        </button>
        <span className="text-[11px] text-slate-500">2+ filled enables rotation · click a card to edit</span>
      </div>

      {editingSlot != null && layout === "grid" ? (
        <RelayTemplateSlotModal {...editorPropsFor(editingSlot)} onClose={() => setEditingSlot(null)} />
      ) : null}
    </div>
  );
}
