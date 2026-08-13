import liveConfig from "@/data/live-embeds.json";

export type LiveEmbedSlot = {
  id: string;
  label: string;
  iframeSrc?: string;
  outboundUrl?: string;
  beaconSlug?: string;
};

export type PerformerLiveMapping = {
  /** Forum tag slug (e.g. from Stash sync). */
  tagSlug: string;
  /** Optional Awempire embed slot id from `embeds[]`. */
  embedId?: string;
  /** Direct room/deeplink when operator has a performer-specific URL. */
  outboundUrl?: string;
  beaconSlug?: string;
};

export type PerformerLiveCta = {
  href: string;
  label: string;
  embedSlot?: LiveEmbedSlot;
};

function parseEmbeds(raw: unknown): LiveEmbedSlot[] {
  if (!raw || typeof raw !== "object") return [];
  const embeds = (raw as { embeds?: unknown }).embeds;
  if (!Array.isArray(embeds)) return [];
  return embeds.filter(
    (e): e is LiveEmbedSlot =>
      !!e &&
      typeof e === "object" &&
      typeof (e as LiveEmbedSlot).id === "string" &&
      typeof (e as LiveEmbedSlot).label === "string"
  );
}

/** Awempire promo-tool iframe slots — override via AWEMPIRE_LIVE_EMBEDS_JSON env (JSON array). */
export function getLiveEmbeds(): LiveEmbedSlot[] {
  const envJson = process.env.AWEMPIRE_LIVE_EMBEDS_JSON?.trim();
  if (envJson) {
    try {
      const parsed = JSON.parse(envJson) as unknown;
      if (Array.isArray(parsed)) return parseEmbeds({ embeds: parsed });
      return parseEmbeds(parsed);
    } catch {
      /* fall through */
    }
  }
  return parseEmbeds(liveConfig);
}

function parsePerformerMappings(raw: unknown): PerformerLiveMapping[] {
  if (!raw || typeof raw !== "object") return [];
  const mappings = (raw as { performerMappings?: unknown }).performerMappings;
  if (!Array.isArray(mappings)) return [];
  return mappings.filter(
    (m): m is PerformerLiveMapping =>
      !!m &&
      typeof m === "object" &&
      typeof (m as PerformerLiveMapping).tagSlug === "string"
  );
}

export function getPerformerLiveMappings(): PerformerLiveMapping[] {
  const envJson = process.env.AWEMPIRE_LIVE_EMBEDS_JSON?.trim();
  if (envJson) {
    try {
      const parsed = JSON.parse(envJson) as unknown;
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
        return parsePerformerMappings(parsed);
      }
    } catch {
      /* fall through */
    }
  }
  return parsePerformerMappings(liveConfig);
}

export function resolvePerformerLiveCta(
  tagSlug: string,
  performerName: string
): PerformerLiveCta | null {
  const mapping = getPerformerLiveMappings().find(
    (m) => m.tagSlug.toLowerCase() === tagSlug.toLowerCase()
  );
  if (!mapping) return null;

  const embedSlot = mapping.embedId
    ? getLiveEmbeds().find((e) => e.id === mapping.embedId)
    : undefined;

  const slotForOutbound: LiveEmbedSlot = {
    id: mapping.embedId || tagSlug,
    label: performerName,
    outboundUrl: mapping.outboundUrl || embedSlot?.outboundUrl,
    beaconSlug: mapping.beaconSlug || embedSlot?.beaconSlug,
  };

  const href = resolveLiveOutboundUrl(slotForOutbound);
  if (!href) return null;

  return {
    href,
    label: `Watch ${performerName} live`,
    embedSlot,
  };
}

export function liveEmbedsConfigured(): boolean {
  return getLiveEmbeds().some((e) => Boolean(e.iframeSrc?.trim()));
}

export function resolveLiveOutboundUrl(slot: LiveEmbedSlot): string | null {
  const direct = slot.outboundUrl?.trim();
  if (direct) {
    const beaconBase = process.env.NEXT_PUBLIC_TBCC_BEACON_BASE?.replace(/\/$/, "");
    const slug = slot.beaconSlug?.trim();
    if (beaconBase && slug) return `${beaconBase}/r/${slug}`;
    return direct;
  }
  return null;
}
