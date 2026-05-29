import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

async function createGroup(formData: FormData) {
  "use server";
  const slug = String(formData.get("slug") ?? "").trim().toLowerCase();
  const name = String(formData.get("name") ?? "").trim();
  const description = String(formData.get("description") ?? "").trim();
  const visibility = (String(formData.get("visibility") ?? "public") as "public" | "unlisted" | "private");

  if (!slug || !name) throw new Error("slug and name required");
  if (!/^[a-z0-9][a-z0-9-]*[a-z0-9]$/.test(slug)) throw new Error("invalid slug");

  const db = await createClient();
  const { data: u } = await db.auth.getUser();
  if (!u.user) redirect("/auth/sign-in?next=/groups/new");

  const { error } = await db.from("groups").insert({
    slug,
    name,
    description: description || null,
    owner_id: u.user.id,
    visibility,
  });
  if (error) {
    if (error.code === "23505") throw new Error("that slug is taken");
    throw new Error(error.message);
  }
  redirect(`/groups/${slug}`);
}

export default async function NewGroupPage() {
  const db = await createClient();
  const { data: u } = await db.auth.getUser();
  if (!u.user) redirect("/auth/sign-in?next=/groups/new");

  return (
    <article style={{ maxWidth: 560 }}>
      <h1>Create a group</h1>
      <p className="muted">
        Groups are first-class communities. You become the owner; members can submit media and
        threads. The recommender will use member overlap to suggest related groups.
      </p>
      <form action={createGroup}>
        <label>Slug (URL identifier)<br />
          <input name="slug" required minLength={2} maxLength={64} pattern="^[a-z0-9][a-z0-9-]*[a-z0-9]$" placeholder="e.g. amateur-vintage" />
        </label>
        <label style={{ marginTop: "0.75rem", display: "block" }}>Name<br />
          <input name="name" required minLength={2} maxLength={80} />
        </label>
        <label style={{ marginTop: "0.75rem", display: "block" }}>Description<br />
          <textarea name="description" rows={4} maxLength={2000} />
        </label>
        <label style={{ marginTop: "0.75rem", display: "block" }}>Visibility<br />
          <select name="visibility" defaultValue="public">
            <option value="public">Public</option>
            <option value="unlisted">Unlisted (link only)</option>
            <option value="private">Private (members only)</option>
          </select>
        </label>
        <button type="submit" className="primary" style={{ marginTop: "1rem" }}>Create</button>
      </form>
    </article>
  );
}
