/** Storage Hub network_key → AOF Forum group (tube lane communities). */
export type HubLaneGroup = {
  slug: string;
  name: string;
  description: string;
};

export const STORAGE_HUB_LANE_GROUPS: Record<string, HubLaneGroup> = {
  ai: {
    slug: "hub-ai",
    name: "AOF AI",
    description: "AI lane — synced from Storage Hub AOF AI STORAGE.",
  },
  ass: {
    slug: "hub-ass",
    name: "AOF Ass",
    description: "Ass lane — synced from Storage Hub AOF ASS STORAGE.",
  },
  big_tits: {
    slug: "hub-big-tits",
    name: "AOF Big Tits",
    description: "Big tits lane — synced from Storage Hub.",
  },
  blowjob: {
    slug: "hub-blowjob",
    name: "AOF Blowjob",
    description: "Blowjob lane — synced from Storage Hub.",
  },
  bop: {
    slug: "hub-bop",
    name: "AOF BOP",
    description: "BOP lane — synced from Storage Hub.",
  },
  goon: {
    slug: "hub-goon",
    name: "AOF Goon",
    description: "Goon lane — synced from Storage Hub.",
  },
  milf: {
    slug: "hub-milf",
    name: "AOF MILF/GILF",
    description: "MILF/GILF lane — synced from Storage Hub.",
  },
  packs: {
    slug: "hub-packs",
    name: "AOF Packs",
    description: "Packs lane — synced from Storage Hub.",
  },
  voyeur: {
    slug: "hub-voyeur",
    name: "AOF Public / Voyeur",
    description: "Public / voyeur lane — synced from Storage Hub.",
  },
  taboo: {
    slug: "hub-taboo",
    name: "AOF Taboo 18+",
    description: "Taboo lane — synced from Storage Hub.",
  },
  abg: {
    slug: "hub-abg",
    name: "AOF ABG/LBFM",
    description: "ABG/LBFM lane — synced from Storage Hub.",
  },
  full_length: {
    slug: "hub-full-length",
    name: "AOF Full Length",
    description: "Full-length lane — synced from Storage Hub.",
  },
  inbox: {
    slug: "hub-inbox",
    name: "AOF Inbox",
    description: "Manual inbox lane — synced from Storage Hub.",
  },
  main: {
    slug: "hub-loot-room",
    name: "AOF Loot Room",
    description: "Main hub lane — synced from AOF Loot Room pool.",
  },
};

export const STORAGE_HUB_FALLBACK_GROUP: HubLaneGroup = {
  slug: "hub-storage",
  name: "Storage Hub",
  description: "Storage Hub imports without a mapped lane.",
};

export function laneGroupForNetworkKey(networkKey: string | null | undefined): HubLaneGroup {
  const key = (networkKey || "").trim().toLowerCase();
  if (key && STORAGE_HUB_LANE_GROUPS[key]) {
    return STORAGE_HUB_LANE_GROUPS[key];
  }
  return STORAGE_HUB_FALLBACK_GROUP;
}
