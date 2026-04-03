import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import { useState, useEffect } from "react";
import { QueryErrorBanner } from "../components/QueryErrorBanner";

/** Telegram fetches URLs from its servers — not your browser. */
function promoUrlWarning(url: string): string | null {
  const t = url.trim();
  if (!t) return null;
  const low = t.toLowerCase();
  if (low.includes("localhost") || low.includes("127.0.0.1")) {
    return "Telegram cannot load images from localhost. Set TBCC_PROMO_PUBLIC_BASE_URL (or TBCC_PUBLIC_BASE_URL) in tbcc/.env to your public https:// host, restart the API, re-upload — or paste a direct https:// image link.";
  }
  if (/^http:\/\//i.test(t) && !/^https:\/\//i.test(t)) {
    return "Use https:// for Telegram invoice/catalog photos.";
  }
  if ((/imgbb\.com|\/ibb\.co\//i.test(t) || /^https?:\/\/[^/]*ibb\.co\//i.test(t)) && !/i\.ibb\.co/i.test(t)) {
    return "Use ImgBB’s direct image link (https://i.ibb.co/.../file.jpg), not the ibb.co HTML page.";
  }
  return null;
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

  const channelMap = Object.fromEntries(
    (channels as Array<Record<string, unknown>>).map((c) => [String(c.id), String(c.name || c.identifier || c.id)])
  );

  /** New product (top form only) */
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [priceStars, setPriceStars] = useState(100);
  const [durationDays, setDurationDays] = useState(30);
  const [channelId, setChannelId] = useState<number | "">("");
  const [productType, setProductType] = useState<"subscription" | "bundle">("subscription");
  const [isActive, setIsActive] = useState(true);
  const [promoImageUrl, setPromoImageUrl] = useState("");
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
  const [editPriceStars, setEditPriceStars] = useState(100);
  const [editDurationDays, setEditDurationDays] = useState(30);
  const [editChannelId, setEditChannelId] = useState<number | "">("");
  const [editProductType, setEditProductType] = useState<"subscription" | "bundle">("subscription");
  const [editIsActive, setEditIsActive] = useState(true);
  const [editPromoImageUrl, setEditPromoImageUrl] = useState("");
  const [editPromoHintAfterUpload, setEditPromoHintAfterUpload] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: () =>
      api.subscriptionPlans.create({
        name: name.trim() || "New product",
        description: description.trim() || undefined,
        price_stars: priceStars,
        duration_days: durationDays,
        channel_id: channelId === "" ? undefined : channelId,
        product_type: productType,
        is_active: isActive,
        promo_image_url: promoImageUrl.trim() || undefined,
      }),
    onMutate: () => {
      setJustCreatedOk(false);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["subscriptionPlans"] });
      setName("");
      setDescription("");
      setPriceStars(100);
      setDurationDays(30);
      setChannelId("");
      setProductType("subscription");
      setIsActive(true);
      setPromoImageUrl("");
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

  const uploadBundleZip = useMutation({
    mutationFn: ({ id, file }: { id: number; file: File }) => api.subscriptionPlans.uploadBundleZip(id, file),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["subscriptionPlans"] }),
  });

  const deleteBundleZip = useMutation({
    mutationFn: (id: number) => api.subscriptionPlans.deleteBundleZip(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["subscriptionPlans"] }),
  });

  const uploadPromoImage = useMutation({
    mutationFn: async ({ file, target }: { file: File; target: "new" | "edit" }) => {
      const data = await api.subscriptionPlans.uploadPromoImage(file);
      return { ...data, target };
    },
    onSuccess: (data) => {
      const hint = data.telegram_hint ?? (data.telegram_reachable === false ? "This URL is not reachable by Telegram’s servers." : null);
      if (data.target === "edit") {
        setEditPromoImageUrl(data.url);
        setEditPromoHintAfterUpload(hint);
      } else {
        setPromoImageUrl(data.url);
        setPromoHintAfterUpload(hint);
      }
    },
  });

  function openProductEditor(p: Record<string, unknown>) {
    setEditId(Number(p.id));
    setEditName(String(p.name || ""));
    setEditDescription(String(p.description || ""));
    setEditPriceStars(Number(p.price_stars ?? 0));
    setEditDurationDays(Number(p.duration_days ?? 30));
    setEditChannelId(p.channel_id != null ? Number(p.channel_id) : "");
    setEditProductType(((p.product_type as string) || "subscription") === "bundle" ? "bundle" : "subscription");
    setEditIsActive(p.is_active !== false);
    setEditPromoImageUrl(String(p.promo_image_url || ""));
    setEditPromoHintAfterUpload(null);
    setEditOpen(true);
  }

  function closeProductEditor() {
    setEditOpen(false);
  }

  function saveProductEditor() {
    if (!editId) return;
    patch.mutate({
      id: editId,
      body: {
        name: editName.trim() || "Product",
        description: editDescription.trim() || null,
        price_stars: editPriceStars,
        duration_days: editDurationDays,
        channel_id: editChannelId === "" ? null : editChannelId,
        product_type: editProductType,
        is_active: editIsActive,
        promo_image_url: editPromoImageUrl.trim() || null,
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
        show a separate <strong>Wallet / crypto</strong> row (order code + admin confirms) — that is{" "}
        <strong>not</strong> configured on this page; it appears automatically in Telegram after you add a product.
      </p>
      <p className="text-amber-200/90 text-sm mb-6 bg-amber-950/40 border border-amber-800/50 rounded-lg px-3 py-2">
        <strong>Subscriptions</strong> = time-limited access to the linked channel/group (e.g. AOF) — listed under{" "}
        <code className="text-amber-100/90">/subscribe</code> / Premium. <strong>Bundles</strong> = one-time digital packs — listed under{" "}
        <code className="text-amber-100/90">/packs</code> / Digital packs (upload the .zip after creating the product).
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
          <label className="block sm:col-span-2">
            <span className="text-slate-400 text-xs">
              Promo image — <strong className="text-slate-300">one URL only</strong> (max 1024 chars). Not a list — do
              not use commas. The /shop carousel uses a single image per section (see env{" "}
              <code className="text-cyan-300/80">SHOP_*_IMAGE_URL</code> in <code className="text-cyan-300/80">.env</code>{" "}
              for global hero/section overrides).
            </span>
            <div className="mt-1 flex flex-col gap-2 sm:flex-row sm:items-center">
              <input
                type="text"
                value={promoImageUrl}
                onChange={(e) => {
                  setPromoImageUrl(e.target.value);
                  setPromoHintAfterUpload(null);
                }}
                placeholder="https://… (one image URL for bot /shop promo)"
                className="w-full flex-1 bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200 text-sm"
              />
              <label className="inline-flex items-center justify-center px-3 py-2 bg-slate-600 text-white rounded cursor-pointer hover:bg-slate-500 text-sm shrink-0">
                <input
                  type="file"
                  accept="image/jpeg,image/png,image/gif,image/webp"
                  className="hidden"
                  disabled={uploadPromoImage.isPending}
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    e.target.value = "";
                    if (f) uploadPromoImage.mutate({ file: f, target: "new" });
                  }}
                />
                {uploadPromoImage.isPending ? "Uploading…" : "Upload file"}
              </label>
            </div>
            {uploadPromoImage.isError && (
              <p className="text-red-400 text-xs mt-1">{String((uploadPromoImage.error as Error)?.message ?? "")}</p>
            )}
            <p className="text-slate-500 text-xs mt-1">
              Upload saves under <code className="text-slate-400">/static/promo/</code> and fills this field using{" "}
              <code className="text-slate-400">TBCC_PROMO_PUBLIC_BASE_URL</code> (best) or{" "}
              <code className="text-slate-400">TBCC_PUBLIC_BASE_URL</code> / <code className="text-slate-400">TBCC_API_URL</code>{" "}
              from <code className="text-slate-400">tbcc/.env</code>. Set <strong>one</strong> public{" "}
              <code className="text-slate-400">https://</code> base (e.g. ngrok) so you can keep using Upload — no need to
              paste ImgBB for every product. <code className="text-slate-400">localhost</code> is not visible to Telegram.
            </p>
            {(promoUrlWarning(promoImageUrl) || promoHintAfterUpload) && (
              <div className="mt-2 text-xs text-amber-100 bg-amber-950/70 border border-amber-700/60 rounded px-2 py-2 leading-snug">
                {promoUrlWarning(promoImageUrl) || promoHintAfterUpload}
              </div>
            )}
            {promoImageUrl.match(/^https?:\/\//i) && (
              <img
                src={promoImageUrl}
                alt="Promo preview"
                className="mt-2 max-h-32 rounded border border-slate-600 object-contain"
                onError={(e) => {
                  (e.target as HTMLImageElement).style.display = "none";
                }}
              />
            )}
          </label>
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
            Product added — it should appear in the table below. Subscriptions show in the bot under{" "}
            <strong>/subscribe</strong> (not under /packs).
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
              <label className="block sm:col-span-2">
                <span className="text-slate-400 text-xs">Promo image URL (one HTTPS URL)</span>
                <div className="mt-1 flex flex-col gap-2 sm:flex-row sm:items-center">
                  <input
                    type="text"
                    value={editPromoImageUrl}
                    onChange={(e) => {
                      setEditPromoImageUrl(e.target.value);
                      setEditPromoHintAfterUpload(null);
                    }}
                    className="w-full flex-1 bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200 text-sm"
                  />
                  <label className="inline-flex items-center justify-center px-3 py-2 bg-slate-600 text-white rounded cursor-pointer hover:bg-slate-500 text-sm shrink-0">
                    <input
                      type="file"
                      accept="image/jpeg,image/png,image/gif,image/webp"
                      className="hidden"
                      disabled={uploadPromoImage.isPending}
                      onChange={(e) => {
                        const f = e.target.files?.[0];
                        e.target.value = "";
                        if (f) uploadPromoImage.mutate({ file: f, target: "edit" });
                      }}
                    />
                    Upload
                  </label>
                </div>
                {(promoUrlWarning(editPromoImageUrl) || editPromoHintAfterUpload) && (
                  <div className="mt-2 text-xs text-amber-100 bg-amber-950/70 border border-amber-700/60 rounded px-2 py-2 leading-snug">
                    {promoUrlWarning(editPromoImageUrl) || editPromoHintAfterUpload}
                  </div>
                )}
                {editPromoImageUrl.match(/^https?:\/\//i) && (
                  <img
                    src={editPromoImageUrl}
                    alt=""
                    className="mt-2 max-h-28 rounded border border-slate-600 object-contain"
                    onError={(e) => {
                      (e.target as HTMLImageElement).style.display = "none";
                    }}
                  />
                )}
              </label>
              <label className="block sm:col-span-2">
                <span className="text-slate-400 text-xs">Description (Telegram invoice / help text)</span>
                <textarea
                  value={editDescription}
                  onChange={(e) => setEditDescription(e.target.value)}
                  rows={2}
                  className="mt-1 w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-slate-200 text-sm"
                />
              </label>
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
              <label className="flex items-center gap-2 mt-6 sm:mt-8">
                <input type="checkbox" checked={editIsActive} onChange={(e) => setEditIsActive(e.target.checked)} />
                <span className="text-slate-300 text-sm">Active (show in bot)</span>
              </label>
              {editProductType === "bundle" && (
                <div className="sm:col-span-2 border border-cyan-800/50 rounded-lg p-3 bg-cyan-950/20 space-y-2">
                  <p className="text-cyan-200/90 text-sm font-medium">Digital pack (.zip)</p>
                  <p className="text-slate-400 text-xs leading-relaxed">
                    Upload a single <strong>.zip</strong> of images/videos. After a customer pays with Telegram Stars, the
                    payment bot sends this file in the chat (max ~50 MB — Telegram limit).
                  </p>
                  <div className="flex flex-wrap items-center gap-3">
                    <input
                      type="file"
                      accept=".zip,application/zip"
                      disabled={uploadBundleZip.isPending}
                      onChange={(e) => {
                        const f = e.target.files?.[0];
                        e.target.value = "";
                        if (!f || !editId) return;
                        uploadBundleZip.mutate({ id: editId, file: f });
                      }}
                      className="text-slate-300 text-sm max-w-full"
                    />
                    {(plans as Array<Record<string, unknown>>).find((x) => Number(x.id) === editId)?.bundle_zip_available ===
                      true && (
                      <button
                        type="button"
                        onClick={() => {
                          if (
                            confirm(
                              "Remove the uploaded zip? Buyers will no longer receive a file until you upload again."
                            )
                          )
                            deleteBundleZip.mutate(editId);
                        }}
                        disabled={deleteBundleZip.isPending}
                        className="text-sm text-red-300 hover:text-red-200 px-2 py-1 rounded border border-red-800/50"
                      >
                        Remove zip
                      </button>
                    )}
                  </div>
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
              <th className="p-3">⭐</th>
              <th className="p-3">Days</th>
              <th className="p-3">Channel</th>
              <th className="p-3">Promo</th>
              <th className="p-3">Zip</th>
              <th className="p-3">Active</th>
              <th className="p-3 w-32">Actions</th>
            </tr>
          </thead>
          <tbody>
            {plansPending && !plans.length && !plansError ? (
              <tr>
                <td colSpan={9} className="p-4 text-slate-500">
                  Loading products…
                </td>
              </tr>
            ) : null}
            {(plans as Array<Record<string, unknown>>).map((p) => (
              <tr
                key={String(p.id)}
                className="border-t border-slate-600 hover:bg-slate-800/50 cursor-pointer"
                onClick={() => openProductEditor(p)}
                title="Click row to edit product"
              >
                <td className="p-3 font-medium">{String(p.name)}</td>
                <td className="p-3 text-slate-400">{String(p.product_type || "subscription")}</td>
                <td className="p-3">{String(p.price_stars ?? 0)}</td>
                <td className="p-3">{String(p.duration_days ?? 30)}</td>
                <td className="p-3 text-slate-400 max-w-[140px] truncate">
                  {p.channel_id ? channelMap[String(p.channel_id)] ?? `#${p.channel_id}` : "—"}
                </td>
                <td className="p-3 text-slate-500 max-w-[80px] truncate" title={String(p.promo_image_url || "")}>
                  {p.promo_image_url ? "img" : "—"}
                </td>
                <td className="p-3 text-slate-400 text-xs">
                  {(p.product_type as string) === "bundle" ? (p.bundle_zip_available ? "✓" : "—") : "—"}
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
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-slate-500 text-xs mt-2">
        Tip: click any row to open the editor (same pattern as Content Pools → Pools table).
      </p>
      {(plans as unknown[]).length === 0 && !plansPending && !plansError && (
        <p className="text-slate-500 mt-4">No products yet.</p>
      )}
    </div>
  );
}
