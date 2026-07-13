/** 14-stop green → yellow → warm dark red palette for scheduler on-track nav chip. */
const HUE_STOPS = [
  6, 8, 12, 18, 24, 32, 40, 48, 58, 72, 88, 102, 118, 142,
] as const;
const SAT_STOPS = [
  44, 46, 48, 50, 52, 50, 48, 46, 44, 42, 40, 38, 38, 36,
] as const;
const LIGHT_STOPS = [
  22, 24, 26, 28, 30, 32, 33, 34, 34, 33, 32, 32, 33, 34,
] as const;

export type SchedulerHealthChipStyle = {
  borderColor: string;
  backgroundColor: string;
  color: string;
};

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

function sampleStop(stops: readonly number[], ratio: number): number {
  const clamped = Math.max(0, Math.min(1, ratio));
  const maxIdx = stops.length - 1;
  const pos = clamped * maxIdx;
  const lo = Math.floor(pos);
  const hi = Math.min(maxIdx, lo + 1);
  const t = pos - lo;
  return lerp(stops[lo], stops[hi], t);
}

/** ratio 1 = all healthy (green), 0 = none healthy (warm dark red). */
export function schedulerHealthChipStyle(ratio: number): SchedulerHealthChipStyle {
  const h = sampleStop(HUE_STOPS, ratio);
  const s = sampleStop(SAT_STOPS, ratio);
  const l = sampleStop(LIGHT_STOPS, ratio);
  return {
    borderColor: `hsla(${h}, ${s}%, ${l + 14}%, 0.58)`,
    backgroundColor: `hsla(${h}, ${s}%, ${l}%, 0.38)`,
    color: `hsl(${h}, ${Math.max(28, s - 6)}%, ${Math.min(86, l + 44)}%)`,
  };
}

export function schedulerHealthRatio(healthy: number, total: number): number {
  if (total <= 0) return 1;
  return Math.max(0, Math.min(1, healthy / total));
}
