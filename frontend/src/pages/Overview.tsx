import {
  Activity as ActivityIcon, AlertTriangle, ArrowRight, BellRing, CalendarClock, CheckCircle2, Gauge, Info, PlugZap, ShieldAlert, Users, Wrench, Zap,
} from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { MonitoringCharts, RANGES } from "@/components/shared/MonitoringCharts";
import {
  EmptyState, ErrorState, OutageStatusBadge, PageHeader, SeverityBadge, SimulatedTag, StatCard, VerificationBadge,
} from "@/components/shared";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/menus";
import { Skeleton } from "@/components/ui/table";
import { useApp, useNow } from "@/hooks/app-context";
import { useDashboard, useSeries, useSettings } from "@/hooks/queries";
import { duration, formatRange, number, relative } from "@/lib/format";
import type { Activity } from "@/lib/types";
import { cn } from "@/lib/utils";

const ACTIVITY_ICON: Record<string, typeof Info> = {
  maintenance_created: Wrench, maintenance_scheduled: CalendarClock, maintenance_rescheduled: CalendarClock, maintenance_cancelled: CalendarClock,
  maintenance_started: Wrench, maintenance_completed: CheckCircle2, notification_queued: BellRing, notification_sent: BellRing,
  outage_detected: AlertTriangle, outage_confirmed: ShieldAlert, outage_escalated: ShieldAlert, incident_acknowledged: CheckCircle2,
  outage_resolved: CheckCircle2, meter_offline: PlugZap, low_voltage: Gauge, detection_suppressed: Info,
};
const SEVERITY_COLOR = { info: "text-muted-foreground bg-muted", success: "text-success bg-success-soft", warning: "text-amber-600 bg-warning-soft dark:text-warning", critical: "text-danger bg-danger-soft" };

export function ActivityFeed({ items, now }: { items: Activity[]; now: number }) {
  if (!items.length) return <EmptyState title="No activity yet" />;
  return (
    <ol className="space-y-3">
      {items.map((a) => {
        const Icon = ACTIVITY_ICON[a.type] ?? Info;
        return (
          <li key={a.id} className="flex gap-3 animate-fade-in">
            <span className={cn("mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full", SEVERITY_COLOR[a.severity])}>
              <Icon className="h-3.5 w-3.5" aria-hidden />
            </span>
            <div className="min-w-0">
              <p className="text-[13px] leading-snug">{a.message}</p>
              <p className="text-[11px] text-muted-foreground">{relative(a.ts, now)}</p>
            </div>
          </li>
        );
      })}
    </ol>
  );
}

export default function Overview() {
  const dash = useDashboard();
  const settings = useSettings();
  const [range, setRange] = useState("6h");
  const series = useSeries(range);
  const now = useNow(5000);
  const navigate = useNavigate();
  const { setDemoOpen } = useApp();
  const s = dash.data?.summary;
  const loading = dash.isLoading;
  const det = settings.data?.detection;

  return (
    <div className="animate-fade-in">
      <PageHeader
        title="Operations overview"
        description={<>Live view of the mini-grid network, planned work and customer communication. <SimulatedTag className="ml-1 align-middle" /></>}
        actions={
          <>
            <Button variant="outline" onClick={() => setDemoOpen(true)}>Guided demo</Button>
            <Button onClick={() => navigate("/scheduled?new=1")}><CalendarClock /> Schedule interruption</Button>
          </>
        }
      />
      {dash.error && <div className="mb-4"><ErrorState message={(dash.error as Error).message} onRetry={() => dash.refetch()} /></div>}

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <StatCard label="Connected meters" value={s?.total_meters} hint={`${s?.total_customers ?? "–"} customers on 5 service areas`} icon={Gauge} loading={loading} onClick={() => navigate("/monitoring")} />
        <StatCard label="Active meters" value={s ? `${s.active_meters}` : ""} hint={s ? `${s.offline_meters} offline · ${s.meters_no_supply} without supply` : ""} icon={ActivityIcon} tone="success" loading={loading} onClick={() => navigate("/monitoring")} />
        <StatCard label="Scheduled interruptions" value={s?.scheduled_interruptions} hint={s?.planned_in_progress ? `${s.planned_in_progress} area(s) in planned outage now` : "Upcoming planned work"} icon={CalendarClock} tone="warning" loading={loading} onClick={() => navigate("/scheduled")} />
        <StatCard label="Unexpected outages" value={s?.unexpected_outages} hint={s?.unconfirmed_incidents ? `${s.unconfirmed_incidents} awaiting verification` : "Open incidents"} icon={ShieldAlert} tone="danger" loading={loading} highlight={!!s?.unexpected_outages} onClick={() => navigate("/incidents")} />
        <StatCard label="Customers affected" value={s?.customers_affected} hint="Unexpected + planned, right now" icon={Users} tone={s?.customers_affected ? "danger" : "neutral"} loading={loading} />
        <StatCard label="Notifications scheduled" value={s?.notifications_scheduled} hint="Queued WhatsApp messages (simulated)" icon={BellRing} loading={loading} onClick={() => navigate("/notifications?tab=queue")} />
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader className="flex-row flex-wrap items-start justify-between gap-3 space-y-0">
            <div>
              <CardTitle>Electricity monitoring</CardTitle>
              <CardDescription>
                {s ? <>Now: <b className="text-foreground">{number(s.total_power_kw, 1)} kW</b> load · <b className="text-foreground">{number(s.avg_voltage, 1)} V</b> average</> : "Simulated consumption and voltage trends"}
              </CardDescription>
            </div>
            <Tabs value={range} onValueChange={setRange}>
              <TabsList>{RANGES.map((r) => <TabsTrigger key={r.value} value={r.value}>{r.label}</TabsTrigger>)}</TabsList>
            </Tabs>
          </CardHeader>
          <CardContent>
            <MonitoringCharts data={series.data} range={range} loading={series.isLoading} thresholds={det ? { low: det.low_voltage_max, outage: det.outage_voltage_max } : undefined} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex-row items-center justify-between space-y-0">
            <div>
              <CardTitle className="flex items-center gap-2">Active incidents {!!dash.data?.active_incidents.length && <span className="h-2 w-2 animate-pulse rounded-full bg-danger" />}</CardTitle>
              <CardDescription>Unexpected outages needing attention</CardDescription>
            </div>
            <Button variant="ghost" size="sm" asChild><Link to="/incidents">All <ArrowRight /></Link></Button>
          </CardHeader>
          <CardContent className="space-y-2">
            {loading ? <Skeleton className="h-24" /> : !dash.data?.active_incidents.length ? (
              <EmptyState icon={Zap} title="Normal supply everywhere" description="No unexpected outages detected." />
            ) : (
              dash.data.active_incidents.map((i) => (
                <Link key={i.id} to={`/incidents?id=${i.id}`} className={cn("block rounded-lg border p-3 transition hover:shadow-sm", i.severity === "critical" || i.severity === "high" ? "border-danger/40 bg-danger-soft/50" : "bg-card")}>
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-semibold">{i.code} · {i.service_area_name}</span>
                    <SeverityBadge severity={i.severity} />
                  </div>
                  <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                    <VerificationBadge status={i.verification_status} />
                    <span>{i.affected_meters}/{i.area_meter_count} meters · ~{i.estimated_customers} customers</span>
                    <span>· {i.power_restored_at ? "power restored" : `for ${duration(i.detected_at, null, now)}`}</span>
                  </div>
                </Link>
              ))
            )}
          </CardContent>
        </Card>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader className="flex-row items-center justify-between space-y-0">
            <div>
              <CardTitle>Upcoming maintenance</CardTitle>
              <CardDescription>Planned interruptions and their customer notifications</CardDescription>
            </div>
            <Button variant="ghost" size="sm" asChild><Link to="/scheduled">Calendar <ArrowRight /></Link></Button>
          </CardHeader>
          <CardContent>
            {loading ? <Skeleton className="h-40" /> : !dash.data?.upcoming_maintenance.length ? (
              <EmptyState icon={CalendarClock} title="No planned work" description="Schedule maintenance to notify customers in advance." action={<Button size="sm" onClick={() => navigate("/scheduled?new=1")}>Schedule interruption</Button>} />
            ) : (
              <div className="divide-y">
                {dash.data.upcoming_maintenance.map((o) => (
                  <Link key={o.id} to={`/scheduled?id=${o.id}`} className="flex flex-col gap-2 py-3 first:pt-0 last:pb-0 hover:opacity-90 sm:flex-row sm:items-center">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="truncate text-sm font-medium">{o.title}</p>
                        <OutageStatusBadge status={o.status} />
                      </div>
                      <p className="mt-0.5 text-xs text-muted-foreground">{o.service_areas.map((a) => a.name).join(", ")} · {formatRange(o.start_at, o.end_at)}</p>
                    </div>
                    <div className="flex shrink-0 items-center gap-4 text-xs">
                      <span className="flex items-center gap-1 text-muted-foreground"><Users className="h-3.5 w-3.5" /> {o.affected_customers}</span>
                      <span className="w-44 text-right">
                        {o.status === "draft" ? <Badge tone="muted">Not published</Badge> : (
                          <>
                            <span className="block font-medium">{o.notifications_sent} sent · {o.notifications_pending} pending</span>
                            {o.next_notification_at && <span className="text-muted-foreground">next {relative(o.next_notification_at, now)}</span>}
                          </>
                        )}
                      </span>
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Recent activity</CardTitle>
            <CardDescription>System and operator events</CardDescription>
          </CardHeader>
          <CardContent className="max-h-[420px] overflow-y-auto scrollbar-thin">
            {loading ? <Skeleton className="h-40" /> : <ActivityFeed items={dash.data?.recent_activity ?? []} now={now} />}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
