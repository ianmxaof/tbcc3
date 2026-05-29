/** Pick best telethon HTML from extract / import-macro API responses. */
export function bodyFromTelegramExtract(data: {
  full_message_html?: string;
  custom_emoji_html_with_body?: string;
  custom_emoji_html?: string;
  html?: string;
  plain_text?: string;
}): string {
  const fromMacro = (data.html || "").trim();
  if (fromMacro) return fromMacro;
  const full = (data.full_message_html || "").trim();
  if (full) return full;
  const withBody = (data.custom_emoji_html_with_body || "").trim();
  if (withBody) return withBody;
  const banner = (data.custom_emoji_html || "").trim();
  if (banner) return banner;
  return (data.plain_text || "").trim();
}

export type ImportMacroTarget = "library" | "sketchbook" | "both" | "library_and_send";

export function importMacroOptions(target: ImportMacroTarget): {
  save_preset: boolean;
  save_sketchbook: boolean;
  send_to_saved: boolean;
} {
  switch (target) {
    case "library":
      return { save_preset: true, save_sketchbook: false, send_to_saved: false };
    case "sketchbook":
      return { save_preset: false, save_sketchbook: true, send_to_saved: false };
    case "both":
      return { save_preset: true, save_sketchbook: true, send_to_saved: false };
    case "library_and_send":
      return { save_preset: true, save_sketchbook: false, send_to_saved: true };
    default:
      return { save_preset: true, save_sketchbook: true, send_to_saved: false };
  }
}
