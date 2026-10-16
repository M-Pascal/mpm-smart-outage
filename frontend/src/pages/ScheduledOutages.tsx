import {
  Ban, CalendarClock, CalendarDays, ChevronLeft, ChevronRight, Clock, List, Megaphone, MoreHorizontal, Pencil, Plus, Search, Send, Users,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ChannelDialog } from "@/components/shared/ChannelDialog";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import {
  EmptyState, ErrorState, JobStatusBadge, KeyValue, OutageStatusBadge, PageHeader, PriorityBadge, TableSkeleton,
} from "@/components/shared";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogDescription, DialogTitle, SheetContent } from "@/components/ui/dialog";
import { Switch } from "@/components/ui/form-bits";
import { Input } from "@/components/ui/input";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger, Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/menus";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useNow } from "@/hooks/app-context";
import { useAction, useScheduled, useScheduledOne } from "@/hooks/queries";
import { api } from "@/lib/api";
import { OUTAGE_STATUS } from "@/lib/constants";
import { duration, formatDateTime, formatRange, formatTime, localDateKey, offsetLabel, relative } from "@/lib/format";
import type { OutageStatus, ScheduledOutage } from "@/lib/types";
import { cn } from "@/lib/utils";
import { OutageForm, type FormMode } from "./scheduled/OutageForm";

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function useOutageActions() {
  const [cancelTarget, setCancelTarget] = useState<ScheduledOutage | null>(null);
  const [notify, setNotify] = useState(true);
  const publish = useAction((o: ScheduledOutage) => api.post<ScheduledOutage>(`/outages/scheduled/${o.id}/publish`), {
    success: (o) => `${o.code} published. Notice sent in simulation, reminders queued.`,
  });
  const cancel = useAction(({ o, reason }: { o: ScheduledOutage; reason: string }) =>
    api.postWithMeta<ScheduledOutage>(`/outages/scheduled/${o.id}/cancel`, { reason, notify_customers: notify }), {
    success: (r: any) => `${r.data.code} cancelled · ${r.meta.changes.pending_cancelled} pending notification(s) cancelled${r.meta.changes.announcement_job_id ? " · cancellation notice sent" : ""}`,
  });
  const dialog = (
    <ConfirmDialog
      open={!!cancelTarget}
      onOpenChange={(v) => !v && setCancelTarget(null)}
      title={`Cancel ${cancelTarget?.code}?`}
      description={<>“{cancelTarget?.title}” will be cancelled and all pending reminders withdrawn. This cannot be undone.</>}
      confirmLabel="Cancel interruption"
      destructive
      input={{ label: "Reason (internal)", placeholder: "e.g. Contractor unavailable" }}
      onConfirm={(reason) => { cancel.mutate({ o: cancelTarget!, reason }); setCancelTarget(null); }}
    >
      {cancelTarget?.customers_notified && (
        <label className="flex items-center justify-between gap-3 rounded-lg bg-muted/60 p-3 text-sm">
          <span>Send a cancellation notice to the {cancelTarget.eligible_recipients} customers already informed</span>
          <Switch checked={notify} onCheckedChange={setNotify} />
        </label>
      )}
    </ConfirmDialog>
  );
  return { publish, askCancel: (o: ScheduledOutage) => { setNotify(true); setCancelTarget(o); }, dialog };
}

function OutageCalendar({ items, onSelect }: { items: ScheduledOutage[]; onSelect: (o: ScheduledOutage) => void }) {
  const now = useNow(60_000);
  const todayKey = localDateKey(new Date(now));
  const [month, setMonth] = useState(() => { const [y, m] = todayKey.split("-").map(Number); return { y, m }; });
  const days = useMemo(() => {
    const first = new Date(Date.UTC(month.y, month.m - 1, 1));
    const startDow = (first.getUTCDay() + 6) % 7;
    const start = new Date(first.getTime() - startDow * 86400000);
    return Array.from({ length: 42 }, (_, i) => new Date(start.getTime() + i * 86400000).toISOString().slice(0, 10));
  }, [month]);
  const byDay = useMemo(() => {
    const map: Record<string, ScheduledOutage[]> = {};
    for (const o of items) {
      let k = localDateKey(o.start_at);
      const endK = localDateKey(o.end_at);
      for (let guard = 0; guard < 8; guard++) {
        (map[k] ??= []).push(o);
        if (k >= endK) break;
        k = new Date(new Date(`${k}T00:00:00Z`).getTime() + 86400000).toISOString().slice(0, 10);
      }
    }
    return map;
  }, [items]);
  const label = new Date(Date.UTC(month.y, month.m - 1, 1)).toLocaleString("en-GB", { month: "long", year: "numeric", timeZone: "UTC" });
  const shift = (d: number) => setMonth(({ y, m }) => { const t = new Date(Date.UTC(y, m - 1 + d, 1)); return { y: t.getUTCFullYear(), m: t.getUTCMonth() + 1 }; });
  return (
    <Card>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b p-4">
        <div className="flex items-center gap-2">
          <Button variant="outline" size="icon" onClick={() => shift(-1)} aria-label="Previous month"><ChevronLeft /></Button>
          <Button variant="outline" size="icon" onClick={() => shift(1)} aria-label="Next month"><ChevronRight /></Button>
          <h3 className="ml-2 text-base font-semibold">{label}</h3>
          <Button variant="ghost" size="sm" onClick={() => { const [y, m] = todayKey.split("-").map(Number); setMonth({ y, m }); }}>Today</Button>
        </div>
        <div className="flex flex-wrap gap-3 text-xs">
          {(Object.keys(OUTAGE_STATUS) as OutageStatus[]).map((k) => (
            <span key={k} className="flex items-center gap-1.5 text-muted-foreground"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: OUTAGE_STATUS[k].dot }} />{OUTAGE_STATUS[k].label}</span>
          ))}
        </div>
      </div>
      <div className="overflow-x-auto scrollbar-thin">
        <div className="grid min-w-[720px] grid-cols-7">
          {WEEKDAYS.map((d) => <div key={d} className="border-b px-2 py-2 text-xs font-medium text-muted-foreground">{d}</div>)}
          {days.map((k) => {
            const inMonth = Number(k.slice(5, 7)) === month.m;
            const evts = byDay[k] ?? [];
            return (
              <div key={k} className={cn("min-h-[104px] border-b border-r p-1.5 [&:nth-child(7n)]:border-r-0", !inMonth && "bg-muted/40")}>
                <div className={cn("mb-1 flex h-6 w-6 items-center justify-center rounded-full text-xs", k === todayKey ? "bg-primary font-semibold text-primary-foreground" : inMonth ? "" : "text-muted-foreground")}>{Number(k.slice(8))}</div>
                <div className="space-y-1">
                  {evts.slice(0, 3).map((o) => (
                    <button key={o.id} onClick={() => onSelect(o)}
                            className={cn("block w-full truncate rounded px-1.5 py-1 text-left text-[11px] font-medium text-white shadow-sm transition hover:brightness-110", o.status === "cancelled" && "line-through opacity-70")}
                            style={{ background: OUTAGE_STATUS[o.status].dot }} title={`${o.title} · ${formatRange(o.start_at, o.end_at)}`}>
                      {formatTime(o.start_at)} {o.title}
                    </button>
                  ))}
                  {evts.length > 3 && <p className="px-1 text-[10px] text-muted-foreground">+{evts.length - 3} more</p>}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </Card>
  );
}

function OutageDetail({ id, onClose, onEdit }: { id: number | null; onClose: () => void; onEdit: (o: ScheduledOutage, mode: FormMode) => void }) {
  const q = useScheduledOne(id);
  const o = q.data;
  const now = useNow(5000);
  const { publish, askCancel, dialog } = useOutageActions();
  const [channel, setChannel] = useState(false);
  const editable = o && ["draft", "scheduled", "notification_queued"].includes(o.status);
  return (
    <Dialog open={id != null} onOpenChange={(v) => !v && onClose()}>
      <SheetContent className="sm:max-w-2xl">
        {!o ? <div className="p-6"><TableSkeleton rows={6} cols={2} /></div> : (
          <>
            <div className="border-b p-6 pr-12">
              <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground"><span className="font-mono">{o.code}</span><OutageStatusBadge status={o.status} /><PriorityBadge priority={o.priority} /></div>
              <DialogTitle className="mt-2 text-xl font-semibold">{o.title}</DialogTitle>
              <DialogDescription className="mt-1 text-sm text-muted-foreground">{o.reason_detail || o.reason_label} · {o.mini_grid_name}</DialogDescription>
              <div className="mt-4 flex flex-wrap gap-2">
                {o.status === "draft" && <Button size="sm" disabled={publish.isPending} onClick={() => publish.mutate(o)}><Send /> Publish & notify</Button>}
                {editable && <Button size="sm" variant="outline" onClick={() => onEdit(o, "edit")}><Pencil /> Edit</Button>}
                {editable && o.status !== "draft" && <Button size="sm" variant="outline" onClick={() => onEdit(o, "reschedule")}><CalendarClock /> Reschedule</Button>}
                {o.status === "in_progress" && <Button size="sm" variant="outline" onClick={() => onEdit(o, "edit")}><Clock /> Extend restoration time</Button>}
                {o.status !== "draft" && <Button size="sm" variant="outline" onClick={() => setChannel(true)}><Megaphone /> Channel post</Button>}
                {editable && <Button size="sm" variant="ghost" className="text-destructive" onClick={() => askCancel(o)}><Ban /> Cancel event</Button>}
              </div>
            </div>
            <div className="space-y-6 p-6">
              <dl className="grid grid-cols-2 gap-4 sm:grid-cols-3">
                <KeyValue label="Starts">{formatDateTime(o.start_at)}</KeyValue>
                <KeyValue label="Expected restoration">{formatDateTime(o.end_at)}</KeyValue>
                <KeyValue label="Duration">{duration(o.start_at, o.end_at)}</KeyValue>
                <KeyValue label="Service areas">{o.service_areas.map((a) => a.name).join(", ")}</KeyValue>
                <KeyValue label="Affected customers">{o.affected_customers} <span className="font-normal text-muted-foreground">({o.eligible_recipients} reachable on WhatsApp)</span></KeyValue>
                <KeyValue label="Reminders">{o.reminder_offsets.length ? o.reminder_offsets.map((m) => offsetLabel(m)).join(", ") + " before" : "None"}</KeyValue>
              </dl>
              {o.description && <p className="rounded-lg bg-muted/50 p-3 text-sm">{o.description}</p>}
              {o.status === "cancelled" && <p className="rounded-lg border border-dashed p-3 text-sm text-muted-foreground">Cancelled {o.cancelled_at && formatDateTime(o.cancelled_at)}{o.cancel_reason && `: ${o.cancel_reason}`}</p>}
              <div>
                <h4 className="mb-3 text-sm font-semibold">Customer notifications</h4>
                {!o.notifications?.length ? (
                  <EmptyState icon={Send} title="No notifications yet" description={o.status === "draft" ? "Publish the event to send the notice and queue reminders." : "No reminders were configured."} />
                ) : (
                  <ol className="relative space-y-3 border-l pl-5">
                    {o.notifications.map((j) => (
                      <li key={j.id} className="relative">
                        <span className={cn("absolute -left-[26px] top-1 h-3 w-3 rounded-full border-2 border-card", j.status === "sent" ? "bg-success" : j.status === "scheduled" ? "bg-primary" : j.status === "failed" ? "bg-danger" : "bg-slate-400")} />
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <p className="text-sm font-medium">{j.kind_label}{j.offset_minutes ? ` · ${offsetLabel(j.offset_minutes)} before` : ""}</p>
                          <JobStatusBadge status={j.status} failed={j.failed_count} simulated={j.simulated} />
                        </div>
                        <p className="text-xs text-muted-foreground">
                          {j.status === "scheduled" ? `Sends ${formatDateTime(j.send_at)} (${relative(j.send_at, now)})` : `${formatDateTime(j.processed_at ?? j.send_at)}`}
                          {" · "}{j.status === "sent" || j.status === "failed" ? `${j.sent_count}/${j.recipients_count} sent${j.simulated ? " in simulation" : ""} · ${j.delivered_count} delivered` : `${j.recipients_count} recipients`}
                        </p>
                        {j.note && <p className="text-xs italic text-muted-foreground">{j.note}</p>}
                        <Link to={`/notifications?job=${j.id}`} className="text-xs font-medium text-primary hover:underline">View messages</Link>
                      </li>
                    ))}
                  </ol>
                )}
              </div>
            </div>
            {dialog}
            <ChannelDialog open={channel} onOpenChange={setChannel} source={channel ? { scheduled_outage_id: o.id } : null} />
          </>
        )}
      </SheetContent>
    </Dialog>
  );
}

export default function ScheduledOutages() {
  const [params, setParams] = useSearchParams();
  const list = useScheduled();
  const now = useNow(10_000);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState<string>("upcoming");
  const [form, setForm] = useState<{ mode: FormMode; outage?: ScheduledOutage | null; preset?: "demo" | null } | null>(null);
  const { publish, askCancel, dialog } = useOutageActions();
  const [channelFor, setChannelFor] = useState<number | null>(null);
  const selected = params.get("id") ? Number(params.get("id")) : null;

  // Deep links: ?new=1 | ?new=demo | ?id=5 | ?id=5&reschedule=1
  useEffect(() => {
    const n = params.get("new");
    if (n) {
      setForm({ mode: "create", preset: n === "demo" ? "demo" : null });
      params.delete("new");
      setParams(params, { replace: true });
    }
    if (params.get("reschedule") && selected && list.data) {
      const o = list.data.find((x) => x.id === selected);
      if (o) {
        setForm({ mode: "reschedule", outage: o });
        params.delete("reschedule");
        params.delete("id");
        setParams(params, { replace: true });
      }
    }
  }, [params, setParams, selected, list.data]);

  const items = useMemo(() => {
    const ql = q.toLowerCase();
    return (list.data ?? []).filter((o) => {
      if (status === "upcoming" && !["draft", "scheduled", "notification_queued", "in_progress"].includes(o.status)) return false;
      if (status !== "upcoming" && status !== "all" && o.status !== status) return false;
      return !ql || o.title.toLowerCase().includes(ql) || o.code.toLowerCase().includes(ql) || o.service_areas.some((a) => a.name.toLowerCase().includes(ql));
    }).sort((a, b) => (status === "upcoming" ? a.start_at.localeCompare(b.start_at) : b.start_at.localeCompare(a.start_at)));
  }, [list.data, q, status]);

  const open = (o: ScheduledOutage) => setParams({ id: String(o.id) });

  return (
    <div className="animate-fade-in">
      <PageHeader
        title="Scheduled outages"
        description="Plan interruptions and inform affected customers before they happen."
        actions={<Button onClick={() => setForm({ mode: "create" })}><Plus /> Schedule interruption</Button>}
      />
      <Tabs defaultValue="list">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <TabsList>
            <TabsTrigger value="list"><List /> List</TabsTrigger>
            <TabsTrigger value="calendar"><CalendarDays /> Calendar</TabsTrigger>
          </TabsList>
          <div className="flex flex-wrap gap-2">
            <div className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search events or areas" className="w-56 pl-8" aria-label="Search scheduled outages" />
            </div>
            <Select value={status} onValueChange={setStatus}>
              <SelectTrigger className="w-48" aria-label="Filter by status"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="upcoming">Upcoming & active</SelectItem>
                <SelectItem value="all">All statuses</SelectItem>
                {(Object.keys(OUTAGE_STATUS) as OutageStatus[]).map((k) => <SelectItem key={k} value={k}>{OUTAGE_STATUS[k].label}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
        </div>
        <TabsContent value="list">
          <Card>
            <CardContent className="p-0">
              {list.error ? <div className="p-4"><ErrorState message={(list.error as Error).message} onRetry={() => list.refetch()} /></div> : list.isLoading ? <div className="p-4"><TableSkeleton /></div> : items.length === 0 ? (
                <div className="p-6"><EmptyState icon={CalendarClock} title="No interruptions match" description="Change the filters or schedule a new planned interruption." action={<Button size="sm" onClick={() => setForm({ mode: "create" })}><Plus /> Schedule interruption</Button>} /></div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Event</TableHead>
                      <TableHead>Service areas</TableHead>
                      <TableHead>Schedule</TableHead>
                      <TableHead className="text-right">Customers</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Notifications</TableHead>
                      <TableHead className="w-10"><span className="sr-only">Actions</span></TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {items.map((o) => (
                      <TableRow key={o.id} className="cursor-pointer" onClick={() => open(o)}>
                        <TableCell>
                          <p className="font-medium">{o.title}</p>
                          <p className="text-xs text-muted-foreground"><span className="font-mono">{o.code}</span> · {o.reason_label}</p>
                        </TableCell>
                        <TableCell className="max-w-[220px] text-sm">{o.service_areas.map((a) => a.name).join(", ")}</TableCell>
                        <TableCell className="whitespace-nowrap text-sm">
                          {formatRange(o.start_at, o.end_at)}
                          <p className="text-xs text-muted-foreground">{o.status === "in_progress" ? `ends ${relative(o.end_at, now)}` : relative(o.start_at, now)}</p>
                        </TableCell>
                        <TableCell className="text-right tabular"><span className="inline-flex items-center gap-1"><Users className="h-3.5 w-3.5 text-muted-foreground" />{o.affected_customers}</span></TableCell>
                        <TableCell><OutageStatusBadge status={o.status} /></TableCell>
                        <TableCell className="text-xs">
                          {o.status === "draft" ? <span className="text-muted-foreground">Not published</span> : (
                            <>
                              <p className="font-medium">{o.notifications_sent} sent · {o.notifications_pending} pending</p>
                              {o.next_notification_at && <p className="text-muted-foreground">next {relative(o.next_notification_at, now)}</p>}
                            </>
                          )}
                        </TableCell>
                        <TableCell onClick={(e) => e.stopPropagation()}>
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild><Button variant="ghost" size="icon" aria-label={`Actions for ${o.code}`}><MoreHorizontal /></Button></DropdownMenuTrigger>
                            <DropdownMenuContent align="end">
                              <DropdownMenuItem onSelect={() => open(o)}>View details</DropdownMenuItem>
                              {o.status === "draft" && <DropdownMenuItem onSelect={() => publish.mutate(o)}><Send /> Publish & notify</DropdownMenuItem>}
                              {["draft", "scheduled", "notification_queued"].includes(o.status) && <DropdownMenuItem onSelect={() => setForm({ mode: "edit", outage: o })}><Pencil /> Edit</DropdownMenuItem>}
                              {["scheduled", "notification_queued"].includes(o.status) && <DropdownMenuItem onSelect={() => setForm({ mode: "reschedule", outage: o })}><CalendarClock /> Reschedule</DropdownMenuItem>}
                              {o.status !== "draft" && <DropdownMenuItem onSelect={() => setChannelFor(o.id)}><Megaphone /> Channel announcement</DropdownMenuItem>}
                              {["draft", "scheduled", "notification_queued"].includes(o.status) && (
                                <>
                                  <DropdownMenuSeparator />
                                  <DropdownMenuItem destructive onSelect={() => askCancel(o)}><Ban /> Cancel event</DropdownMenuItem>
                                </>
                              )}
                            </DropdownMenuContent>
                          </DropdownMenu>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>
        <TabsContent value="calendar">
          {list.isLoading ? <TableSkeleton rows={6} cols={7} /> : <OutageCalendar items={list.data ?? []} onSelect={open} />}
        </TabsContent>
      </Tabs>

      <OutageDetail id={selected} onClose={() => { params.delete("id"); setParams(params); }} onEdit={(o, mode) => setForm({ mode, outage: o })} />
      <OutageForm
        open={!!form}
        onOpenChange={(v) => !v && setForm(null)}
        mode={form?.mode ?? "create"}
        outage={form?.outage}
        preset={form?.preset}
        onSaved={(o) => setParams({ id: String(o.id) })}
      />
      {dialog}
      <ChannelDialog open={channelFor != null} onOpenChange={(v) => !v && setChannelFor(null)} source={channelFor != null ? { scheduled_outage_id: channelFor } : null} />
    </div>
  );
}
