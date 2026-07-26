import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import { TbccInsertLibraryToolbar } from "../components/TbccInsertLibraryToolbar";
import { PromoAffiliateLinksPopover } from "../components/PromoAffiliateLinksPopover";
import { QueryErrorBanner } from "../components/QueryErrorBanner";
import type { ListeningRelaySettings, RelaySlotExtra } from "../api";
import { EmojiPackWayfinding } from "../components/EmojiPackWayfinding";
import { CustomEmojiTools } from "./CustomEmojiTools";
import { EmojiFactoryPanel } from "./EmojiFactoryPanel";
import { EmojiFactoryRowDividers } from "../components/EmojiFactoryRowDividers";
import { SilentTelegramSendOption } from "../components/SilentTelegramSendOption";
import { EMPTY_RELAY_SLOT_EXTRA, normalizeRelaySlotExtra } from "../components/RelayCopySlotExtras";
import { RelayTemplateSlotsEditor } from "../components/RelayTemplateSlotsEditor";
import { RelayPostHistory } from "../components/RelayPostHistory";

function relaySlotsFromApiSettings(st: ListeningRelaySettings): {
  templates: string[];
  footers: string[];
  copyBlocks: string[];
  slotExtras: RelaySlotExtra[];
} {
  const variants = Array.isArray(st.message_template_variations) ? st.message_template_variations.map(String) : [];
  const legacy = String(st.message_template_html || "").trim();
  let nextTpl: string[];
  if (variants.length > 0) {
    nextTpl = variants;
  } else if (legacy) {
    nextTpl = [legacy];
  } else {
    nextTpl = [""];
  }
  const footApi = Array.isArray(st.message_footer_variations) ? st.message_footer_variations.map(String) : [];
  const padFoot = [...footApi];
  while (padFoot.length < nextTpl.length) padFoot.push("");
  const copyApi = Array.isArray(st.message_copy_block_variations)
    ? st.message_copy_block_variations.map(String)
    : [];
  const padCopy = [...copyApi];
  while (padCopy.length < nextTpl.length) padCopy.push("");
  const extrasApi = Array.isArray(st.message_slot_extras) ? st.message_slot_extras : [];
  const padExtras: RelaySlotExtra[] = extrasApi.map((x) => normalizeRelaySlotExtra(x as Partial<RelaySlotExtra>));
  while (padExtras.length < nextTpl.length) padExtras.push({ ...EMPTY_RELAY_SLOT_EXTRA });
  return {
    templates: nextTpl,
    footers: padFoot.slice(0, nextTpl.length),
    copyBlocks: padCopy.slice(0, nextTpl.length),
    slotExtras: padExtras.slice(0, nextTpl.length),
  };
}

/** Sentinel channel dropdown value — random AOF network lane each scrobble. */
const RELAY_RANDOM_CHANNEL = "__random__";

function relayForumDestFromSettings(
  s: ListeningRelaySettings,
  dest: { loot_room?: { channel_id: number | null }; vip?: { channel_id: number | null } } | undefined
): string {
  if (s.relay_random_network_channel) return "";
  const lootId = dest?.loot_room?.channel_id ?? null;
  const vipId = dest?.vip?.channel_id ?? null;
  const cid = s.channel_id;
  if (cid != null && vipId != null && cid === vipId) return "vip";
  if (cid != null && lootId != null && cid === lootId) {
    return s.message_thread_id != null ? `loot:${s.message_thread_id}` : "";
  }
  if (s.message_thread_id != null) return `topic:${s.message_thread_id}`;
  return "";
}

function relayChannelSelectValue(
  s: ListeningRelaySettings
): number | typeof RELAY_RANDOM_CHANNEL | "" {
  if (s.relay_random_network_channel) return RELAY_RANDOM_CHANNEL;
  return s.channel_id != null ? Number(s.channel_id) : "";
}

const TEMPLATE_HINT = `Placeholders (main template only): {emoji} {headline} {artist} {title} {album} {album_line} {url} {source} {source_label} {link}
Default builds {headline} as “Artist — Title”, or just the title for webhook/YouTube-style posts.
With 2+ non-empty templates below, TBCC rotates on each scrobble (sequential or random). Copy panels support scheduler-style albums, promo URLs, and inline buttons — they post under the Last.fm preview card.

Each slot also has optional boxes below the main template:
• “Promo / flavor caption” — your prose (Telegram HTML); appears in the first message above the Last.fm preview card.
• “Copy block (below preview)” — plain text or HTML; TBCC wraps it in &lt;pre&gt; and sends a second silent message so it sits under the scrobble footer (tap-to-copy panel). Telegram cannot put text below a link preview inside one bubble.

Up to 160 main+footer pairs can be saved (rotation walks them in order). The editor shows 16 slots per tab so large libraries stay manageable — the old “16 max” limit was UI-only; the API stores JSON in TEXT with no separate slot cap.`;

function ZipBundlePromoSection() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["zipBundleSettings"], queryFn: () => api.zipBundle.get() });
  const [enabled, setEnabled] = useState(false);
  const [includeText, setIncludeText] = useState(true);
  const [includeImage, setIncludeImage] = useState(true);
  const [textFilename, setTextFilename] = useState("TBCC_README.txt");
  const [textBody, setTextBody] = useState("");
  const [promoImageFile, setPromoImageFile] = useState<File | null>(null);
  const [edited, setEdited] = useState(false);

  const s = q.data?.settings;

  useEffect(() => {
    if (!s || edited) return;
    setEnabled(Boolean(s.enabled));
    setIncludeText(s.include_text_file !== false);
    setIncludeImage(s.include_image !== false);
    setTextFilename(String(s.text_filename || "TBCC_README.txt"));
    setTextBody(String(s.text_body || ""));
  }, [s, edited]);

  const save = useMutation({
    mutationFn: () =>
      api.zipBundle.patch({
        enabled,
        include_text_file: includeText,
        include_image: includeImage,
        text_filename: textFilename.trim() || "TBCC_README.txt",
        text_body: textBody,
      }),
    onSuccess: () => {
      setEdited(false);
      setPromoImageFile(null);
      qc.invalidateQueries({ queryKey: ["zipBundleSettings"] });
    },
  });

  const uploadImage = useMutation({
    mutationFn: () => {
      if (!promoImageFile) throw new Error("Pick an image first");
      return api.zipBundle.uploadPromoImage(promoImageFile);
    },
    onSuccess: () => {
      setPromoImageFile(null);
      qc.invalidateQueries({ queryKey: ["zipBundleSettings"] });
    },
  });

  return (
    <section className="h-full border border-slate-700 rounded-lg p-6 bg-slate-900/40">
      <h2 className="text-lg font-medium text-slate-100 mb-1">ZIP promo inserts</h2>
      <p className="text-slate-400 text-sm mb-4">
        When enabled, every TBCC zip gets an extra readme text file and/or promo image at the root of the archive:
        gallery <strong>ZIP selected</strong>, digital-pack uploads, and loot modifier zip uploads. Extension option:
        Gallery → Options → <strong>Include global ZIP promo files</strong>.
      </p>
      {q.isError ? (
        <QueryErrorBanner
          title="Could not load ZIP promo settings"
          message={String(q.error instanceof Error ? q.error.message : q.error ?? "Unknown error")}
          onRetry={() => void q.refetch()}
        />
      ) : null}
      <label className="flex items-center gap-2 text-sm text-slate-200 mb-4">
        <input type="checkbox" checked={enabled} onChange={(e) => { setEdited(true); setEnabled(e.target.checked); }} />
        Enable promo inserts in all zips
      </label>
      <div className="space-y-3">
        <label className="flex items-center gap-2 text-sm text-slate-300">
          <input
            type="checkbox"
            checked={includeText}
            disabled={!enabled}
            onChange={(e) => { setEdited(true); setIncludeText(e.target.checked); }}
          />
          Include text file (links &amp; contact info)
        </label>
        <input
          type="text"
          className="w-full max-w-xs bg-slate-800 border border-slate-600 rounded px-3 py-1.5 text-slate-200 text-sm font-mono"
          value={textFilename}
          disabled={!enabled}
          onChange={(e) => { setEdited(true); setTextFilename(e.target.value); }}
          placeholder="TBCC_README.txt"
        />
        <textarea
          className="w-full min-h-[140px] bg-slate-800 border border-slate-600 rounded px-3 py-2 text-slate-100 font-mono text-sm"
          value={textBody}
          disabled={!enabled}
          onChange={(e) => { setEdited(true); setTextBody(e.target.value); }}
          placeholder={"Your channels, support, affiliate links…\nhttps://t.me/…\nhttps://…"}
        />
        <label className="flex items-center gap-2 text-sm text-slate-300">
          <input
            type="checkbox"
            checked={includeImage}
            disabled={!enabled}
            onChange={(e) => { setEdited(true); setIncludeImage(e.target.checked); }}
          />
          Include promo image (JPG/PNG)
        </label>
        {s?.image_url ? (
          <p className="text-xs text-slate-500">
            Current: <a className="text-cyan-400 underline" href={s.image_url} target="_blank" rel="noreferrer">{s.image_filename}</a>
          </p>
        ) : null}
        <div className="flex flex-wrap items-center gap-2">
          <input
            type="file"
            accept="image/jpeg,image/png,image/webp"
            disabled={!enabled}
            onChange={(e) => setPromoImageFile(e.target.files?.[0] ?? null)}
          />
          <button
            type="button"
            className="px-3 py-1.5 rounded bg-slate-700 text-slate-200 text-sm hover:bg-slate-600 disabled:opacity-40"
            disabled={!enabled || !promoImageFile || uploadImage.isPending}
            onClick={() => uploadImage.mutate()}
          >
            {uploadImage.isPending ? "Uploading…" : "Upload image"}
          </button>
          {s?.has_image_on_disk ? (
            <button
              type="button"
              className="px-3 py-1.5 rounded border border-slate-600 text-slate-400 text-sm hover:text-red-300"
              disabled={!enabled}
              onClick={() => {
                api.zipBundle.patch({ clear_image: true }).then(() => {
                  qc.invalidateQueries({ queryKey: ["zipBundleSettings"] });
                  setEdited(false);
                });
              }}
            >
              Remove image
            </button>
          ) : null}
        </div>
      </div>
      <button
        type="button"
        className="mt-4 px-4 py-2 rounded bg-cyan-700 text-white text-sm hover:bg-cyan-600 disabled:opacity-50"
        disabled={save.isPending}
        onClick={() => save.mutate()}
      >
        {save.isPending ? "Saving…" : "Save ZIP promo settings"}
      </button>
      {save.isError ? (
        <p className="text-xs text-red-400 mt-2">{save.error instanceof Error ? save.error.message : "Save failed"}</p>
      ) : null}
    </section>
  );
}

function GallerySendPromoSection() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["gallerySendPromo"], queryFn: () => api.gallerySendPromo.get() });
  const [enabled, setEnabled] = useState(true);
  const [promoFile, setPromoFile] = useState<File | null>(null);
  const [label, setLabel] = useState("");

  const s = q.data?.settings;

  useEffect(() => {
    if (!s) return;
    setEnabled(s.enabled !== false);
  }, [s]);

  const save = useMutation({
    mutationFn: () => api.gallerySendPromo.patch({ enabled }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["gallerySendPromo"] }),
  });

  const upload = useMutation({
    mutationFn: () => {
      if (!promoFile) throw new Error("Pick an image");
      return api.gallerySendPromo.uploadImage(promoFile, label.trim() || undefined);
    },
    onSuccess: () => {
      setPromoFile(null);
      setLabel("");
      qc.invalidateQueries({ queryKey: ["gallerySendPromo"] });
    },
  });

  const images = s?.images ?? [];

  return (
    <section className="h-full border border-amber-800/40 rounded-lg p-6 bg-amber-950/10">
      <h2 className="text-lg font-medium text-amber-100 mb-1">Gallery send promo</h2>
      <p className="text-slate-400 text-sm mb-4">
        Closing tile included in the <strong className="text-slate-300">last album</strong> of gallery batch sends (Saved Messages,
        channel, group, topic) — like a logo card at the end of a Fapello album. Gallery toolbar ★ to pick the active
        tile; extension option <strong className="text-slate-300">Append</strong> in Send settings.
      </p>
      {q.isError ? (
        <QueryErrorBanner
          title="Could not load send promo settings"
          message={String(q.error instanceof Error ? q.error.message : q.error ?? "Unknown")}
          onRetry={() => void q.refetch()}
        />
      ) : null}
      <label className="flex items-center gap-2 text-sm text-slate-200 mb-4">
        <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
        Enable send promo tail
      </label>
      <div className="flex flex-wrap gap-2 mb-3">
        {images.map((img) => (
          <div key={img.id} className="relative w-20 h-20 rounded border border-slate-600 overflow-hidden">
            <img src={img.url} alt={img.label || ""} className="w-full h-full object-cover" />
            {img.id === s?.active_image_id ? (
              <span className="absolute top-0 left-0 text-[9px] bg-amber-600 text-white px-1">active</span>
            ) : null}
            <button
              type="button"
              className="absolute bottom-0 inset-x-0 text-[9px] bg-black/70 text-slate-200 py-0.5"
              onClick={() => api.gallerySendPromo.patch({ active_image_id: img.id }).then(() => qc.invalidateQueries({ queryKey: ["gallerySendPromo"] }))}
            >
              Use
            </button>
          </div>
        ))}
        {!images.length ? <p className="text-xs text-slate-500">No promo images yet.</p> : null}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <input
          type="text"
          className="bg-slate-800 border border-slate-600 rounded px-2 py-1 text-sm text-slate-200 w-28"
          placeholder="Label"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
        />
        <input type="file" accept="image/jpeg,image/png,image/webp" onChange={(e) => setPromoFile(e.target.files?.[0] ?? null)} />
        <button
          type="button"
          className="px-3 py-1.5 rounded bg-slate-700 text-slate-200 text-sm disabled:opacity-40"
          disabled={!promoFile || upload.isPending}
          onClick={() => upload.mutate()}
        >
          {upload.isPending ? "Uploading…" : "Add image"}
        </button>
        <button
          type="button"
          className="px-3 py-1.5 rounded bg-cyan-800 text-white text-sm disabled:opacity-40"
          disabled={save.isPending}
          onClick={() => save.mutate()}
        >
          Save
        </button>
      </div>
    </section>
  );
}

function K2SLibrarySection() {
  const qc = useQueryClient();
  const statusQ = useQuery({ queryKey: ["k2sStatus"], queryFn: () => api.k2s.status(), retry: false });
  const [lane, setLane] = useState("packs");
  const [checkUrl, setCheckUrl] = useState("");
  const [mirrorModId, setMirrorModId] = useState("");
  const libraryQ = useQuery({
    queryKey: ["k2sLibrary", lane],
    queryFn: () => api.k2s.library(lane),
    enabled: statusQ.data?.configured === true,
    retry: false,
  });
  const ensureFolders = useMutation({
    mutationFn: () => api.k2s.ensureFolders(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["k2sStatus"] });
      qc.invalidateQueries({ queryKey: ["k2sLibrary"] });
    },
  });
  const check = useMutation({
    mutationFn: () => api.k2s.checkUrl(checkUrl.trim()),
  });
  const mirror = useMutation({
    mutationFn: () => {
      const id = parseInt(mirrorModId, 10);
      if (!id) throw new Error("Enter modifier id");
      return api.k2s.mirror(id, lane);
    },
  });
  const st = statusQ.data;
  const lanes = st?.lanes ?? [];

  return (
    <section
      id="k2s-library"
      className="h-full border border-slate-700 rounded-lg p-6 bg-slate-900/40 overflow-visible xl:col-span-2"
    >
      <h2 className="text-lg font-medium text-slate-100 mb-1">Keep2Share library</h2>
      <p className="text-slate-400 text-sm mb-4">
        Lane folders for <strong className="text-slate-300">main</strong>,{" "}
        <strong className="text-slate-300">AI</strong>,{" "}
        <strong className="text-slate-300">taboo</strong>,{" "}
        <strong className="text-slate-300">voyeur</strong>, packs, and loot. MEGA resolves mirror here;
        VIP gets direct <code className="text-slate-500">getUrl</code> when mirrored.
      </p>
      <div className="flex flex-wrap gap-2 text-xs mb-4">
        <span className={`px-2 py-0.5 rounded ${st?.enabled ? "bg-emerald-900 text-emerald-200" : "bg-slate-800 text-slate-400"}`}>
          {st?.enabled ? "enabled" : "disabled"}
        </span>
        <span className={`px-2 py-0.5 rounded ${st?.configured ? "bg-emerald-900 text-emerald-200" : "bg-amber-900 text-amber-200"}`}>
          {st?.configured ? "API configured" : "needs TBCC_K2S_ACCESS_TOKEN"}
        </span>
        <span className={`px-2 py-0.5 rounded ${st?.mirror_enabled ? "bg-cyan-900 text-cyan-200" : "bg-slate-800 text-slate-400"}`}>
          mirror {st?.mirror_enabled ? "on" : "off"}
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-2 mb-4">
        <select
          className="bg-slate-800 border border-slate-600 rounded px-2 py-1 text-sm text-slate-200"
          value={lane}
          onChange={(e) => setLane(e.target.value)}
        >
          {lanes.map((l) => (
            <option key={l.lane} value={l.lane}>
              {l.folder_name || l.lane}
              {l.folder_id ? ` (${l.folder_id.slice(0, 8)}…)` : ""}
            </option>
          ))}
        </select>
        <button
          type="button"
          className="px-3 py-1.5 rounded bg-slate-700 text-slate-200 text-sm disabled:opacity-40"
          disabled={!st?.configured || ensureFolders.isPending}
          onClick={() => ensureFolders.mutate()}
        >
          {ensureFolders.isPending ? "Creating…" : "Ensure lane folders"}
        </button>
        <button
          type="button"
          className="px-3 py-1.5 rounded bg-slate-700 text-slate-200 text-sm disabled:opacity-40"
          disabled={!st?.configured}
          onClick={() => qc.invalidateQueries({ queryKey: ["k2sLibrary", lane] })}
        >
          Refresh library
        </button>
      </div>
      <div className="grid gap-4 md:grid-cols-2 mb-4">
        <div className="space-y-2">
          <label className="text-xs text-slate-400 block">Dead-link check (K2S + file hosts)</label>
          <div className="flex gap-2">
            <input
              type="url"
              className="flex-1 bg-slate-800 border border-slate-600 rounded px-2 py-1 text-sm text-slate-200"
              placeholder="https://k2s.cc/file/…"
              value={checkUrl}
              onChange={(e) => setCheckUrl(e.target.value)}
            />
            <button
              type="button"
              className="px-3 py-1.5 rounded bg-violet-800 text-white text-sm disabled:opacity-40"
              disabled={!checkUrl.trim() || check.isPending}
              onClick={() => check.mutate()}
            >
              Check
            </button>
          </div>
          {check.data ? (
            <p className={`text-xs ${check.data.ok ? "text-emerald-400" : "text-rose-400"}`}>
              {check.data.ok ? "Live" : "Dead"} · {check.data.host_kind || "unknown"}
              {check.data.reason ? ` · ${check.data.reason}` : ""}
            </p>
          ) : null}
        </div>
        <div className="space-y-2">
          <label className="text-xs text-slate-400 block">Manual mirror (loot modifier id)</label>
          <div className="flex gap-2">
            <input
              type="text"
              className="w-28 bg-slate-800 border border-slate-600 rounded px-2 py-1 text-sm text-slate-200"
              placeholder="mod id"
              value={mirrorModId}
              onChange={(e) => setMirrorModId(e.target.value)}
            />
            <button
              type="button"
              className="px-3 py-1.5 rounded bg-cyan-800 text-white text-sm disabled:opacity-40"
              disabled={!mirrorModId.trim() || !st?.mirror_enabled || mirror.isPending}
              onClick={() => mirror.mutate()}
            >
              Mirror to K2S
            </button>
          </div>
          {mirror.data ? (
            <p className="text-xs text-slate-400 truncate">
              {String((mirror.data as { ok?: boolean }).ok ? "OK" : "Failed")}{" "}
              {(mirror.data as { k2s_url?: string }).k2s_url || (mirror.data as { error?: string }).error || ""}
            </p>
          ) : null}
        </div>
      </div>
      {libraryQ.isError ? (
        <p className="text-xs text-amber-400">Library unavailable — configure K2S token and ensure folders.</p>
      ) : (
        <div className="max-h-64 overflow-auto border border-slate-800 rounded">
          <table className="w-full text-xs text-left">
            <thead className="text-slate-500 sticky top-0 bg-slate-900">
              <tr>
                <th className="p-2">Name</th>
                <th className="p-2">Size</th>
                <th className="p-2">Link</th>
              </tr>
            </thead>
            <tbody>
              {(libraryQ.data?.files ?? []).map((f) => (
                <tr key={f.id} className="border-t border-slate-800">
                  <td className="p-2 text-slate-200">{f.name || f.id}</td>
                  <td className="p-2 text-slate-400">{f.size ? `${Math.round(f.size / 1024 / 1024)} MB` : "—"}</td>
                  <td className="p-2">
                    {f.public_url ? (
                      <a href={f.public_url} className="text-cyan-400 hover:underline" target="_blank" rel="noreferrer">
                        open
                      </a>
                    ) : (
                      "—"
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!libraryQ.data?.files?.length && !libraryQ.isLoading ? (
            <p className="text-xs text-slate-500 p-3">No files in this lane folder yet.</p>
          ) : null}
        </div>
      )}
    </section>
  );
}

function MainChannelDividerSection() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["mainChannelDivider"], queryFn: () => api.mainChannelDivider.get() });
  const emojiSrcQ = useQuery({
    queryKey: ["mainChannelDividerEmojiSources"],
    queryFn: () => api.mainChannelDivider.listEmojiFactorySources(),
  });
  const [enabled, setEnabled] = useState(false);
  const [rotateImages, setRotateImages] = useState(true);
  const [applyInTopics, setApplyInTopics] = useState(false);
  const [dividerFile, setDividerFile] = useState<File | null>(null);
  const [label, setLabel] = useState("");

  const s = q.data?.settings;

  useEffect(() => {
    if (!s) return;
    setEnabled(s.enabled === true);
    setRotateImages(s.rotate_images !== false);
    setApplyInTopics(s.apply_in_topics === true);
  }, [s]);

  const save = useMutation({
    mutationFn: () =>
      api.mainChannelDivider.patch({
        enabled,
        rotate_images: rotateImages,
        apply_in_topics: applyInTopics,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["mainChannelDivider"] }),
  });

  const upload = useMutation({
    mutationFn: () => {
      if (!dividerFile) throw new Error("Pick an image");
      return api.mainChannelDivider.uploadImage(dividerFile, label.trim() || undefined);
    },
    onSuccess: () => {
      setDividerFile(null);
      setLabel("");
      qc.invalidateQueries({ queryKey: ["mainChannelDivider"] });
    },
  });

  const importEmoji = useMutation({
    mutationFn: (body: { job_id: string; tile: string; label?: string }) =>
      api.mainChannelDivider.importFromEmojiFactory(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["mainChannelDivider"] });
    },
  });

  const images = s?.images ?? [];
  const emojiJobs = emojiSrcQ.data?.jobs ?? [];

  return (
    <section className="h-full border border-violet-800/40 rounded-lg p-6 bg-violet-950/10">
      <h2 className="text-lg font-medium text-violet-100 mb-1">Main channel post dividers</h2>
      <p className="text-slate-400 text-sm mb-4">
        After each post to the <strong className="text-slate-300">AOF Main Group</strong> main chat, TBCC sends a
        standalone divider image (like the ornamental line in your reference). Telegram shows its own{" "}
        <strong className="text-slate-300">views + timestamp</strong> on that spacer message between content drops.
        Upload a transparent PNG of your divider art (horizontal line / flourish), or import a frame from a completed{" "}
        <strong className="text-slate-300">emoji splitter</strong> job below.
        <span className="block mt-2 text-slate-500 text-xs">
          Telegram <strong className="text-slate-400">custom emoji packs</strong> cannot be used as full-width dividers —
          they are tiny inline caption tiles (~100–512px), not standalone channel images.
        </span>
      </p>
      {q.isError ? (
        <QueryErrorBanner
          title="Could not load divider settings"
          message={String(q.error instanceof Error ? q.error.message : q.error ?? "Unknown")}
          onRetry={() => void q.refetch()}
        />
      ) : null}
      <label className="flex items-center gap-2 text-sm text-slate-200 mb-2">
        <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
        Enable dividers after main-chat posts
      </label>
      <label className="flex items-center gap-2 text-sm text-slate-200 mb-2">
        <input type="checkbox" checked={rotateImages} onChange={(e) => setRotateImages(e.target.checked)} />
        Rotate divider images (random pick when multiple uploaded)
      </label>
      <label className="flex items-center gap-2 text-sm text-slate-200 mb-4">
        <input type="checkbox" checked={applyInTopics} onChange={(e) => setApplyInTopics(e.target.checked)} />
        Also send after forum topic posts (off = main chat only)
      </label>
      <div className="flex flex-wrap gap-2 mb-3">
        {images.map((img) => (
          <div key={img.id} className="relative w-28 h-12 rounded border border-slate-600 overflow-hidden bg-slate-900">
            <img src={img.url} alt={img.label || ""} className="w-full h-full object-contain" />
            {img.id === s?.active_image_id ? (
              <span className="absolute top-0 left-0 text-[9px] bg-violet-600 text-white px-1">active</span>
            ) : null}
            <button
              type="button"
              className="absolute bottom-0 inset-x-0 text-[9px] bg-black/70 text-slate-200 py-0.5"
              onClick={() =>
                api.mainChannelDivider.patch({ active_image_id: img.id }).then(() =>
                  qc.invalidateQueries({ queryKey: ["mainChannelDivider"] })
                )
              }
            >
              Use
            </button>
          </div>
        ))}
        {!images.length ? <p className="text-xs text-slate-500">No divider images yet — upload your line art PNG.</p> : null}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <input
          type="text"
          className="bg-slate-800 border border-slate-600 rounded px-2 py-1 text-sm text-slate-200 w-28"
          placeholder="Label"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
        />
        <input type="file" accept="image/png,image/webp,image/jpeg" onChange={(e) => setDividerFile(e.target.files?.[0] ?? null)} />
        <button
          type="button"
          className="px-3 py-1.5 rounded bg-slate-700 text-slate-200 text-sm disabled:opacity-40"
          disabled={!dividerFile || upload.isPending}
          onClick={() => upload.mutate()}
        >
          {upload.isPending ? "Uploading…" : "Add divider"}
        </button>
        <button
          type="button"
          className="px-3 py-1.5 rounded bg-violet-800 text-white text-sm disabled:opacity-40"
          disabled={save.isPending}
          onClick={() => save.mutate()}
        >
          Save
        </button>
      </div>

      <div className="mt-5 pt-4 border-t border-violet-900/50">
        <h3 className="text-sm font-medium text-violet-200 mb-2">Import from emoji splitter</h3>
        <p className="text-xs text-slate-500 mb-3">
          Completed jobs in <code className="text-slate-400">.tbcc-run/emoji-factory-jobs</code> — import single tiles,
          or use <strong className="text-slate-400">row strips</strong> (full horizontal crop per grid row) for dividers.
        </p>
        {emojiSrcQ.isError ? (
          <p className="text-xs text-red-400 mb-2">Could not list emoji factory jobs.</p>
        ) : null}
        {!emojiJobs.length && !emojiSrcQ.isLoading ? (
          <p className="text-xs text-slate-500">No completed emoji splitter jobs found.</p>
        ) : null}
        {emojiJobs.map((job) => (
          <details key={job.job_id} className="mb-3 rounded border border-slate-700/80 bg-slate-900/40 p-2">
            <summary className="cursor-pointer text-xs text-slate-300">
              Job {job.job_id} · {job.cols}×{job.rows} grid · {job.tile_count} tiles
              {job.tile_px ? ` · ${job.tile_px}px` : ""}
            </summary>
            <div className="mt-2 flex flex-wrap gap-2">
              {job.has_normalized ? (
                <button
                  type="button"
                  className="text-left rounded border border-slate-600 p-1 hover:border-violet-500"
                  disabled={importEmoji.isPending}
                  onClick={() =>
                    importEmoji.mutate({ job_id: job.job_id, tile: "normalized", label: `master ${job.job_id.slice(0, 8)}` })
                  }
                >
                  <img
                    src={job.normalized_preview_url}
                    alt="normalized master"
                    className="w-24 h-16 object-contain bg-black/40"
                  />
                  <span className="block text-[9px] text-slate-400 mt-0.5">full master</span>
                </button>
              ) : null}
              {job.tiles.map((tile) => (
                <button
                  key={tile.tile}
                  type="button"
                  className="text-left rounded border border-slate-600 p-1 hover:border-violet-500"
                  disabled={importEmoji.isPending}
                  onClick={() =>
                    importEmoji.mutate({
                      job_id: job.job_id,
                      tile: tile.tile,
                      label: `${tile.emoji || ""} ${tile.tile}`.trim(),
                    })
                  }
                >
                  <img src={tile.preview_url} alt={tile.tile} className="w-14 h-14 object-contain bg-black/40" />
                  <span className="block text-[9px] text-slate-400 mt-0.5">
                    {tile.emoji} {tile.row},{tile.col}
                  </span>
                </button>
              ))}
            </div>
            {job.row_strips?.length ? (
              <div className="mt-3">
                <EmojiFactoryRowDividers
                  jobId={job.job_id}
                  rows={job.rows}
                  rowStrips={job.row_strips}
                  compact
                />
              </div>
            ) : null}
          </details>
        ))}
      </div>
    </section>
  );
}

type MiscTab = "tools" | "emoji";

export function MiscPanel({ initialTab = "tools" }: { initialTab?: MiscTab }) {
  const location = useLocation();
  const navigate = useNavigate();
  const [tab, setTab] = useState<MiscTab>(initialTab);

  useEffect(() => {
    if (location.pathname.includes("/emoji")) setTab("emoji");
    else if (location.pathname === "/misc") setTab("tools");
  }, [location.pathname]);

  function selectMiscTab(next: MiscTab) {
    setTab(next);
    navigate(next === "emoji" ? "/misc/emoji" : "/misc", { replace: true });
  }
  const qc = useQueryClient();
  const channelsQ = useQuery({ queryKey: ["channels"], queryFn: () => api.channels.list() });
  const poolsQ = useQuery({ queryKey: ["pools"], queryFn: () => api.pools.list() });
  const relayQ = useQuery({
    queryKey: ["listeningRelay"],
    queryFn: () => api.listeningRelay.get(),
  });
  const relayDestQ = useQuery({
    queryKey: ["listeningRelayDestinations"],
    queryFn: () => api.listeningRelay.destinations(),
  });
  const asciiQ = useQuery({
    queryKey: ["listeningRelayAscii"],
    queryFn: () => api.listeningRelay.listAsciiArt(),
    retry: false,
  });
  const { data: subscriptionPlansRaw = [] } = useQuery({
    queryKey: ["subscriptionPlans"],
    queryFn: () => api.subscriptionPlans.list(),
  });
  const salablePlans = (subscriptionPlansRaw as Array<Record<string, unknown>>).filter(
    (p) => p.is_active !== false && Number(p.price_stars || 0) > 0
  ) as Array<{ id: number; name?: string; price_stars?: number; product_type?: string }>;

  const [webhookSecret, setWebhookSecret] = useState<string | null>(null);
  const [enabled, setEnabled] = useState(false);
  const [channelId, setChannelId] = useState<number | typeof RELAY_RANDOM_CHANNEL | "">("");
  const [forumDest, setForumDest] = useState<string>("");
  const [lastfmUser, setLastfmUser] = useState("");
  const [lastfmKey, setLastfmKey] = useState("");
  const [pollMinutes, setPollMinutes] = useState(3);
  const [templateVariants, setTemplateVariants] = useState<string[]>([""]);
  const [footerVariants, setFooterVariants] = useState<string[]>([""]);
  const [copyBlockVariants, setCopyBlockVariants] = useState<string[]>([""]);
  const [slotExtras, setSlotExtras] = useState<RelaySlotExtra[]>([{ ...EMPTY_RELAY_SLOT_EXTRA }]);
  const [templateRotationMode, setTemplateRotationMode] = useState<"sequential" | "random">("sequential");
  const [asciiArtEnabled, setAsciiArtEnabled] = useState(false);
  const [asciiMinInterval, setAsciiMinInterval] = useState(3);
  const [asciiMaxInterval, setAsciiMaxInterval] = useState(6);
  const [tryptychEnabled, setTryptychEnabled] = useState(false);
  const [tryptychOnAsciiBeat, setTryptychOnAsciiBeat] = useState(true);
  const [asciiUploadName, setAsciiUploadName] = useState("");
  const [asciiUploadBody, setAsciiUploadBody] = useState("");
  const [templatePage, setTemplatePage] = useState(0);
  const [sendSilent, setSendSilent] = useState(true);
  const [bufferRelayEnabled, setBufferRelayEnabled] = useState(false);
  const [bufferRelayMinMinutes, setBufferRelayMinMinutes] = useState(360);
  const [bufferRelayMaxPerDay, setBufferRelayMaxPerDay] = useState(5);
  const [goblinModeEnabled, setGoblinModeEnabled] = useState(false);
  const [goblinSpawnChance, setGoblinSpawnChance] = useState(0.2);
  const [goblinCooldownMinutes, setGoblinCooldownMinutes] = useState(120);
  const [goblinAnnounceTtl, setGoblinAnnounceTtl] = useState(45);
  const [goblinClaimsCap, setGoblinClaimsCap] = useState(5);
  const [goblinMaxPerDay, setGoblinMaxPerDay] = useState(3);
  const [edited, setEdited] = useState(false);

  const s = relayQ.data?.settings;

  useEffect(() => {
    const relayTotalPages = Math.max(1, Math.ceil(templateVariants.length / 16));
    setTemplatePage((p) => Math.min(Math.max(0, p), relayTotalPages - 1));
  }, [templateVariants.length]);

  useEffect(() => {
    if (relayQ.data?.webhook_secret) {
      setWebhookSecret(relayQ.data.webhook_secret);
    }
  }, [relayQ.data?.webhook_secret]);

  useEffect(() => {
    if (!s || edited) return;
    setEnabled(Boolean(s.enabled));
    setChannelId(relayChannelSelectValue(s));
    setForumDest(relayForumDestFromSettings(s, relayDestQ.data));
    setLastfmUser(String(s.lastfm_username || ""));
    setLastfmKey("");
    setPollMinutes(Number(s.poll_interval_minutes || 3));
    const { templates, footers, copyBlocks, slotExtras: ex } = relaySlotsFromApiSettings(s);
    setTemplateVariants(templates);
    setFooterVariants(footers);
    setCopyBlockVariants(copyBlocks);
    setSlotExtras(ex);
    setTemplateRotationMode(s.template_rotation_mode === "random" ? "random" : "sequential");
    setAsciiArtEnabled(Boolean(s.ascii_art_enabled));
    setAsciiMinInterval(Number(s.ascii_art_min_interval ?? 3));
    setAsciiMaxInterval(Number(s.ascii_art_max_interval ?? 6));
    setTryptychEnabled(Boolean(s.tryptych_enabled));
    setTryptychOnAsciiBeat(s.tryptych_on_ascii_beat !== false);
    setSendSilent(s.send_silent !== false);
    setBufferRelayEnabled(Boolean(s.buffer_relay_enabled));
    setBufferRelayMinMinutes(Number(s.buffer_relay_min_interval_minutes ?? 360));
    setBufferRelayMaxPerDay(Number(s.buffer_relay_max_per_day_utc ?? 5));
    setGoblinModeEnabled(Boolean(s.goblin_mode_enabled));
    setGoblinSpawnChance(Number(s.goblin_spawn_chance ?? 0.2));
    setGoblinCooldownMinutes(Number(s.goblin_cooldown_minutes ?? 120));
    setGoblinAnnounceTtl(Number(s.goblin_announce_ttl_seconds ?? 45));
    setGoblinClaimsCap(Number(s.goblin_claims_cap ?? 5));
    setGoblinMaxPerDay(Number(s.goblin_max_per_day_utc ?? 3));
  }, [s, edited, relayDestQ.data]);

  const lootRoomChannelId = relayDestQ.data?.loot_room?.channel_id ?? null;
  const vipChannelId = relayDestQ.data?.vip?.channel_id ?? null;

  const lootTopicsQ = useQuery({
    queryKey: ["forumTopics", "lootRoom", lootRoomChannelId],
    queryFn: () => api.channels.forumTopics(Number(lootRoomChannelId)),
    enabled: typeof lootRoomChannelId === "number" && lootRoomChannelId > 0,
  });

  const topicsChannelId =
    channelId === RELAY_RANDOM_CHANNEL || channelId === "" || forumDest === "vip"
      ? null
      : forumDest.startsWith("loot:")
        ? lootRoomChannelId
        : typeof channelId === "number"
          ? channelId
          : null;

  const topicsQ = useQuery({
    queryKey: ["forumTopics", topicsChannelId],
    queryFn: () => api.channels.forumTopics(Number(topicsChannelId)),
    enabled: typeof topicsChannelId === "number" && topicsChannelId > 0 && !forumDest.startsWith("loot:") && forumDest !== "vip",
  });

  const lootTopicOptions = (() => {
    const live = lootTopicsQ.data?.topics ?? [];
    if (live.length > 0) return live;
    return relayDestQ.data?.loot_room?.topics ?? [];
  })();

  const save = useMutation({
    mutationFn: async () => {
      const trimmedTemplates: string[] = [];
      const footersParallel: string[] = [];
      const copyParallel: string[] = [];
      const extrasParallel: RelaySlotExtra[] = [];
      templateVariants.forEach((t, i) => {
        const ts = String(t ?? "").trim();
        const fv = String(footerVariants[i] ?? "");
        const cv = String(copyBlockVariants[i] ?? "");
        const ex = normalizeRelaySlotExtra(slotExtras[i]);
        const hasExtra =
          ex.copy_buttons.some((b) => b.text.trim() && b.url.trim()) ||
          ex.copy_media_ids.length > 0 ||
          ex.copy_attachment_urls.length > 0 ||
          ex.copy_checkout_stars_enabled;
        if (!ts && !fv.trim() && !cv.trim() && !hasExtra) return;
        trimmedTemplates.push(ts);
        footersParallel.push(fv);
        copyParallel.push(cv);
        extrasParallel.push(ex);
      });
      const body: Record<string, unknown> = {
        enabled,
        lastfm_username: lastfmUser.trim() || null,
        poll_interval_minutes: Math.max(1, Math.min(120, Number(pollMinutes || 3))),
        message_template_variations: trimmedTemplates.length ? trimmedTemplates : null,
        message_footer_variations: trimmedTemplates.length ? footersParallel : null,
        message_copy_block_variations: trimmedTemplates.length ? copyParallel : null,
        message_slot_extras: trimmedTemplates.length ? extrasParallel : null,
        template_rotation_mode: templateRotationMode,
        ascii_art_enabled: asciiArtEnabled,
        ascii_art_min_interval: Math.max(1, Math.min(50, Number(asciiMinInterval || 3))),
        ascii_art_max_interval: Math.max(
          Math.max(1, Number(asciiMinInterval || 3)),
          Math.min(50, Number(asciiMaxInterval || 6))
        ),
        tryptych_enabled: tryptychEnabled,
        tryptych_on_ascii_beat: tryptychOnAsciiBeat,
        message_template_html: null,
        send_silent: sendSilent,
        buffer_relay_enabled: bufferRelayEnabled,
        buffer_relay_min_interval_minutes: Math.max(30, Math.min(1440, Number(bufferRelayMinMinutes || 360))),
        buffer_relay_max_per_day_utc: Math.max(1, Math.min(50, Number(bufferRelayMaxPerDay || 5))),
        goblin_mode_enabled: goblinModeEnabled,
        goblin_spawn_chance: Math.max(0, Math.min(1, Number(goblinSpawnChance || 0.2))),
        goblin_cooldown_minutes: Math.max(0, Math.min(1440, Number(goblinCooldownMinutes || 120))),
        goblin_announce_ttl_seconds: Math.max(5, Math.min(300, Number(goblinAnnounceTtl || 45))),
        goblin_claims_cap: Math.max(1, Math.min(100, Number(goblinClaimsCap || 5))),
        goblin_max_per_day_utc: Math.max(1, Math.min(50, Number(goblinMaxPerDay || 3))),
      };
      if (channelId === RELAY_RANDOM_CHANNEL) {
        body.relay_random_network_channel = true;
        body.channel_id = null;
        body.message_thread_id = null;
      } else if (forumDest === "vip") {
        body.relay_random_network_channel = false;
        body.channel_id = vipChannelId;
        body.message_thread_id = null;
      } else if (forumDest.startsWith("loot:")) {
        const tid = forumDest.slice(5);
        body.relay_random_network_channel = false;
        body.channel_id = lootRoomChannelId;
        body.message_thread_id = tid === "" || tid === "0" ? null : Number(tid);
      } else {
        body.relay_random_network_channel = false;
        body.channel_id = channelId === "" ? null : Number(channelId);
        body.message_thread_id = forumDest.startsWith("topic:") ? Number(forumDest.slice(6)) : null;
      }
      if (lastfmKey.trim()) {
        body.lastfm_api_key = lastfmKey.trim();
      }
      return api.listeningRelay.patch(body);
    },
    onSuccess: (data) => {
      if (data.webhook_secret) setWebhookSecret(data.webhook_secret);
      setLastfmKey("");
      if (data.settings) {
        const st = data.settings;
        setEnabled(Boolean(st.enabled));
        setChannelId(relayChannelSelectValue(st));
        setForumDest(relayForumDestFromSettings(st, relayDestQ.data));
        setLastfmUser(String(st.lastfm_username || ""));
        setPollMinutes(Number(st.poll_interval_minutes || 3));
        const { templates, footers, copyBlocks, slotExtras: ex } = relaySlotsFromApiSettings(st);
        setTemplateVariants(templates);
        setFooterVariants(footers);
        setCopyBlockVariants(copyBlocks);
        setSlotExtras(ex);
        setTemplateRotationMode(st.template_rotation_mode === "random" ? "random" : "sequential");
        setAsciiArtEnabled(Boolean(st.ascii_art_enabled));
        setAsciiMinInterval(Number(st.ascii_art_min_interval ?? 3));
        setAsciiMaxInterval(Number(st.ascii_art_max_interval ?? 6));
        setTryptychEnabled(Boolean(st.tryptych_enabled));
        setTryptychOnAsciiBeat(st.tryptych_on_ascii_beat !== false);
        setSendSilent(st.send_silent !== false);
        setBufferRelayEnabled(Boolean(st.buffer_relay_enabled));
        setBufferRelayMinMinutes(Number(st.buffer_relay_min_interval_minutes ?? 360));
        setBufferRelayMaxPerDay(Number(st.buffer_relay_max_per_day_utc ?? 5));
        setGoblinModeEnabled(Boolean(st.goblin_mode_enabled));
        setGoblinSpawnChance(Number(st.goblin_spawn_chance ?? 0.2));
        setGoblinCooldownMinutes(Number(st.goblin_cooldown_minutes ?? 120));
        setGoblinAnnounceTtl(Number(st.goblin_announce_ttl_seconds ?? 45));
        setGoblinClaimsCap(Number(st.goblin_claims_cap ?? 5));
        setGoblinMaxPerDay(Number(st.goblin_max_per_day_utc ?? 3));
      }
      setEdited(false);
      qc.invalidateQueries({ queryKey: ["listeningRelay"] });
    },
  });

  const regen = useMutation({
    mutationFn: () => api.listeningRelay.patch({ regenerate_webhook_secret: true }),
    onSuccess: (data) => {
      if (data.webhook_secret) setWebhookSecret(data.webhook_secret);
      qc.invalidateQueries({ queryKey: ["listeningRelay"] });
    },
  });

  const clearLastfmDedupe = useMutation({
    mutationFn: () => api.listeningRelay.patch({ clear_lastfm_dedupe: true }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["listeningRelay"] }),
  });

  const clearHookDedupe = useMutation({
    mutationFn: () => api.listeningRelay.patch({ clear_webhook_dedupe: true }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["listeningRelay"] }),
  });

  const [promoBulkJson, setPromoBulkJson] = useState("");
  const [affiliatePreviewPlacement, setAffiliatePreviewPlacement] = useState("telegram_footer");
  const [affiliateNetworkKey, setAffiliateNetworkKey] = useState("ai");
  const promoStatsQ = useQuery({
    queryKey: ["promoAffiliateStats"],
    queryFn: () => api.promoAffiliateLinks.stats(),
  });
  const promoPreviewQ = useQuery({
    queryKey: ["promoAffiliatePreview", affiliatePreviewPlacement, affiliateNetworkKey],
    queryFn: () =>
      api.promoAffiliateLinks.previewRotation({
        placement: affiliatePreviewPlacement,
        network_key: affiliateNetworkKey || undefined,
        count: 5,
      }),
  });
  const promoLinksListQ = useQuery({
    queryKey: ["promoAffiliateLinks", "misc-panel"],
    queryFn: () => api.promoAffiliateLinks.list({ sort: "priority_asc", active_only: true }),
  });
  const promoBulkImport = useMutation({
    mutationFn: (body: {
      items: Array<{
        label: string;
        url: string;
        short_url?: string | null;
        payout_kind?: string;
        payout_detail?: string | null;
        priority_tier?: number;
        expires_at?: string | null;
        active?: boolean;
        placements?: string[];
        network_keys?: string[];
        copy_template?: string | null;
      }>;
    }) => api.promoAffiliateLinks.bulk(body),
    onSuccess: () => {
      setPromoBulkJson("");
      qc.invalidateQueries({ queryKey: ["promoAffiliateLinks"] });
      qc.invalidateQueries({ queryKey: ["promoAffiliateStats"] });
      qc.invalidateQueries({ queryKey: ["promoAffiliatePreview"] });
    },
  });
  const syncAffiliateRotation = useMutation({
    mutationFn: () => api.growthHub.syncAffiliateRotation(),
    onSuccess: (r) => {
      const n = r.affiliate?.active_rows ?? 0;
      const partners = r.bulletin_has_partners ? "yes" : "no";
      qc.invalidateQueries({ queryKey: ["growth-hub-status"] });
      qc.invalidateQueries({ queryKey: ["scheduledPosts"] });
      window.alert(`Affiliate sync done — ${n} active rows · partners in bulletin: ${partners}`);
    },
  });

  const preview = useMutation({
    mutationFn: () => api.listeningRelay.lastfmPreview(),
  });

  const testPost = useMutation({
    mutationFn: () => api.listeningRelay.testPost(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["listeningRelayHistory"] }),
  });

  const [bufferTestMsg, setBufferTestMsg] = useState<string | null>(null);
  const bufferTest = useMutation({
    mutationFn: () => api.listeningRelay.bufferTestPost({ x_only: true }),
    onSuccess: (data) => {
      const n = data.queued?.length ?? 0;
      setBufferTestMsg(
        n
          ? `Queued ${n} post(s) in Buffer (X). Open publish.buffer.com → Queue.`
          : "Buffer returned no queued posts — check API response / errors."
      );
      window.setTimeout(() => setBufferTestMsg(null), 12000);
    },
    onError: (err: unknown) => {
      setBufferTestMsg(err instanceof Error ? err.message : "Buffer test failed");
      window.setTimeout(() => setBufferTestMsg(null), 12000);
    },
  });

  const channels = channelsQ.data ?? [];
  const webhookUrlBase =
    typeof window !== "undefined"
      ? `${window.location.origin}/api/listening-relay/webhook/`
      : "/api/listening-relay/webhook/";

  return (
    <div className="max-w-7xl pb-16 space-y-8">
      <h1 className="text-2xl font-semibold mb-2">Misc</h1>
      <p className="text-slate-400 mb-4 max-w-4xl">
        Listening relay, caption emoji tools, affiliate promos, and split-grid emoji pack workflow.
      </p>

      <div className="flex gap-1 mb-6 border-b border-slate-700 flex-wrap">
        <button
          type="button"
          onClick={() => selectMiscTab("tools")}
          className={`px-4 py-2 text-sm font-medium rounded-t-lg border-b-2 -mb-px transition-colors ${
            tab === "tools"
              ? "border-cyan-500 text-cyan-400 bg-slate-800/80"
              : "border-transparent text-slate-400 hover:text-slate-200"
          }`}
        >
          Relay &amp; tools
        </button>
        <button
          type="button"
          onClick={() => selectMiscTab("emoji")}
          className={`px-4 py-2 text-sm font-medium rounded-t-lg border-b-2 -mb-px transition-colors ${
            tab === "emoji"
              ? "border-cyan-500 text-cyan-400 bg-slate-800/80"
              : "border-transparent text-slate-400 hover:text-slate-200"
          }`}
        >
          Emoji packs
        </button>
      </div>

      {tab === "emoji" ? (
        <EmojiFactoryPanel embedded />
      ) : (
        <>
      <p className="text-slate-400 mb-4 max-w-4xl -mt-4">
        Listening relay posts what you are playing or watching to a Telegram channel — similar to a Last.fm + IFTTT
        pipeline, but centralized in TBCC.
      </p>

      <EmojiPackWayfinding />

      <CustomEmojiTools />

      <section className="border border-slate-700 rounded-lg p-6 bg-slate-900/40 overflow-visible">
        <h2 className="text-lg font-medium text-slate-100 mb-1">Listening relay</h2>
        <p className="text-slate-400 text-sm mb-6">
          <strong className="text-slate-300">Last.fm</strong> picks up{" "}
          <span className="text-slate-300">Spotify</span>, <span className="text-slate-300">SoundCloud</span> (when
          linked to Last.fm), and other scrobbled sources. For <span className="text-slate-300">YouTube</span>, use a
          browser scrobbler to Last.fm, or send events through the webhook below (IFTTT, Zapier, etc.).
        </p>

        {(relayQ.isError || channelsQ.isError) && (
          <QueryErrorBanner
            title="Could not load listening relay or channels"
            message={String(
              (relayQ.error ?? channelsQ.error) instanceof Error
                ? (relayQ.error ?? channelsQ.error)?.message
                : relayQ.error ?? channelsQ.error ?? "Unknown error"
            )}
            onRetry={() => {
              void relayQ.refetch();
              void channelsQ.refetch();
            }}
          />
        )}
        {(save.isError || regen.isError || preview.isError || testPost.isError) && (
          <QueryErrorBanner
            title="Action failed"
            message={String(
              (save.error ?? regen.error ?? preview.error ?? testPost.error) instanceof Error
                ? (save.error ?? regen.error ?? preview.error ?? testPost.error)?.message
                : save.error ?? regen.error ?? preview.error ?? testPost.error ?? "Unknown error"
            )}
            onRetry={() => {
              save.reset();
              regen.reset();
              preview.reset();
              testPost.reset();
            }}
          />
        )}

        <div className="space-y-4">
          <label className="flex items-center gap-2 text-sm text-slate-200">
            <input
              type="checkbox"
              checked={enabled}
              onChange={(e) => {
                setEdited(true);
                setEnabled(e.target.checked);
              }}
            />
            Enable relay (requires Celery beat + worker + Redis for Last.fm polling)
          </label>

          {edited ? (
            <p className="text-sm text-amber-200/95 rounded border border-amber-600/60 bg-amber-950/35 px-3 py-2">
              <strong className="font-medium">Unsaved changes.</strong> Celery only sees what was last written by{" "}
              <strong className="font-medium">Save settings</strong>. If your editor shows more slots than workers use,
              click Save once and confirm the slot count below matches — or verify API + worker share the same{" "}
              <code className="text-amber-100/90 text-xs">DATABASE_URL</code>.
            </p>
          ) : null}

          {!edited && s ? (
            <p className="text-xs text-slate-500">
              Saved on server: <strong className="text-slate-400">{s.message_template_variations?.length ?? 0}</strong>{" "}
              template slots (rotation cycles 0 → N−1 each new track).
            </p>
          ) : null}

          {edited && s ? (
            <p className="text-xs text-slate-500">
              Editor: <strong className="text-slate-400">{templateVariants.length}</strong> slots · Last saved:{" "}
              <strong className="text-slate-400">{s.message_template_variations?.length ?? 0}</strong> slots
            </p>
          ) : null}

          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block text-sm">
              <span className="text-slate-400">Telegram channel</span>
              <select
                className="mt-1 w-full bg-slate-800 border border-slate-600 rounded px-3 py-2 text-slate-100"
                value={channelId === "" ? "" : String(channelId)}
                onChange={(e) => {
                  setEdited(true);
                  const v = e.target.value;
                  if (v === RELAY_RANDOM_CHANNEL) {
                    setChannelId(RELAY_RANDOM_CHANNEL);
                    setForumDest("");
                    return;
                  }
                  setChannelId(v ? Number(v) : "");
                  setForumDest("");
                }}
              >
                <option value="">— select —</option>
                <option value={RELAY_RANDOM_CHANNEL}>
                  🎲 Random — any AOF network channel (one per scrobble)
                  {relayDestQ.data?.network_channel_count
                    ? ` · ${relayDestQ.data.network_channel_count} lanes`
                    : ""}
                </option>
                {channels.map((c) => (
                  <option key={String(c.id)} value={String(c.id)}>
                    {(c.name as string) || (c.identifier as string)} ({String(c.identifier)})
                  </option>
                ))}
              </select>
              {channelId === RELAY_RANDOM_CHANNEL ? (
                <span className="text-xs text-violet-300/90 mt-1 block">
                  Each new track posts once to a random lane main chat (not all channels at once).
                </span>
              ) : null}
            </label>
            <label className="block text-sm">
              <span className="text-slate-400">Forum topic (optional)</span>
              <select
                className="mt-1 w-full bg-slate-800 border border-slate-600 rounded px-3 py-2 text-slate-100"
                value={forumDest}
                onChange={(e) => {
                  setEdited(true);
                  const v = e.target.value;
                  setForumDest(v);
                  if (v === "vip" && vipChannelId) {
                    setChannelId(vipChannelId);
                  } else if (v.startsWith("loot:") && lootRoomChannelId) {
                    setChannelId(lootRoomChannelId);
                  } else if (channelId === RELAY_RANDOM_CHANNEL) {
                    setChannelId("");
                  }
                }}
                disabled={false}
              >
                <option value="">Main / non-forum</option>
                {lootRoomChannelId ? (
                  <optgroup label={relayDestQ.data?.loot_room?.name ?? "AOF LOOT ROOM"}>
                    {lootTopicOptions.map((t) => (
                      <option key={`loot-${t.id}`} value={`loot:${t.id}`}>
                        {t.title} (#{t.id})
                      </option>
                    ))}
                  </optgroup>
                ) : null}
                {vipChannelId ? (
                  <optgroup label="Paid lane">
                    <option value="vip">{relayDestQ.data?.vip?.name ?? "AOF VIP"}</option>
                  </optgroup>
                ) : null}
                {(topicsQ.data?.topics ?? []).length > 0 && typeof channelId === "number" ? (
                  <optgroup label="Topics (selected channel)">
                    {(topicsQ.data?.topics ?? []).map((t) => (
                      <option key={`topic-${t.id}`} value={`topic:${t.id}`}>
                        {t.title} (#{t.id})
                      </option>
                    ))}
                  </optgroup>
                ) : null}
              </select>
              {channelId === RELAY_RANDOM_CHANNEL ? (
                <span className="text-xs text-slate-500 mt-1 block">
                  Pick Loot Room topic or VIP above, or choose a fixed channel instead of random.
                </span>
              ) : null}
              {topicsQ.data?.error && !forumDest.startsWith("loot:") && forumDest !== "vip" ? (
                <span className="text-amber-400 text-xs mt-1 block">{topicsQ.data.error}</span>
              ) : null}
              {lootTopicsQ.data?.error && forumDest.startsWith("loot:") ? (
                <span className="text-amber-400 text-xs mt-1 block">{lootTopicsQ.data.error}</span>
              ) : null}
            </label>
          </div>

          <div className="border-t border-slate-700 pt-4">
            <h3 className="text-sm font-medium text-slate-200 mb-3">Last.fm polling</h3>
            <div className="grid gap-4 sm:grid-cols-2">
              <label className="block text-sm">
                <span className="text-slate-400">Last.fm username</span>
                <input
                  className="mt-1 w-full bg-slate-800 border border-slate-600 rounded px-3 py-2 text-slate-100"
                  value={lastfmUser}
                  onChange={(e) => {
                    setEdited(true);
                    setLastfmUser(e.target.value);
                  }}
                  placeholder="your_username"
                />
              </label>
              <label className="block text-sm">
                <span className="text-slate-400">
                  API key {s?.lastfm_api_key_masked ? <>(saved: {s.lastfm_api_key_masked})</> : null}
                </span>
                <input
                  className="mt-1 w-full bg-slate-800 border border-slate-600 rounded px-3 py-2 text-slate-100"
                  value={lastfmKey}
                  onChange={(e) => {
                    setEdited(true);
                    setLastfmKey(e.target.value);
                  }}
                  placeholder={s?.lastfm_api_key_masked ? "Replace key (optional)" : "from last.fm/api/account"}
                  autoComplete="off"
                />
              </label>
            </div>
            <p className="text-xs text-slate-500 mt-2">
              Create an API key at{" "}
              <a className="text-cyan-400 hover:underline" href="https://www.last.fm/api/account/create" target="_blank" rel="noreferrer">
                last.fm/api/account/create
              </a>
              . Connect Spotify/SoundCloud in Last.fm “Applications” so plays appear in your recent tracks.
            </p>
            <label className="block text-sm mt-3">
              <span className="text-slate-400">Poll every (minutes)</span>
              <input
                type="number"
                min={1}
                max={120}
                className="mt-1 w-32 bg-slate-800 border border-slate-600 rounded px-3 py-2 text-slate-100"
                value={pollMinutes}
                onChange={(e) => {
                  setEdited(true);
                  setPollMinutes(Number(e.target.value));
                }}
              />
            </label>
          </div>

          <div className="flex flex-wrap items-center justify-end gap-2 mb-2 -mt-2">
            <TbccInsertLibraryToolbar />
          </div>
          <RelayTemplateSlotsEditor
            channels={(channelsQ.data ?? []) as Array<Record<string, unknown>>}
            pools={(poolsQ.data ?? []) as Array<Record<string, unknown>>}
            templateHint={TEMPLATE_HINT}
            rotationActive={templateVariants.filter((x) => String(x).trim()).length >= 2}
            templateVariants={templateVariants}
            footerVariants={footerVariants}
            copyBlockVariants={copyBlockVariants}
            slotExtras={slotExtras}
            templatePage={templatePage}
            onTemplatePageChange={setTemplatePage}
            salablePlans={salablePlans}
            onEdited={() => setEdited(true)}
            onTemplateVariantsChange={setTemplateVariants}
            onFooterVariantsChange={setFooterVariants}
            onCopyBlockVariantsChange={setCopyBlockVariants}
            onSlotExtrasChange={setSlotExtras}
          />

          <div className="grid gap-4 xl:grid-cols-2 items-start mt-4">
            <div className="min-w-0 space-y-4">
            <div className="rounded border border-violet-800/40 bg-violet-950/20 p-3 space-y-3 h-full">
              <h4 className="text-xs font-medium text-violet-200 uppercase tracking-wide">Rotation &amp; ASCII beats</h4>
              <label className="flex items-center gap-2 text-sm text-slate-300">
                <span className="text-slate-400 text-xs">Template order</span>
                <select
                  value={templateRotationMode}
                  onChange={(e) => {
                    setEdited(true);
                    setTemplateRotationMode(e.target.value === "random" ? "random" : "sequential");
                  }}
                  className="bg-slate-800 border border-slate-600 rounded px-2 py-1 text-sm text-slate-200"
                >
                  <option value="sequential">Sequential (A→B→C…)</option>
                  <option value="random">Random slot each scrobble</option>
                </select>
              </label>
              <label className="flex items-center gap-2 text-sm text-slate-300 cursor-pointer">
                <input
                  type="checkbox"
                  checked={asciiArtEnabled}
                  onChange={(e) => {
                    setEdited(true);
                    setAsciiArtEnabled(e.target.checked);
                  }}
                />
                ASCII art cadence (every N scrobbles, overrides copy text)
              </label>
              {asciiArtEnabled ? (
                <div className="flex flex-wrap gap-3 text-xs text-slate-400 pl-6">
                  <label>
                    Min scrobbles
                    <input
                      type="number"
                      min={1}
                      max={50}
                      value={asciiMinInterval}
                      onChange={(e) => {
                        setEdited(true);
                        setAsciiMinInterval(Number(e.target.value) || 3);
                      }}
                      className="ml-1 w-14 bg-slate-800 border border-slate-600 rounded px-1 text-slate-200"
                    />
                  </label>
                  <label>
                    Max scrobbles
                    <input
                      type="number"
                      min={1}
                      max={50}
                      value={asciiMaxInterval}
                      onChange={(e) => {
                        setEdited(true);
                        setAsciiMaxInterval(Number(e.target.value) || 6);
                      }}
                      className="ml-1 w-14 bg-slate-800 border border-slate-600 rounded px-1 text-slate-200"
                    />
                  </label>
                  {s ? (
                    <span className="text-slate-500 self-center">
                      Counter {s.ascii_art_scrobble_counter}/{s.ascii_art_next_threshold ?? "—"}
                    </span>
                  ) : null}
                </div>
              ) : null}
              <label className="flex items-center gap-2 text-sm text-slate-300 cursor-pointer">
                <input
                  type="checkbox"
                  checked={tryptychEnabled}
                  onChange={(e) => {
                    setEdited(true);
                    setTryptychEnabled(e.target.checked);
                  }}
                />
                Tryptych on ASCII beat (3 chained copy panels — e.g. sonic_panel_1…3)
              </label>
              {tryptychEnabled ? (
                <label className="flex items-center gap-2 text-xs text-slate-400 pl-6 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={tryptychOnAsciiBeat}
                    onChange={(e) => {
                      setEdited(true);
                      setTryptychOnAsciiBeat(e.target.checked);
                    }}
                  />
                  Only when ASCII cadence fires (not every post)
                </label>
              ) : null}
              <div className="border-t border-violet-800/30 pt-2 space-y-2">
                <p className="text-[10px] text-slate-500">
                  Built-in + custom ASCII (max {asciiQ.data?.max_width ?? 42} cols × {asciiQ.data?.max_lines ?? 40} lines).
                  Upload Adultforce / promo art via copy panel media above; ASCII library is for monospace &lt;pre&gt; beats.
                </p>
                <div className="flex flex-wrap gap-1 max-h-24 overflow-y-auto">
                  {(asciiQ.data?.entries ?? []).map((e) => (
                    <span
                      key={e.id}
                      className="text-[10px] px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-600"
                      title={e.builtin ? "Built-in" : "Custom"}
                    >
                      {e.name}
                      {!e.builtin ? (
                        <button
                          type="button"
                          className="ml-1 text-red-400"
                          onClick={async () => {
                            await api.listeningRelay.deleteAsciiArt(e.id);
                            void asciiQ.refetch();
                          }}
                        >
                          ×
                        </button>
                      ) : null}
                    </span>
                  ))}
                </div>
                <input
                  value={asciiUploadName}
                  onChange={(e) => setAsciiUploadName(e.target.value)}
                  placeholder="Name"
                  className="w-full bg-slate-800 border border-slate-600 rounded px-2 py-1 text-xs text-slate-200"
                />
                <textarea
                  rows={6}
                  value={asciiUploadBody}
                  onChange={(e) => {
                    setAsciiUploadBody(e.target.value);
                  }}
                  placeholder="Paste mobile-safe ASCII (monospace)…"
                  className="w-full font-mono text-xs bg-slate-900 border border-slate-600 rounded px-2 py-1 text-slate-200"
                />
                <div className="flex gap-2 items-center">
                  <button
                    type="button"
                    className="text-xs px-3 py-1 rounded bg-violet-700 text-white hover:bg-violet-600"
                    onClick={async () => {
                      try {
                        await api.listeningRelay.uploadAsciiArt({
                          name: asciiUploadName || "Custom",
                          content: asciiUploadBody,
                        });
                        setAsciiUploadBody("");
                        setAsciiUploadName("");
                        void asciiQ.refetch();
                      } catch (err) {
                        alert(err instanceof Error ? err.message : "Upload failed");
                      }
                    }}
                  >
                    Add to library
                  </button>
                </div>
              </div>
            </div>
            <SilentTelegramSendOption
              checked={sendSilent}
              onChange={(v) => {
                setEdited(true);
                setSendSilent(v);
              }}
            />
            </div>

            <div className="min-w-0 space-y-4">
            <div className="rounded border border-slate-600/80 bg-slate-950/30 p-3 space-y-3 h-full">
              <h4 className="text-xs font-medium text-slate-300 uppercase tracking-wide">Buffer + Discord fan-out</h4>
              <p className="text-xs text-slate-500">
                <strong className="text-slate-400">Scheduled channel posts → X:</strong> use{" "}
                <strong className="text-slate-300">Scheduler</strong> → Social · Buffer and enable{" "}
                <strong className="text-slate-300">Buffer → X</strong> on each job (Destinations column). This section is only
                for Last.fm listening relay fan-out.
              </p>

              <div className="rounded border border-emerald-800/50 bg-emerald-950/25 p-3 space-y-2">
                <p className="text-xs text-emerald-100/90 font-medium">Step 1 — Test Buffer → X (relay wiring)</p>
                <p className="text-xs text-slate-400">
                  Same test as Scheduler → Social · Buffer. One post to Buffer’s X queue via API. Then check{" "}
                  <a className="text-cyan-400 hover:underline" href="https://publish.buffer.com" target="_blank" rel="noreferrer">
                    publish.buffer.com → Queue
                  </a>
                  .
                </p>
                <button
                  type="button"
                  className="px-4 py-2 rounded bg-emerald-600 text-white text-sm font-medium hover:bg-emerald-500 disabled:opacity-50"
                  disabled={bufferTest.isPending}
                  onClick={() => bufferTest.mutate()}
                >
                  {bufferTest.isPending ? "Sending…" : "Test Buffer → X now"}
                </button>
                {bufferTestMsg ? <p className="text-xs text-emerald-200">{bufferTestMsg}</p> : null}
              </div>

              <p className="text-xs text-slate-500">
                <strong className="text-slate-400">Step 2 — Automatic</strong> (optional): each new Last.fm track also queues
                Buffer (template + footer above). Check the box below, click <strong>Save settings</strong>, keep relay + Last.fm
                on, and leave <strong>TBCC-Celery + TBCC-Beat</strong> tabs open.
              </p>
              {s ? (
                <p className="text-[11px] text-slate-500">
                  Today (UTC): {s.buffer_relay_posts_today} Buffer relay post(s) on day {s.buffer_relay_utc_day ?? "—"}
                  {s.buffer_relay_last_post_at ? ` · last ${s.buffer_relay_last_post_at}` : ""}
                </p>
              ) : null}
              <label className="flex items-center gap-2 text-sm text-slate-200">
                <input
                  type="checkbox"
                  checked={bufferRelayEnabled}
                  onChange={(e) => {
                    setEdited(true);
                    setBufferRelayEnabled(e.target.checked);
                  }}
                />
                Also queue Buffer (rate-limited)
              </label>
              <div className="grid gap-3 sm:grid-cols-2">
                <label className="block text-xs text-slate-400">
                  Min minutes between Buffer relay posts
                  <input
                    type="number"
                    min={30}
                    max={1440}
                    className="mt-1 w-full bg-slate-800 border border-slate-600 rounded px-3 py-2 text-slate-100"
                    value={bufferRelayMinMinutes}
                    onChange={(e) => {
                      setEdited(true);
                      setBufferRelayMinMinutes(Number(e.target.value));
                    }}
                  />
                </label>
                <label className="block text-xs text-slate-400">
                  Max Buffer relay posts per UTC day
                  <input
                    type="number"
                    min={1}
                    max={50}
                    className="mt-1 w-full bg-slate-800 border border-slate-600 rounded px-3 py-2 text-slate-100"
                    value={bufferRelayMaxPerDay}
                    onChange={(e) => {
                      setEdited(true);
                      setBufferRelayMaxPerDay(Number(e.target.value));
                    }}
                  />
                </label>
              </div>
            </div>

            <div className="rounded border border-amber-700/40 bg-amber-950/20 p-3 space-y-3">
              <h3 className="text-sm font-medium text-amber-100">Loot goblin (deep-link grants)</h3>
              <p className="text-xs text-slate-400">
                Rare spawn on relay scrobbles: loot bot posts a short channel announce (Bot API, ~45s TTL) with a{" "}
                <code className="text-slate-300">@aof_lootgod_bot?start=goblin_…</code> button. Token is cap-only — no expiry.
              </p>
              {s ? (
                <p className="text-[11px] text-slate-500">
                  Today (UTC): {s.goblin_spawns_today ?? 0} spawn(s) on day {s.goblin_utc_day ?? "—"}
                  {s.goblin_last_spawn_at ? ` · last ${s.goblin_last_spawn_at}` : ""}
                </p>
              ) : null}
              <label className="flex items-center gap-2 text-sm text-slate-200">
                <input
                  type="checkbox"
                  checked={goblinModeEnabled}
                  onChange={(e) => {
                    setEdited(true);
                    setGoblinModeEnabled(e.target.checked);
                  }}
                />
                Enable loot goblin spawns
              </label>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                <label className="block text-xs text-slate-400">
                  Spawn chance (0–1)
                  <input
                    type="number"
                    min={0}
                    max={1}
                    step={0.05}
                    className="mt-1 w-full bg-slate-800 border border-slate-600 rounded px-3 py-2 text-slate-100"
                    value={goblinSpawnChance}
                    onChange={(e) => {
                      setEdited(true);
                      setGoblinSpawnChance(Number(e.target.value));
                    }}
                  />
                </label>
                <label className="block text-xs text-slate-400">
                  Cooldown (minutes)
                  <input
                    type="number"
                    min={0}
                    max={1440}
                    className="mt-1 w-full bg-slate-800 border border-slate-600 rounded px-3 py-2 text-slate-100"
                    value={goblinCooldownMinutes}
                    onChange={(e) => {
                      setEdited(true);
                      setGoblinCooldownMinutes(Number(e.target.value));
                    }}
                  />
                </label>
                <label className="block text-xs text-slate-400">
                  Announce TTL (seconds)
                  <input
                    type="number"
                    min={5}
                    max={300}
                    className="mt-1 w-full bg-slate-800 border border-slate-600 rounded px-3 py-2 text-slate-100"
                    value={goblinAnnounceTtl}
                    onChange={(e) => {
                      setEdited(true);
                      setGoblinAnnounceTtl(Number(e.target.value));
                    }}
                  />
                </label>
                <label className="block text-xs text-slate-400">
                  Claims cap per drop
                  <input
                    type="number"
                    min={1}
                    max={100}
                    className="mt-1 w-full bg-slate-800 border border-slate-600 rounded px-3 py-2 text-slate-100"
                    value={goblinClaimsCap}
                    onChange={(e) => {
                      setEdited(true);
                      setGoblinClaimsCap(Number(e.target.value));
                    }}
                  />
                </label>
                <label className="block text-xs text-slate-400">
                  Max spawns per UTC day
                  <input
                    type="number"
                    min={1}
                    max={50}
                    className="mt-1 w-full bg-slate-800 border border-slate-600 rounded px-3 py-2 text-slate-100"
                    value={goblinMaxPerDay}
                    onChange={(e) => {
                      setEdited(true);
                      setGoblinMaxPerDay(Number(e.target.value));
                    }}
                  />
                </label>
              </div>
            </div>

            <div className="rounded border border-slate-600/80 bg-slate-950/30 p-3">
            <h3 className="text-sm font-medium text-slate-200 mb-2">Webhook (IFTTT / YouTube / custom)</h3>
            <p className="text-xs text-slate-500 mb-2">
              POST JSON: <code className="text-slate-400">title</code>, <code className="text-slate-400">url</code>, optional{" "}
              <code className="text-slate-400">source</code> (e.g. youtube), <code className="text-slate-400">artist</code>,{" "}
              <code className="text-slate-400">album</code>. IFTTT can use value1/value2/value3 for the same fields.
            </p>
            <div className="flex flex-wrap gap-2 items-center">
              <code className="text-xs text-cyan-200 break-all bg-slate-950/80 px-2 py-1 rounded border border-slate-700">
                {webhookUrlBase}
                {webhookSecret || "…your-secret…"}
              </code>
              <button
                type="button"
                className="text-sm px-3 py-1 rounded bg-slate-700 text-slate-200 hover:bg-slate-600"
                onClick={() => regen.mutate()}
                disabled={regen.isPending}
              >
                Regenerate secret
              </button>
            </div>
            <p className="text-xs text-slate-500 mt-2">
              Masked on save: {s?.webhook_secret_masked || "—"}. Full secret is shown when you open this page or after
              regenerate. For production, set your public API base URL in IFTTT (same path{" "}
              <code className="text-slate-500">/listening-relay/webhook/&lt;secret&gt;</code>).
            </p>
            </div>
            </div>
          </div>

          <div className="border-t border-slate-700 pt-4 mt-4 flex flex-wrap gap-2">
            <button
              type="button"
              className="px-4 py-2 rounded bg-cyan-600 text-white text-sm font-medium hover:bg-cyan-500 disabled:opacity-50"
              disabled={save.isPending}
              onClick={() => save.mutate()}
            >
              Save settings
            </button>
            <button
              type="button"
              className="px-4 py-2 rounded bg-slate-700 text-slate-100 text-sm hover:bg-slate-600 disabled:opacity-50"
              disabled={preview.isPending}
              onClick={() => preview.mutate()}
            >
              Preview Last.fm
            </button>
            <button
              type="button"
              className="px-4 py-2 rounded bg-slate-700 text-slate-100 text-sm hover:bg-slate-600 disabled:opacity-50"
              disabled={testPost.isPending}
              onClick={() => testPost.mutate()}
            >
              Test Telegram
            </button>
            <button
              type="button"
              className="px-4 py-2 rounded bg-slate-800 text-slate-400 text-sm border border-slate-600 hover:text-slate-200 disabled:opacity-50"
              disabled={clearLastfmDedupe.isPending}
              onClick={() => clearLastfmDedupe.mutate()}
            >
              Reset Last.fm dedupe {s?.has_lastfm_dedupe ? "" : "(idle)"}
            </button>
            <button
              type="button"
              className="px-4 py-2 rounded bg-slate-800 text-slate-400 text-sm border border-slate-600 hover:text-slate-200 disabled:opacity-50"
              disabled={clearHookDedupe.isPending}
              onClick={() => clearHookDedupe.mutate()}
            >
              Reset webhook dedupe {s?.has_webhook_dedupe ? "" : "(idle)"}
            </button>
          </div>

          {preview.data ? (
            <div className="rounded border border-slate-700 bg-slate-950/50 p-3 text-sm">
              <div className="text-slate-400 text-xs mb-1">Last.fm preview</div>
              {!preview.data.ok ? (
                <p className="text-amber-400">{preview.data.detail || "No track"}</p>
              ) : (
                <>
                  <pre className="text-slate-500 text-xs overflow-auto mb-2">
                    {JSON.stringify(preview.data.track, null, 2)}
                  </pre>
                  <pre className="text-slate-300 whitespace-pre-wrap font-mono text-xs border border-slate-700 rounded p-2 bg-slate-900/80">
                    {preview.data.formatted || ""}
                  </pre>
                  <p className="text-xs text-slate-500 mt-1">Rendered Telegram HTML (same string the bot sends).</p>
                </>
              )}
            </div>
          ) : null}

          {s?.last_poll_at ? (
            <p className="text-xs text-slate-500">Last Last.fm poll (UTC): {s.last_poll_at}</p>
          ) : null}

          <RelayPostHistory />
        </div>
      </section>

      <div className="grid gap-6 xl:grid-cols-2 items-start">
      <K2SLibrarySection />
      <MainChannelDividerSection />
      <GallerySendPromoSection />
      <ZipBundlePromoSection />

      <section
        id="promo-affiliate-links"
        className="h-full border border-slate-700 rounded-lg p-6 bg-slate-900/40 overflow-visible"
      >
        <h2 className="text-lg font-medium text-slate-100 mb-1">Promo affiliate links</h2>
        <p className="text-slate-400 text-sm mb-4">
          Curated tracking URLs with <strong className="text-slate-300">placements</strong> for auto-rotation:
          <code className="text-slate-500"> telegram_footer</code>,{" "}
          <code className="text-slate-500"> x_buffer</code>,{" "}
          <code className="text-slate-500"> links_hub</code>,{" "}
          <code className="text-slate-500"> links_hub_ai</code>, or{" "}
          <code className="text-slate-500"> manual_only</code>. Use the Insert menu on caption fields, bulk-import
          JSON, then <strong className="text-slate-300">Sync affiliate rotation</strong> to push sponsor footers into
          network schedulers and the links hub bulletin.
        </p>
        <div className="flex flex-wrap items-center gap-2 mb-4">
          <PromoAffiliateLinksPopover buttonLabel="Open promo picker…" dropUp />
          <button
            type="button"
            className="text-xs px-3 py-1.5 rounded bg-emerald-700 text-white hover:bg-emerald-600 disabled:opacity-50"
            disabled={syncAffiliateRotation.isPending}
            onClick={() => syncAffiliateRotation.mutate()}
          >
            {syncAffiliateRotation.isPending ? "Syncing…" : "Sync affiliate rotation"}
          </button>
        </div>
        {promoStatsQ.data ? (
          <p className="text-xs text-slate-500 mb-3">
            Active: {promoStatsQ.data.active_rows} · telegram_footer:{" "}
            {promoStatsQ.data.by_placement?.telegram_footer ?? 0} · x_buffer:{" "}
            {promoStatsQ.data.by_placement?.x_buffer ?? 0} · links_hub:{" "}
            {promoStatsQ.data.by_placement?.links_hub ?? 0} · links_hub_ai:{" "}
            {promoStatsQ.data.by_placement?.links_hub_ai ?? 0}
          </p>
        ) : null}
        <div className="mb-4 grid gap-2 sm:grid-cols-3">
          <label className="text-xs text-slate-400">
            Preview placement
            <select
              className="mt-1 block w-full bg-slate-800 border border-slate-600 rounded px-2 py-1 text-slate-100"
              value={affiliatePreviewPlacement}
              onChange={(e) => setAffiliatePreviewPlacement(e.target.value)}
            >
              <option value="telegram_footer">telegram_footer</option>
              <option value="x_buffer">x_buffer</option>
              <option value="links_hub">links_hub</option>
              <option value="links_hub_ai">links_hub_ai</option>
              <option value="manual_only">manual_only</option>
            </select>
          </label>
          <label className="text-xs text-slate-400">
            Network key
            <input
              className="mt-1 block w-full bg-slate-800 border border-slate-600 rounded px-2 py-1 text-slate-100"
              value={affiliateNetworkKey}
              onChange={(e) => setAffiliateNetworkKey(e.target.value)}
              placeholder="ai, main, …"
            />
          </label>
          <div className="text-xs text-slate-400">
            Next picks
            <ul className="mt-1 max-h-24 overflow-auto rounded border border-slate-700 bg-slate-950/60 p-2 text-slate-300">
              {(promoPreviewQ.data?.picks ?? []).map((p) => (
                <li key={p.id} className="truncate">
                  {p.label}
                </li>
              ))}
              {promoPreviewQ.isSuccess && !(promoPreviewQ.data?.picks?.length) ? (
                <li className="text-slate-500">No matches</li>
              ) : null}
            </ul>
          </div>
        </div>
        {promoLinksListQ.data && promoLinksListQ.data.length > 0 ? (
          <div className="mb-4 max-h-40 overflow-auto rounded border border-slate-700 text-xs">
            <table className="w-full text-left">
              <thead className="sticky top-0 bg-slate-900 text-slate-500">
                <tr>
                  <th className="p-2">Label</th>
                  <th className="p-2">Tier</th>
                  <th className="p-2">Placements</th>
                </tr>
              </thead>
              <tbody>
                {promoLinksListQ.data.slice(0, 20).map((row) => (
                  <tr key={row.id} className="border-t border-slate-800">
                    <td className="p-2 text-slate-200">{row.label}</td>
                    <td className="p-2 text-slate-400">{row.priority_tier}</td>
                    <td className="p-2 text-slate-500">{(row.placements || []).join(", ") || "manual_only"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
        <details className="border border-slate-700 rounded-lg p-4 bg-slate-950/40">
          <summary className="text-sm text-slate-300 cursor-pointer select-none">Bulk import JSON</summary>
          <p className="text-xs text-slate-500 mt-3 mb-2 whitespace-pre-wrap">
            {`{
  "items": [
    {
      "label": "Musebox AI",
      "url": "https://musebox.ai/?ref=uOg77ImI",
      "payout_kind": "revshare",
      "priority_tier": 4,
      "placements": ["x_buffer", "telegram_footer", "links_hub_ai"],
      "network_keys": ["ai", "main"],
      "copy_template": "🎨 {link} — AI creative playground"
    }
  ]
}`}
          </p>
          <textarea
            className="w-full min-h-[120px] bg-slate-800 border border-slate-600 rounded px-3 py-2 text-slate-100 font-mono text-xs"
            value={promoBulkJson}
            onChange={(e) => setPromoBulkJson(e.target.value)}
            placeholder='{"items":[{"label":"Example","url":"https://..."}]}'
          />
          <button
            type="button"
            className="mt-3 px-4 py-2 rounded bg-cyan-700 text-white text-sm hover:bg-cyan-600 disabled:opacity-50"
            disabled={promoBulkImport.isPending || !promoBulkJson.trim()}
            onClick={() => {
              try {
                const parsed = JSON.parse(promoBulkJson) as {
                  items?: Array<{
                    label?: string;
                    url?: string;
                    short_url?: string | null;
                    payout_kind?: string;
                    payout_detail?: string | null;
                    priority_tier?: number;
                    expires_at?: string | null;
                    active?: boolean;
                    placements?: string[];
                    network_keys?: string[];
                    copy_template?: string | null;
                  }>;
                };
                const raw = Array.isArray(parsed.items) ? parsed.items : [];
                const items = raw
                  .map((it) => ({
                    label: String(it.label || "").trim(),
                    url: String(it.url || "").trim(),
                    short_url:
                      typeof it.short_url === "string" && it.short_url.trim() ? it.short_url.trim() : undefined,
                    payout_kind: it.payout_kind,
                    payout_detail: it.payout_detail,
                    priority_tier: it.priority_tier,
                    expires_at: it.expires_at,
                    active: it.active,
                    placements: Array.isArray(it.placements) ? it.placements.map(String) : undefined,
                    network_keys: Array.isArray(it.network_keys) ? it.network_keys.map(String) : undefined,
                    copy_template: typeof it.copy_template === "string" ? it.copy_template : undefined,
                  }))
                  .filter((it) => it.label && it.url);
                if (!items.length) return;
                promoBulkImport.mutate({ items });
              } catch {
                /* invalid JSON — ignore */
              }
            }}
          >
            Import to database
          </button>
          {promoBulkImport.isSuccess ? (
            <p className="text-xs text-emerald-400/95 mt-2">Imported {promoBulkImport.data.created} row(s).</p>
          ) : null}
          {promoBulkImport.isError ? (
            <p className="text-xs text-red-400 mt-2">
              {promoBulkImport.error instanceof Error ? promoBulkImport.error.message : "Import failed"}
            </p>
          ) : null}
        </details>
      </section>
      </div>
        </>
      )}
    </div>
  );
}
