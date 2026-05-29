"use client";

import { useState } from "react";
import type { VoteTarget } from "@/lib/types";

export function VoteButtons({
  targetKind,
  targetId,
  initialUp,
  initialDown,
  initialValue = 0,
}: {
  targetKind: VoteTarget;
  targetId: number;
  initialUp: number;
  initialDown: number;
  initialValue?: -1 | 0 | 1;
}) {
  const [up, setUp] = useState(initialUp);
  const [down, setDown] = useState(initialDown);
  const [value, setValue] = useState<-1 | 0 | 1>(initialValue);
  const [pending, setPending] = useState(false);

  async function send(newValue: -1 | 0 | 1) {
    if (pending) return;
    setPending(true);
    const prev = value;
    setValue(newValue);
    setUp((u) => u + (newValue === 1 ? 1 : 0) - (prev === 1 ? 1 : 0));
    setDown((d) => d + (newValue === -1 ? 1 : 0) - (prev === -1 ? 1 : 0));
    try {
      const r = await fetch("/api/vote", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ target_kind: targetKind, target_id: targetId, value: newValue }),
      });
      if (!r.ok) {
        // rollback
        setValue(prev);
        setUp((u) => u + (prev === 1 ? 1 : 0) - (newValue === 1 ? 1 : 0));
        setDown((d) => d + (prev === -1 ? 1 : 0) - (newValue === -1 ? 1 : 0));
        if (r.status === 401) window.location.href = "/auth/sign-in";
      }
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="vote-bar">
      <button
        className={`up ${value === 1 ? "active" : ""}`}
        aria-label="upvote"
        onClick={() => send(value === 1 ? 0 : 1)}
        disabled={pending}
      >
        ▲
      </button>
      <span className="count">{up - down}</span>
      <button
        className={`down ${value === -1 ? "active" : ""}`}
        aria-label="downvote"
        onClick={() => send(value === -1 ? 0 : -1)}
        disabled={pending}
      >
        ▼
      </button>
    </div>
  );
}
