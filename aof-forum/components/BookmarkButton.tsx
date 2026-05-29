"use client";

import { useState } from "react";

export function BookmarkButton({
  mediaId,
  initial,
}: {
  mediaId: number;
  initial?: boolean;
}) {
  const [bookmarked, setBookmarked] = useState(!!initial);
  const [pending, setPending] = useState(false);

  async function toggle() {
    if (pending) return;
    setPending(true);
    const next = !bookmarked;
    setBookmarked(next);
    try {
      const r = await fetch("/api/bookmark", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ media_id: mediaId, bookmarked: next }),
      });
      if (!r.ok) {
        setBookmarked(!next);
        if (r.status === 401) window.location.href = "/auth/sign-in";
      }
    } finally {
      setPending(false);
    }
  }

  return (
    <button onClick={toggle} disabled={pending} aria-pressed={bookmarked}>
      {bookmarked ? "★ Saved" : "☆ Save"}
    </button>
  );
}
