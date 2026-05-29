import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";

export type CustomEmojiPreset = {
  id: number;
  title: string;
  html_fragment: string;
  source_note?: string | null;
};

export function useCustomEmojiPresets() {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["customEmojiPresets"],
    queryFn: () => api.telegramCustomEmoji.listPresets(),
  });

  const invalidate = () => void qc.invalidateQueries({ queryKey: ["customEmojiPresets"] });

  const remove = useMutation({
    mutationFn: (id: number) => api.telegramCustomEmoji.deletePreset(id),
    onSuccess: invalidate,
  });

  return { presets: q.data ?? [], isLoading: q.isLoading, isError: q.isError, error: q.error, refetch: q.refetch, remove };
}

export function customEmojiPresetLabel(p: CustomEmojiPreset): string {
  const t = (p.title || "").trim() || `Preset #${p.id}`;
  const n = (p.html_fragment.match(/<tg-emoji/gi) || []).length;
  return n > 0 ? `${t} (${n} emoji)` : t;
}
