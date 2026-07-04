import { describe, expect, it } from "vitest";
import {
  classifySchedulerPost,
  computeTransportStats,
  inferSchedulerGroup,
  isRecurringActive,
  isSentOneShot,
  matchesStatusFilter,
} from "./schedulerPostStatus";

describe("schedulerPostStatus", () => {
  it("infers scheduler groups from names", () => {
    expect(inferSchedulerGroup("AOF MILF SCHEDULER")).toBe("main_lane");
    expect(inferSchedulerGroup("AOF — bot commands — AOF AI")).toBe("bot_commands");
    expect(inferSchedulerGroup("AOF — network liveness — heartbeat")).toBe("liveness");
    expect(inferSchedulerGroup("AOF MAIN — Links Hub bulletin (pinned)")).toBe("promo_bulletin");
    expect(inferSchedulerGroup("My custom job")).toBe("manual");
  });

  it("prefers scheduler_category when set", () => {
    expect(inferSchedulerGroup("anything", "bot_commands")).toBe("bot_commands");
  });

  it("detects recurring active vs sent one-shot", () => {
    expect(isRecurringActive({ interval_minutes: 240 })).toBe(true);
    expect(isSentOneShot({ sent_at: "2026-01-01T00:00:00Z" })).toBe(true);
    expect(isSentOneShot({ interval_minutes: 60, sent_at: "2026-01-01T00:00:00Z" })).toBe(false);
  });

  it("computes transport stats for running and stalled mix", () => {
    const now = Date.parse("2026-07-02T12:00:00Z");
    const health = { beatRunning: true, celeryPostRunning: true, schedulingPaused: false };
    const posts = [
      {
        id: 1,
        name: "AOF AI SCHEDULER",
        interval_minutes: 60,
        last_posted_at: "2026-07-02T11:30:00Z",
      },
      {
        id: 2,
        name: "AOF MILF SCHEDULER",
        interval_minutes: 60,
        last_posted_at: "2026-07-02T09:00:00Z",
      },
      {
        id: 3,
        name: "AOF — bot commands — X",
        interval_minutes: 1440,
        posting_auto_paused_at: "2026-07-02T11:00:00Z",
      },
      { id: 4, name: "One-shot", sent_at: "2026-06-01T00:00:00Z" },
    ];
    const stats = computeTransportStats(posts, health, now);
    expect(stats.total).toBe(3);
    expect(stats.onTrack).toBe(1);
    expect(stats.stalled).toBe(1);
    expect(stats.autoPaused).toBe(1);
    expect(stats.healthyPrimary).toBe(1);
  });

  it("treats focus pause as focus_paused not stalled when workers are up", () => {
    const now = Date.parse("2026-07-02T12:00:00Z");
    const health = { beatRunning: true, celeryPostRunning: true, schedulingPaused: true };
    const row = classifySchedulerPost(
      { interval_minutes: 120, last_posted_at: "2026-07-02T11:30:00Z" },
      health,
      now
    );
    expect(row.phase).toBe("focus_paused");
    const stats = computeTransportStats(
      [{ interval_minutes: 120, last_posted_at: "2026-07-02T11:30:00Z" }],
      health,
      now
    );
    expect(stats.stalled).toBe(0);
    expect(stats.focusPaused).toBe(1);
  });

  it("matches status filters", () => {
    const health = { beatRunning: true, celeryPostRunning: true, schedulingPaused: false };
    const stalled = classifySchedulerPost(
      { interval_minutes: 60, last_posted_at: "2026-07-02T08:00:00Z" },
      health,
      Date.parse("2026-07-02T12:00:00Z")
    );
    expect(stalled.phase).toBe("stalled");
    expect(matchesStatusFilter(stalled, "stalled")).toBe(true);
    expect(matchesStatusFilter(stalled, "auto_paused")).toBe(false);
  });
});
