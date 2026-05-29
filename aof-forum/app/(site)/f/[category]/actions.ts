"use server";

import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { createClient } from "@/lib/supabase/server";

function slugify(s: string): string {
  return s
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80);
}

export async function createThread(formData: FormData) {
  const categorySlug = String(formData.get("category_slug") ?? "");
  const title = String(formData.get("title") ?? "").trim();
  const body = String(formData.get("body") ?? "").trim();
  if (!title || !body) throw new Error("title and body required");

  const db = await createClient();
  const { data: u } = await db.auth.getUser();
  if (!u.user) redirect("/auth/sign-in");

  const { data: cat } = await db.from("forum_categories").select("id").eq("slug", categorySlug).maybeSingle();
  if (!cat) throw new Error("unknown category");

  const slug = `${slugify(title)}-${Math.random().toString(36).slice(2, 6)}`;
  const { data: thread, error } = await db
    .from("forum_threads")
    .insert({
      category_id: cat.id,
      author_id: u.user.id,
      title,
      slug,
    })
    .select("id, slug")
    .single();
  if (error || !thread) throw new Error(error?.message ?? "create thread failed");

  await db.from("forum_posts").insert({
    thread_id: thread.id,
    author_id: u.user.id,
    body_md: body,
  });

  revalidatePath(`/f/${categorySlug}`);
  redirect(`/f/${categorySlug}/${thread.slug}`);
}

export async function createReply(formData: FormData) {
  const threadId = Number.parseInt(String(formData.get("thread_id") ?? "0"), 10);
  const parentId = Number.parseInt(String(formData.get("parent_post_id") ?? "0"), 10) || null;
  const body = String(formData.get("body") ?? "").trim();
  const categorySlug = String(formData.get("category_slug") ?? "");
  const threadSlug = String(formData.get("thread_slug") ?? "");
  if (!threadId || !body) throw new Error("thread_id and body required");

  const db = await createClient();
  const { data: u } = await db.auth.getUser();
  if (!u.user) redirect("/auth/sign-in");

  const { error } = await db.from("forum_posts").insert({
    thread_id: threadId,
    author_id: u.user.id,
    parent_post_id: parentId,
    body_md: body,
  });
  if (error) throw new Error(error.message);

  revalidatePath(`/f/${categorySlug}/${threadSlug}`);
}
