import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api, type SecretaryUserContext } from "../api";
import { QueryErrorBanner } from "../components/QueryErrorBanner";

type SubTab = "settings" | "contexts" | "knowledge" | "test";

const PHASES = ["introduction", "engagement", "support", "recovery"] as const;

export function SecretarySettingsPanel() {
  const [sub, setSub] = useState<SubTab>("settings");
  const qc = useQueryClient();

  const settingsQ = useQuery({
    queryKey: ["secretarySettings"],
    queryFn: () => api.secretary.settings.get(),
  });
  const eff = settingsQ.data?.effective;
  const ov = settingsQ.data?.overrides ?? {};

  const [formatOn, setFormatOn] = useState(true);
  const [feVerbosity, setFeVerbosity] = useState<"compact" | "standard">("compact");
  const [publicFaq, setPublicFaq] = useState(false);
  const [llmRefine, setLlmRefine] = useState(false);
  const [llmProvider, setLlmProvider] = useState<"openai" | "openrouter">("openai");
  const [llmModel, setLlmModel] = useState("");
  const [llmBaseUrl, setLlmBaseUrl] = useState("");
  const [llmApiKey, setLlmApiKey] = useState("");
  const [clearLlmKey, setClearLlmKey] = useState(false);
  const [ragOn, setRagOn] = useState(true);
  const [ragTopK, setRagTopK] = useState("4");
  const [promptExtra, setPromptExtra] = useState("");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [clearSystemPrompt, setClearSystemPrompt] = useState(false);

  useEffect(() => {
    if (!eff && !ov) return;
    setFormatOn(Boolean(ov.format_engine_enabled ?? eff?.format_engine_enabled ?? true));
    setFeVerbosity((ov.fe_verbosity ?? eff?.fe_verbosity ?? "compact") as "compact" | "standard");
    setPublicFaq(Boolean(ov.public_faq_enabled ?? eff?.public_faq_enabled ?? true));
    setLlmRefine(Boolean(ov.llm_refine_on_phase_change ?? eff?.llm_refine_on_phase_change ?? false));
    setLlmProvider((ov.llm_provider ?? eff?.llm_provider ?? "openai") as "openai" | "openrouter");
    setLlmModel(String(ov.llm_model ?? eff?.llm_model ?? ""));
    setLlmBaseUrl(String(ov.llm_base_url ?? eff?.llm_base_url ?? ""));
    setRagOn(Boolean(ov.rag_enabled ?? eff?.rag_enabled ?? true));
    setRagTopK(String(ov.rag_top_k ?? eff?.rag_top_k ?? 4));
    setPromptExtra(String(ov.system_prompt_extra ?? eff?.system_prompt_extra ?? ""));
    setSystemPrompt(String(ov.system_prompt ?? eff?.system_prompt ?? ""));
  }, [eff, ov]);

  const saveSettings = useMutation({
    mutationFn: () =>
      api.secretary.settings.patch({
        format_engine_enabled: formatOn,
        fe_verbosity: feVerbosity,
        public_faq_enabled: publicFaq,
        llm_refine_on_phase_change: llmRefine,
        llm_provider: llmProvider,
        llm_model: llmModel.trim() || undefined,
        llm_base_url: llmBaseUrl.trim() || undefined,
        llm_api_key: llmApiKey.trim() || undefined,
        clear_llm_api_key: clearLlmKey || undefined,
        rag_enabled: ragOn,
        rag_top_k: Math.max(1, Math.min(12, parseInt(ragTopK, 10) || 4)),
        system_prompt: clearSystemPrompt ? undefined : systemPrompt.trim() || undefined,
        clear_system_prompt: clearSystemPrompt || undefined,
        system_prompt_extra: promptExtra.trim() || undefined,
      }),
    onSuccess: () => {
      setLlmApiKey("");
      setClearSystemPrompt(false);
      qc.invalidateQueries({ queryKey: ["secretarySettings"] });
    },
  });

  const [llmTestResult, setLlmTestResult] = useState<string | null>(null);

  const testLlm = useMutation({
    mutationFn: () => api.secretary.settings.testLlm(),
    onSuccess: (data) => {
      if (data.ok) {
        setLlmTestResult(
          `OK — ${data.latency_ms}ms — ${data.reply_preview ?? ""} (${data.endpoint ?? ""})`
        );
      } else {
        setLlmTestResult(`Failed [${data.stage}]: ${data.message ?? "unknown"}`);
      }
    },
    onError: (e) => setLlmTestResult(String(e)),
  });

  const [ctxSearch, setCtxSearch] = useState("");
  const [ctxPhase, setCtxPhase] = useState("");
  const [selectedCtxId, setSelectedCtxId] = useState<number | null>(null);

  const contextsQ = useQuery({
    queryKey: ["secretaryContexts", ctxSearch, ctxPhase],
    queryFn: () =>
      api.secretary.contexts.list({
        q: ctxSearch.trim() || undefined,
        phase: ctxPhase || undefined,
        limit: 50,
      }),
    enabled: sub === "contexts",
  });

  const ctxDetailQ = useQuery({
    queryKey: ["secretaryContext", selectedCtxId],
    queryFn: () => api.secretary.contexts.get(selectedCtxId!, 60),
    enabled: sub === "contexts" && selectedCtxId != null,
  });

  const resetCtx = useMutation({
    mutationFn: (id: number) => api.secretary.contexts.reset(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["secretaryContexts"] });
      if (selectedCtxId != null) qc.invalidateQueries({ queryKey: ["secretaryContext", selectedCtxId] });
    },
  });

  const [knowSearch, setKnowSearch] = useState("");
  const [knowTitle, setKnowTitle] = useState("");
  const [knowBody, setKnowBody] = useState("");
  const [knowTags, setKnowTags] = useState("");

  const knowledgeQ = useQuery({
    queryKey: ["secretaryKnowledge", knowSearch],
    queryFn: () => api.secretary.knowledge.list(knowSearch.trim() || undefined),
    enabled: sub === "knowledge",
  });

  const createKnow = useMutation({
    mutationFn: () =>
      api.secretary.knowledge.create({
        title: knowTitle.trim() || undefined,
        body: knowBody.trim(),
        tags: knowTags.trim() || undefined,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["secretaryKnowledge"] });
      setKnowTitle("");
      setKnowBody("");
      setKnowTags("");
    },
  });

  const importDocs = useMutation({
    mutationFn: () => api.secretary.knowledge.importDocs(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["secretaryKnowledge"] }),
  });

  const reindexEmb = useMutation({
    mutationFn: () => api.secretary.knowledge.reindexEmbeddings(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["secretaryKnowledge"] }),
  });

  const deleteKnow = useMutation({
    mutationFn: (id: number) => api.secretary.knowledge.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["secretaryKnowledge"] }),
  });

  const [testMsg, setTestMsg] = useState("How do I subscribe with Stars?");
  const [testUid, setTestUid] = useState("");
  const [testResult, setTestResult] = useState<{
    reply: string;
    context_suffix_preview: string;
    rag_hits: Array<{ title: string | null; score: number }>;
  } | null>(null);

  const testReply = useMutation({
    mutationFn: () =>
      api.secretary.settings.testReply({
        message: testMsg.trim(),
        telegram_user_id: testUid.trim() ? parseInt(testUid, 10) : undefined,
        include_format_engine: true,
        include_rag: true,
      }),
    onSuccess: (data) => setTestResult(data),
  });

  const tabBtn = (id: SubTab, label: string) => (
    <button
      type="button"
      onClick={() => setSub(id)}
      className={`px-3 py-1.5 text-sm rounded-md ${
        sub === id ? "bg-cyan-600 text-white" : "bg-slate-800 text-slate-300 hover:bg-slate-700"
      }`}
    >
      {label}
    </button>
  );

  return (
    <div className="space-y-6 max-w-5xl">
      <div>
        <h2 className="text-lg font-semibold text-slate-100">Secretary / Format Engine</h2>
        <p className="text-sm text-slate-400 mt-1">
          Adaptive emotional context (FE-LLMv4), FAQ knowledge retrieval, and user thread inspection for{" "}
          <code className="text-cyan-400/90">@aof_secretary_bot</code>.
        </p>
      </div>

      <div className="flex flex-wrap gap-2">{tabBtn("settings", "Settings")}{tabBtn("contexts", "User contexts")}{tabBtn("knowledge", "FAQ knowledge")}{tabBtn("test", "Test playground")}</div>

      {sub === "settings" && (
        <section className="rounded-lg border border-slate-700 bg-slate-900/50 p-4 space-y-4">
          {settingsQ.isError && <QueryErrorBanner error={settingsQ.error} onRetry={() => settingsQ.refetch()} />}
          {settingsQ.isPending && <p className="text-slate-400 text-sm">Loading settings…</p>}
          {eff && (
            <>
              <label className="flex items-center gap-2 text-sm text-slate-200">
                <input type="checkbox" checked={formatOn} onChange={(e) => setFormatOn(e.target.checked)} />
                Format Engine enabled (persistent context + phases)
              </label>
              <div>
                <label className="block text-xs text-slate-400 mb-1">Format Engine verbosity</label>
                <select
                  className="rounded bg-slate-800 border border-slate-600 px-2 py-1 text-sm"
                  value={feVerbosity}
                  onChange={(e) => setFeVerbosity(e.target.value as "compact" | "standard")}
                >
                  <option value="compact">Compact (default — short LLM suffix)</option>
                  <option value="standard">Standard (full FE block)</option>
                </select>
              </div>
              <label className="flex items-center gap-2 text-sm text-slate-200">
                <input type="checkbox" checked={publicFaq} onChange={(e) => setPublicFaq(e.target.checked)} />
                Public FAQ DMs (off = admin-only bot except Business supervise)
              </label>
              <label className="flex items-center gap-2 text-sm text-slate-200">
                <input type="checkbox" checked={llmRefine} onChange={(e) => setLlmRefine(e.target.checked)} />
                LLM emotion refine on phase transitions
              </label>
              <section className="rounded border border-slate-700/80 p-3 space-y-3">
                <h3 className="text-sm font-medium text-cyan-200">Secretary LLM (admin)</h3>
                {eff.llm?.api_key_hint && (
                  <p className="text-xs text-slate-500">
                    Active key: <code className="text-slate-400">{eff.llm.api_key_hint}</code>
                    {eff.llm.api_key_override ? " (dashboard override)" : " (from .env)"}
                  </p>
                )}
                <div className="flex flex-wrap gap-3">
                  <div>
                    <label className="block text-xs text-slate-400 mb-1">Provider</label>
                    <select
                      className="rounded bg-slate-800 border border-slate-600 px-2 py-1 text-sm"
                      value={llmProvider}
                      onChange={(e) => setLlmProvider(e.target.value as "openai" | "openrouter")}
                    >
                      <option value="openai">OpenAI</option>
                      <option value="openrouter">OpenRouter</option>
                    </select>
                  </div>
                  <div className="flex-1 min-w-[12rem]">
                    <label className="block text-xs text-slate-400 mb-1">Model</label>
                    <input
                      className="w-full rounded bg-slate-800 border border-slate-600 px-2 py-1 text-sm font-mono"
                      value={llmModel}
                      onChange={(e) => setLlmModel(e.target.value)}
                      placeholder="gpt-4o-mini or openrouter model id"
                    />
                  </div>
                </div>
                <div>
                  <label className="block text-xs text-slate-400 mb-1">API key override (leave blank to keep)</label>
                  <input
                    type="password"
                    autoComplete="off"
                    className="w-full rounded bg-slate-800 border border-slate-600 px-2 py-1 text-sm font-mono"
                    value={llmApiKey}
                    onChange={(e) => setLlmApiKey(e.target.value)}
                    placeholder="sk-… or or-…"
                  />
                </div>
                <label className="flex items-center gap-2 text-xs text-slate-400">
                  <input type="checkbox" checked={clearLlmKey} onChange={(e) => setClearLlmKey(e.target.checked)} />
                  Clear dashboard API key override (fall back to .env)
                </label>
                <div>
                  <label className="block text-xs text-slate-400 mb-1">API endpoint URL (OpenRouter / custom OpenAI)</label>
                  <input
                    className="w-full rounded bg-slate-800 border border-slate-600 px-2 py-1 text-sm font-mono"
                    value={llmBaseUrl}
                    onChange={(e) => setLlmBaseUrl(e.target.value)}
                    placeholder="https://openrouter.ai/api/v1"
                  />
                </div>
              </section>
              <label className="flex items-center gap-2 text-sm text-slate-200">
                <input type="checkbox" checked={ragOn} onChange={(e) => setRagOn(e.target.checked)} />
                FAQ RAG retrieval enabled
              </label>
              <div>
                <label className="block text-xs text-slate-400 mb-1">RAG top-K chunks</label>
                <input
                  className="w-20 rounded bg-slate-800 border border-slate-600 px-2 py-1 text-sm"
                  value={ragTopK}
                  onChange={(e) => setRagTopK(e.target.value)}
                />
              </div>
              <div>
                <label className="block text-xs text-slate-400 mb-1">
                  System prompt{" "}
                  {eff.system_prompt_source ? (
                    <span className="text-slate-500">(source: {eff.system_prompt_source})</span>
                  ) : null}
                </label>
                <textarea
                  className="w-full min-h-[120px] rounded bg-slate-800 border border-slate-600 px-3 py-2 text-sm font-mono"
                  value={systemPrompt}
                  onChange={(e) => setSystemPrompt(e.target.value)}
                  placeholder="Full secretary persona / rules (also editable via /sysprompt in Telegram)"
                />
              </div>
              <label className="flex items-center gap-2 text-xs text-slate-400">
                <input
                  type="checkbox"
                  checked={clearSystemPrompt}
                  onChange={(e) => setClearSystemPrompt(e.target.checked)}
                />
                Clear dashboard system prompt override
              </label>
              <div>
                <label className="block text-xs text-slate-400 mb-1">Extra system prompt (appended)</label>
                <textarea
                  className="w-full min-h-[80px] rounded bg-slate-800 border border-slate-600 px-3 py-2 text-sm font-mono"
                  value={promptExtra}
                  onChange={(e) => setPromptExtra(e.target.value)}
                  placeholder="Brand voice notes, escalation policy…"
                />
              </div>
              <p className="text-xs text-slate-500">
                Env fallbacks: TBCC_FORMAT_ENGINE_VERBOSITY, TBCC_SECRETARY_PUBLIC_FAQ, TBCC_LLM_PROVIDER,
                TBCC_OPENROUTER_API_KEY / TBCC_OPENAI_API_KEY. Dashboard LLM key overrides .env for secretary only.
              </p>
                <button
                type="button"
                disabled={saveSettings.isPending}
                onClick={() => saveSettings.mutate()}
                className="px-4 py-2 rounded bg-cyan-600 hover:bg-cyan-500 text-sm font-medium disabled:opacity-50"
              >
                {saveSettings.isPending ? "Saving…" : "Save settings"}
              </button>
              <button
                type="button"
                disabled={testLlm.isPending}
                onClick={() => testLlm.mutate()}
                className="px-4 py-2 rounded bg-slate-700 hover:bg-slate-600 text-sm font-medium disabled:opacity-50"
              >
                {testLlm.isPending ? "Testing…" : "Test LLM connection"}
              </button>
              {saveSettings.isSuccess && <p className="text-sm text-emerald-400">Saved.</p>}
              {llmTestResult && (
                <p className={`text-sm ${llmTestResult.startsWith("OK") ? "text-emerald-400" : "text-amber-300"}`}>
                  {llmTestResult}
                </p>
              )}
            </>
          )}
        </section>
      )}

      {sub === "contexts" && (
        <section className="space-y-4">
          <div className="flex flex-wrap gap-2 items-end">
            <div>
              <label className="block text-xs text-slate-400 mb-1">Search @user or Telegram ID</label>
              <input
                className="rounded bg-slate-800 border border-slate-600 px-3 py-1.5 text-sm w-48"
                value={ctxSearch}
                onChange={(e) => setCtxSearch(e.target.value)}
              />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">Phase</label>
              <select
                className="rounded bg-slate-800 border border-slate-600 px-2 py-1.5 text-sm"
                value={ctxPhase}
                onChange={(e) => setCtxPhase(e.target.value)}
              >
                <option value="">All</option>
                {PHASES.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            </div>
          </div>
          {contextsQ.isError && <QueryErrorBanner error={contextsQ.error} onRetry={() => contextsQ.refetch()} />}
          <div className="grid md:grid-cols-2 gap-4">
            <div className="rounded-lg border border-slate-700 overflow-hidden">
              <div className="px-3 py-2 bg-slate-800/80 text-xs text-slate-400">
                {contextsQ.data?.total ?? 0} user contexts
              </div>
              <ul className="max-h-96 overflow-y-auto divide-y divide-slate-800">
                {(contextsQ.data?.items ?? []).map((c) => (
                  <li key={c.id}>
                    <button
                      type="button"
                      onClick={() => setSelectedCtxId(c.id)}
                      className={`w-full text-left px-3 py-2 text-sm hover:bg-slate-800/60 ${
                        selectedCtxId === c.id ? "bg-cyan-950/40" : ""
                      }`}
                    >
                      <span className="text-slate-200">
                        @{c.telegram_username || "—"} · {c.telegram_user_id}
                      </span>
                      <span className="ml-2 text-xs text-cyan-400">{c.current_phase}</span>
                      <div className="text-xs text-slate-500 truncate">{c.emotional_summary}</div>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
            <div className="rounded-lg border border-slate-700 p-3 min-h-[200px]">
              {!selectedCtxId && <p className="text-sm text-slate-500">Select a user context.</p>}
              {ctxDetailQ.isPending && selectedCtxId && <p className="text-sm text-slate-400">Loading…</p>}
              {ctxDetailQ.data && (
                <ContextDetail
                  ctx={ctxDetailQ.data}
                  onReset={() => resetCtx.mutate(ctxDetailQ.data!.id)}
                  resetting={resetCtx.isPending}
                />
              )}
            </div>
          </div>
        </section>
      )}

      {sub === "knowledge" && (
        <section className="space-y-4">
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => importDocs.mutate()}
              disabled={importDocs.isPending}
              className="px-3 py-1.5 rounded bg-slate-700 hover:bg-slate-600 text-sm"
            >
              Import from tbcc/docs/*.md
            </button>
            <button
              type="button"
              onClick={() => reindexEmb.mutate()}
              disabled={reindexEmb.isPending}
              className="px-3 py-1.5 rounded bg-slate-700 hover:bg-slate-600 text-sm"
            >
              Reindex embeddings
            </button>
          </div>
          {(importDocs.data || reindexEmb.data) && (
            <pre className="text-xs text-slate-400 bg-slate-900 p-2 rounded overflow-x-auto">
              {JSON.stringify(importDocs.data || reindexEmb.data, null, 2)}
            </pre>
          )}
          <input
            className="w-full max-w-md rounded bg-slate-800 border border-slate-600 px-3 py-1.5 text-sm"
            placeholder="Filter knowledge…"
            value={knowSearch}
            onChange={(e) => setKnowSearch(e.target.value)}
          />
          <div className="rounded-lg border border-slate-700 p-3 space-y-2">
            <p className="text-xs text-slate-400 uppercase tracking-wide">Add FAQ chunk</p>
            <input
              className="w-full rounded bg-slate-800 border border-slate-600 px-3 py-1.5 text-sm"
              placeholder="Title"
              value={knowTitle}
              onChange={(e) => setKnowTitle(e.target.value)}
            />
            <textarea
              className="w-full min-h-[72px] rounded bg-slate-800 border border-slate-600 px-3 py-2 text-sm"
              placeholder="Body (markdown ok)"
              value={knowBody}
              onChange={(e) => setKnowBody(e.target.value)}
            />
            <input
              className="w-full rounded bg-slate-800 border border-slate-600 px-3 py-1.5 text-sm"
              placeholder="Tags (comma-separated)"
              value={knowTags}
              onChange={(e) => setKnowTags(e.target.value)}
            />
            <button
              type="button"
              disabled={!knowBody.trim() || createKnow.isPending}
              onClick={() => createKnow.mutate()}
              className="px-3 py-1.5 rounded bg-cyan-600 text-sm disabled:opacity-50"
            >
              Add chunk
            </button>
          </div>
          <ul className="space-y-2 max-h-[420px] overflow-y-auto">
            {(knowledgeQ.data ?? []).map((k) => (
              <li key={k.id} className="rounded border border-slate-700 p-3 text-sm">
                <div className="flex justify-between gap-2">
                  <strong className="text-slate-200">{k.title || `(#${k.id})`}</strong>
                  <button
                    type="button"
                    className="text-xs text-red-400 hover:text-red-300"
                    onClick={() => deleteKnow.mutate(k.id)}
                  >
                    Delete
                  </button>
                </div>
                {k.source_path && <div className="text-xs text-slate-500">{k.source_path}</div>}
                <p className="text-slate-400 mt-1 line-clamp-3 whitespace-pre-wrap">{k.body}</p>
              </li>
            ))}
          </ul>
        </section>
      )}

      {sub === "test" && (
        <section className="rounded-lg border border-slate-700 p-4 space-y-3">
          <textarea
            className="w-full min-h-[80px] rounded bg-slate-800 border border-slate-600 px-3 py-2 text-sm"
            value={testMsg}
            onChange={(e) => setTestMsg(e.target.value)}
          />
          <input
            className="w-48 rounded bg-slate-800 border border-slate-600 px-3 py-1.5 text-sm"
            placeholder="Telegram user ID (optional)"
            value={testUid}
            onChange={(e) => setTestUid(e.target.value)}
          />
          <button
            type="button"
            disabled={!testMsg.trim() || testReply.isPending}
            onClick={() => testReply.mutate()}
            className="px-4 py-2 rounded bg-cyan-600 text-sm disabled:opacity-50"
          >
            {testReply.isPending ? "Generating…" : "Test reply"}
          </button>
          {testReply.isError && <QueryErrorBanner error={testReply.error} />}
          {testResult && (
            <div className="space-y-3 text-sm">
              <div>
                <p className="text-xs text-slate-400 mb-1">Reply</p>
                <pre className="whitespace-pre-wrap bg-slate-900 p-3 rounded text-slate-200">{testResult.reply}</pre>
              </div>
              {testResult.rag_hits.length > 0 && (
                <div>
                  <p className="text-xs text-slate-400 mb-1">RAG hits</p>
                  <ul className="text-xs text-slate-400 space-y-1">
                    {testResult.rag_hits.map((h, i) => (
                      <li key={i}>
                        {h.title} (score {h.score})
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {testResult.context_suffix_preview && (
                <details>
                  <summary className="text-xs text-slate-400 cursor-pointer">Context suffix preview</summary>
                  <pre className="mt-1 text-xs whitespace-pre-wrap bg-slate-900 p-2 rounded max-h-48 overflow-y-auto">
                    {testResult.context_suffix_preview}
                  </pre>
                </details>
              )}
            </div>
          )}
        </section>
      )}
    </div>
  );
}

function ContextDetail({
  ctx,
  onReset,
  resetting,
}: {
  ctx: SecretaryUserContext;
  onReset: () => void;
  resetting: boolean;
}) {
  const fmt = ctx.interaction_format as Record<string, unknown>;
  const phaseHistory = (fmt.phase_history as Array<Record<string, string>>) || [];
  const llmRef = (fmt.llm_refinements as Array<Record<string, string>>) || [];

  return (
    <div className="space-y-3 text-sm">
      <div className="flex justify-between items-start gap-2">
        <div>
          <p className="text-slate-200 font-medium">
            @{ctx.telegram_username || "—"} · <code>{ctx.telegram_user_id}</code>
          </p>
          <p className="text-cyan-400 text-xs mt-0.5">Phase: {ctx.current_phase}</p>
          <p className="text-xs text-slate-500">{ctx.emotional_summary}</p>
        </div>
        <button
          type="button"
          onClick={onReset}
          disabled={resetting}
          className="text-xs px-2 py-1 rounded border border-red-800 text-red-400 hover:bg-red-950/40"
        >
          Reset
        </button>
      </div>
      {phaseHistory.length > 0 && (
        <div>
          <p className="text-xs text-slate-400 mb-1">Phase history</p>
          <ul className="text-xs text-slate-500 space-y-0.5">
            {phaseHistory.map((h, i) => (
              <li key={i}>
                {h.from} → {h.to} {h.at ? `@ ${h.at.slice(0, 19)}` : ""}
              </li>
            ))}
          </ul>
        </div>
      )}
      {llmRef.length > 0 && (
        <div>
          <p className="text-xs text-slate-400 mb-1">LLM refinements</p>
          <pre className="text-xs bg-slate-900 p-2 rounded max-h-32 overflow-y-auto">
            {JSON.stringify(llmRef.slice(-3), null, 2)}
          </pre>
        </div>
      )}
      <div>
        <p className="text-xs text-slate-400 mb-1">Messages ({ctx.messages?.length ?? 0})</p>
        <ul className="max-h-64 overflow-y-auto space-y-2 text-xs">
          {(ctx.messages ?? []).map((m) => (
            <li key={m.id} className={`p-2 rounded ${m.role === "user" ? "bg-slate-800/80" : "bg-slate-900/80"}`}>
              <span className="text-slate-500 uppercase">{m.role}</span>
              {m.emotion && (
                <span className="ml-2 text-cyan-600/80">{(m.emotion as { dominant?: string }).dominant}</span>
              )}
              <p className="text-slate-300 mt-0.5 whitespace-pre-wrap">{m.content}</p>
            </li>
          ))}
        </ul>
      </div>
      <details>
        <summary className="text-xs text-slate-400 cursor-pointer">Full interaction format JSON</summary>
        <pre className="mt-1 text-xs bg-slate-900 p-2 rounded max-h-48 overflow-y-auto">
          {JSON.stringify(fmt, null, 2)}
        </pre>
      </details>
    </div>
  );
}
