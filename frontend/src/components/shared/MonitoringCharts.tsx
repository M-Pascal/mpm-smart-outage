import { Area, AreaChart, CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Skeleton } from "@/components/ui/table";
import { CHART } from "@/lib/constants";
import { formatDay, formatTime } from "@/lib/format";
import type { SeriesPoint } from "@/lib/types";

export const RANGES = [
  { value: "1h", label: "1 hour" },
  { value: "6h", label: "6 hours" },
  { value: "24h", label: "24 hours" },
  { value: "7d", label: "7 days" },
];

const axis = { stroke: "var(--chart-axis)", fontSize: 11, tickLine: false, axisLine: false } as const;

function ChartTooltip({ active, payload, unit, label }: { active?: boolean; payload?: any[]; unit: string; label?: string }) {
  if (!active || !payload?.length) return null;
  const p = payload[0];
  return (
    <div className="rounded-lg border bg-popover px-3 py-2 text-xs shadow-lg">
      <p className="mb-1 text-muted-foreground">{label ? `${formatDay(label)} · ${formatTime(label)}` : ""}</p>
      <p className="flex items-center gap-2 font-medium">
        <span className="h-2 w-2 rounded-full" style={{ background: p.color ?? p.stroke }} />
        {p.value == null ? "No data" : `${Number(p.value).toFixed(unit === "V" ? 1 : 2)} ${unit}`}
      </p>
    </div>
  );
}

/** Consumption and voltage as two stacked charts sharing a time axis and a synced crosshair (never a dual axis). */
export function MonitoringCharts({ data, range, loading, height = 170, thresholds }: {
  data?: SeriesPoint[];
  range: string;
  loading?: boolean;
  height?: number;
  thresholds?: { low: number; outage: number };
}) {
  if (loading && !data) return <div className="space-y-3"><Skeleton className="h-[170px]" /><Skeleton className="h-[170px]" /></div>;
  const tick = (v: string) => (range === "7d" ? formatDay(v) : formatTime(v));
  const syncId = "monitoring";
  return (
    <div className="space-y-4">
      <div>
        <div className="mb-1 flex items-baseline justify-between">
          <p className="text-sm font-medium">Electricity consumption</p>
          <p className="text-xs text-muted-foreground">kW, total load</p>
        </div>
        <div style={{ height }}>
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data} syncId={syncId} margin={{ top: 6, right: 8, left: -12, bottom: 0 }}>
              <defs>
                <linearGradient id="powerFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={CHART.power} stopOpacity={0.28} />
                  <stop offset="100%" stopColor={CHART.power} stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
              <XAxis dataKey="ts" tickFormatter={tick} minTickGap={40} {...axis} />
              <YAxis width={44} {...axis} />
              <Tooltip content={<ChartTooltip unit="kW" />} cursor={{ stroke: "var(--chart-axis)", strokeDasharray: "3 3" }} />
              <Area type="monotone" dataKey="power_kw" stroke={CHART.power} strokeWidth={2} fill="url(#powerFill)" isAnimationActive={false} activeDot={{ r: 4, strokeWidth: 2 }} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>
      <div>
        <div className="mb-1 flex items-baseline justify-between">
          <p className="text-sm font-medium">Average supply voltage</p>
          <p className="text-xs text-muted-foreground">V, reporting meters · nominal 230 V</p>
        </div>
        <div style={{ height }}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} syncId={syncId} margin={{ top: 6, right: 8, left: -12, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
              <XAxis dataKey="ts" tickFormatter={tick} minTickGap={40} {...axis} />
              <YAxis width={44} domain={[0, 260]} ticks={[0, 50, 100, 150, 200, 250]} {...axis} />
              {thresholds && (
                <>
                  <ReferenceLine y={thresholds.low} stroke="#F59E0B" strokeDasharray="4 4" label={{ value: `Low ${thresholds.low} V`, position: "insideBottomLeft", fontSize: 10, fill: "var(--chart-axis)" }} />
                  <ReferenceLine y={thresholds.outage} stroke="#EF4444" strokeDasharray="4 4" label={{ value: `Outage ${thresholds.outage} V`, position: "insideTopLeft", fontSize: 10, fill: "var(--chart-axis)" }} />
                </>
              )}
              <Tooltip content={<ChartTooltip unit="V" />} cursor={{ stroke: "var(--chart-axis)", strokeDasharray: "3 3" }} />
              <Line type="monotone" dataKey="voltage" stroke={CHART.voltage} strokeWidth={2} dot={false} connectNulls={false} isAnimationActive={false} activeDot={{ r: 4, strokeWidth: 2 }} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
