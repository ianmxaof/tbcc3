import Link from "next/link";
import { MediaGrid } from "@/components/MediaGrid";
import { HomeExploreRails } from "@/components/HomeExploreRails";

export const dynamic = "force-dynamic";

export default function FeedPage({
  searchParams,
}: {
  searchParams: { sort?: string };
}) {
  const sort = searchParams?.sort === "recent" ? "recent" : "hot";
  return (
    <>
      <HomeExploreRails />
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: "1rem" }}>
        <h1>{sort === "recent" ? "New" : "Hot"}</h1>
        <div className="tabs" style={{ margin: 0, border: 0 }}>
          <Link className={sort === "hot" ? "active" : ""} href="/">Hot</Link>
          <Link className={sort === "recent" ? "active" : ""} href="/?sort=recent">New</Link>
          <Link href="/foryou">For You</Link>
        </div>
      </div>
      <MediaGrid
        endpoint={`/api/feed?sort=${sort}&limit=24`}
        context="feed"
        queryKey={["feed", sort]}
      />
    </>
  );
}
