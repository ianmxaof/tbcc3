import { useMemo } from "react";
import { PoolIntervalsChart, type PoolIntervalChartPoint } from "./PoolIntervalsChart";
import { SchedulerPoolsPanel } from "./SchedulerPoolsPanel";
import { SchedulerWeek } from "./SchedulerWeek";

const BAND_H = "h-[7.75rem]";

type WeekPost = {
  id: number;
  name?: string | null;
  scheduled_at?: string | null;
  interval_minutes?: number | null;
  channel_name?: string | null;
  campaign_group_id?: string | null;
};

export function SchedulerOverviewBand({
  pools,
  scheduledPosts,
  poolMap,
  weekPosts,
  onWeekDayClick,
}: {
  pools: Array<Record<string, unknown>>;
  scheduledPosts: Array<Record<string, unknown>>;
  poolMap: Record<string, Record<string, unknown>>;
  weekPosts: WeekPost[];
  onWeekDayClick?: (isoDate: string) => void;
}) {
  const poolIntervalChartData: PoolIntervalChartPoint[] = useMemo(
    () =>
      pools.map((p) => ({
        name: String(p.name || `Pool ${p.id}`),
        interval: Number(p.interval_minutes) || 60,
        id: p.id,
      })),
    [pools]
  );

  return (
    <div className={`flex flex-wrap lg:flex-nowrap gap-2 mb-2 items-stretch ${BAND_H} max-w-full`}>
      <div
        className={`tbcc-panel shrink-0 w-full sm:w-52 ${BAND_H} rounded-md border border-slate-600/90 bg-slate-900/40 px-2 py-1.5 flex flex-col min-h-0`}
      >
        <PoolIntervalsChart data={poolIntervalChartData} height={100} className="flex-1 min-h-0" />
      </div>
      <div className={`shrink-0 w-full sm:w-[17.5rem] ${BAND_H} min-h-0`}>
        <SchedulerPoolsPanel scheduledPosts={scheduledPosts} poolMap={poolMap} />
      </div>
      <div className={`tbcc-panel flex-1 min-w-[14rem] ${BAND_H} min-h-0 rounded-md border border-slate-600/90 bg-slate-800/40 overflow-hidden`}>
        <SchedulerWeek posts={weekPosts} onDayClick={onWeekDayClick} compact />
      </div>
    </div>
  );
}
