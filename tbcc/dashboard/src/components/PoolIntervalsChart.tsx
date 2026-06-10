import { BarChart, Bar, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { InfoDisclosure } from "./InfoDisclosure";

export type PoolIntervalChartPoint = {
  name: string;
  interval: number;
  id?: unknown;
};

export function PoolIntervalsChart({
  data,
  height = 120,
  className = "",
}: {
  data: PoolIntervalChartPoint[];
  height?: number;
  className?: string;
}) {
  return (
    <div className={`min-w-0 ${className}`.trim()}>
      <div className="flex items-center justify-between gap-1 mb-0.5">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">
          Pool intervals
        </span>
        <InfoDisclosure>
          Minutes between auto-posts per pool (Beat + TBCC-Celery-Post).
        </InfoDisclosure>
      </div>
      {data.length > 0 ? (
        <ResponsiveContainer width="100%" height={height}>
          <BarChart data={data} margin={{ top: 2, right: 2, left: -22, bottom: 0 }}>
            <XAxis
              dataKey="name"
              stroke="#94a3b8"
              fontSize={7}
              interval={0}
              angle={-50}
              textAnchor="end"
              height={44}
            />
            <YAxis stroke="#94a3b8" fontSize={8} width={26} tickCount={4} />
            <Tooltip
              contentStyle={{ backgroundColor: "#1e293b", border: "1px solid #475569", fontSize: 11 }}
              labelStyle={{ color: "#e2e8f0" }}
            />
            <Bar dataKey="interval" radius={[3, 3, 0, 0]}>
              {data.map((_, i) => (
                <Cell key={i} fill="#06b6d4" />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      ) : (
        <p className="text-[10px] text-slate-500 py-4">No pools.</p>
      )}
    </div>
  );
}
