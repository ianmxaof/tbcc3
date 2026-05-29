"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import type { MediaKind, ViewContext } from "@/lib/types";

export interface MediaCardItem {
  id: number;
  kind: MediaKind;
  title: string | null;
  url: string;
  thumb_url: string;
  width: number | null;
  height: number | null;
  duration_seconds: number | null;
  views_count: number;
}

function formatDuration(s: number | null): string | null {
  if (!s || s <= 0) return null;
  const m = Math.floor(s / 60);
  const ss = Math.floor(s % 60).toString().padStart(2, "0");
  return `${m}:${ss}`;
}

function postView(mediaId: number, ctx: ViewContext | null, sourceId: number | null, dwell: number | null) {
  const body = JSON.stringify({ media_id: mediaId, context: ctx, source_id: sourceId, dwell_ms: dwell });
  // Use sendBeacon for unload-safe heartbeats; fall back to fetch.
  if (typeof navigator !== "undefined" && "sendBeacon" in navigator) {
    try {
      const blob = new Blob([body], { type: "application/json" });
      navigator.sendBeacon("/api/view", blob);
      return;
    } catch {
      /* fallthrough */
    }
  }
  fetch("/api/view", { method: "POST", headers: { "content-type": "application/json" }, body, keepalive: true }).catch(() => {});
}

export function MediaCard({
  item,
  context = "feed",
  sourceId = null,
  autoplayVideo = true,
  groupLinkSlug,
}: {
  item: MediaCardItem;
  context?: ViewContext;
  sourceId?: number | null;
  autoplayVideo?: boolean;
  /** When opening from a group feed, keep group context on the media detail page. */
  groupLinkSlug?: string;
}) {
  const rootRef = useRef<HTMLAnchorElement | null>(null);
  const vidRef = useRef<HTMLVideoElement | null>(null);
  const [visible, setVisible] = useState(false);
  const visibleSinceRef = useRef<number | null>(null);
  const sentViewRef = useRef(false);
  const viewTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const el = rootRef.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      ([entry]) => {
        const isVisible = entry.isIntersecting && entry.intersectionRatio > 0.5;
        setVisible(isVisible);
        if (isVisible) {
          visibleSinceRef.current = performance.now();
          if (!sentViewRef.current && !viewTimerRef.current) {
            viewTimerRef.current = setTimeout(() => {
              viewTimerRef.current = null;
              if (!sentViewRef.current && rootRef.current && rootRef.current.getBoundingClientRect().bottom > 0) {
                postView(item.id, context, sourceId, null);
                sentViewRef.current = true;
              }
            }, 1000);
          }
        } else {
          if (viewTimerRef.current) {
            clearTimeout(viewTimerRef.current);
            viewTimerRef.current = null;
          }
          if (visibleSinceRef.current != null) {
            const dwell = Math.round(performance.now() - visibleSinceRef.current);
            visibleSinceRef.current = null;
            if (sentViewRef.current && dwell > 1500) {
              postView(item.id, context, sourceId, dwell);
            }
          }
        }
      },
      { threshold: [0, 0.5, 1] }
    );
    obs.observe(el);
    return () => {
      obs.disconnect();
      if (viewTimerRef.current) {
        clearTimeout(viewTimerRef.current);
        viewTimerRef.current = null;
      }
    };
  }, [item.id, context, sourceId]);

  useEffect(() => {
    const v = vidRef.current;
    if (!v || !autoplayVideo) return;
    if (visible) {
      v.muted = true;
      v.play().catch(() => {});
    } else {
      v.pause();
    }
  }, [visible, autoplayVideo]);

  const dur = formatDuration(item.duration_seconds);
  const isVideo = item.kind === "video";
  const isGif = item.kind === "gif";
  const href =
    groupLinkSlug != null && groupLinkSlug !== ""
      ? `/m/${item.id}?group=${encodeURIComponent(groupLinkSlug)}`
      : `/m/${item.id}`;

  return (
    <Link ref={rootRef} className="media-card" href={href}>
      <div className="thumb">
        {isVideo ? (
          <video
            ref={vidRef}
            src={item.url}
            poster={item.thumb_url || undefined}
            preload="metadata"
            muted
            loop
            playsInline
          />
        ) : (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={item.thumb_url || item.url} alt={item.title ?? ""} loading="lazy" />
        )}
        {isVideo && <span className="badge">video</span>}
        {isGif && <span className="badge">gif</span>}
        {dur && <span className="duration">{dur}</span>}
      </div>
      <div className="meta">
        <div className="title">{item.title || `media #${item.id}`}</div>
        <div className="sub">
          <span>{item.views_count.toLocaleString()} views</span>
          {item.width && item.height && <span>{item.width}x{item.height}</span>}
        </div>
      </div>
    </Link>
  );
}
