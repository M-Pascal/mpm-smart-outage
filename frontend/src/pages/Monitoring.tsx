import { Activity, CalendarClock, Gauge, PlugZap, Search, ShieldAlert, WifiOff, Zap, ZapOff } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { MonitoringCharts, RANGES } from "@/components/shared/MonitoringCharts";
import { SimulationControls } from "@/components/shared/SimulationControls";
import { EmptyState, ErrorState, KeyValue, MeterStatusBadge, PageHeader, SimulatedTag, StatCard, TableSkeleton } from "@/components/shared";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogDescription, DialogTitle, SheetContent } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger, Tip } from "@/components/ui/menus";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useNow } from "@/hooks/app-context";
import { useAreas, useMeterReadings, useMeters, useSeries, useSettings } from "@/hooks/queries";
import { METER_STATUS } from "@/lib/constants";
import { formatDateTime, number, relative } from "@/lib/format";
import type { MeterStatus, ServiceArea } from "@/lib/types";
import { cn } from "@/lib/utils";

function MeterDetail({ id, onClose }: { id: number | null; onClose: () => void }) {
  const meters = useMeters();
  const m = meters.data?.find((x) => x.id === id);
  const [range, setRange] = useState("24h");
  const readings = useMeterReadings(id, range);
  const now = useNow(5000);
  return (
    <Dialog open={id != null} onOpenChange={(v) => !v && onClose()}>
      <SheetContent className="sm:max-w-2xl">
        {!m ? <div className="p-6"><TableSkeleton rows={6} cols={2} /></div> : (
          <>
            <div className="border-b p-6 pr-12">
              <div className="flex items-center gap-2"><span className="font-mono text-xs text-muted-foreground">{m.serial}</span><MeterStatusBadge status={m.status} /><SimulatedTag /></div>
              <DialogTitle className="mt-2 text-xl font-semibold">{m.customer_name ?? "Unassigned meter"}</DialogTitle>
              <DialogDescription className="mt-1 text-sm text-muted-foreground">{m.service_area_name}</DialogDescription>
            </div>
            <div className="space-y-6 p-6">
              <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                <KeyValue label="Voltage">{number(m.voltage, 1)} V</KeyValue>
                <KeyValue label="Current">{number(m.current, 2)} A</KeyValue>
                <KeyValue label="Power">{number(m.power_kw, 2)} kW</KeyValue>
                <KeyValue label="Last reading">{relative(m.last_reading_at, now)}</KeyValue>
                <KeyValue label="Connection">{m.status === "offline" ? "Not reporting" : "Online"}</KeyValue>
                <KeyValue label="Status since">{m.status_since ? formatDateTime(m.status_since) : "—"}</KeyValue>
                {m.pending_status && <KeyValue label="Pending">{METER_STATUS[m.pending_status].label} ({m.pending_count} reading)</KeyValue>}
                {m.customer_id && <KeyValue label="Customer"><Link className="text-primary hover:underline" to={`/customers?id=${m.customer_id}`}>View profile</Link></KeyValue>}
              </dl>
              <div>
                <div className="mb-3 flex items-center justify-between">
                  <h4 className="text-sm font-semibold">Historical readings</h4>
                  <Tabs value={range} onValueChange={setRange}><TabsList>{RANGES.slice(0, 3).map((r) => <TabsTrigger key={r.value} value={r.value}>{r.label}</TabsTrigger>)}</TabsList></Tabs>
                </div>
                {readings.data && readings.data.length === 0 ? <EmptyState title="No readings in this range" /> : <MonitoringCharts data={readings.data} range={range} loading={readings.isLoading} height={150} />}
              </div>
            </div>
          </>
        )}
      </SheetContent>
    </Dialog>
  );
}

function AreaCard({ a, selected, onClick }: { a: ServiceArea; selected: boolean; onClick: () => void }) {
  const state = a.open_incident ? "incident" : a.planned_outage ? "planned" : a.meters_offline === a.meter_count && a.meter_count ? "offline" : a.meters_low_voltage ? "low" : "ok";
  const styles = {
    incident: "border-danger/50 bg-danger-soft/60",
    planned: "border-warning/60 bg-warning-soft/60",
    offline: "border-slate-400/60",
    low: "border-warning/40",
    ok: "",
  }[state];
  return (
    <button onClick={onClick} className={cn("rounded-xl border bg-card p-4 text-left shadow-sm transition hover:shadow-md", styles, selected && "ring-2 ring-primary")}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold">{a.name}</p>
          <p className="text-xs text-muted-foreground">{a.mini_grid_name}</p>
        </div>
        {state === "incident" ? <ShieldAlert className="h-4 w-4 shrink-0 text-danger" aria-label="Incident" /> : state === "planned" ? <CalendarClock className="h-4 w-4 shrink-0 text-amber-500" aria-label="Planned outage" /> : state === "offline" ? <WifiOff className="h-4 w-4 text-slate-500" /> : <Zap className="h-4 w-4 shrink-0 text-success" aria-label="Normal" />}
      </div>
      <div className="mt-3 flex items-end justify-between">
        <div>
          <p className="text-2xl font-semibold tabular">{a.avg_voltage != null ? `${a.avg_voltage.toFixed(0)} V` : "—"}</p>
          <p className="text-xs text-muted-foreground">{number(a.total_power_kw, 1)} kW load</p>
        </div>
        <div className="text-right text-xs">
          <p>{a.meters_online}/{a.meter_count} online</p>
          {a.meters_no_supply > 0 && <p className="font-medium text-danger">{a.meters_no_supply} no supply</p>}
        </div>
      </div>
      {a.open_incident && <Badge tone="danger" className="mt-2">{a.open_incident.code} · {a.open_incident.verification_status}</Badge>}
      {a.planned_outage && <Badge tone="warning" className="mt-2">{a.planned_outage.code} planned</Badge>}
    </button>
  );
}

export default function Monitoring() {
  const [params, setParams] = useSearchParams();
  const areas = useAreas();
  const meters = useMeters();
  const settings = useSettings();
  const now = useNow(2000);
  const [range, setRange] = useState("1h");
  const [status, setStatus] = useState<string>("all");
  const [q, setQ] = useState("");
  const areaId = params.get("area") ? Number(params.get("area")) : null;
  const meterId = params.get("meter") ? Number(params.get("meter")) : null;
  const series = useSeries(range, areaId);
  const det = settings.data?.detection;

  const list = useMemo(() => (meters.data ?? []).filter((m) =>
    (!areaId || m.service_area_id === areaId) && (status === "all" || m.status === status)
    && (!q || m.serial.toLowerCase().includes(q.toLowerCase()) || (m.customer_name ?? "").toLowerCase().includes(q.toLowerCase()))), [meters.data, areaId, status, q]);
  const all = meters.data ?? [];
  const count = (s: MeterStatus) => all.filter((m) => m.status === s).length;
  const setArea = (id: number | null) => { if (id) params.set("area", String(id)); else params.delete("area"); setParams(params); };
  const lastUpdate = all.reduce<string | null>((acc, m) => (m.last_reading_at && (!acc || m.last_reading_at > acc) ? m.last_reading_at : acc), null);

  return (
    <div className="animate-fade-in">
      <PageHeader title="Power monitoring" description={<>Real-time readings from smart meters <SimulatedTag className="ml-1 align-middle" /> · last update {relative(lastUpdate, now)}</>} />
      <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <StatCard label="Online devices" value={all.length - count("offline")} hint={`of ${all.length} meters`} icon={Activity} tone="success" loading={meters.isLoading} />
        <StatCard label="Offline devices" value={count("offline")} hint="Possible communication issue" icon={WifiOff} tone="neutral" loading={meters.isLoading} />
        <StatCard label="No supply" value={count("no_supply")} hint="Near-zero voltage" icon={ZapOff} tone="danger" loading={meters.isLoading} highlight={count("no_supply") > 0} />
        <StatCard label="Low voltage" value={count("low_voltage")} hint={`Below ${det?.low_voltage_max ?? 196} V`} icon={PlugZap} tone="warning" loading={meters.isLoading} />
        <StatCard label="Average voltage" value={`${number(all.filter((m) => m.status !== "offline" && m.status !== "no_supply").reduce((s, m, _, arr) => s + (m.voltage ?? 0) / arr.length, 0), 0)} V`} hint="Powered meters" icon={Gauge} loading={meters.isLoading} />
        <StatCard label="Total load" value={`${number(all.reduce((s, m) => s + (m.status === "offline" ? 0 : m.power_kw ?? 0), 0), 1)} kW`} hint="All reporting meters" icon={Zap} loading={meters.isLoading} />
      </div>

      {areas.error && <ErrorState message={(areas.error as Error).message} />}
      <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-5">
        {areas.isLoading ? Array.from({ length: 5 }).map((_, i) => <div key={i} className="h-36 animate-pulse rounded-xl bg-muted" />) :
          areas.data?.map((a) => <AreaCard key={a.id} a={a} selected={areaId === a.id} onClick={() => setArea(areaId === a.id ? null : a.id)} />)}
      </div>

      <div className="grid gap-4 xl:grid-cols-[1fr_420px]">
        <Card>
          <CardHeader className="flex-row flex-wrap items-start justify-between gap-3 space-y-0">
            <div>
              <CardTitle>Voltage & consumption</CardTitle>
              <CardDescription>{areaId ? areas.data?.find((a) => a.id === areaId)?.name : "All service areas"} · click an area card to filter</CardDescription>
            </div>
            <Tabs value={range} onValueChange={setRange}><TabsList>{RANGES.map((r) => <TabsTrigger key={r.value} value={r.value}>{r.label}</TabsTrigger>)}</TabsList></Tabs>
          </CardHeader>
          <CardContent><MonitoringCharts data={series.data} range={range} loading={series.isLoading} thresholds={det ? { low: det.low_voltage_max, outage: det.outage_voltage_max } : undefined} /></CardContent>
        </Card>
        <SimulationControls />
      </div>

      <Card className="mt-4">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b p-4">
          <div>
            <h3 className="text-base font-semibold">Meter status</h3>
            <p className="text-sm text-muted-foreground">{list.length} meters{areaId ? " in selected area" : ""} · select a meter for its history</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <div className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Meter ID or customer" className="w-52 pl-8" aria-label="Search meters" />
            </div>
            <Select value={areaId ? String(areaId) : "all"} onValueChange={(v) => setArea(v === "all" ? null : Number(v))}>
              <SelectTrigger className="w-48" aria-label="Service area"><SelectValue /></SelectTrigger>
              <SelectContent><SelectItem value="all">All service areas</SelectItem>{areas.data?.map((a) => <SelectItem key={a.id} value={String(a.id)}>{a.name}</SelectItem>)}</SelectContent>
            </Select>
            <Select value={status} onValueChange={setStatus}>
              <SelectTrigger className="w-36" aria-label="Status"><SelectValue /></SelectTrigger>
              <SelectContent><SelectItem value="all">Any status</SelectItem>{(Object.keys(METER_STATUS) as MeterStatus[]).map((s) => <SelectItem key={s} value={s}>{METER_STATUS[s].label}</SelectItem>)}</SelectContent>
            </Select>
          </div>
        </div>
        <CardContent className="p-0">
          {meters.isLoading ? <div className="p-4"><TableSkeleton rows={8} cols={7} /></div> : list.length === 0 ? <div className="p-6"><EmptyState title="No meters match" /></div> : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Meter ID</TableHead>
                  <TableHead>Customer</TableHead>
                  <TableHead>Service area</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Voltage</TableHead>
                  <TableHead className="text-right">Current</TableHead>
                  <TableHead className="text-right">Power</TableHead>
                  <TableHead>Last reading</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {list.map((m) => {
                  const area = areas.data?.find((a) => a.id === m.service_area_id);
                  return (
                    <TableRow key={m.id} className={cn("cursor-pointer", m.status === "no_supply" && "bg-danger-soft/40")} onClick={() => { params.set("meter", String(m.id)); setParams(params); }}>
                      <TableCell className="font-mono text-xs">{m.serial}</TableCell>
                      <TableCell>{m.customer_name ?? "—"}</TableCell>
                      <TableCell className="text-sm text-muted-foreground">
                        <span className="inline-flex items-center gap-1.5">
                          {m.service_area_name}
                          {area?.open_incident && <Tip content={`${area.open_incident.code} open`}><ShieldAlert className="h-3.5 w-3.5 text-danger" /></Tip>}
                          {area?.planned_outage && <Tip content={`${area.planned_outage.code} planned outage in progress`}><CalendarClock className="h-3.5 w-3.5 text-amber-500" /></Tip>}
                        </span>
                      </TableCell>
                      <TableCell>
                        <MeterStatusBadge status={m.status} />
                        {m.pending_status && <span className="ml-1.5 text-[11px] text-muted-foreground">confirming {METER_STATUS[m.pending_status].label.toLowerCase()}…</span>}
                      </TableCell>
                      <TableCell className={cn("text-right font-medium tabular", m.status === "no_supply" && "text-danger", m.status === "low_voltage" && "text-amber-600")}>{m.status === "offline" ? "—" : `${number(m.voltage, 1)} V`}</TableCell>
                      <TableCell className="text-right tabular">{m.status === "offline" ? "—" : `${number(m.current, 2)} A`}</TableCell>
                      <TableCell className="text-right tabular">{m.status === "offline" ? "—" : `${number(m.power_kw, 2)} kW`}</TableCell>
                      <TableCell className={cn("whitespace-nowrap text-xs", m.status === "offline" ? "font-medium text-amber-600" : "text-muted-foreground")}>{relative(m.last_reading_at, now)}</TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
      <MeterDetail id={meterId} onClose={() => { params.delete("meter"); setParams(params); }} />
    </div>
  );
}
