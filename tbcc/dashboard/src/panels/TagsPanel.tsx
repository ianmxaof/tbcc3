import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import { useState } from "react";

/**
 * Tag registry (structured tags used for auto-tag rules + manual assignments).
 * Media Library shows combined tags on each row; new imports get rule-based tags automatically.
 */
export function TagsPanel() {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [category, setCategory] = useState("");

  const { data: tags = [], isLoading, isError, error, refetch } = useQuery({
    queryKey: ["tags"],
    queryFn: () => api.tags.list(),
  });

  const createTag = useMutation({
    mutationFn: () => api.tags.create({ name: name.trim(), ...(slug.trim() ? { slug: slug.trim() } : {}), ...(category.trim() ? { category: category.trim() } : {}) }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["tags"] });
      setName("");
      setSlug("");
      setCategory("");
    },
  });

  if (isError)
    return (
      <div className="rounded-lg bg-red-900/30 border border-red-700 p-4 text-red-200">
        <p className="font-medium">Could not load tags.</p>
        <p className="text-sm mt-1">{String((error as Error)?.message)}</p>
        <button type="button" onClick={() => refetch()} className="mt-3 px-3 py-1 rounded bg-red-800 hover:bg-red-700">
          Retry
        </button>
      </div>
    );

  return (
    <div>
      <h1 className="text-2xl font-semibold mb-2">Tags</h1>
      <p className="text-slate-400 text-sm max-w-2xl mb-6">
        Rule-based tags (e.g. <code className="text-slate-300">type-photo</code>, <code className="text-slate-300">src-erome</code>) are
        applied automatically when media is imported. Manual tags from the Media Library are stored here too. Use{" "}
        <strong>Re-apply rules</strong> on selected rows to refresh rule tags without clearing manual ones.
      </p>

      <div className="bg-slate-800 border border-slate-600 rounded-lg p-4 mb-6 max-w-xl">
        <h2 className="text-sm font-medium text-slate-200 mb-2">Create tag (optional)</h2>
        <p className="text-slate-500 text-xs mb-3">Usually tags are created automatically; add custom labels for routing or filters.</p>
        <div className="flex flex-wrap gap-2 items-end">
          <label className="block text-xs text-slate-400">
            Name
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="mt-1 block w-40 bg-slate-900 border border-slate-600 rounded px-2 py-1.5 text-slate-100 text-sm"
              placeholder="e.g. cosplay"
            />
          </label>
          <label className="block text-xs text-slate-400">
            Slug (optional)
            <input
              value={slug}
              onChange={(e) => setSlug(e.target.value)}
              className="mt-1 block w-40 bg-slate-900 border border-slate-600 rounded px-2 py-1.5 text-slate-100 text-sm"
              placeholder="auto from name"
            />
          </label>
          <label className="block text-xs text-slate-400">
            Category
            <input
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="mt-1 block w-32 bg-slate-900 border border-slate-600 rounded px-2 py-1.5 text-slate-100 text-sm"
              placeholder="topic"
            />
          </label>
          <button
            type="button"
            disabled={createTag.isPending || !name.trim()}
            onClick={() => createTag.mutate()}
            className="px-3 py-2 rounded bg-cyan-700 text-white text-sm hover:bg-cyan-600 disabled:opacity-50"
          >
            {createTag.isPending ? "Saving…" : "Create"}
          </button>
        </div>
        {createTag.isError && <p className="text-red-400 text-xs mt-2">{(createTag.error as Error)?.message}</p>}
      </div>

      <div className="overflow-x-auto">
        <table className="w-full border border-slate-600 rounded-lg overflow-hidden max-w-4xl">
          <thead className="bg-slate-700">
            <tr>
              <th className="text-left p-3">Slug</th>
              <th className="text-left p-3">Name</th>
              <th className="text-left p-3">Category</th>
              <th className="text-left p-3">Usage</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && !tags.length ? (
              <tr>
                <td colSpan={4} className="p-4 text-slate-500">
                  Loading…
                </td>
              </tr>
            ) : null}
            {!isLoading && !tags.length ? (
              <tr>
                <td colSpan={4} className="p-4 text-slate-500">
                  No tags yet — import media to create rule-based tags, or add one above.
                </td>
              </tr>
            ) : null}
            {tags.map((t) => (
              <tr key={t.id} className="border-t border-slate-600">
                <td className="p-3 font-mono text-sm text-cyan-300/90">{t.slug}</td>
                <td className="p-3">{t.name}</td>
                <td className="p-3 text-slate-400 text-sm">{t.category ?? "—"}</td>
                <td className="p-3 text-slate-400">{t.usage_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
