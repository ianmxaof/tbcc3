"use client";

import { useRouter, useSearchParams } from "next/navigation";
import type { ConnectPlatform } from "@/lib/connect/types";

const PLATFORMS: { value: ConnectPlatform | ""; label: string }[] = [
  { value: "", label: "All platforms" },
  { value: "snapchat", label: "Snapchat" },
  { value: "telegram", label: "Telegram" },
  { value: "instagram", label: "Instagram" },
  { value: "other", label: "Other" },
];

const GENDERS = ["", "female", "male", "trans", "couple", "other"] as const;
const ORIENTATIONS = ["", "straight", "gay", "lesbian", "bi", "other"] as const;

export function ConnectFilterSidebar() {
  const router = useRouter();
  const sp = useSearchParams();

  function setParam(key: string, value: string) {
    const next = new URLSearchParams(sp.toString());
    if (value) next.set(key, value);
    else next.delete(key);
    router.push(`/connect?${next.toString()}`);
  }

  return (
    <aside className="connect-filters card">
      <h3 style={{ marginTop: 0 }}>Filters</h3>

      <label>
        Platform
        <select
          value={sp.get("platform") ?? ""}
          onChange={(e) => setParam("platform", e.target.value)}
        >
          {PLATFORMS.map((p) => (
            <option key={p.value || "all"} value={p.value}>
              {p.label}
            </option>
          ))}
        </select>
      </label>

      <label>
        Gender
        <select value={sp.get("gender") ?? ""} onChange={(e) => setParam("gender", e.target.value)}>
          <option value="">Any</option>
          {GENDERS.filter(Boolean).map((g) => (
            <option key={g} value={g}>
              {g}
            </option>
          ))}
        </select>
      </label>

      <label>
        Orientation
        <select
          value={sp.get("orientation") ?? ""}
          onChange={(e) => setParam("orientation", e.target.value)}
        >
          <option value="">Any</option>
          {ORIENTATIONS.filter(Boolean).map((o) => (
            <option key={o} value={o}>
              {o}
            </option>
          ))}
        </select>
      </label>

      <label>
        Country (ISO)
        <input
          type="text"
          maxLength={2}
          placeholder="US"
          defaultValue={sp.get("country") ?? ""}
          onBlur={(e) => setParam("country", e.target.value.toUpperCase())}
        />
      </label>

      <label className="connect-check">
        <input
          type="checkbox"
          checked={sp.get("vip") === "1"}
          onChange={(e) => setParam("vip", e.target.checked ? "1" : "")}
        />
        VIP only
      </label>

      <label className="connect-check">
        <input
          type="checkbox"
          checked={sp.get("photo") === "1"}
          onChange={(e) => setParam("photo", e.target.checked ? "1" : "")}
        />
        Has photo
      </label>

      <label>
        Sort
        <select value={sp.get("sort") ?? "hot"} onChange={(e) => setParam("sort", e.target.value)}>
          <option value="hot">Hot</option>
          <option value="active">Last active</option>
          <option value="new">New</option>
        </select>
      </label>
    </aside>
  );
}
