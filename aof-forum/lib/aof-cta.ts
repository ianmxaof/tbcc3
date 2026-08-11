export type CtaSurface = "hub" | "live" | "media" | "gallery" | "tag" | "vpapi";

export type CtaContext = {
  surface: CtaSurface;
  id?: string | number;
  slug?: string;
};

export type HubCta = {
  key: "loot" | "vip" | "spicy";
  href: string;
  label: string;
  icon: string;
};

const LOOT_HREF = "https://telegram.me/aof_lootgod_bot";
const VIP_HREF = "https://t.me/aofsubscriptions_bot";
const SPICY_HREF = "https://t.me/aof_spicybot_bot";

function beaconBase(): string | null {
  const b = process.env.NEXT_PUBLIC_TBCC_BEACON_BASE?.trim();
  return b ? b.replace(/\/$/, "") : null;
}

function sourceRef(ctx: CtaContext): string {
  const token = ctx.slug ?? String(ctx.id ?? ctx.surface);
  return `src_web_${ctx.surface}_${token}`.replace(/[^a-zA-Z0-9_]/g, "_").slice(0, 48);
}

function beaconHref(slug: string): string | null {
  const base = beaconBase();
  if (!base || !slug) return null;
  return `${base}/r/${slug}`;
}

function botHref(bot: HubCta["key"], ctx?: CtaContext): string {
  const ref = ctx ? sourceRef(ctx) : null;

  if (bot === "loot") {
    // Hub strip: bare loot link per sprint doctrine. Contextual surfaces get attribution.
    if (!ctx || !ref || ctx.surface === "hub") return LOOT_HREF;
    const slug = process.env.NEXT_PUBLIC_BEACON_SLUG_LOOT?.trim() || `web-loot-${ctx.surface}`;
    return beaconHref(slug) ?? `${LOOT_HREF}?start=${encodeURIComponent(ref)}`;
  }

  if (bot === "vip") {
    const slug = process.env.NEXT_PUBLIC_BEACON_SLUG_VIP?.trim() || (ref ? `web-vip-${ctx?.surface}` : "web-vip");
    return beaconHref(slug) ?? (ref ? `${VIP_HREF}?start=${encodeURIComponent(ref)}` : VIP_HREF);
  }

  const slug = process.env.NEXT_PUBLIC_BEACON_SLUG_SPICY?.trim() || (ref ? `web-spicy-${ctx?.surface}` : "web-spicy");
  return beaconHref(slug) ?? (ref ? `${SPICY_HREF}?start=${encodeURIComponent(ref)}` : SPICY_HREF);
}

/** Default hub CTAs (homepage strip — loot stays bare). */
export function hubCtas(): HubCta[] {
  return [
    { key: "loot", href: LOOT_HREF, label: "Loot Room — free daily pulls", icon: "🪙" },
    { key: "vip", href: botHref("vip", { surface: "hub" }), label: "VIP ladder — daily god-rolls", icon: "🔞" },
    { key: "spicy", href: botHref("spicy", { surface: "hub" }), label: "Meet your companion", icon: "💬" },
  ];
}

/** Contextual conversion footer (media, gallery, tag, live pages). */
export function contextualCtas(ctx: CtaContext): HubCta[] {
  return [
    { key: "loot", href: botHref("loot", ctx), label: "Loot Room — free daily pulls", icon: "🪙" },
    { key: "vip", href: botHref("vip", ctx), label: "VIP ladder", icon: "🔞" },
    { key: "spicy", href: botHref("spicy", ctx), label: "Companion trial", icon: "💬" },
  ];
}
