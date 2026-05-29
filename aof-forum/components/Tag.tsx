import Link from "next/link";
import type { TagKind } from "@/lib/types";

export function TagPill({
  slug,
  name,
  kind = "tag",
}: {
  slug: string;
  name: string;
  kind?: TagKind;
}) {
  return (
    <Link href={`/t/${slug}`} className={`tag-pill kind-${kind}`}>{name}</Link>
  );
}

export function TagList({ tags }: { tags: { slug: string; name: string; kind: TagKind }[] }) {
  if (!tags.length) return null;
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
      {tags.map((t) => (
        <TagPill key={t.slug} slug={t.slug} name={t.name} kind={t.kind} />
      ))}
    </div>
  );
}
