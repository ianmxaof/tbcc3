"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export function JoinLeaveButton({
  slug,
  initialRole,
}: {
  slug: string;
  initialRole: "owner" | "mod" | "member" | null;
}) {
  const router = useRouter();
  const [role, setRole] = useState(initialRole);
  const [pending, setPending] = useState(false);

  async function go(action: "join" | "leave") {
    if (pending) return;
    setPending(true);
    try {
      const r = await fetch(`/api/groups/${encodeURIComponent(slug)}/${action}`, { method: "POST" });
      if (!r.ok) {
        if (r.status === 401) window.location.href = "/auth/sign-in";
        return;
      }
      setRole(action === "join" ? "member" : null);
      router.refresh();
    } finally {
      setPending(false);
    }
  }

  if (role === "owner") return <span className="muted">Owner</span>;
  if (role) {
    return (
      <button onClick={() => go("leave")} disabled={pending}>Leave</button>
    );
  }
  return (
    <button className="primary" onClick={() => go("join")} disabled={pending}>Join</button>
  );
}
