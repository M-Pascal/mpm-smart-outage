import {
  BellRing, CheckCircle2, CircleCheckBig, Eye, Hand, Lightbulb, Megaphone, Search, ShieldAlert, ShieldCheck, ShieldX, Timer, Zap,
} from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ChannelDialog } from "@/components/shared/ChannelDialog";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import {
  EmptyState, ErrorState, JobStatusBadge, KeyValue, MeterStatusBadge, PageHeader, ResolutionBadge, SeverityBadge, StatCard, TableSkeleton, VerificationBadge,
} from "@/components/shared";
import { SimulationControls } from "@/components/shared/SimulationControls";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, SheetContent } from "@/components/ui/dialog";
import { Field, Switch } from "@/components/ui/form-bits";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useNow } from "@/hooks/app-context";
import { useAction, useIncident, useIncidents } from "@/hooks/queries";
import { api } from "@/lib/api";
import { duration, formatDateTime, formatTimeSec, relative, secondsLabel } from "@/lib/format";
import type { Incident } from "@/lib/types";
import { cn } from "@/lib/utils";

const EVENT_STYLE: Record<string, string> = {
  detected: "bg-warning", confirmed: "bg-danger", escalated: "bg-danger", notification: "bg-primary", acknowledged: "bg-slate-400",
  investigating: "bg-amber-500", power_restored: "bg-success", resolved: "bg-success", rejected: "bg-slate-500", evidence: "bg-slate-300", note: "bg-slate-300", supply_lost: "bg-danger",
};

function IncidentDetail({ id, onClose }: { id: number | null; onClose: () => void }) {
  const q = useIncident(id);
  const inc = q.data;
  const now = useNow(1000);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [notify, setNotify] = useState(true);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [resolveOpen, setResolveOpen] = useState(false);
  const [restoreOpen, setRestoreOpen] = useState(false);
  const [updateOpen, setUpdateOpen] = useState(false);
  const [eta, setEta] = useState("");
  const [channel, setChannel] = useState(false);
  const act = (path: string, msg: string) => useAction((body: object = {}) => api.post<Incident>(`/incidents/${id}/${path}`, body), { success: msg });
  const ack = act("acknowledge", "Incident acknowledged");
  const investigate = act("investigate", "Investigation started");
  const confirm = act("confirm", "Outage confirmed");
  const reject = act("reject", "Incident rejected as a false alarm");
  const resolve = act("resolve", "Incident resolved");
  const restoration = act("announce-restoration", "Restoration announcement sent in simulation");
  const update = act("send-update", "Outage update sent in simulation");
  const open = inc && inc.resolution_status !== "resolved";

  return (
    <Dialog open={id != null} onOpenChange={(v) => !v && onClose()}>
      <SheetContent className="sm:max-w-2xl">
        {!inc ? <div className="p-6"><TableSkeleton rows={8} cols={2} /></div> : (
          <>
            <div className={cn("border-b p-6 pr-12", open && inc.verification_status === "confirmed" && "bg-danger-soft/50")}>
              <div className="flex flex-wrap items-center gap-2"><span className="font-mono text-xs text-muted-foreground">{inc.code}</span><SeverityBadge severity={inc.severity} /><VerificationBadge status={inc.verification_status} /><ResolutionBadge status={inc.resolution_status} /></div>
              <DialogTitle className="mt-2 text-xl font-semibold">Unexpected outage · {inc.service_area_name}</DialogTitle>
              <DialogDescription className="mt-1 text-sm text-muted-foreground">
                {inc.mini_grid_name} · {inc.evidence_type === "communication_loss" ? "Meters stopped reporting: outage or communication failure?" : inc.scope === "area" ? "Service-area outage" : "Single-meter event (not community-wide)"} · detected {relative(inc.detected_at, now)}
              </DialogDescription>
              <div className="mt-4 flex flex-wrap gap-2">
                {open && !inc.acknowledged_at && <Button size="sm" variant="outline" disabled={ack.isPending} onClick={() => ack.mutate({})}><Hand /> Acknowledge</Button>}
                {open && inc.resolution_status === "open" && <Button size="sm" variant="outline" disabled={investigate.isPending} onClick={() => investigate.mutate({})}><Eye /> Investigate</Button>}
                {open && inc.verification_status === "potential" && <Button size="sm" variant="destructive" onClick={() => { setNotify(true); setConfirmOpen(true); }}><ShieldCheck /> Confirm outage</Button>}
                {open && inc.verification_status === "potential" && <Button size="sm" variant="outline" onClick={() => setRejectOpen(true)}><ShieldX /> Reject</Button>}
                {open && inc.verification_status === "confirmed" && !inc.power_restored_at && <Button size="sm" variant="outline" onClick={() => setUpdateOpen(true)}><BellRing /> Send update</Button>}
                {open && <Button size="sm" variant="success" onClick={() => setResolveOpen(true)}><CircleCheckBig /> Resolve</Button>}
                {inc.verification_status === "confirmed" && inc.power_restored_at && <Button size="sm" variant={inc.restoration_suggested ? "default" : "outline"} onClick={() => setRestoreOpen(true)}><Zap /> Restoration announcement</Button>}
                {inc.verification_status === "confirmed" && <Button size="sm" variant="ghost" onClick={() => setChannel(true)}><Megaphone /> Channel post</Button>}
              </div>
            </div>
            <div className="space-y-6 p-6">
              {inc.evidence_type === "communication_loss" && inc.resolution_status !== "resolved" && (
                <div className="flex gap-3 rounded-lg border border-warning/50 bg-warning-soft p-3 text-sm">
                  <Lightbulb className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
                  <p>These meters went silent together. That can mean a power outage <b>or</b> a network problem, so PowerChat never confirms it automatically. Check on site or call a customer before confirming and alerting customers.</p>
                </div>
              )}
              {inc.verification_status === "potential" && inc.evidence_type === "voltage" && inc.scope === "area" && inc.resolution_status !== "resolved" && (
                <div className="flex gap-3 rounded-lg border border-primary/30 bg-brand-soft p-3 text-sm">
                  <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                  <p>Repeated near-zero voltage readings indicate a power interruption. Customers are alerted only after this incident is <b>verified</b>: confirm it once you are satisfied.</p>
                </div>
              )}
              {inc.restoration_suggested && (
                <div className="flex gap-3 rounded-lg border border-primary/30 bg-brand-soft p-3 text-sm">
                  <Lightbulb className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                  <p>Power is back. This outage affected about <b>{inc.estimated_customers} customers</b>, so a restoration announcement may be helpful. It is <b>not sent automatically</b>.</p>
                </div>
              )}
              <dl className="grid grid-cols-2 gap-4 sm:grid-cols-3">
                <KeyValue label="Detected">{formatDateTime(inc.detected_at)}</KeyValue>
                <KeyValue label="Affected meters">{inc.affected_meters} now · peak {inc.peak_affected_meters}/{inc.area_meter_count}</KeyValue>
                <KeyValue label="Estimated customers">~{inc.estimated_customers}</KeyValue>
                <KeyValue label="Detection time">{inc.first_evidence_at ? secondsLabel((new Date(inc.detected_at).getTime() - new Date(inc.first_evidence_at).getTime()) / 1000) : "—"}</KeyValue>
                <KeyValue label="Verification">{inc.confirmed_at ? `${inc.confirmation_method === "auto" ? "Automatic" : "Manual"} · ${formatTimeSec(inc.confirmed_at)}` : inc.verification_status}</KeyValue>
                <KeyValue label="Acknowledged">{inc.acknowledged_at ? `${inc.acknowledged_by} · ${formatTimeSec(inc.acknowledged_at)}` : "Not yet"}</KeyValue>
                <KeyValue label="Outage duration">{duration(inc.first_evidence_at ?? inc.detected_at, inc.power_restored_at, now)}{!inc.power_restored_at && " (ongoing)"}</KeyValue>
                <KeyValue label="Power restored">{inc.power_restored_at ? formatDateTime(inc.power_restored_at) : "No"}</KeyValue>
                <KeyValue label="Resolution">{inc.resolved_at ? formatDateTime(inc.resolved_at) : inc.resolution_status}</KeyValue>
              </dl>
              {inc.resolution_note && <p className="rounded-lg bg-muted/50 p-3 text-sm">{inc.resolution_note}</p>}

              <div>
                <h4 className="mb-3 text-sm font-semibold">Incident timeline</h4>
                <ol className="relative space-y-3 border-l pl-5">
                  {inc.events?.map((e) => (
                    <li key={e.id} className="relative">
                      <span className={cn("absolute -left-[26px] top-1 h-3 w-3 rounded-full border-2 border-card", EVENT_STYLE[e.type] ?? "bg-slate-300")} />
                      <p className="text-sm">{e.message}</p>
                      <p className="text-xs text-muted-foreground">{formatDateTime(e.ts)} · {e.actor}</p>
                    </li>
                  ))}
                </ol>
              </div>

              <div>
                <h4 className="mb-3 text-sm font-semibold">Notification history</h4>
                {!inc.notifications?.length ? (
                  <p className="text-sm text-muted-foreground">{inc.scope === "meter" ? "No customer broadcast for single-meter events." : "No customer messages sent for this incident."}</p>
                ) : (
                  <div className="space-y-2">
                    {inc.notifications.map((j) => (
                      <Link key={j.id} to={`/notifications?job=${j.id}`} className="flex items-center justify-between gap-3 rounded-lg border p-3 text-sm hover:bg-muted/40">
                        <span><span className="font-medium">{j.kind_label}</span><span className="block text-xs text-muted-foreground">{formatDateTime(j.processed_at ?? j.send_at)} · {j.sent_count}/{j.recipients_count} delivered in simulation</span></span>
                        <JobStatusBadge status={j.status} failed={j.failed_count} simulated={j.simulated} />
                      </Link>
                    ))}
                  </div>
                )}
              </div>

              {!!inc.affected_meter_list?.length && (
                <div>
                  <h4 className="mb-3 text-sm font-semibold">Affected meters</h4>
                  <div className="grid gap-2 sm:grid-cols-2">
                    {inc.affected_meter_list.map((m) => (
                      <Link key={m.id} to={`/monitoring?meter=${m.id}`} className="flex items-center justify-between rounded-lg border p-2.5 text-sm hover:bg-muted/40">
                        <span><span className="font-mono text-xs">{m.serial}</span><span className="block text-xs text-muted-foreground">{m.customer_name}</span></span>
                        <MeterStatusBadge status={m.status} />
                      </Link>
                    ))}
                  </div>
                </div>
              )}
            </div>

            <ConfirmDialog open={confirmOpen} onOpenChange={setConfirmOpen} title={`Confirm ${inc.code} as an outage?`}
              description="Confirming marks this as a verified unexpected interruption."
              confirmLabel="Confirm outage" destructive onConfirm={() => { confirm.mutate({ notify_customers: notify }); setConfirmOpen(false); }}>
              <label className="flex items-center justify-between gap-3 rounded-lg bg-muted/60 p-3 text-sm">
                <span>Send the “Unexpected outage” WhatsApp alert to customers in {inc.service_area_name} (simulated)</span>
                <Switch checked={notify} onCheckedChange={setNotify} />
              </label>
            </ConfirmDialog>
            <ConfirmDialog open={rejectOpen} onOpenChange={setRejectOpen} title={`Reject ${inc.code}?`} description="Use this for false alarms, e.g. a field test or a known customer-side fault. No customer will be notified."
              confirmLabel="Reject incident" destructive input={{ label: "Reason", placeholder: "e.g. Meter maintenance at customer premises", required: true }}
              onConfirm={(reason) => { reject.mutate({ reason }); setRejectOpen(false); }} />
            <ConfirmDialog open={resolveOpen} onOpenChange={setResolveOpen} title={`Resolve ${inc.code}?`} description="The incident will be closed. No customer message is sent automatically."
              confirmLabel="Resolve" input={{ label: "Resolution note", placeholder: "e.g. Blown fuse replaced at distribution box" }}
              onConfirm={(note) => { resolve.mutate({ note }); setResolveOpen(false); }} />
            <ConfirmDialog open={restoreOpen} onOpenChange={setRestoreOpen} title="Send a restoration announcement?"
              description={<>A “Power restored” WhatsApp message will be sent (simulated) to opted-in customers in {inc.service_area_name}. Only send it when it is genuinely useful, e.g. after a widespread outage.</>}
              confirmLabel="Send announcement" onConfirm={() => { restoration.mutate({}); setRestoreOpen(false); }} />
            <Dialog open={updateOpen} onOpenChange={setUpdateOpen}>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Extended outage update</DialogTitle>
                  <DialogDescription>Let customers know the outage is taking longer than expected. Only share a reliable estimate.</DialogDescription>
                </DialogHeader>
                <Field label="Estimated restoration" htmlFor="eta" error={update.fieldErrors.eta} hint="e.g. “around 6:00 PM today”">
                  <Input id="eta" value={eta} onChange={(e) => setEta(e.target.value)} />
                </Field>
                <DialogFooter>
                  <Button variant="outline" onClick={() => setUpdateOpen(false)}>Cancel</Button>
                  <Button disabled={!eta.trim() || update.isPending} onClick={() => update.mutate({ eta }, { onSuccess: () => { setUpdateOpen(false); setEta(""); } })}>Send update</Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
            <ChannelDialog open={channel} onOpenChange={setChannel} source={channel ? { incident_id: inc.id } : null} />
          </>
        )}
      </SheetContent>
    </Dialog>
  );
}

export default function Incidents() {
  const [params, setParams] = useSearchParams();
  const [status, setStatus] = useState("all");
  const [severity, setSeverity] = useState("all");
  const [q, setQ] = useState("");
  const all = useIncidents("all");
  const now = useNow(1000);
  const selected = params.get("id") ? Number(params.get("id")) : null;
  const data = all.data ?? [];
  const items = useMemo(() => data.filter((i) =>
    (status === "all" || (status === "active" ? i.resolution_status !== "resolved" : i.resolution_status === "resolved"))
    && (severity === "all" || i.severity === severity)
    && (!q || i.code.toLowerCase().includes(q.toLowerCase()) || i.service_area_name.toLowerCase().includes(q.toLowerCase()))), [data, status, severity, q]);
  const active = data.filter((i) => i.resolution_status !== "resolved");

  return (
    <div className="animate-fade-in">
      <PageHeader title="Incident management" description="Unexpected outages detected from smart-meter readings. Verify, respond and close them." />
      <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard label="Open incidents" value={active.length} icon={ShieldAlert} tone="danger" highlight={active.length > 0} loading={all.isLoading} />
        <StatCard label="Awaiting verification" value={active.filter((i) => i.verification_status === "potential").length} icon={Timer} tone="warning" loading={all.isLoading} />
        <StatCard label="Unacknowledged" value={active.filter((i) => !i.acknowledged_at).length} icon={Hand} tone="neutral" loading={all.isLoading} />
        <StatCard label="Resolved (all time)" value={data.filter((i) => i.resolution_status === "resolved").length} icon={CheckCircle2} tone="success" loading={all.isLoading} />
      </div>
      <div className="grid gap-4 xl:grid-cols-[1fr_380px]">
        <Card>
          <div className="flex flex-wrap items-center gap-2 border-b p-4">
            <div className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search INC-… or area" className="w-52 pl-8" aria-label="Search incidents" />
            </div>
            <Select value={status} onValueChange={setStatus}>
              <SelectTrigger className="w-36" aria-label="Status"><SelectValue /></SelectTrigger>
              <SelectContent><SelectItem value="all">All</SelectItem><SelectItem value="active">Active</SelectItem><SelectItem value="resolved">Resolved</SelectItem></SelectContent>
            </Select>
            <Select value={severity} onValueChange={setSeverity}>
              <SelectTrigger className="w-36" aria-label="Severity"><SelectValue /></SelectTrigger>
              <SelectContent><SelectItem value="all">Any severity</SelectItem>{["critical", "high", "medium", "low"].map((s) => <SelectItem key={s} value={s} className="capitalize">{s[0].toUpperCase() + s.slice(1)}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <CardContent className="p-0">
            {all.error ? <div className="p-4"><ErrorState message={(all.error as Error).message} /></div> : all.isLoading ? <div className="p-4"><TableSkeleton /></div> : items.length === 0 ? (
              <div className="p-6"><EmptyState icon={ShieldCheck} title="No incidents match" description="Use the simulation panel to trigger a voltage loss and watch detection work." /></div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Incident</TableHead>
                    <TableHead>Detected</TableHead>
                    <TableHead className="text-right">Meters</TableHead>
                    <TableHead className="text-right">Est. customers</TableHead>
                    <TableHead>Severity</TableHead>
                    <TableHead>Verification</TableHead>
                    <TableHead>Ack</TableHead>
                    <TableHead>Resolution</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {items.map((i) => (
                    <TableRow key={i.id} className={cn("cursor-pointer", i.resolution_status !== "resolved" && "bg-danger-soft/30")} onClick={() => setParams({ id: String(i.id) })}>
                      <TableCell><p className="font-medium">{i.code}</p><p className="text-xs text-muted-foreground">{i.service_area_name}{i.scope === "meter" && " · single meter"}{i.evidence_type === "communication_loss" && " · comms loss"}</p></TableCell>
                      <TableCell className="whitespace-nowrap text-sm">{formatDateTime(i.detected_at)}<p className="text-xs text-muted-foreground">{i.power_restored_at ? `lasted ${duration(i.first_evidence_at ?? i.detected_at, i.power_restored_at)}` : `ongoing ${duration(i.detected_at, null, now)}`}</p></TableCell>
                      <TableCell className="text-right tabular">{i.resolution_status === "resolved" ? i.peak_affected_meters : i.affected_meters}/{i.area_meter_count}</TableCell>
                      <TableCell className="text-right tabular">{i.estimated_customers}</TableCell>
                      <TableCell><SeverityBadge severity={i.severity} /></TableCell>
                      <TableCell><VerificationBadge status={i.verification_status} /></TableCell>
                      <TableCell>{i.acknowledged_at ? <CheckCircle2 className="h-4 w-4 text-success" aria-label="Acknowledged" /> : <Badge tone="warning">No</Badge>}</TableCell>
                      <TableCell><ResolutionBadge status={i.resolution_status} /></TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
        <div className="space-y-4">
          <SimulationControls compact />
          <Card className="p-4 text-sm">
            <p className="mb-2 font-medium">How detection works</p>
            <ul className="list-disc space-y-1 pl-4 text-muted-foreground">
              <li>Near-zero voltage on consecutive readings marks a meter <i>without supply</i>.</li>
              <li>Several meters in one area create a <i>potential</i> outage, auto-confirmed after a verification period.</li>
              <li>A single meter never triggers a community-wide alert.</li>
              <li>Missing data = communication problem, not an outage.</li>
              <li>When power returns the incident closes internally. A restoration message is optional.</li>
            </ul>
          </Card>
        </div>
      </div>
      <IncidentDetail id={selected} onClose={() => setParams({})} />
    </div>
  );
}
