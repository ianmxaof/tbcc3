import { describe, expect, it } from "vitest";
import {
  schedulerHealthChipStyle,
  schedulerHealthRatio,
} from "./schedulerHealthChipColors";

describe("schedulerHealthChipColors", () => {
  it("maps full health to green hues", () => {
    const style = schedulerHealthChipStyle(1);
    expect(style.color).toMatch(/hsl\(14[0-9]/);
  });

  it("maps low health to warm dark red hues", () => {
    const ratio = schedulerHealthRatio(14, 43);
    expect(ratio).toBeCloseTo(14 / 43, 4);
    const style = schedulerHealthChipStyle(ratio);
    const hue = Number(style.backgroundColor.match(/hsla\((\d+)/)?.[1]);
    expect(hue).toBeLessThan(40);
    expect(hue).toBeGreaterThan(5);
  });

  it("returns 1 when total is zero", () => {
    expect(schedulerHealthRatio(0, 0)).toBe(1);
  });
});
