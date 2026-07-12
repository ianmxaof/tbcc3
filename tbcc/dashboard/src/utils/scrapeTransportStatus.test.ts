import { describe, expect, it } from "vitest";
import {
  filterScrapeSources,
  formatViewers,
  runProgressPct,
  sortScrapeSources,
  type ScrapeTransportSource,
} from "./scrapeTransportStatus";

function row(partial: Partial<ScrapeTransportSource> & { source_id: number }): ScrapeTransportSource {
  return {
    name: `src-${partial.source_id}`,
    identifier: `@c${partial.source_id}`,
    phase: "idle",
    ...partial,
  };
}

describe("scrapeTransportStatus", () => {
  it("formats viewers compactly", () => {
    expect(formatViewers(null)).toBe("—");
    expect(formatViewers(850)).toBe("850");
    expect(formatViewers(1500)).toBe("1.5k");
    expect(formatViewers(2_500_000)).toBe("2.5M");
  });

  it("filters by phase", () => {
    const sources = [
      row({ source_id: 1, phase: "running" }),
      row({ source_id: 2, phase: "idle" }),
      row({ source_id: 3, phase: "error" }),
    ];
    expect(filterScrapeSources(sources, "all")).toHaveLength(3);
    expect(filterScrapeSources(sources, "running").map((s) => s.source_id)).toEqual([1]);
  });

  it("computes progress pct from latest run", () => {
    expect(
      runProgressPct(
        row({
          source_id: 1,
          max_messages_per_run: 100,
          latest_run: { status: "running", messages_scanned: 40 },
        })
      )
    ).toBe(40);
    expect(
      runProgressPct(
        row({
          source_id: 2,
          latest_run: { status: "done", messages_scanned: 10 },
        })
      )
    ).toBe(100);
    expect(runProgressPct(row({ source_id: 3 }))).toBeNull();
  });

  it("sorts by views desc", () => {
    const sources = [
      row({ source_id: 1, avg_views_sample: 10 }),
      row({ source_id: 2, avg_views_sample: 500 }),
      row({ source_id: 3, avg_views_sample: 50 }),
    ];
    const sorted = sortScrapeSources(sources, "views", "desc");
    expect(sorted.map((s) => s.source_id)).toEqual([2, 3, 1]);
  });
});
