import type { Metadata } from "next";
import { LivePageBody } from "@/components/LivePageBody";
import { liveEmbedsConfigured } from "@/lib/live-embeds";

export const metadata: Metadata = {
  title: "Live — AOF Hub",
  description: "Find cam models online now. Live streams via our affiliate partner; Telegram for owned drops.",
};

export default function LivePage() {
  return (
    <article className="live-page">
      <h1>
        <span className="live-dot" />
        Live
      </h1>
      <p className="muted" style={{ marginBottom: "1rem" }}>
        {liveEmbedsConfigured()
          ? "Streaming partner rooms below — Telegram CTAs for owned loot, VIP, and companion."
          : "Configure Awempire widgets to go live here. Telegram links work today."}
      </p>
      <LivePageBody />
    </article>
  );
}
