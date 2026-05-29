/**
 * Telegram post layout & caption aesthetics — reference for loot overseer tier styling.
 * Send order: earlier messages appear higher in the chat.
 */

export type PostAestheticEntry = {
  id: string;
  category: "media_album" | "document" | "caption" | "sequence" | "loot_hook";
  title: string;
  description: string;
  /** How to reproduce with Telethon / loot bot (conceptual). */
  tbccNotes: string;
  /** Suggested loot tier tags (1–7) — design intent only. */
  tierHints?: number[];
  example?: string;
};

export const TELEGRAM_POST_AESTHETICS: PostAestheticEntry[] = [
  {
    id: "solo_photo",
    category: "media_album",
    title: "Single photo",
    description: "One image, full width. Cleanest drop for low tiers.",
    tbccNotes: "send_photo ×1. Caption optional on same message.",
    tierHints: [1, 2],
  },
  {
    id: "solo_video",
    category: "media_album",
    title: "Single video",
    description: "One video with play overlay, full width.",
    tbccNotes: "send_video ×1. Use spoiler flag for loot reveals.",
    tierHints: [1, 2, 3],
  },
  {
    id: "album_2_horizontal",
    category: "media_album",
    title: "2-up horizontal album (your screenshot)",
    description: "Two videos or photos side-by-side in one media group — Telegram tiles them in one row.",
    tbccNotes:
      "send_media_group with 2 items, same type (both video OR both photo). Appears as wide pair. Your screenshot: two videos + .mp4 file bubble below = separate messages.",
    tierHints: [3, 4, 5],
    example: "Message 1: document (small .mp4 placeholder). Message 2: media_group[video, video].",
  },
  {
    id: "album_3",
    category: "media_album",
    title: "3-item album",
    description: "One large + two small, or L-shaped grid depending on aspect ratios.",
    tbccNotes: "media_group length 3. Order in array affects left-to-right tile order.",
    tierHints: [4, 5],
  },
  {
    id: "album_4_grid",
    category: "media_album",
    title: "2×2 album (4 items)",
    description: "Classic quad grid — strong “pack” feel.",
    tbccNotes: "media_group ×4, same bucket (all photos best). loot_media_layout chunks by 10 max.",
    tierHints: [5, 6, 7],
  },
  {
    id: "album_mixed_avoid",
    category: "media_album",
    title: "Mixed photo + video in one group",
    description: "Telegram may split or reorder; behavior varies by client. Prefer same-type albums for predictable grids.",
    tbccNotes: "TBCC loot planner sends photos in photo groups, videos separately (see plan_media_send_groups).",
    tierHints: [4, 5],
  },
  {
    id: "document_then_album",
    category: "sequence",
    title: "File above, media album below",
    description: "Document message first (appears on top), then album — matches your 2-video + file layout.",
    tbccNotes:
      "Send order: (1) send_document with filename/caption (2) send_media_group. Use for “payload + preview” aesthetic.",
    tierHints: [4, 5, 6],
    example: "003_E008.mp4 stub + twin video thumbs",
  },
  {
    id: "album_then_document",
    category: "sequence",
    title: "Album above, file below",
    description: "Visuals first, download/archive file underneath.",
    tbccNotes: "Reverse send order. Good for “watch first, grab zip/mp4 after.”",
    tierHints: [5, 6, 7],
  },
  {
    id: "document_solo",
    category: "document",
    title: "Document only",
    description: "Blue file bubble — .mp4, .zip, .txt. No thumbnail grid.",
    tbccNotes: "send_document. Caption supports HTML + custom emoji.",
    tierHints: [2, 3],
  },
  {
    id: "hero_video_album_photos",
    category: "loot_hook",
    title: "Loot: hero video + photo album",
    description: "TBCC default high-tier layout: one video bookend, then photo grid chunks.",
    tbccNotes: "plan_media_send_groups() when 1 video + multiple photos.",
    tierHints: [6, 7],
  },
  {
    id: "caption_bold",
    category: "caption",
    title: "Bold / italic HTML",
    description: "<b>bold</b>, <i>italic</i>, <u>underline</u>, <s>strike</s>.",
    tbccNotes: "Scheduler + loot use parse_mode=HTML. Sketchbook stores telethon HTML.",
    tierHints: [1, 2, 3, 4, 5, 6, 7],
  },
  {
    id: "caption_spoiler",
    category: "caption",
    title: "Spoiler text",
    description: "<tg-spoiler>hidden until tap</tg-spoiler> — works in captions.",
    tbccNotes: "Entity spoiler in Telethon HTML.",
    tierHints: [3, 4, 5],
  },
  {
    id: "caption_blockquote",
    category: "caption",
    title: "Block quote",
    description: "Indented quote block — separates flavor text from links.",
    tbccNotes: "<blockquote>…</blockquote> (Bot API HTML).",
    tierHints: [4, 5, 6],
  },
  {
    id: "caption_monospace",
    category: "caption",
    title: "Monospace / code",
    description: "Inline <code>mono</code> or multiline <pre>fixed-width block</pre> — “terminal/card” look.",
    tbccNotes: "Great for rarity stats, seed hashes, tier IDs. Combine with custom emoji header.",
    tierHints: [3, 4, 5, 6, 7],
    example: "<pre>TIER IV · 3 items · seed a8f2</pre>",
  },
  {
    id: "caption_custom_emoji",
    category: "caption",
    title: "Custom emoji banner",
    description: "<tg-emoji emoji-id=\"…\">⭐</tg-emoji> — animated/static third-party emoji in text.",
    tbccNotes: "Use sketchbook picker → insert tag. Poster account must have pack installed.",
    tierHints: [4, 5, 6, 7],
  },
  {
    id: "tier_banner_preset",
    category: "loot_hook",
    title: "Loot tier opening line",
    description: "Custom emoji preset with source_note loot_tier:N + tier name line.",
    tbccNotes: "loot_tier_banner.build_tier_opening_html — save presets from sketchbook.",
    tierHints: [1, 2, 3, 4, 5, 6, 7],
  },
  {
    id: "zip_last",
    category: "sequence",
    title: "ZIP / modifiers last",
    description: "Albums first, link modifiers, zip bundles sent after media (loot overseer default).",
    tbccNotes: "send_loot_preview_to_chat order in loot_preview_delivery.py.",
    tierHints: [5, 6, 7],
  },
];

export const AESTHETIC_CATEGORIES: Record<PostAestheticEntry["category"], string> = {
  media_album: "Media albums",
  document: "Files",
  sequence: "Multi-message sequences",
  caption: "Caption & text styling",
  loot_hook: "Loot overseer patterns",
};
