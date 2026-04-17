import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import { useState, useEffect, useRef, useMemo } from "react";

function bundleZipPartCount(p: Record<string, unknown>): number {
  const c = p.bundle_zip_part_count;
  if (typeof c === "number" && Number.isFinite(c) && c >= 0) return c;
  const parts = p.bundle_zip_parts;
  if (Array.isArray(parts)) return parts.length;
  const legacy =
    (p.bundle_zip1_available === true ? 1 : 0) + (p.bundle_zip2_available === true ? 1 : 0);
  return legacy;
}

function planTagCount(p: Record<string, unknown>): number {
  const tags = p.tags;
  if (Array.isArray(tags)) return tags.length;
  const ids = p.tag_ids;
  if (Array.isArray(ids)) return ids.length;
  return 0;
}

import { QueryErrorBanner } from "../components/QueryErrorBanner";
import { WalletPendingOrders } from "../components/WalletPendingOrders";

/**
 * Hints for promo URLs. Localhost after upload is expected in dev — use "info", not error styling.
 * Telegram fetches URLs from its servers — not your browser.
 */
function promoUrlHint(url: string): { kind: "info" | "warn"; message: string } | null {
  const t = url.trim();
  if (!t) return null;
  const low = t.toLowerCase();
  if (low.includes("localhost") || low.includes("127.0.0.1")) {
    return {
      kind: "info",
      message:
        "Upload succeeded — preview works in this dashboard. Telegram cannot load localhost URLs for invoices or the bot. For production, set TBCC_PROMO_PUBLIC_BASE_URL (or TBCC_PUBLIC_BASE_URL) in tbcc/.env to a public https:// base (e.g. ngrok), restart the API, then upload again or replace the URLs.",
    };
  }
  if (/^http:\/\//i.test(t) && !/^https:\/\//i.test(t)) {
    return {
      kind: "warn",
      message: "Use https:// for Telegram invoice/catalog photos when the host is public.",
    };
  }
  if ((/imgbb\.com|\/ibb\.co\//i.test(t) || /^https?:\/\/[^/]*ibb\.co\//i.test(t)) && !/i\.ibb\.co/i.test(t)) {
    return {
      kind: "warn",
      message: "Use ImgBB’s direct image link (https://i.ibb.co/.../file.jpg), not the ibb.co HTML page.",
    };
  }
  return null;
}

function PromoUrlHintBox({ url, serverHint }: { url: string; serverHint: string | null }) {
  const hint = promoUrlHint(url);
  if (!hint && !serverHint) return null;
  const info = hint?.kind === "info";
  return (
    <div
      className={
        info
          ? "mt-2 text-xs text-slate-200 bg-slate-800/90 border border-slate-600 rounded px-2 py-2 leading-snug"
          : "mt-2 text-xs text-amber-100 bg-amber-950/70 border border-amber-700/60 rounded px-2 py-2 leading-snug"
      }
    >
      {hint?.message ? <p className="m-0">{hint.message}</p> : null}
      {serverHint ? (
        <p className={hint?.message ? "m-0 mt-2 text-slate-300" : "m-0"}>{serverHint}</p>
      ) : null}
    </div>
  );
}

const MAX_PROMO_IMAGES = 5;
/** Extra description lines (plus main Description) — bot picks randomly for invoices / pack cards. */
const MAX_DESC_VARIANTS = 15;

function promoUrlsFromPlan(p: Record<string, unknown>): string[] {
  const raw = p.promo_image_urls;
  if (Array.isArray(raw)) {
    return raw.map((x) => String(x || "").trim()).filter(Boolean).slice(0, MAX_PROMO_IMAGES);
  }
  const one = String(p.promo_image_url || "").trim();
  return one ? [one] : [];
}

/**
 * Products backed by `subscription_plans` — the payment bot reads GET /subscription-plans.
 * Subscriptions → /subscribe; bundles (digital packs) → /packs.
 */
export function BotShop() {
  const queryClient = useQueryClient();
  const {
    data: plans = [],
    isPending: plansPending,
    isError: plansError,
    error: plansErr,
    refetch: refetchPlans,
  } = useQuery({
    queryKey: ["subscriptionPlans"],
    queryFn: () => api.subscriptionPlans.list(),
  });
  const {
    data: channels = [],
    isPending: channelsPending,
    isError: channelsError,
    error: channelsErr,
    refetch: refetchChannels,
  } = useQuery({
    queryKey: ["channels"],
    queryFn: () => api.channels.list(),
  });
  const { data: tagCatalog = [] } = useQuery({
    queryKey: ["tags"],
    queryFn: () => api.tags.list(),
  });
  const { data: llmStatus } = useQuery({
    queryKey: ["llmStatus"],
    queryFn: () => api.llm.status(),
  });
  const sortedTags = useMemo(
    () => [...tagCatalog].sort((a, b) => a.slug.localeCompare(b.slug)),
    [tagCatalog],
  );

  function toggleNewTag(id: number) {
    setNewTagIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  }
  function toggleEditTag(id: number) {
    setEditTagIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  }

  const channelMap = Object.fromEntries(
    (channels as Array<Record<string, unknown>>).map((c) => [String(c.id), String(c.name || c.identifier || c.id)])
  );

  /** New product (top form only) */
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [descriptionVariants, setDescriptionVariants] = useState<string[]>([]);
  const [newTagIds, setNewTagIds] = useState<number[]>([]);
  const [priceStars, setPriceStars] = useState(100);
  const [durationDays, setDurationDays] = useState(30);
  const [channelId, setChannelId] = useState<number | "">("");
  const [productType, setProductType] = useState<"subscription" | "bundle">("subscription");
  const [botSection, setBotSection] = useState<"main" | "loot" | "packs">("main");
  const [isActive, setIsActive] = useState(true);
  const [promoImageUrls, setPromoImageUrls] = useState<string[]>([]);
  /** Set when dashboard upload returns telegram_hint from API */
  const [promoHintAfterUpload, setPromoHintAfterUpload] = useState<string | null>(null);
  /** Shown briefly after a successful "Add product" (avoid sticky create.isSuccess from react-query). */
  const [justCreatedOk, setJustCreatedOk] = useState(false);
  useEffect(() => {
    if (!justCreatedOk) return;
    const t = window.setTimeout(() => setJustCreatedOk(false), 12_000);
    return () => window.clearTimeout(t);
  }, [justCreatedOk]);

  /** Modal edit (same shape as ContentPools edit pool) */
  const [editOpen, setEditOpen] = useState(false);
  const [editId, setEditId] = useState(0);
  const [editName, setEditName] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editDescriptionVariants, setEditDescriptionVariants] = useState<string[]>([]);
  const [editTagIds, setEditTagIds] = useState<number[]>([]);
  const [editPriceStars, setEditPriceStars] = useState(100);
  const [editDurationDays, setEditDurationDays] = useState(30);
  const [editChannelId, setEditChannelId] = useState<number | "">("");
  const [editProductType, setEditProductType] = useState<"subscription" | "bundle">("subscription");
  const [editBotSection, setEditBotSection] = useState<"main" | "loot" | "packs">("main");
  const [editIsActive, setEditIsActive] = useState(true);
  const [editPromoImageUrls, setEditPromoImageUrls] = useState<string[]>([]);
  const [editPromoHintAfterUpload, setEditPromoHintAfterUpload] = useState<string | null>(null);
  const newPromoFileInputRef = useRef<HTMLInputElement>(null);
  const editPromoFileInputRef = useRef<HTMLInputElement>(null);

  const create = useMutation({
    mutationFn: () =>
      api.subscriptionPlans.create({
        name: name.trim() || "New product",
        description: description.trim() || undefined,
        description_variations:
          descriptionVariants.map((s) => s.trim()).filter(Boolean).slice(0, MAX_DESC_VARIANTS).length > 0
            ? descriptionVariants.map((s) => s.trim()).filter(Boolean).slice(0, MAX_DESC_VARIANTS)
            : undefined,
        tag_ids: newTagIds.length > 0 ? newTagIds : undefined,
        price_stars: priceStars,
        duration_days: durationDays,
        channel_id: channelId === "" ? undefined : channelId,
        product_type: productType,
        bot_section: botSection,
        is_active: isActive,
        promo_image_urls:
          promoImageUrls.map((s) => s.trim()).filter(Boolean).length > 0
            ? promoImageUrls.map((s) => s.trim()).filter(Boolean).slice(0, MAX_PROMO_IMAGES)
            : undefined,
      }),
    onMutate: () => {
      setJustCreatedOk(false);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["subscriptionPlans"] });
      setName("");
      setDescription("");
      setDescriptionVariants([]);
      setNewTagIds([]);
      setPriceStars(100);
      setDurationDays(30);
      setChannelId("");
      setProductType("subscription");
      setBotSection("main");
      setIsActive(true);
      setPromoImageUrls([]);
      setPromoHintAfterUpload(null);
      setJustCreatedOk(true);
    },
  });

  const patch = useMutation({
    mutationFn: ({ id, body }: { id: number; body: Record<string, unknown> }) =>
      api.subscriptionPlans.update(id, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["subscriptionPlans"] });
      setEditOpen(false);
    },
  });

  const remove = useMutation({
    mutationFn: (id: number) => api.subscriptionPlans.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["subscriptionPlans"] });
      setEditOpen(false);
    },
  });

  const [bundleUploadFlash, setBundleUploadFlash] = useState<string | null>(null);
  useEffect(() => {
    if (!bundleUploadFlash) return;
    const t = window.setTimeout(() => setBundleUploadFlash(null), 7000);
    return () => clearTimeout(t);
  }, [bundleUploadFlash]);

  const bundleAddInputRef = useRef<HTMLInputElement>(null);

  const uploadBundleZip = useMutation({
    mutationFn: ({ id, file }: { id: number; file: File }) => api.subscriptionPlans.uploadBundleZip(id, file),
    onSuccess: (data, vars) => {
      queryClient.invalidateQueries({ queryKey: ["subscriptionPlans"] });
      const n = typeof data.bundle_zip_part_count === "number" ? data.bundle_zip_part_count : 0;
      setBundleUploadFlash(
        n > 0
          ? `Uploaded “${vars.file.name}” — this pack now has ${n} part${n === 1 ? "" : "s"}.`
          : `Uploaded “${vars.file.name}”.`,
      );
    },
  });

  const deleteBundleZip = useMutation({
    mutationFn: ({ id, index }: { id: number; index?: number }) => api.subscriptionPlans.deleteBundleZip(id, index),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["subscriptionPlans"] }),
  });

  const aiSuggest = useMutation({
    mutationFn: () =>
      api.llm.suggestShopProduct({
        name: editName.trim() || "Product",
        description: editDescription.trim() || undefined,
        product_type: editProductType,
      }),
    onSuccess: (data) => {
      if (Array.isArray(data.tag_ids) && data.tag_ids.length) {
        setEditTagIds(data.tag_ids);
      }
      const parts: string[] = [];
      if (data.hook_line) parts.push(data.hook_line);
      if (data.description) parts.push(data.description);
      if (parts.length) {
        setEditDescription(parts.join("\n\n").trim());
      }
      if (Array.isArray(data.description_variations) && data.description_variations.length) {
        setEditDescriptionVariants(data.description_variations.map((s: string) => String(s || "")));
      }
    },
  });

  const uploadPromoImage = useMutation({
    mutationFn: async ({ file, target }: { file: File; target: "new" | "edit" }) => {
      const data = await api.subscriptionPlans.uploadPromoImage(file);
      return { ...data, target };
    },
    onSuccess: (data) => {
      const hint = data.telegram_hint ?? (data.telegram_reachable === false ? "This URL is not reachable by Telegram’s servers." : null);
      if (data.target === "edit") {
        setEditPromoImageUrls((prev) => {
          if (prev.length >= MAX_PROMO_IMAGES) return prev;
          return prev.includes(data.url) ? prev : [...prev, data.url];
        });
        setEditPromoHintAfterUpload(hint);
      } else {
        setPromoImageUrls((prev) => {
          if (prev.length >= MAX_PROMO_IMAGES) return prev;
          return prev.includes(data.url) ? prev : [...prev, data.url];
        });
        setPromoHintAfterUpload(hint);
      }
    },
  });

  /**
   * Copy files to an array before clearing the `<input type="file">`.
   * Clearing the input empties the live `FileList` in many browsers, so async upload would see 0 files otherwise.
   */
  async function handlePromoFilesSelected(fileArray: File[], target: "new" | "edit") {
    if (!fileArray.length) return;
    uploadPromoImage.reset();
    for (const f of fileArray) {
      try {
        await uploadPromoImage.mutateAsync({ file: f, target });
      } catch (e) {
        console.error("Promo upload failed:", e);
        break;
      }
    }
  }

  function openProductEditor(p: Record<string, unknown>) {
    setEditId(Number(p.id));
    setEditName(String(p.name || ""));
    setEditDescription(String(p.description || ""));
    const dv = p.description_variations;
    setEditDescriptionVariants(Array.isArray(dv) ? dv.map((x) => String(x || "")) : []);
    setEditPriceStars(Number(p.price_stars ?? 0));
    setEditDurationDays(Number(p.duration_days ?? 30));
    setEditChannelId(p.channel_id != null ? Number(p.channel_id) : "");
    setEditProductType(((p.product_type as string) || "subscription") === "bundle" ? "bundle" : "subscription");
    const sec = String(p.bot_section || "main").toLowerCase();
    setEditBotSection(sec === "loot" || sec === "packs" ? (sec as "loot" | "packs") : "main");
    setEditIsActive(p.is_active !== false);
    setEditPromoImageUrls(promoUrlsFromPlan(p));
    setEditPromoHintAfterUpload(null);
    setBundleUploadFlash(null);
    const tids = p.tag_ids;
    setEditTagIds(
      Array.isArray(tids) ? tids.map((x) => Number(x)).filter((n) => Number.isFinite(n)) : [],
    );
    setEditOpen(true);
  }

  function closeProductEditor() {
    setBundleUploadFlash(null);
    setEditOpen(false);
  }

  function saveProductEditor() {
    if (!editId) return;
    patch.mutate({
      id: editId,
      body: {
        name: editName.trim() || "Product",
        description: editDescription.trim() || null,
        description_variations: editDescriptionVariants.map((s) => s.trim()).filter(Boolean).slice(0, MAX_DESC_VARIANTS),
        price_stars: editPriceStars,
        duration_days: editDurationDays,
        channel_id: editChannelId === "" ? null : editChannelId,
        product_type: editProductType,
        bot_section: editBotSection,
        is_active: editIsActive,
        promo_image_urls: editPromoImageUrls.map((s) => s.trim()).filter(Boolean).slice(0, MAX_PROMO_IMAGES),
        tag_ids: editTagIds,
      },
    });
  }

  const channelSelectOptions = (
    <>
      <option value="">— none —</option>
      {channelsPending && !channels.length ? (
        <option value="" disabled>
          Loading channels…
        </option>
      ) : (
        (channels as Array<Record<string, unknown>>).map((c) => (
          <option key={String(c.id)} value={String(c.id)}>
            {String(c.name || c.identifier || c.id)}
          </option>
        ))
      )}
    </>
  );

  return (
    <div className="max-w-4xl">
      {plansError && (
        <QueryErrorBanner
          title="Could not load products"
          message={String((plansErr as Error)?.message ?? plansErr)}
          onRetry={() => void refetchPlans()}
        />
      )}
      {channelsError && (
        <QueryErrorBanner
          title="Could not load channels"
          message={String((channelsErr as Error)?.message ?? channelsErr)}
          onRetry={() => void refetchChannels()}
        />
      )}
      <h2 className="text-xl font-semibold mb-2">Shop products</h2>
      <p className="text-slate-400 text-sm mb-4 leading-relaxed">
        Products are stored as subscription plans. The <strong>payment bot</strong> lists them via{" "}
        <code className="text-cyan-300/90 bg-slate-800 px-1 rounded">GET /subscription-plans/</code> when a user runs{" "}
        <code className="text-cyan-300/90 bg-slate-800 px-1 rounded">/subscribe</code> or <code className="text-cyan-300/90 bg-slate-800 px-1 rounded">/packs</code>{" "}
        — changes apply immediately (no bot restart). You set the <strong>Stars (XTR)</strong> price here; the bot can also
        show <strong>Wallet / crypto</strong>: with NOWPayments + a public <code className="text-cyan-300/90">https://</code> API URL,
        checkout and fulfillment are <strong>automatic</strong>. Otherwise use <strong>Pending wallet orders</strong> below to mark paid manually.
      </p>
      <p className="text-amber-200/90 text-sm mb-6 bg-amber-950/40 border border-amber-800/50 rounded-lg px-3 py-2">
        <strong>Subscriptions</strong> = time-limited access to the linked channel/group (e.g. AOF) — listed under{" "}
        <code className="text-amber-100/90">/subscribe</code> / Premium. <strong>Bundles</strong> = one-time digital packs — listed under{" "}
        <code className="text-amber-100/90">/packs</code> / Digital packs (upload the .zip after creating the product).
      </p>
      <p className="text-slate-400 text-sm mb-6 border border-slate-600/60 rounded-lg px-3 py-2 bg-slate-900/40 leading-relaxed">
        <strong className="text-slate-300">Multiple tiers (e.g. AOF Tier 1 / 2 / 3):</strong> add{" "}
        <em>one product per tier</em> below — use the <strong>same channel / group</strong> if every tier unlocks the same
        private chat, and set different <strong>name</strong>, <strong>duration</strong>, and <strong>Stars price</strong>{" "}
        per tier. There is no separate “tier” field: each tier is its own row. Inactive products are hidden from the bot.
      </p>

      <div className="bg-slate-800 rounded-lg p-4 mb-8 border border-slate-700">
        <h3 className="text-sm font-medium text-slate-300 mb-3">New product</h3>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block sm:col-span-2">
            <span className="text-slate-400 text-xs">Name</span>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. AOF — 30 days"
              className="mt-1 w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200"
            />
          </label>
          <div className="block sm:col-span-2">
            <span className="text-slate-400 text-xs">
              Promo images — <strong className="text-slate-300">album (up to {MAX_PROMO_IMAGES})</strong>, one HTTPS URL
              per image (max 1024 chars each). Telegram sends them as a media group for pack previews; the Stars invoice
              uses the <strong>first</strong> image only. Global /shop section images can still be overridden with{" "}
              <code className="text-cyan-300/80">SHOP_*_IMAGE_URL</code> in <code className="text-cyan-300/80">.env</code>.
            </span>
            <div className="mt-2 space-y-2">
              {promoImageUrls.map((url, i) => (
                <div key={i + url} className="flex flex-col gap-1 sm:flex-row sm:items-center">
                  <input
                    type="text"
                    value={url}
                    onChange={(e) => {
                      const next = [...promoImageUrls];
                      next[i] = e.target.value;
                      setPromoImageUrls(next);
                      setPromoHintAfterUpload(null);
                    }}
                    placeholder={`https://… (image ${i + 1})`}
                    className="w-full flex-1 bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200 text-sm"
                  />
                  <button
                    type="button"
                    onClick={() => setPromoImageUrls((prev) => prev.filter((_, j) => j !== i))}
                    className="text-sm text-red-300 hover:text-red-200 px-2 py-1 shrink-0"
                  >
                    Remove
                  </button>
                </div>
              ))}
              {promoImageUrls.length < MAX_PROMO_IMAGES && (
                <div className="flex flex-col gap-2 sm:flex-row sm:items-center flex-wrap">
                  <button
                    type="button"
                    onClick={() => setPromoImageUrls((prev) => [...prev, ""])}
                    className="text-sm text-cyan-400 hover:underline"
                  >
                    + Add URL slot
                  </button>
                  <input
                    ref={newPromoFileInputRef}
                    type="file"
                    multiple
                    accept="image/*"
                    className="hidden"
                    disabled={uploadPromoImage.isPending}
                    onChange={(e) => {
                      const input = e.currentTarget;
                      const picked = input.files ? Array.from(input.files) : [];
                      input.value = "";
                      void handlePromoFilesSelected(picked, "new");
                    }}
                  />
                  <button
                    type="button"
                    className="inline-flex items-center justify-center px-3 py-2 bg-slate-600 text-white rounded hover:bg-slate-500 text-sm shrink-0 disabled:opacity-50"
                    disabled={uploadPromoImage.isPending}
                    onClick={() => newPromoFileInputRef.current?.click()}
                  >
                    {uploadPromoImage.isPending ? "Uploading…" : "Upload image(s)"}
                  </button>
                </div>
              )}
            </div>
            {uploadPromoImage.isError && (
              <p className="text-red-400 text-xs mt-1">{String((uploadPromoImage.error as Error)?.message ?? "")}</p>
            )}
            <p className="text-slate-500 text-xs mt-1">
              Upload saves under <code className="text-slate-400">/static/promo/</code> using{" "}
              <code className="text-slate-400">TBCC_PROMO_PUBLIC_BASE_URL</code> (or{" "}
              <code className="text-slate-400">TBCC_PUBLIC_BASE_URL</code>). Telegram must fetch images over public{" "}
              <code className="text-slate-400">https://</code>; <code className="text-slate-400">localhost</code> is not
              visible to Telegram.
            </p>
            <PromoUrlHintBox url={promoImageUrls[0] || ""} serverHint={promoHintAfterUpload} />
            {promoImageUrls.some((u) => u.match(/^https?:\/\//i)) && (
              <div className="mt-2 flex flex-wrap gap-2">
                {promoImageUrls
                  .filter((u) => u.match(/^https?:\/\//i))
                  .map((u, i) => (
                    <img
                      key={i + u}
                      src={u}
                      alt=""
                      className="max-h-24 rounded border border-slate-600 object-contain"
                      onError={(e) => {
                        (e.target as HTMLImageElement).style.display = "none";
                      }}
                    />
                  ))}
              </div>
            )}
          </div>
          <label className="block sm:col-span-2">
            <span className="text-slate-400 text-xs">Description (Telegram invoice / help text)</span>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
              placeholder="Short line shown on the Stars invoice"
              className="mt-1 w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200 text-sm"
            />
          </label>
          <div className="block sm:col-span-2">
            <span className="text-slate-400 text-xs">
              Extra description variants (optional) — the bot picks one at random from the main description plus these lines
              when someone opens this product (max {MAX_DESC_VARIANTS})
            </span>
            <div className="mt-2 space-y-2">
              {descriptionVariants.map((line, i) => (
                <div key={i} className="flex flex-col gap-1 sm:flex-row sm:items-start">
                  <textarea
                    value={line}
                    onChange={(e) => {
                      const next = [...descriptionVariants];
                      next[i] = e.target.value;
                      setDescriptionVariants(next);
                    }}
                    rows={2}
                    placeholder="Alternate pitch / copy"
                    className="flex-1 w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200 text-sm"
                  />
                  <button
                    type="button"
                    onClick={() => setDescriptionVariants((prev) => prev.filter((_, j) => j !== i))}
                    className="text-sm text-red-300 hover:text-red-200 shrink-0"
                  >
                    Remove
                  </button>
                </div>
              ))}
              {descriptionVariants.length < MAX_DESC_VARIANTS && (
                <button
                  type="button"
                  onClick={() => setDescriptionVariants((prev) => [...prev, ""])}
                  className="text-sm text-cyan-400 hover:underline"
                >
                  + Add description variant
                </button>
              )}
            </div>
          </div>
          <div className="block sm:col-span-2 border border-slate-600/70 rounded-lg p-3 bg-slate-800/30">
            <span className="text-slate-400 text-xs">Catalog tags (same pool as media — GET /tags)</span>
            <p className="text-slate-500 text-xs mt-1">Used for organization; bot can append #hashtags on digital pack cards.</p>
            {sortedTags.length === 0 ? (
              <p className="text-amber-200/80 text-xs mt-2">No tags in the database yet — add tags first.</p>
            ) : (
              <div className="mt-2 max-h-32 overflow-y-auto border border-slate-600 rounded p-2 space-y-1">
                {sortedTags.map((t) => (
                  <label key={t.id} className="flex items-center gap-2 text-sm text-slate-300 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={newTagIds.includes(t.id)}
                      onChange={() => toggleNewTag(t.id)}
                    />
                    <span className="font-mono text-slate-400">{t.slug}</span>
                    <span className="text-slate-500 truncate">{t.name}</span>
                  </label>
                ))}
              </div>
            )}
          </div>
          <label className="block">
            <span className="text-slate-400 text-xs">Price (Telegram Stars — XTR)</span>
            <input
              type="number"
              min={0}
              value={priceStars}
              onChange={(e) => setPriceStars(Number(e.target.value) || 0)}
              className="mt-1 w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200"
            />
          </label>
          <label className="block">
            <span className="text-slate-400 text-xs">Duration (days)</span>
            <input
              type="number"
              min={1}
              value={durationDays}
              onChange={(e) => setDurationDays(Number(e.target.value) || 30)}
              className="mt-1 w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200"
            />
          </label>
          <label className="block sm:col-span-2">
            <span className="text-slate-400 text-xs">Grant access to channel / group</span>
            <select
              value={channelId}
              onChange={(e) => setChannelId(e.target.value === "" ? "" : Number(e.target.value))}
              className="mt-1 w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200"
              disabled={channelsPending && !channels.length}
            >
              {channelSelectOptions}
            </select>
          </label>
          <label className="block">
            <span className="text-slate-400 text-xs">Product type</span>
            <select
              value={productType}
              onChange={(e) => setProductType(e.target.value as "subscription" | "bundle")}
              className="mt-1 w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200"
            >
              <option value="subscription">Subscription (channel access)</option>
              <option value="bundle">Bundle (digital pack — bot checkout TBD)</option>
            </select>
          </label>
          <label className="block">
            <span className="text-slate-400 text-xs">Payment bot section</span>
            <select
              value={botSection}
              onChange={(e) => setBotSection(e.target.value as "main" | "loot" | "packs")}
              className="mt-1 w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200"
            >
              <option value="main">Main (/subscribe)</option>
              <option value="loot">Loot Room (/loot)</option>
              <option value="packs">Packs-focused section</option>
            </select>
          </label>
          <label className="flex items-center gap-2 mt-6 sm:mt-8">
            <input type="checkbox" checked={isActive} onChange={(e) => setIsActive(e.target.checked)} />
            <span className="text-slate-300 text-sm">Active (show in bot)</span>
          </label>
          {productType === "bundle" && (
            <p className="sm:col-span-2 text-amber-200/80 text-xs">
              After creating a <strong>bundle</strong>, open it from the table below to upload the .zip.
            </p>
          )}
        </div>
        {create.isError && (
          <div
            className="mt-4 text-sm text-red-200 bg-red-950/50 border border-red-800/60 rounded-lg px-3 py-2"
            role="alert"
          >
            <strong className="block text-red-100 mb-1">Could not create product</strong>
            {String((create.error as Error)?.message ?? create.error)}
            <p className="text-red-200/80 text-xs mt-2">
              Check that the API is running and the dashboard can reach it (same host as{" "}
              <code className="text-red-100/90">/api</code>). Open the browser devtools Network tab if this keeps failing.
            </p>
          </div>
        )}
        {justCreatedOk && (
          <p className="mt-4 text-sm text-emerald-200/90 bg-emerald-950/40 border border-emerald-800/50 rounded-lg px-3 py-2">
            Product added — it should appear in the table below. In the payment bot, visibility is controlled by{" "}
            <strong>Product type</strong> + <strong>Payment bot section</strong> (for example /subscribe vs /loot).
          </p>
        )}
        <div className="flex flex-wrap items-center gap-2 mt-4">
          <button
            type="button"
            onClick={() => create.mutate()}
            disabled={create.isPending || priceStars <= 0}
            className="px-4 py-2 bg-cyan-600 text-white rounded hover:bg-cyan-500 disabled:opacity-50"
            title={priceStars <= 0 ? "Set Stars price greater than 0" : "Save this product to the database"}
          >
            {create.isPending ? "Creating…" : "Add product"}
          </button>
          {priceStars <= 0 && (
            <span className="text-amber-200/90 text-xs">Set price (Stars) above 0 to enable Add product.</span>
          )}
        </div>
      </div>

      {editOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 overflow-y-auto"
          role="dialog"
          aria-modal="true"
          aria-labelledby="product-edit-title"
          onClick={(e) => {
            if (e.target === e.currentTarget) closeProductEditor();
          }}
        >
          <div
            className="bg-slate-800 border border-slate-600 rounded-lg p-6 max-w-2xl w-full shadow-xl my-8"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 id="product-edit-title" className="text-lg font-medium mb-3">
              Edit product
            </h2>
            <div className="grid gap-3 sm:grid-cols-2 max-h-[min(70vh,720px)] overflow-y-auto pr-1">
              <label className="block sm:col-span-2">
                <span className="text-slate-400 text-xs">Name</span>
                <input
                  type="text"
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  className="mt-1 w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200"
                />
              </label>
              <div className="block sm:col-span-2">
                <span className="text-slate-400 text-xs">
                  Promo images (album, up to {MAX_PROMO_IMAGES}) — one HTTPS URL per line; invoice uses the first image
                </span>
                <div className="mt-2 space-y-2">
                  {editPromoImageUrls.map((url, i) => (
                    <div key={i + url} className="flex flex-col gap-1 sm:flex-row sm:items-center">
                      <input
                        type="text"
                        value={url}
                        onChange={(e) => {
                          const next = [...editPromoImageUrls];
                          next[i] = e.target.value;
                          setEditPromoImageUrls(next);
                          setEditPromoHintAfterUpload(null);
                        }}
                        className="w-full flex-1 bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200 text-sm"
                      />
                      <button
                        type="button"
                        onClick={() => setEditPromoImageUrls((prev) => prev.filter((_, j) => j !== i))}
                        className="text-sm text-red-300 hover:text-red-200 px-2 py-1 shrink-0"
                      >
                        Remove
                      </button>
                    </div>
                  ))}
                  {editPromoImageUrls.length < MAX_PROMO_IMAGES && (
                    <div className="flex flex-col gap-2 sm:flex-row sm:items-center flex-wrap">
                      <button
                        type="button"
                        onClick={() => setEditPromoImageUrls((prev) => [...prev, ""])}
                        className="text-sm text-cyan-400 hover:underline"
                      >
                        + Add URL slot
                      </button>
                      <input
                        ref={editPromoFileInputRef}
                        type="file"
                        multiple
                        accept="image/*"
                        className="hidden"
                        disabled={uploadPromoImage.isPending}
                        onChange={(e) => {
                          const input = e.currentTarget;
                          const picked = input.files ? Array.from(input.files) : [];
                          input.value = "";
                          void handlePromoFilesSelected(picked, "edit");
                        }}
                      />
                      <button
                        type="button"
                        className="inline-flex items-center justify-center px-3 py-2 bg-slate-600 text-white rounded hover:bg-slate-500 text-sm shrink-0 disabled:opacity-50"
                        disabled={uploadPromoImage.isPending}
                        onClick={() => editPromoFileInputRef.current?.click()}
                      >
                        {uploadPromoImage.isPending ? "Uploading…" : "Upload"}
                      </button>
                    </div>
                  )}
                </div>
                {uploadPromoImage.isError && (
                  <p className="text-red-400 text-xs mt-1">{String((uploadPromoImage.error as Error)?.message ?? "")}</p>
                )}
                <PromoUrlHintBox url={editPromoImageUrls[0] || ""} serverHint={editPromoHintAfterUpload} />
                {editPromoImageUrls.some((u) => u.match(/^https?:\/\//i)) && (
                  <div className="mt-2 flex flex-wrap gap-2">
                    {editPromoImageUrls
                      .filter((u) => u.match(/^https?:\/\//i))
                      .map((u, i) => (
                        <img
                          key={i + u}
                          src={u}
                          alt=""
                          className="max-h-24 rounded border border-slate-600 object-contain"
                          onError={(e) => {
                            (e.target as HTMLImageElement).style.display = "none";
                          }}
                        />
                      ))}
                  </div>
                )}
              </div>
              <label className="block sm:col-span-2">
                <span className="text-slate-400 text-xs">Description (Telegram invoice / help text)</span>
                <textarea
                  value={editDescription}
                  onChange={(e) => setEditDescription(e.target.value)}
                  rows={2}
                  className="mt-1 w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200 text-sm"
                />
              </label>
              <div className="block sm:col-span-2">
                <span className="text-slate-400 text-xs">
                  Extra description variants (optional) — random pick with main description (max {MAX_DESC_VARIANTS})
                </span>
                <div className="mt-2 space-y-2">
                  {editDescriptionVariants.map((line, i) => (
                    <div key={i} className="flex flex-col gap-1 sm:flex-row sm:items-start">
                      <textarea
                        value={line}
                        onChange={(e) => {
                          const next = [...editDescriptionVariants];
                          next[i] = e.target.value;
                          setEditDescriptionVariants(next);
                        }}
                        rows={2}
                        placeholder="Alternate pitch / copy"
                        className="flex-1 w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200 text-sm"
                      />
                      <button
                        type="button"
                        onClick={() => setEditDescriptionVariants((prev) => prev.filter((_, j) => j !== i))}
                        className="text-sm text-red-300 hover:text-red-200 shrink-0"
                      >
                        Remove
                      </button>
                    </div>
                  ))}
                  {editDescriptionVariants.length < MAX_DESC_VARIANTS && (
                    <button
                      type="button"
                      onClick={() => setEditDescriptionVariants((prev) => [...prev, ""])}
                      className="text-sm text-cyan-400 hover:underline"
                    >
                      + Add description variant
                    </button>
                  )}
                </div>
              </div>
              <div className="block sm:col-span-2 border border-cyan-900/40 rounded-lg p-3 bg-cyan-950/15">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="text-slate-400 text-xs">Catalog tags (tbcc tag pool)</span>
                  <button
                    type="button"
                    disabled={aiSuggest.isPending || !editName.trim() || !llmStatus?.openai_configured}
                    onClick={() => aiSuggest.mutate()}
                    className="text-xs px-2 py-1 rounded border border-violet-600/60 text-violet-200 hover:bg-violet-950/40 disabled:opacity-40"
                  >
                    {aiSuggest.isPending ? "AI…" : "Suggest copy & tags (AI)"}
                  </button>
                </div>
                {llmStatus && !llmStatus.openai_configured ? (
                  <p className="text-amber-200/85 text-xs mt-1">
                    Set <code className="text-slate-300">OPENAI_API_KEY</code> or{" "}
                    <code className="text-slate-300">TBCC_OPENAI_API_KEY</code> in tbcc/.env and restart the API.
                  </p>
                ) : null}
                {aiSuggest.isError ? (
                  <p className="text-red-300 text-xs mt-1">{(aiSuggest.error as Error).message}</p>
                ) : null}
                <p className="text-slate-500 text-xs mt-1">AI only assigns tags that already exist in TBCC.</p>
                {sortedTags.length === 0 ? (
                  <p className="text-amber-200/80 text-xs mt-2">No tags yet — create tags first.</p>
                ) : (
                  <div className="mt-2 max-h-36 overflow-y-auto border border-slate-600 rounded p-2 space-y-1">
                    {sortedTags.map((t) => (
                      <label key={t.id} className="flex items-center gap-2 text-sm text-slate-300 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={editTagIds.includes(t.id)}
                          onChange={() => toggleEditTag(t.id)}
                        />
                        <span className="font-mono text-slate-400">{t.slug}</span>
                        <span className="text-slate-500 truncate">{t.name}</span>
                      </label>
                    ))}
                  </div>
                )}
              </div>
              <label className="block">
                <span className="text-slate-400 text-xs">Price (Telegram Stars — XTR)</span>
                <input
                  type="number"
                  min={0}
                  value={editPriceStars}
                  onChange={(e) => setEditPriceStars(Number(e.target.value) || 0)}
                  className="mt-1 w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200"
                />
              </label>
              <label className="block">
                <span className="text-slate-400 text-xs">Duration (days)</span>
                <input
                  type="number"
                  min={1}
                  value={editDurationDays}
                  onChange={(e) => setEditDurationDays(Number(e.target.value) || 30)}
                  className="mt-1 w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200"
                />
              </label>
              <label className="block sm:col-span-2">
                <span className="text-slate-400 text-xs">Grant access to channel / group</span>
                <select
                  value={editChannelId}
                  onChange={(e) => setEditChannelId(e.target.value === "" ? "" : Number(e.target.value))}
                  className="mt-1 w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200"
                >
                  {channelSelectOptions}
                </select>
              </label>
              <label className="block">
                <span className="text-slate-400 text-xs">Product type</span>
                <select
                  value={editProductType}
                  onChange={(e) => setEditProductType(e.target.value as "subscription" | "bundle")}
                  className="mt-1 w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200"
                >
                  <option value="subscription">Subscription (channel access)</option>
                  <option value="bundle">Bundle (digital pack)</option>
                </select>
              </label>
              <label className="block">
                <span className="text-slate-400 text-xs">Payment bot section</span>
                <select
                  value={editBotSection}
                  onChange={(e) => setEditBotSection(e.target.value as "main" | "loot" | "packs")}
                  className="mt-1 w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200"
                >
                  <option value="main">Main (/subscribe)</option>
                  <option value="loot">Loot Room (/loot)</option>
                  <option value="packs">Packs-focused section</option>
                </select>
              </label>
              <label className="flex items-center gap-2 mt-6 sm:mt-8">
                <input type="checkbox" checked={editIsActive} onChange={(e) => setEditIsActive(e.target.checked)} />
                <span className="text-slate-300 text-sm">Active (show in bot)</span>
              </label>
              {editProductType === "bundle" && (
                <div className="sm:col-span-2 border border-cyan-800/50 rounded-lg p-3 bg-cyan-950/20 space-y-3">
                  <p className="text-cyan-200/90 text-sm font-medium">Digital pack (.zip)</p>
                  <p className="text-slate-400 text-xs leading-relaxed">
                    Add one <strong>.zip</strong> per part (split large packs). After purchase, the payment bot sends each
                    part as its own message. <strong>Max ~50 MB per zip</strong> (Telegram Bot API). Up to{" "}
                    <strong>20 parts</strong> per product.
                  </p>
                  {bundleUploadFlash ? (
                    <p className="text-emerald-300/95 text-xs font-medium border border-emerald-800/50 rounded px-2 py-2 bg-emerald-950/40">
                      {bundleUploadFlash}
                    </p>
                  ) : null}
                  {(() => {
                    const cur = (plans as Array<Record<string, unknown>>).find((x) => Number(x.id) === editId);
                    const rawParts = cur?.bundle_zip_parts;
                    const parts = Array.isArray(rawParts)
                      ? rawParts.map((x) => String(x || "").trim()).filter(Boolean)
                      : [];
                    const count = bundleZipPartCount(cur ?? {});
                    const maxParts = 20;
                    return (
                      <>
                        {parts.length > 0 ? (
                          <ul className="space-y-2 list-none m-0 p-0">
                            {parts.map((name, idx) => (
                              <li
                                key={`${idx}-${name}`}
                                className="flex flex-wrap items-center gap-2 justify-between rounded border border-slate-600/80 bg-slate-800/40 px-2 py-2"
                              >
                                <div className="min-w-0 flex-1 flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                                  <span className="text-slate-500 text-xs shrink-0">Part {idx + 1}</span>
                                  <span className="text-slate-100 text-sm truncate max-w-[min(100%,16rem)]" title={name}>
                                    {name}
                                  </span>
                                  <span className="text-emerald-400/90 text-xs font-medium shrink-0">Uploaded</span>
                                </div>
                                <button
                                  type="button"
                                  onClick={() => {
                                    if (
                                      confirm(
                                        `Remove part ${idx + 1} (“${name}”)? Buyers will not receive this file until you upload again.`,
                                      )
                                    )
                                      deleteBundleZip.mutate({ id: editId, index: idx });
                                  }}
                                  disabled={deleteBundleZip.isPending}
                                  className="text-sm text-red-300 hover:text-red-200 px-2 py-1 rounded border border-red-800/50 shrink-0"
                                >
                                  Remove
                                </button>
                              </li>
                            ))}
                          </ul>
                        ) : (
                          <p className="text-slate-500 text-xs">No zips yet — use “Add part” to upload the first archive.</p>
                        )}
                        <input
                          ref={bundleAddInputRef}
                          type="file"
                          accept=".zip,application/zip"
                          className="hidden"
                          disabled={uploadBundleZip.isPending || count >= maxParts}
                          onChange={(e) => {
                            const f = e.target.files?.[0];
                            e.target.value = "";
                            if (!f || !editId) return;
                            uploadBundleZip.mutate({ id: editId, file: f });
                          }}
                        />
                        <div className="flex flex-wrap items-center gap-2">
                          <button
                            type="button"
                            onClick={() => bundleAddInputRef.current?.click()}
                            disabled={uploadBundleZip.isPending || count >= maxParts}
                            className="text-sm px-3 py-1.5 rounded border border-cyan-700/60 text-cyan-200 hover:bg-cyan-950/50 disabled:opacity-50"
                          >
                            + Add part
                          </button>
                          {count >= maxParts ? (
                            <span className="text-amber-200/90 text-xs">Maximum {maxParts} parts reached.</span>
                          ) : null}
                        </div>
                        {parts.length > 0 ? (
                          <button
                            type="button"
                            onClick={() => {
                              if (
                                confirm(
                                  "Remove all uploaded zips for this product? Buyers will not receive files until you upload again.",
                                )
                              )
                                deleteBundleZip.mutate({ id: editId });
                            }}
                            disabled={deleteBundleZip.isPending}
                            className="text-xs text-slate-400 hover:text-slate-300 underline"
                          >
                            Remove all zips
                          </button>
                        ) : null}
                      </>
                    );
                  })()}
                  {uploadBundleZip.isError && (
                    <p className="text-red-300 text-xs">{(uploadBundleZip.error as Error).message}</p>
                  )}
                </div>
              )}
            </div>
            {patch.isError && (
              <p className="text-red-300 text-sm mt-2">{(patch.error as Error)?.message}</p>
            )}
            <div className="flex flex-wrap justify-between gap-2 mt-6 pt-4 border-t border-slate-600">
              <button
                type="button"
                onClick={() => {
                  if (confirm("Delete this product?")) remove.mutate(editId);
                }}
                disabled={remove.isPending}
                className="px-3 py-2 rounded bg-red-900/50 text-red-200 hover:bg-red-900/70 border border-red-800/50"
              >
                Delete product
              </button>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={closeProductEditor}
                  className="px-4 py-2 bg-slate-600 text-slate-200 rounded hover:bg-slate-500"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={saveProductEditor}
                  disabled={patch.isPending || editPriceStars <= 0}
                  className="px-4 py-2 bg-cyan-600 text-white rounded hover:bg-cyan-500 disabled:opacity-50"
                >
                  {patch.isPending ? "Saving…" : "Save changes"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="w-full text-sm border border-slate-600 rounded-lg overflow-hidden">
          <thead className="bg-slate-700">
            <tr className="text-left text-slate-300">
              <th className="p-3">Name</th>
              <th className="p-3">Type</th>
              <th className="p-3">Bot section</th>
              <th className="p-3">⭐</th>
              <th className="p-3">Days</th>
              <th className="p-3">Channel</th>
              <th className="p-3">Promo</th>
              <th className="p-3">Zip</th>
              <th className="p-3">Tags</th>
              <th className="p-3">Active</th>
              <th className="p-3 w-32">Actions</th>
            </tr>
          </thead>
          <tbody>
            {plansPending && !plans.length && !plansError ? (
              <tr>
                <td colSpan={11} className="p-4 text-slate-500">
                  Loading products…
                </td>
              </tr>
            ) : null}
            {(plans as Array<Record<string, unknown>>).map((p) => {
              const promoList = promoUrlsFromPlan(p);
              const promoN = promoList.length;
              return (
              <tr
                key={String(p.id)}
                className="border-t border-slate-600 hover:bg-slate-800/50 cursor-pointer"
                onClick={() => openProductEditor(p)}
                title="Click row to edit product"
              >
                <td className="p-3 font-medium">{String(p.name)}</td>
                <td className="p-3 text-slate-400">{String(p.product_type || "subscription")}</td>
                <td className="p-3 text-slate-400">{String(p.bot_section || "main")}</td>
                <td className="p-3">{String(p.price_stars ?? 0)}</td>
                <td className="p-3">{String(p.duration_days ?? 30)}</td>
                <td className="p-3 text-slate-400 max-w-[140px] truncate">
                  {p.channel_id ? channelMap[String(p.channel_id)] ?? `#${p.channel_id}` : "—"}
                </td>
                <td className="p-3 text-slate-500 max-w-[80px] truncate" title={promoList.join("\n") || ""}>
                  {promoN > 1 ? `${promoN}×` : promoN === 1 ? "img" : "—"}
                </td>
                <td className="p-3 text-slate-400 text-xs">
                  {(p.product_type as string) === "bundle"
                    ? (() => {
                        const n = bundleZipPartCount(p);
                        if (n === 0) return "—";
                        return String(n);
                      })()
                    : "—"}
                </td>
                <td className="p-3 text-slate-400 text-xs" title="Tag count (catalog)">
                  {planTagCount(p) === 0 ? "—" : String(planTagCount(p))}
                </td>
                <td className="p-3">{p.is_active === false ? "—" : "✓"}</td>
                <td className="p-3 whitespace-nowrap">
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      openProductEditor(p);
                    }}
                    className="text-cyan-400 hover:underline mr-2"
                  >
                    Edit
                  </button>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      if (confirm("Delete this product?")) remove.mutate(Number(p.id));
                    }}
                    className="text-red-400 hover:text-red-300"
                  >
                    Delete
                  </button>
                </td>
              </tr>
            );
            })}
          </tbody>
        </table>
      </div>
      <p className="text-slate-500 text-xs mt-2">
        Tip: click any row to open the editor (same pattern as Content Pools → Pools table).
      </p>
      {(plans as unknown[]).length === 0 && !plansPending && !plansError && (
        <p className="text-slate-500 mt-4">No products yet.</p>
      )}

      <WalletPendingOrders />
    </div>
  );
}
