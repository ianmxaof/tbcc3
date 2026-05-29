"use server";

import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { createClient } from "@/lib/supabase/server";

export async function attachExistingMediaToGroup(formData: FormData) {
  const slug = String(formData.get("group_slug") ?? "");
  const mediaId = Number.parseInt(String(formData.get("media_id") ?? ""), 10);
  if (!slug || !Number.isFinite(mediaId) || mediaId <= 0) {
    throw new Error("group slug and valid media_id required");
  }

  const db = await createClient();
  const { data: user } = await db.auth.getUser();
  if (!user.user) redirect(`/auth/sign-in?next=/groups/${slug}/new`);

  const { data: g } = await db.from("groups").select("id").eq("slug", slug).maybeSingle();
  if (!g) throw new Error("group not found");

  const { data: mem } = await db
    .from("group_members")
    .select("role")
    .eq("group_id", g.id)
    .eq("user_id", user.user.id)
    .maybeSingle();
  if (!mem) throw new Error("join the group before submitting");

  const { data: media } = await db
    .from("media_items")
    .select("id")
    .eq("id", mediaId)
    .eq("is_public", true)
    .eq("is_deleted", false)
    .maybeSingle();
  if (!media) throw new Error("media not found or not public");

  const { error } = await db.from("group_media").insert({
    group_id: g.id,
    media_id: mediaId,
    added_by: user.user.id,
  });
  if (error) {
    if (error.code === "23505") throw new Error("this item is already in the group");
    throw new Error(error.message);
  }

  revalidatePath(`/groups/${slug}`);
  redirect(`/groups/${slug}?tab=media&ok=1`);
}

export async function queueIngestToGroup(formData: FormData) {
  const slug = String(formData.get("group_slug") ?? "");
  const url = String(formData.get("source_url") ?? "").trim();
  if (!slug || !url) throw new Error("group slug and source URL required");

  const db = await createClient();
  const { data: user } = await db.auth.getUser();
  if (!user.user) redirect(`/auth/sign-in?next=/groups/${slug}/new`);

  const { data: g } = await db.from("groups").select("id").eq("slug", slug).maybeSingle();
  if (!g) throw new Error("group not found");

  const { data: mem } = await db
    .from("group_members")
    .select("role")
    .eq("group_id", g.id)
    .eq("user_id", user.user.id)
    .maybeSingle();
  if (!mem) throw new Error("join the group before submitting");

  const { error } = await db.from("ingest_jobs").insert({
    requester_id: user.user.id,
    source_url: url,
    source_kind: "web_pull",
    destination_group_id: g.id,
    status: "queued",
  });
  if (error) throw new Error(error.message);

  redirect(`/upload?queued=1`);
}
