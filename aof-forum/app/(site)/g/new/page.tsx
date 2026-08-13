import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

async function createGallery(formData: FormData) {
  "use server";
  const slug = String(formData.get("slug") ?? "").trim().toLowerCase();
  const title = String(formData.get("title") ?? "").trim();
  const description = String(formData.get("description") ?? "").trim();
  const isPublic = String(formData.get("is_public") ?? "1") === "1";

  if (!slug || !title) throw new Error("slug and title required");
  if (!/^[a-z0-9][a-z0-9-]*[a-z0-9]$/.test(slug)) throw new Error("invalid slug");

  const db = await createClient();
  const { data: u } = await db.auth.getUser();
  if (!u.user) redirect("/auth/sign-in?next=/g/new");

  const { error } = await db.from("galleries").insert({
    slug,
    title,
    description: description || null,
    owner_id: u.user.id,
    is_public: isPublic,
  });
  if (error) {
    if (error.code === "23505") throw new Error("that slug is taken");
    throw new Error(error.message);
  }
  redirect(`/g/${slug}`);
}

export default async function NewGalleryPage() {
  const db = await createClient();
  const { data: u } = await db.auth.getUser();
  if (!u.user) redirect("/auth/sign-in?next=/g/new");

  return (
    <article style={{ maxWidth: 560 }}>
      <h1>Create a gallery</h1>
      <p className="muted">
        Curate your own collection. After you create it, head to{" "}
        <a href="/upload">Upload</a> to add media (bulk upload ships in the next pass).
      </p>
      <form action={createGallery}>
        <label>
          Slug (URL identifier)
          <br />
          <input
            name="slug"
            required
            minLength={2}
            maxLength={64}
            pattern="^[a-z0-9][a-z0-9-]*[a-z0-9]$"
            placeholder="e.g. my-favorites"
          />
        </label>
        <label style={{ marginTop: "0.75rem", display: "block" }}>
          Title
          <br />
          <input name="title" required minLength={2} maxLength={120} />
        </label>
        <label style={{ marginTop: "0.75rem", display: "block" }}>
          Description
          <br />
          <textarea name="description" rows={4} maxLength={2000} />
        </label>
        <label style={{ marginTop: "0.75rem", display: "block" }}>
          Visibility
          <br />
          <select name="is_public" defaultValue="1">
            <option value="1">Public</option>
            <option value="0">Private (only you)</option>
          </select>
        </label>
        <button type="submit" className="primary" style={{ marginTop: "1rem" }}>
          Create gallery
        </button>
      </form>
    </article>
  );
}
