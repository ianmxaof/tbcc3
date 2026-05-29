import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

async function enqueueUrl(formData: FormData) {
  "use server";
  const sourceUrl = String(formData.get("source_url") ?? "").trim();
  if (!sourceUrl) throw new Error("URL required");
  const db = await createClient();
  const { data: u } = await db.auth.getUser();
  if (!u.user) redirect("/auth/sign-in?next=/upload");

  const { error } = await db.from("ingest_jobs").insert({
    requester_id: u.user.id,
    source_url: sourceUrl,
    source_kind: "web_pull",
    status: "queued",
  });
  if (error) throw new Error(error.message);
  redirect("/upload?queued=1");
}

export default async function UploadPage({
  searchParams,
}: {
  searchParams: Promise<{ queued?: string }>;
}) {
  const { queued } = await searchParams;
  const db = await createClient();
  const { data: u } = await db.auth.getUser();
  if (!u.user) redirect("/auth/sign-in?next=/upload");

  const { data: jobs } = await db
    .from("ingest_jobs")
    .select("id, source_url, status, error, result_media_id, created_at")
    .eq("requester_id", u.user.id)
    .order("created_at", { ascending: false })
    .limit(20);

  return (
    <article style={{ maxWidth: 720 }}>
      <h1>Upload</h1>
      <p className="muted">
        Paste a URL (erome / onlyfans / bunkr / generic) and the local ingest worker will
        download it, dedupe by phash, upload to B2, and create a <code>media_items</code> row.
        For direct file uploads, drop into <code>C:\aof-media\inbox\</code> instead.
      </p>

      {queued && <div className="card" style={{ marginBottom: "1rem" }}>Job queued. Watch the worker terminal for progress.</div>}

      <form action={enqueueUrl} className="card">
        <label>Source URL<br />
          <input name="source_url" type="url" placeholder="https://..." required />
        </label>
        <button type="submit" className="primary" style={{ marginTop: "0.75rem" }}>Queue</button>
      </form>

      <h3 style={{ marginTop: "2rem" }}>Recent jobs</h3>
      {(jobs ?? []).length === 0 ? (
        <div className="empty muted">No jobs yet.</div>
      ) : (
        <ul style={{ listStyle: "none", padding: 0 }}>
          {(jobs ?? []).map((j) => (
            <li key={j.id} className="card" style={{ marginBottom: "0.4rem", padding: "0.5rem 0.75rem" }}>
              <div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}>
                <span style={{ fontFamily: "monospace", fontSize: "0.8rem" }}>#{j.id}</span>
                <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {j.source_url}
                </span>
                <span className="muted" style={{ fontSize: "0.8rem" }}>{j.status}</span>
              </div>
              {j.error && <div className="muted" style={{ fontSize: "0.8rem", color: "var(--danger)" }}>{j.error}</div>}
              {j.result_media_id && (
                <div style={{ fontSize: "0.85rem", marginTop: "0.25rem" }}>
                  → <a href={`/m/${j.result_media_id}`}>media #{j.result_media_id}</a>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </article>
  );
}
