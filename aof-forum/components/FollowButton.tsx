"use client";

import { useState } from "react";
import type { FollowTarget } from "@/lib/types";

export function FollowButton({
  targetKind,
  targetUserId,
  targetObjectId,
  initial,
  labelFollow = "Follow",
  labelFollowing = "Following",
}: {
  targetKind: FollowTarget;
  targetUserId?: string;
  targetObjectId?: number;
  initial?: boolean;
  labelFollow?: string;
  labelFollowing?: string;
}) {
  const [following, setFollowing] = useState(!!initial);
  const [pending, setPending] = useState(false);

  async function toggle() {
    if (pending) return;
    setPending(true);
    const next = !following;
    setFollowing(next);
    try {
      const r = await fetch("/api/follow", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          target_kind: targetKind,
          target_user_id: targetUserId,
          target_object_id: targetObjectId,
          follow: next,
        }),
      });
      if (!r.ok) {
        setFollowing(!next);
        if (r.status === 401) window.location.href = "/auth/sign-in";
      }
    } finally {
      setPending(false);
    }
  }

  return (
    <button onClick={toggle} disabled={pending} className={following ? "" : "primary"}>
      {following ? labelFollowing : labelFollow}
    </button>
  );
}
