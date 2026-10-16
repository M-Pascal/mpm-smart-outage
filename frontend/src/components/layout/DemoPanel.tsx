import { CalendarClock, CheckCircle2, Clock, FastForward, History, Loader2, MonitorPlay, RotateCcw, ShieldAlert, SkipForward } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogDescription, DialogTitle, SheetContent } from "@/components/ui/dialog";
import { Label, Switch } from "@/components/ui/form-bits";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/menus";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useApp, useNow } from "@/hooks/app-context";
import { useAction, useAreas, useDemoClock, useIncidents, useScheduled } from "@/hooks/queries";
import { api } from "@/lib/api";
import { formatDateTime, formatLongDate, formatTimeSec, relative } from "@/lib/format";
import type { Incident, ScheduledOutage } from "@/lib/types";
import { cn } from "@/lib/utils";

function Step({ n, title, children, done, active }: { n: number; title: string; children?: ReactNode; done?: boolean; active?: boolean }) {
  return (
    <li className={cn("relative flex gap-3 rounded-lg border p-3 transition-colors", done ? "border-success/40 bg-success-soft/40" : active ? "border-primary/50 bg-brand-soft/40" : "bg-card")}>
      <div className="mt-0.5 shrink-0">
        {done ? <CheckCircle2 className="h-5 w-5 text-success" /> : <span className="flex h-5 w-5 items-center justify-center rounded-full border text-[11px] font-semibold text-muted-foreground">{n}</span>}
      </div>
      <div className="min-w-0 flex-1 space-y-2">
        <p className="text-sm font-medium leading-snug">{title}</p>
        {children}
      </div>
    </li>
  );
}

function ClockControls() {
  const clock = useDemoClock();
  const now = useNow(1000);
  const { offsetMs } = useApp();
  const advance = useAction((body: object) => api.post<{ advanced?: boolean; reason?: string; notifications_sent?: number }>("/demo/advance", body), {
    success: (r) => (r.advanced === false ? r.reason ?? "Nothing to advance to" : `Clock advanced${r.notifications_sent ? ` · ${r.notifications_sent} notification job(s) processed` : ""}`),
  });
  const reset = useAction(() => api.post("/demo/clock/reset"), { success: "Demo clock reset to real time" });
  const auto = useAction((enabled: boolean) => api.post("/demo/auto-tick", { enabled }), { success: (r: any) => (r.auto_tick ? "Live meter feed resumed" : "Live meter feed paused") });
  const next = clock.data?.next_notification;
  return (
    <div className="space-y-3 rounded-xl border bg-muted/40 p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground"><Clock className="h-3.5 w-3.5" /> Demo clock</p>
          <p className="text-xl font-semibold tabular">{formatTimeSec(new Date(now))}</p>
          <p className="text-xs text-muted-foreground">{formatLongDate(new Date(now))}</p>
        </div>
        {offsetMs > 0 ? <Badge tone="warning">+{(offsetMs / 3600000).toFixed(1)} h ahead</Badge> : <Badge tone="success">Real time</Badge>}
      </div>
      <div className="grid grid-cols-3 gap-2">
        {[{ m: 60, l: "+1 hour" }, { m: 360, l: "+6 hours" }, { m: 1440, l: "+1 day" }].map((b) => (
          <Button key={b.m} size="sm" variant="outline" disabled={advance.isPending} onClick={() => advance.mutate({ minutes: b.m })}><FastForward /> {b.l}</Button>
        ))}
      </div>
      <Button className="w-full" size="sm" disabled={advance.isPending || !next} onClick={() => advance.mutate({ to_next_notification: true })}>
        {advance.isPending ? <Loader2 className="animate-spin" /> : <SkipForward />} Jump to next scheduled notification
      </Button>
      <p className="text-xs text-muted-foreground">
        {next ? <>Next: <span className="font-medium text-foreground">{next.kind_label}</span>{next.linked && <> for {next.linked.code}</>} · {formatDateTime(next.send_at)} ({relative(next.send_at, now)})</> : "No notifications are scheduled."}
      </p>
      <div className="flex items-center justify-between border-t pt-3">
        <div className="flex items-center gap-2">
          <Switch id="auto-tick" checked={clock.data?.auto_tick ?? true} onCheckedChange={(v) => auto.mutate(v)} />
          <Label htmlFor="auto-tick" className="text-xs">Live meter feed</Label>
        </div>
        <Button size="sm" variant="ghost" disabled={offsetMs === 0 || reset.isPending} onClick={() => reset.mutate()}><RotateCcw /> Reset clock</Button>
      </div>
    </div>
  );
}

function ScenarioA({ close }: { close: () => void }) {
  const navigate = useNavigate();
  const scheduled = useScheduled();
  const demoEvent = useMemo(
    () => (scheduled.data ?? []).filter((o) => o.title.startsWith("Feeder maintenance") && o.status !== "cancelled").sort((a, b) => b.id - a.id)[0],
    [scheduled.data],
  );
  const jumped = useAction(() => api.post<{ advanced: boolean; job_id?: number; reason?: string }>("/demo/advance", { to_next_notification: true }), {
    success: (r) => (r.advanced ? "Time advanced: the scheduled reminder was processed" : r.reason ?? "Nothing scheduled"),
  });
  const sentReminder = demoEvent && demoEvent.notifications_sent >= 2;
  return (
    <ol className="space-y-2">
      <Step n={1} title="Create a maintenance event, choose the area and time, schedule a reminder and review the WhatsApp preview" done={!!demoEvent} active={!demoEvent}>
        <p className="text-xs text-muted-foreground">Opens the scheduling form pre-filled with demo values (Sector B, tomorrow 9:00–11:00, 1-hour reminder). Review the live preview, then click <b>Schedule & queue notifications</b>.</p>
        <Button size="sm" onClick={() => { navigate("/scheduled?new=demo"); close(); }}><CalendarClock /> Open scheduling form</Button>
        {demoEvent && <p className="text-xs text-success">Created {demoEvent.code}: {demoEvent.title}. The initial notice was sent in simulation.</p>}
      </Step>
      <Step n={2} title="Advance the demo clock to trigger the scheduled reminder" done={!!sentReminder} active={!!demoEvent && !sentReminder}>
        <Button size="sm" disabled={!demoEvent || jumped.isPending} onClick={() => jumped.mutate()}><SkipForward /> Jump to the reminder time</Button>
        {demoEvent?.next_notification_at && !sentReminder && <p className="text-xs text-muted-foreground">Reminder due {formatDateTime(demoEvent.next_notification_at)}.</p>}
      </Step>
      <Step n={3} title="Show the notification in the history" active={!!sentReminder}>
        <Button size="sm" variant="outline" onClick={() => { navigate("/notifications?tab=history"); close(); }}><History /> Open notification history</Button>
      </Step>
    </ol>
  );
}

function ScenarioB({ close }: { close: () => void }) {
  const navigate = useNavigate();
  const areas = useAreas();
  const incidents = useIncidents("all");
  const area = areas.data?.find((a) => a.code === "D");
  const [since, setSince] = useState<number | null>(null);
  const inc: Incident | undefined = useMemo(
    () => (incidents.data ?? []).filter((i) => area && i.service_area_id === area.id && since != null && new Date(i.detected_at).getTime() >= since - 60_000).sort((a, b) => b.id - a.id)[0],
    [incidents.data, area, since],
  );
  const normal = useAction(() => api.post("/simulation/normal"), { success: "Normal supply on all simulated meters" });
  const loss = useAction(async () => {
    const clock = await api.get<{ now: string }>("/demo/clock");
    setSince(new Date(clock.now).getTime());
    return api.post("/simulation/outage", { scenario: "multi_meter_loss", service_area_id: area!.id });
  }, { success: "Voltage loss simulated in Sector D – Riverside" });
  const reading = useAction(() => api.post("/simulation/tick"), { success: "New meter readings collected" });
  const confirm = useAction(async () => {
    await api.post("/demo/advance", { minutes: 0.2 });
    return api.post(`/incidents/${inc!.id}/confirm`, { notify_customers: true });
  }, { success: "Outage verified by the operator; customer alert sent (simulated)" });
  const restore = useAction(() => api.post("/simulation/restore", { service_area_id: area!.id }), { success: "Power restored in Sector D" });
  const alertJob = inc?.verification_status === "confirmed";
  const supplyNormal = area && area.meters_no_supply === 0 && !area.sim_scenario;
  return (
    <ol className="space-y-2">
      <Step n={1} title="Dashboard shows normal supply" done={!!supplyNormal || since != null}>
        <Button size="sm" variant="outline" disabled={normal.isPending} onClick={() => normal.mutate()}>Reset to normal supply</Button>
      </Step>
      <Step n={2} title="Simulate voltage loss in Sector D – Riverside" done={since != null} active={since == null}>
        <Button size="sm" variant="destructive" disabled={!area || loss.isPending} onClick={() => loss.mutate()}>Simulate voltage loss</Button>
      </Step>
      <Step n={3} title="The system detects a potential interruption" done={!!inc} active={since != null && !inc}>
        {!inc && since != null && <p className="flex items-center gap-1.5 text-xs text-muted-foreground"><Loader2 className="h-3 w-3 animate-spin" /> Waiting for consecutive readings…</p>}
        {!inc && <Button size="sm" variant="outline" disabled={since == null || reading.isPending} onClick={() => reading.mutate()}>Take another reading now</Button>}
        {inc && <p className="text-xs">{inc.code}: {inc.affected_meters}/{inc.area_meter_count} meters without supply · <b>{inc.verification_status}</b></p>}
      </Step>
      <Step n={4} title="Additional readings persist; the operator verifies the outage" done={inc?.verification_status === "confirmed"} active={!!inc && inc.verification_status === "potential"}>
        <p className="text-xs text-muted-foreground">Customers are only alerted after verification.</p>
        <Button size="sm" disabled={!inc || inc.verification_status !== "potential" || confirm.isPending} onClick={() => confirm.mutate()}>Collect readings &amp; verify</Button>
      </Step>
      <Step n={5} title="Incident appears on the dashboard and a simulated WhatsApp alert is generated" done={!!alertJob} active={inc?.verification_status === "confirmed"}>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="outline" disabled={!inc} onClick={() => { navigate(`/incidents?id=${inc!.id}`); close(); }}><ShieldAlert /> Open incident</Button>
          <Button size="sm" variant="outline" onClick={() => { navigate("/"); close(); }}>View overview</Button>
        </div>
      </Step>
      <Step n={6} title="Restore power" done={!!inc?.power_restored_at} active={inc?.verification_status === "confirmed" && !inc.power_restored_at}>
        <Button size="sm" variant="success" disabled={!inc || restore.isPending} onClick={() => restore.mutate()}>Restore power</Button>
      </Step>
      <Step n={7} title="Incident closed internally, with no unnecessary customer message" done={inc?.resolution_status === "resolved"}>
        {inc?.resolution_status === "resolved" && <p className="text-xs text-muted-foreground">{inc.resolution_note} An optional restoration announcement remains available on the incident.</p>}
      </Step>
    </ol>
  );
}

function ScenarioC({ close }: { close: () => void }) {
  const navigate = useNavigate();
  const scheduled = useScheduled();
  const options = (scheduled.data ?? []).filter((o) => ["scheduled", "notification_queued"].includes(o.status));
  const [picked, setPicked] = useState<string>("");
  const event: ScheduledOutage | undefined = options.find((o) => String(o.id) === picked) ?? options[0];
  const [result, setResult] = useState<any>(null);
  const quick = useAction(async () => {
    const start = new Date(new Date(event!.start_at).getTime() + 86400000).toISOString();
    const end = new Date(new Date(event!.end_at).getTime() + 86400000).toISOString();
    const r = await api.patch<ScheduledOutage>(`/outages/scheduled/${event!.id}`, { start_at: start, end_at: end, notify_customers: true });
    setResult(r.meta?.changes);
    return r;
  }, { success: "Event moved by one day; pending notifications recalculated" });
  return (
    <ol className="space-y-2">
      <Step n={1} title="Choose an announced maintenance event" done={!!event}>
        <Select value={event ? String(event.id) : ""} onValueChange={setPicked}>
          <SelectTrigger><SelectValue placeholder="No upcoming events" /></SelectTrigger>
          <SelectContent>{options.map((o) => <SelectItem key={o.id} value={String(o.id)}>{o.code} · {o.title}</SelectItem>)}</SelectContent>
        </Select>
        {event && <p className="text-xs text-muted-foreground">Currently {formatDateTime(event.start_at)} · {event.notifications_pending} pending notification(s)</p>}
      </Step>
      <Step n={2} title="Change the maintenance time" done={!!result} active={!!event && !result}>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" disabled={!event} onClick={() => { navigate(`/scheduled?id=${event!.id}&reschedule=1`); close(); }}><CalendarClock /> Open reschedule form</Button>
          <Button size="sm" variant="outline" disabled={!event || quick.isPending} onClick={() => quick.mutate()}>Quick: move +1 day</Button>
        </div>
      </Step>
      <Step n={3} title="Pending notifications are updated or cancelled, and a rescheduling announcement is generated" done={!!result}>
        {result && (
          <ul className="space-y-0.5 text-xs">
            <li>{result.reminders_updated} reminder(s) re-timed · {result.reminders_cancelled} cancelled · {result.reminders_created} created</li>
            <li>{result.announcement_job_ids.length ? "Rescheduling notice sent in simulation" : "No customers had been notified yet, so no announcement was needed"}</li>
          </ul>
        )}
      </Step>
      <Step n={4} title="Notification history records the change" active={!!result}>
        <Button size="sm" variant="outline" onClick={() => { navigate("/notifications?tab=history"); close(); }}><History /> Open notification history</Button>
      </Step>
    </ol>
  );
}

export function DemoPanel() {
  const { demoOpen, setDemoOpen } = useApp();
  const [confirmReset, setConfirmReset] = useState(false);
  const reset = useAction(() => api.post("/demo/reset"), { success: "Demo data restored to its initial state" });
  const close = () => setDemoOpen(false);
  return (
    <Dialog open={demoOpen} onOpenChange={setDemoOpen}>
      <SheetContent className="gap-0 p-0 sm:max-w-lg">
        <div className="border-b p-5 pr-12">
          <DialogTitle className="flex items-center gap-2 text-lg font-semibold"><MonitorPlay className="h-5 w-5 text-amber-500" /> Guided demo</DialogTitle>
          <DialogDescription className="mt-1 text-sm text-muted-foreground">Every step performs a real action against the backend. Meters, customers and WhatsApp delivery are simulated.</DialogDescription>
        </div>
        <div className="space-y-5 p-5">
          <ClockControls />
          <Tabs defaultValue="a">
            <TabsList className="grid w-full grid-cols-3">
              <TabsTrigger value="a">A · Planned</TabsTrigger>
              <TabsTrigger value="b">B · Unexpected</TabsTrigger>
              <TabsTrigger value="c">C · Reschedule</TabsTrigger>
            </TabsList>
            <TabsContent value="a"><ScenarioA close={close} /></TabsContent>
            <TabsContent value="b"><ScenarioB close={close} /></TabsContent>
            <TabsContent value="c"><ScenarioC close={close} /></TabsContent>
          </Tabs>
          <div className="flex items-center justify-between rounded-lg border border-dashed p-3">
            <p className="text-xs text-muted-foreground">Start over with fresh demo data.</p>
            <Button size="sm" variant="ghost" className="text-destructive" disabled={reset.isPending} onClick={() => setConfirmReset(true)}>
              {reset.isPending ? <Loader2 className="animate-spin" /> : <RotateCcw />} Reset demo data
            </Button>
          </div>
        </div>
      </SheetContent>
      <ConfirmDialog
        open={confirmReset}
        onOpenChange={setConfirmReset}
        title="Reset all demo data?"
        description="This deletes every event, incident, notification and customer change made during the demo and reloads the original sample data. The demo clock returns to real time."
        confirmLabel="Reset demo data"
        destructive
        onConfirm={() => { reset.mutate(undefined, { onSuccess: () => toast.message("Tip: open the Overview to see the fresh state.") }); setConfirmReset(false); }}
      />
    </Dialog>
  );
}

