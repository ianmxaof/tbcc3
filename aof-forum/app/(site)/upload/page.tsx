import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { UploadPanel } from "@/components/UploadPanel";

export const dynamic = "force-dynamic";

export default async function UploadPage() {
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
      <UploadPanel />

      <h3 style={{ marginTop: "2rem" }}>Recent URL jobs</h3>
      {(jobs ?? []).length === 0 ? (
        <div className="empty muted">No URL import jobs yet.</div>
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
              {j.error && (
                <div className="muted" style={{ fontSize: "0.8rem", color: "var(--danger)" }}>
                  {j.error}
                </div>
              )}
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
