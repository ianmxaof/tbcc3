export type ConnectPlatform = "snapchat" | "telegram" | "instagram" | "other";
export type ConnectGender = "female" | "male" | "trans" | "couple" | "other";
export type ConnectOrientation = "straight" | "gay" | "lesbian" | "bi" | "other";

export type ConnectListingRow = {
  id: number;
  owner_id: string;
  platform: ConnectPlatform;
  handle: string;
  display_name: string | null;
  age: number;
  gender: ConnectGender | null;
  orientation: ConnectOrientation | null;
  country: string | null;
  bio: string | null;
  bulletin: string | null;
  bulletin_updated_at: string | null;
  avatar_media_id: number | null;
  is_vip: boolean;
  vip_until: string | null;
  fire_pin_until: string | null;
  stealth_pin_until: string | null;
  last_active_at: string;
  views_count: number;
  click_count: number;
  score: number;
  created_at: string;
};

export type ConnectListingCard = ConnectListingRow & {
  avatar_url: string | null;
  tags: string[];
};

export const PLATFORM_LABELS: Record<ConnectPlatform, string> = {
  snapchat: "Snapchat",
  telegram: "Telegram",
  instagram: "Instagram",
  other: "Other",
};

export const PLATFORM_EMOJI: Record<ConnectPlatform, string> = {
  snapchat: "👻",
  telegram: "✈️",
  instagram: "📸",
  other: "💬",
};
