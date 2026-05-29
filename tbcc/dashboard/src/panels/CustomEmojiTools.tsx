import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { QueryErrorBanner } from "../components/QueryErrorBanner";
import { SavedMessagesImportMacros } from "../components/SavedMessagesImportMacros";
import { SilentTelegramSendOption } from "../components/SilentTelegramSendOption";
import { bodyFromTelegramExtract } from "../utils/customEmojiExtract";

export function CustomEmojiTools() {
  const qc = useQueryClient();
  const channelsQ = useQuery({ queryKey: ["channels"], queryFn: () => api.channels.list() });
  const presetsQ = useQuery({ queryKey: ["customEmojiPresets"], queryFn: () => api.telegramCustomEmoji.listPresets() });
  const savedRecentQ = useQuery({
    queryKey: ["customEmojiSavedRecent"],
    queryFn: () => api.telegramCustomEmoji.savedMessagesRecent(25),
    refetchOnWindowFocus: false,
  });

  const [peerLink, setPeerLink] = useState("");
  const [peer, setPeer] = useState("me");
  const [messageId, setMessageId] = useState("");
  const [extracted, setExtracted] = useState("");
  const [presetTitle, setPresetTitle] = useState("");
  const [validateHtml, setValidateHtml] = useState("");
  const [validation, setValidation] = useState<Record<string, unknown> | null>(null);
  const [testChannelId, setTestChannelId] = useState<number | "">("");
  const [testSendSilent, setTestSendSilent] = useState(false);
  const [docId, setDocId] = useState("");
  const [placeholder, setPlaceholder] = useState("⭐");

  const extract = useMutation({
    mutationFn: (override?: { peer?: string; message_id?: number; peer_link?: string }) => {
      const link = (override?.peer_link ?? peerLink).trim();
      return api.telegramCustomEmoji.extract({
        peer_link: link || undefined,
        peer: link ? undefined : (override?.peer ?? peer).trim() || "me",
        message_id: link ? undefined : override?.message_id ?? (Number(messageId.trim()) || undefined),
      });
    },
    onSuccess: (data) => {
      const html = bodyFromTelegramExtract(data);
      setExtracted(html);
      setValidateHtml(html);
    },
  });

  const validate = useMutation({
    mutationFn: () => api.telegramCustomEmoji.validate(validateHtml),
    onSuccess: (data) => setValidation(data),
  });

  const savePreset = useMutation({
    mutationFn: () =>
      api.telegramCustomEmoji.createPreset({
        title: presetTitle.trim() || "Banner",
        html_fragment: extracted.trim(),
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["customEmojiPresets"] });
      setPresetTitle("");
    },
  });

  const testSend = useMutation({
    mutationFn: () =>
      api.telegramCustomEmoji.testSend({
        html: validateHtml,
        channel_id: testChannelId === "" ? undefined : Number(testChannelId),
        send_silent: testChannelId !== "" ? testSendSilent : false,
      }),
  });

  const buildTag = useMutation({
    mutationFn: () =>
      api.telegramCustomEmoji.buildTag({
        document_id: Number(docId.trim()),
        placeholder: placeholder.trim() || "⭐",
      }),
    onSuccess: (data) => {
      setExtracted((prev) => (prev ? `${prev}${data.tag}` : data.tag));
      setValidateHtml((prev) => (prev ? `${prev}${data.tag}` : data.tag));
    },
  });

  const deletePreset = useMutation({
    mutationFn: (id: number) => api.telegramCustomEmoji.deletePreset(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["customEmojiPresets"] }),
  });

  return (
    <div id="caption-emoji-banners" className="rounded-lg border border-violet-800/60 bg-violet-950/20 p-4 space-y-4 mb-8">
      <div>
        <h3 className="text-lg font-semibold text-violet-100">Caption banners (<code className="text-sm">&lt;tg-emoji&gt;</code>)</h3>
        <p className="text-sm text-slate-400 mt-1 max-w-3xl">
          Reuse <strong className="text-slate-300">installed</strong> custom emoji inside scheduled captions and relay
          templates — not the same as building a new split-grid pack. Syntax:{" "}
          <code className="text-violet-200">{`<tg-emoji emoji-id="…">⭐</tg-emoji>`}</code> — inner text must be one
          character. Install the pack on the poster Telethon account (<code className="text-slate-300">admin_poster</code>
          ).
        </p>
      </div>

      <div className="grid md:grid-cols-2 gap-4">
        <div className="space-y-2">
          <h4 className="text-sm font-medium text-slate-200">Import from Saved Messages (one tap)</h4>
          <p className="text-xs text-slate-500 leading-relaxed">
            Forward or paste your design in Telegram Saved Messages, then use a macro below. Full message HTML (links +
            custom emoji) goes to the library and/or{" "}
            <Link to="/misc/emoji#stage-1" className="text-cyan-400 hover:underline">
              Emoji packs → sketchbook
            </Link>
            . Advanced link / peer extract is below.
          </p>
          <div className="flex gap-2 items-center">
            <button
              type="button"
              onClick={() => void savedRecentQ.refetch()}
              className="px-2 py-1 rounded bg-slate-700 text-white text-xs"
            >
              Refresh Saved list
            </button>
            {savedRecentQ.isFetching ? <span className="text-xs text-slate-500">Loading…</span> : null}
          </div>
          {savedRecentQ.data?.messages?.length ? (
            <SavedMessagesImportMacros
              messages={savedRecentQ.data.messages}
              onSketchbookImported={() => {
                setExtracted("");
              }}
            />
          ) : savedRecentQ.isError ? (
            <p className="text-xs text-amber-300">Could not load Saved Messages (is the poster Telethon session logged in?)</p>
          ) : null}
          <details className="text-xs text-slate-500">
            <summary className="cursor-pointer text-slate-400 mt-2">Advanced: message link / manual extract</summary>
          <input
            className="w-full rounded border border-slate-600 bg-slate-950 px-2 py-1.5 text-sm"
            placeholder="Optional: t.me/YourUsername/123 or t.me/c/…/123"
            value={peerLink}
            onChange={(e) => setPeerLink(e.target.value)}
          />
          <div className="flex gap-2">
            <input
              className="flex-1 rounded border border-slate-600 bg-slate-950 px-2 py-1.5 text-sm"
              placeholder="peer: me"
              value={peer}
              onChange={(e) => setPeer(e.target.value)}
            />
            <input
              className="w-28 rounded border border-slate-600 bg-slate-950 px-2 py-1.5 text-sm"
              placeholder="msg id"
              value={messageId}
              onChange={(e) => setMessageId(e.target.value)}
            />
          </div>
          <button
            type="button"
            disabled={extract.isPending}
            onClick={() => extract.mutate(undefined)}
            className="px-3 py-1.5 rounded bg-violet-700 text-white text-sm hover:bg-violet-600 disabled:opacity-50"
          >
            {extract.isPending ? "Extracting…" : "Extract custom emoji HTML"}
          </button>
          {extract.isError ? <p className="text-xs text-red-300">{(extract.error as Error).message}</p> : null}
          </details>
        </div>
        <div className="space-y-2">
          <h4 className="text-sm font-medium text-slate-200">Build one tag</h4>
          <div className="flex gap-2">
            <input
              className="flex-1 rounded border border-slate-600 bg-slate-950 px-2 py-1.5 text-sm"
              placeholder="document_id"
              value={docId}
              onChange={(e) => setDocId(e.target.value)}
            />
            <input
              className="w-16 rounded border border-slate-600 bg-slate-950 px-2 py-1.5 text-sm text-center"
              value={placeholder}
              onChange={(e) => setPlaceholder(e.target.value)}
            />
          </div>
          <button
            type="button"
            disabled={buildTag.isPending || !docId.trim()}
            onClick={() => buildTag.mutate()}
            className="px-3 py-1.5 rounded bg-slate-700 text-white text-sm disabled:opacity-50"
          >
            Append tag
          </button>
        </div>
      </div>
      <label className="block text-xs text-slate-400">
        Banner HTML only (save to Emoji library; insert in Scheduler / relay, then add body text)
        <textarea
          className="mt-1 w-full rounded border border-slate-600 bg-slate-950 px-2 py-1.5 text-sm font-mono min-h-[100px]"
          value={extracted}
          onChange={(e) => {
            setExtracted(e.target.value);
            setValidateHtml(e.target.value);
          }}
        />
      </label>
      <div className="flex flex-wrap gap-2 items-center">
        <button type="button" onClick={() => validate.mutate()} className="px-3 py-1.5 rounded bg-slate-700 text-white text-sm">
          Validate
        </button>
        <input
          className="rounded border border-slate-600 bg-slate-950 px-2 py-1.5 text-sm w-40"
          placeholder="Preset name"
          value={presetTitle}
          onChange={(e) => setPresetTitle(e.target.value)}
        />
        <button
          type="button"
          disabled={savePreset.isPending || !extracted.trim()}
          onClick={() => savePreset.mutate()}
          className="px-3 py-1.5 rounded bg-emerald-700 text-white text-sm disabled:opacity-50"
        >
          Save preset
        </button>
        <select
          className="rounded border border-slate-600 bg-slate-950 px-2 py-1.5 text-sm"
          value={testChannelId === "" ? "" : String(testChannelId)}
          onChange={(e) => setTestChannelId(e.target.value ? Number(e.target.value) : "")}
        >
          <option value="">Test → ADMIN_TELEGRAM_ID</option>
          {(channelsQ.data ?? []).map((c) => {
            const id = String(c.id ?? "");
            const label = String(c.name ?? c.identifier ?? id);
            return (
              <option key={id} value={id}>
                {label}
              </option>
            );
          })}
        </select>
        <button
          type="button"
          disabled={testSend.isPending || !validateHtml.trim()}
          onClick={() => testSend.mutate()}
          className="px-3 py-1.5 rounded bg-cyan-700 text-white text-sm disabled:opacity-50"
        >
          {testSend.isPending ? "Sending…" : "Test send"}
        </button>
      </div>
      {testChannelId !== "" ? (
        <SilentTelegramSendOption compact checked={testSendSilent} onChange={setTestSendSilent} className="max-w-xl" />
      ) : null}
      {validation ? (
        <p className="text-xs text-slate-300">
          Validation: {validation.ok ? "ok" : "fail"} · emojis: {String(validation.custom_emoji_count ?? 0)}
        </p>
      ) : null}
      {testSend.isSuccess ? <p className="text-xs text-emerald-300">Sent to {testSend.data.sent_to}</p> : null}
      {testSend.isError ? <p className="text-xs text-red-300">{(testSend.error as Error).message}</p> : null}
      {presetsQ.isError ? (
        <QueryErrorBanner title="Presets" message={(presetsQ.error as Error).message} onRetry={() => void presetsQ.refetch()} />
      ) : null}
      {(presetsQ.data ?? []).length > 0 ? (
        <ul className="text-sm space-y-1">
          {(presetsQ.data ?? []).map((p) => (
            <li key={p.id} className="flex gap-2 items-center border border-slate-700 rounded px-2 py-1">
              <span className="text-slate-200">{p.title}</span>
              <button type="button" className="text-cyan-300 text-xs" onClick={() => { setExtracted(p.html_fragment); setValidateHtml(p.html_fragment); }}>
                Load
              </button>
              <button type="button" className="text-red-300 text-xs" onClick={() => deletePreset.mutate(p.id)}>
                Delete
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}