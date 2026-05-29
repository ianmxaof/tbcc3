import Link from "next/link";
import { MediaGrid } from "@/components/MediaGrid";

export const dynamic = "force-dynamic";

export default function ForYouPage() {
  return (
    <>
      <header style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: "1rem" }}>
        <h1>For You</h1>
        <div className="tabs" style={{ margin: 0, border: 0 }}>
          <Link href="/">Hot</Link>
          <Link href="/?sort=recent">New</Link>
          <Link className="active" href="/foryou">For You</Link>
        </div>
      </header>
      <p className="muted" style={{ marginBottom: "1rem" }}>
        Ranked by the tags you&apos;ve been viewing. The feed gets sharper the more you scroll;
        ~10% of items are random for serendipity.
      </p>
      <MediaGrid
        endpoint="/api/foryou?limit=24"
        context="foryou"
        queryKey={["foryou"]}
        emptyMessage="Scroll the main feed for a bit so the recommender learns your taste."
      />
    </>
  );
}
