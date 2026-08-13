import Link from "next/link";
import { resolvePerformerLiveCta } from "@/lib/live-embeds";

export function LivePerformerCta({
  tagSlug,
  performerName,
}: {
  tagSlug: string;
  performerName: string;
}) {
  const cta = resolvePerformerLiveCta(tagSlug, performerName);
  if (!cta) return null;

  return (
    <div className="card live-performer-cta" style={{ marginBottom: "1rem" }}>
      <span className="live-dot" />
      <strong>{performerName}</strong> may be live —{" "}
      <a href={cta.href} target="_blank" rel="noopener sponsored noreferrer">
        {cta.label}
      </a>
      {cta.embedSlot?.iframeSrc?.trim() && (
        <>
          {" "}
          or <Link href="/live">browse all cams</Link>
        </>
      )}
    </div>
  );
}
