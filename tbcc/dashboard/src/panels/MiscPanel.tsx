import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import { CaptionSnippetLibraryManageButton } from "../components/CaptionSnippetLibrary";
import { CustomEmojiLibraryManageButton } from "../components/CustomEmojiLibrary";
import { ChannelInviteLinkButtons } from "../components/ChannelInviteLinkButtons";
import { PromoAffiliateLinksPopover } from "../components/PromoAffiliateLinksPopover";
import { QueryErrorBanner } from "../components/QueryErrorBanner";
import type { ListeningRelaySettings, RelaySlotExtra } from "../api";
import { EmojiPackWayfinding } from "../components/EmojiPackWayfinding";
import { CustomEmojiTools } from "./CustomEmojiTools";
import { EmojiFactoryPanel } from "./EmojiFactoryPanel";
import { SilentTelegramSendOption } from "../components/SilentTelegramSendOption";
import { EMPTY_RELAY_SLOT_EXTRA, normalizeRelaySlotExtra } from "../components/RelayCopySlotExtras";
import { RelayTemplateSlotsEditor } from "../components/RelayTemplateSlotsEditor";

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
        Closing tile appended <strong className="text-slate-300">last</strong> on gallery batch sends (Saved Messages,
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
  const relayQ = useQuery({
    queryKey: ["listeningRelay"],
    queryFn: () => api.listeningRelay.get(),
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
  const [channelId, setChannelId] = useState<number | "">("");
  const [messageThreadId, setMessageThreadId] = useState<string>("");
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
    setChannelId(s.channel_id != null ? Number(s.channel_id) : "");
    setMessageThreadId(s.message_thread_id != null ? String(s.message_thread_id) : "");
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
  }, [s, edited]);

  const topicsQ = useQuery({
    queryKey: ["forumTopics", channelId],
    queryFn: () => api.channels.forumTopics(Number(channelId)),
    enabled: typeof channelId === "number" && channelId > 0,
  });

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
        channel_id: channelId === "" ? null : Number(channelId),
        message_thread_id: messageThreadId.trim() ? Number(messageThreadId) : null,
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
      };
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
        setChannelId(st.channel_id != null ? Number(st.channel_id) : "");
        setMessageThreadId(st.message_thread_id != null ? String(st.message_thread_id) : "");
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
  const promoBulkImport = useMutation({
    mutationFn: (body: {
      items: Array<{
        label: string;
        url: string;
        payout_kind?: string;
        payout_detail?: string | null;
        priority_tier?: number;
        expires_at?: string | null;
        active?: boolean;
      }>;
    }) => api.promoAffiliateLinks.bulk(body),
    onSuccess: () => {
      setPromoBulkJson("");
      qc.invalidateQueries({ queryKey: ["promoAffiliateLinks"] });
    },
  });

  const preview = useMutation({
    mutationFn: () => api.listeningRelay.lastfmPreview(),
  });

  const testPost = useMutation({
    mutationFn: () => api.listeningRelay.testPost(),
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
                  setChannelId(v ? Number(v) : "");
                  setMessageThreadId("");
                }}
              >
                <option value="">— select —</option>
                {channels.map((c) => (
                  <option key={String(c.id)} value={String(c.id)}>
                    {(c.name as string) || (c.identifier as string)} ({String(c.identifier)})
                  </option>
                ))}
              </select>
            </label>
            <label className="block text-sm">
              <span className="text-slate-400">Forum topic (optional)</span>
              <select
                className="mt-1 w-full bg-slate-800 border border-slate-600 rounded px-3 py-2 text-slate-100"
                value={messageThreadId}
                onChange={(e) => {
                  setEdited(true);
                  setMessageThreadId(e.target.value);
                }}
                disabled={typeof channelId !== "number"}
              >
                <option value="">Main / non-forum</option>
                {(topicsQ.data?.topics ?? []).map((t) => (
                  <option key={t.id} value={String(t.id)}>
                    {t.title} (#{t.id})
                  </option>
                ))}
              </select>
              {topicsQ.data?.error ? (
                <span className="text-amber-400 text-xs mt-1 block">{topicsQ.data.error}</span>
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
            <PromoAffiliateLinksPopover />
            <CaptionSnippetLibraryManageButton />
            <CustomEmojiLibraryManageButton />
          </div>
          <RelayTemplateSlotsEditor
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
                  <input
                    value={asciiUploadName}
                    onChange={(e) => setAsciiUploadName(e.target.value)}
                    placeholder="Name"
                    className="flex-1 bg-slate-800 border border-slate-600 rounded px-2 py-1 text-xs text-slate-200"
                  />
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
            <ChannelInviteLinkButtons
              channels={channels as Array<Record<string, unknown>>}
              summaryPrefix="Quick insert — channel invite link → template #1"
              onInsertLink={(link) => {
                setEdited(true);
                setTemplateVariants((prev) => {
                  const next = [...prev];
                  while (next.length < 1) next.push("");
                  const cur = next[0] || "";
                  next[0] = cur.trim() ? `${cur.trim()}\n\n${link}` : link;
                  return next;
                });
              }}
            />
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
        </div>
      </section>

      <div className="grid gap-6 xl:grid-cols-2 items-start">
      <GallerySendPromoSection />
      <ZipBundlePromoSection />

      <section className="h-full border border-slate-700 rounded-lg p-6 bg-slate-900/40 overflow-visible">
        <h2 className="text-lg font-medium text-slate-100 mb-1">Promo affiliate links</h2>
        <p className="text-slate-400 text-sm mb-4">
          Curated tracking URLs for scheduled posts and relay templates. Use the picker beside caption tools, or bulk-import
          JSON (same shape as{" "}
          <code className="text-slate-500">{`POST /promo-affiliate-links/bulk`}</code>
          ). Optional <code className="text-slate-500">short_url</code> per row is used first when you insert from the
          picker; you can paste it manually or use <code className="text-slate-500">POST …/shorten</code> from the picker
          when the API has <code className="text-slate-500">TBCC_PROMO_SHORTEN_PROVIDER</code> set (see{" "}
          <code className="text-slate-500">.env.example</code>) — e.g.{" "}
          <code className="text-slate-500">isgd</code>,{" "}
          <code className="text-slate-500">tinyurl</code>, or{" "}
          <code className="text-slate-500">pixeldrain</code>{" "}
          (<code className="text-slate-500">TBCC_PIXELDRAIN_API_KEY</code>; uploads the URL as a tiny{" "}
          <code className="text-slate-500">.txt</code>, viewer link like ShareX).
        </p>
        <div className="flex flex-wrap items-center gap-2 mb-4">
          <PromoAffiliateLinksPopover buttonLabel="Open promo picker…" dropUp />
        </div>
        <details className="border border-slate-700 rounded-lg p-4 bg-slate-950/40">
          <summary className="text-sm text-slate-300 cursor-pointer select-none">Bulk import JSON</summary>
          <p className="text-xs text-slate-500 mt-3 mb-2 whitespace-pre-wrap">
            {`{
  "items": [
    {
      "label": "Brand — offer",
      "url": "https://…",
      "short_url": "https://is.gd/abc",
      "payout_kind": "revshare",
      "payout_detail": "$25",
      "priority_tier": 1
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
