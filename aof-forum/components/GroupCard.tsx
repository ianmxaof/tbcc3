import Link from "next/link";

export function GroupCard({
  slug,
  name,
  description,
  memberCount,
  itemCount,
  threadCount,
}: {
  slug: string;
  name: string;
  description: string | null;
  memberCount: number;
  itemCount: number;
  threadCount?: number;
}) {
  return (
    <Link href={`/groups/${slug}`} className="group-card">
      <div className="name">{name}</div>
      {description && <div className="desc">{description}</div>}
      <div className="stats">
        <span>{memberCount.toLocaleString()} members</span>
        <span>{itemCount.toLocaleString()} items</span>
        {threadCount !== undefined && <span>{threadCount.toLocaleString()} threads</span>}
      </div>
    </Link>
  );
}
