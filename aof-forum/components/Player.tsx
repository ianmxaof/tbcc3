"use client";

import { useEffect, useRef, useState } from "react";
import type { MediaKind } from "@/lib/types";

/**
 * Erome-style top-of-page viewer. Inline gallery of stacked images, or a
 * single playable video. Designed for the media item page.
 */
export function Player({
  kind,
  url,
  thumbUrl,
  title,
  width,
  height,
}: {
  kind: MediaKind;
  url: string;
  thumbUrl?: string;
  title?: string | null;
  width?: number | null;
  height?: number | null;
}) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    setLoaded(false);
  }, [url]);

  const aspectRatio = width && height ? `${width} / ${height}` : "16 / 9";

  return (
    <div className="player-wrap" style={{ aspectRatio }}>
      {kind === "video" ? (
        <video
          ref={videoRef}
          src={url}
          poster={thumbUrl}
          controls
          preload="metadata"
          onLoadedData={() => setLoaded(true)}
        />
      ) : (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={url} alt={title ?? "media"} onLoad={() => setLoaded(true)} />
      )}
      {!loaded && <div className="empty" style={{ position: "absolute", inset: 0 }}><span className="spinner" /></div>}
    </div>
  );
}
