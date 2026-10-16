import { AlarmClock, BellRing, CalendarClock, Hourglass, Send, ShieldAlert, Timer, TriangleAlert } from "lucide-react";
import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ErrorState, PageHeader, SimulatedTag, StatCard } from "@/components/shared";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/menus";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow, Skeleton } from "@/components/ui/table";
import { useAnalytics } from "@/hooks/queries";
import { CHART } from "@/lib/constants";
import { formatDate, number, secondsLabel } from "@/lib/format";

const axis = { stroke: "var(--chart-axis)", fontSize: 11, tickLine: false, axisLine: false } as const;
const KIND: Record<string, string> = { notice: "Notice", reminder: "Reminder", reschedule: "Reschedule", cancellation: "Cancellation", outage_alert: "Outage alert", outage_update: "Outage update", restoration: "Restoration", manual: "Manual" };
const SEV_COLOR = { low: "#94a3b8", medium: "#F59E0B", high: "#f97316", critical: "#EF4444" };

function Tip({ active, payload, label, fmt }: { active?: boolean; payload?: any[]; label?: string; fmt?: (l: string) => string }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border bg-popover px-3 py-2 text-xs shadow-lg">
      <p className="mb-1 text-muted-foreground">{fmt ? fmt(label ?? "") : label}</p>
      {payload.map((p) => (
        <p key={p.dataKey} className="flex items-center gap-2"><span className="h-2 w-2 rounded-full" style={{ background: p.color ?? p.fill }} />{p.name}: <b>{p.value}</b></p>
      ))}
    </div>
  );
}

function ChartCard({ title, description, children, loading }: { title: string; description?: string; children: React.ReactNode; loading?: boolean }) {
  return (
    <Card>
      <CardHeader><CardTitle>{title}</CardTitle>{description && <CardDescription>{description}</CardDescription>}</CardHeader>
      <CardContent className="h-72">{loading ? <Skeleton className="h-full" /> : children}</CardContent>
    </Card>
  );
}

export default function Analytics() {
  const [days, setDays] = useState(90);
  const q = useAnalytics(days);
  const a = q.data;
  const k = a?.kpis;
  const loading = q.isLoading;
  return (
    <div className="animate-fade-in">
      <PageHeader
        title="Analytics"
        description={<>Reliability and communication performance. <SimulatedTag className="ml-1 align-middle" /> All statistics are generated from simulated demo data.</>}
        actions={<Tabs value={String(days)} onValueChange={(v) => setDays(Number(v))}><TabsList><TabsTrigger value="30">30 days</TabsTrigger><TabsTrigger value="90">90 days</TabsTrigger></TabsList></Tabs>}
      />
      {q.error && <ErrorState message={(q.error as Error).message} onRetry={() => q.refetch()} />}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatCard label="Planned interruptions" value={k?.planned_interruptions} hint={`${k?.cancelled_interruptions ?? 0} cancelled`} icon={CalendarClock} tone="warning" loading={loading} />
        <StatCard label="Unexpected outages" value={k?.unexpected_outages} hint={`${k?.confirmed_outages ?? 0} confirmed`} icon={ShieldAlert} tone="danger" loading={loading} />
        <StatCard label="Avg. unexpected outage" value={k?.avg_unexpected_duration_min != null ? `${number(k.avg_unexpected_duration_min)} min` : "—"} hint={`Planned avg ${number(k?.avg_planned_duration_min)} min`} icon={Hourglass} loading={loading} />
        <StatCard label="Avg. detection time" value={secondsLabel(k?.avg_detection_seconds)} hint={`Confirmation +${secondsLabel(k?.avg_confirmation_seconds)}`} icon={Timer} tone="success" loading={loading} />
        <StatCard label="Notification preparation" value={secondsLabel(k?.avg_notification_prep_seconds)} hint="Detection → customer alert queued" icon={AlarmClock} loading={loading} />
        <StatCard label="Avg. advance notice" value={k?.avg_advance_notice_hours != null ? `${number(k.avg_advance_notice_hours, 1)} h` : "—"} hint="Notice sent before planned work" icon={BellRing} tone="warning" loading={loading} />
        <StatCard label="Messages sent (simulated)" value={number(k?.messages_sent)} hint={`${number(k?.messages_failed)} failed`} icon={Send} tone="success" loading={loading} />
        <StatCard label="Notification failure rate" value={k ? `${(k.failure_rate * 100).toFixed(1)}%` : ""} hint="Simulated delivery outcomes" icon={TriangleAlert} tone={k && k.failure_rate > 0.1 ? "danger" : "neutral"} loading={loading} />
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <ChartCard title="Interruptions per week" description="Planned (amber) vs unexpected (red)" loading={loading}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={a?.weekly} margin={{ top: 8, right: 8, left: -20, bottom: 0 }} barGap={2}>
              <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
              <XAxis dataKey="week_start" tickFormatter={(v) => formatDate(v).replace(/ \d{4}$/, "")} {...axis} minTickGap={16} />
              <YAxis allowDecimals={false} {...axis} />
              <Tooltip content={<Tip fmt={(l) => `Week of ${formatDate(l)}`} />} cursor={{ fill: "var(--chart-grid)", opacity: 0.4 }} />
              <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="planned" name="Planned" fill={CHART.planned} radius={[4, 4, 0, 0]} maxBarSize={18} />
              <Bar dataKey="unexpected" name="Unexpected" fill={CHART.unexpected} radius={[4, 4, 0, 0]} maxBarSize={18} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
        <ChartCard title="Unexpected outage durations" description="Minutes from first evidence to restoration" loading={loading}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={a?.durations} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
              <XAxis dataKey="code" {...axis} minTickGap={8} />
              <YAxis {...axis} />
              <Tooltip content={<Tip fmt={(l) => `${l} · ${a?.durations.find((d) => d.code === l)?.area ?? ""}`} />} cursor={{ fill: "var(--chart-grid)", opacity: 0.4 }} />
              <Bar dataKey="minutes" name="Minutes" fill={CHART.unexpected} radius={[4, 4, 0, 0]} maxBarSize={22} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
        <ChartCard title="Simulated messages by type" description="Sent vs failed outcomes" loading={loading}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={a?.messages_by_kind.map((m) => ({ ...m, label: KIND[m.kind] ?? m.kind }))} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
              <XAxis dataKey="label" {...axis} interval={0} fontSize={10} />
              <YAxis {...axis} />
              <Tooltip content={<Tip />} cursor={{ fill: "var(--chart-grid)", opacity: 0.4 }} />
              <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="sent" name="Simulated sent" stackId="m" fill={CHART.sent} maxBarSize={28} />
              <Bar dataKey="failed" name="Failed" stackId="m" fill={CHART.failed} radius={[4, 4, 0, 0]} maxBarSize={28} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
        <ChartCard title="Incident severity" description="Unexpected outages by severity" loading={loading}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={a?.severity} layout="vertical" margin={{ top: 8, right: 24, left: 8, bottom: 0 }}>
              <CartesianGrid horizontal={false} stroke="var(--chart-grid)" />
              <XAxis type="number" allowDecimals={false} {...axis} />
              <YAxis type="category" dataKey="severity" {...axis} width={64} tickFormatter={(v) => v[0].toUpperCase() + v.slice(1)} />
              <Tooltip content={<Tip />} cursor={{ fill: "var(--chart-grid)", opacity: 0.4 }} />
              <Bar dataKey="count" name="Incidents" radius={[0, 4, 4, 0]} maxBarSize={22}>
                {a?.severity.map((s) => <Cell key={s.severity} fill={SEV_COLOR[s.severity]} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      <Card className="mt-4">
        <CardHeader><CardTitle>Most affected service areas</CardTitle><CardDescription>Ranked by number of interruptions; customer-hours estimate the total time customers were without power</CardDescription></CardHeader>
        <CardContent className="p-0">
          {loading ? <div className="p-4"><Skeleton className="h-40" /></div> : (
            <Table>
              <TableHeader><TableRow><TableHead>Service area</TableHead><TableHead className="text-right">Unexpected</TableHead><TableHead className="text-right">Planned</TableHead><TableHead className="w-[40%]">Customer-hours without power</TableHead></TableRow></TableHeader>
              <TableBody>
                {a?.areas.map((r) => {
                  const max = Math.max(...a.areas.map((x) => x.customer_hours_lost), 1);
                  return (
                    <TableRow key={r.service_area_id}>
                      <TableCell className="font-medium">{r.name}</TableCell>
                      <TableCell className="text-right tabular">{r.unexpected}</TableCell>
                      <TableCell className="text-right tabular">{r.planned}</TableCell>
                      <TableCell>
                        <div className="flex items-center gap-3">
                          <div className="h-2 flex-1 overflow-hidden rounded-full bg-muted"><div className="h-full rounded-full bg-primary" style={{ width: `${(r.customer_hours_lost / max) * 100}%` }} /></div>
                          <span className="w-16 text-right text-sm tabular">{number(r.customer_hours_lost, 1)} h</span>
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
