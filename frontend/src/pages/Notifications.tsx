import {
  Ban, CalendarClock, Check, Clock, Copy, FlaskConical, History, Inbox, ListChecks, Loader2, Megaphone, PenSquare, RefreshCw, Search, Send, XCircle,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { copyText } from "@/components/shared/ChannelDialog";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { EmptyState, JobStatusBadge, KeyValue, PageHeader, TableSkeleton } from "@/components/shared";
import { WhatsAppPreview, WhatsAppText } from "@/components/shared/WhatsAppPreview";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, SheetContent } from "@/components/ui/dialog";
import { Checkbox, Field, Label } from "@/components/ui/form-bits";
import { Input, Textarea } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/menus";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useNow } from "@/hooks/app-context";
import { useAction, useAreas, useIncidents, useJob, useJobs, useMessages, useScheduled, useTemplates } from "@/hooks/queries";
import { api, errorMessage } from "@/lib/api";
import { JOB_STATUS } from "@/lib/constants";
import { formatDateTime, localInputToIso, relative } from "@/lib/format";
import type { Job, JobStatus, PreviewResult } from "@/lib/types";
import { cn } from "@/lib/utils";
import { TemplateEditor } from "./notifications/TemplateEditor";

const AUTO = new Set(["organization", "area", "customer_name"]);
const FROM_OUTAGE = new Set(["title", "reason", "date", "start_time", "end_time", "end_date", "time_until"]);
const LABELS: Record<string, string> = {
  message: "Announcement text", eta: "Estimated restoration", title: "Event title", reason: "Reason", date: "Date", start_time: "Start time",
  end_time: "End time", end_date: "End date", time_until: "Time until start", old_date: "Previous date", old_start_time: "Previous start time", old_end_time: "Previous end time",
};

function useAreaNames() {
  const areas = useAreas();
  return (ids: number[]) => ids.map((id) => areas.data?.find((a) => a.id === id)?.name ?? `#${id}`).join(", ");
}

/* ------------------------------------------------------------------ compose */
function Compose({ onDone }: { onDone: () => void }) {
  const templates = useTemplates();
  const areas = useAreas();
  const scheduled = useScheduled();
  const incidents = useIncidents("all");
  const [templateKey, setTemplateKey] = useState("general_announcement");
  const [areaIds, setAreaIds] = useState<number[]>([]);
  const [link, setLink] = useState("none");
  const [vars, setVars] = useState<Record<string, string>>({});
  const [mode, setMode] = useState<"send_now" | "schedule" | "draft">("send_now");
  const [sendAt, setSendAt] = useState("");
  const [preview, setPreview] = useState<PreviewResult | null>(null);
  const [previewErr, setPreviewErr] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [confirm, setConfirm] = useState(false);
  const tpl = templates.data?.data.find((t) => t.key === templateKey);
  const [linkType, linkId] = link === "none" ? [null, null] : link.split(":");
  const needed = useMemo(() => Array.from(new Set((tpl?.body.match(/\{([a-z_]+)\}/g) ?? []).map((m) => m.slice(1, -1))))
    .filter((p) => !AUTO.has(p) && !(linkType === "o" && FROM_OUTAGE.has(p))), [tpl, linkType]);

  useEffect(() => {
    if (linkType === "o") {
      const o = scheduled.data?.find((x) => String(x.id) === linkId);
      if (o) setAreaIds(o.service_areas.map((a) => a.id));
    } else if (linkType === "i") {
      const i = incidents.data?.find((x) => String(x.id) === linkId);
      if (i) setAreaIds([i.service_area_id]);
    }
  }, [link]); // eslint-disable-line react-hooks/exhaustive-deps

  const body = {
    template_key: templateKey, area_ids: areaIds, context: Object.fromEntries(needed.map((k) => [k, vars[k] ?? ""])),
    scheduled_outage_id: linkType === "o" ? Number(linkId) : undefined, incident_id: linkType === "i" ? Number(linkId) : undefined,
  };
  const key = JSON.stringify(body);
  useEffect(() => {
    if (!areaIds.length) { setPreview(null); return; }
    const id = setTimeout(() => {
      api.post<PreviewResult>("/notifications/preview", body).then((p) => { setPreview(p); setPreviewErr(""); }).catch((e) => setPreviewErr(errorMessage(e)));
    }, 300);
    return () => clearTimeout(id);
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps

  const submit = useAction(() => api.post<Job>("/notifications", { ...body, mode, send_at: mode === "schedule" ? localInputToIso(sendAt) : undefined }), {
    success: (j) => (j.status === "draft" ? `${j.code} saved as draft` : j.status === "scheduled" ? `${j.code} scheduled for ${formatDateTime(j.send_at)}` : `${j.code} sent in simulation to ${j.sent_count} customers`),
    onSuccess: () => { setVars({}); onDone(); },
  });
  useEffect(() => setErrors((e) => ({ ...e, ...submit.fieldErrors })), [submit.fieldErrors]);

  const validate = () => {
    const e: Record<string, string> = {};
    if (!areaIds.length) e.area_ids = "Select at least one service area.";
    for (const k of needed) if (!vars[k]?.trim()) e[k] = "Required for this template.";
    if (mode === "schedule" && !sendAt) e.send_at = "Choose when to send.";
    setErrors(e);
    return !Object.keys(e).length;
  };

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_400px]">
      <Card>
        <CardHeader><CardTitle>Compose notification</CardTitle><CardDescription>Messages go only to opted-in, active customers in the selected areas. Delivery is simulated.</CardDescription></CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Message template" htmlFor="n-tpl">
              <Select value={templateKey} onValueChange={setTemplateKey}>
                <SelectTrigger id="n-tpl"><SelectValue /></SelectTrigger>
                <SelectContent>{templates.data?.data.map((t) => <SelectItem key={t.key} value={t.key}>{t.name}</SelectItem>)}</SelectContent>
              </Select>
            </Field>
            <Field label="Related event (optional)" htmlFor="n-link" hint="Fills in dates, times and areas automatically.">
              <Select value={link} onValueChange={setLink}>
                <SelectTrigger id="n-link"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">None</SelectItem>
                  {scheduled.data?.filter((o) => !["completed", "cancelled"].includes(o.status)).map((o) => <SelectItem key={`o${o.id}`} value={`o:${o.id}`}>{o.code} · {o.title}</SelectItem>)}
                  {incidents.data?.filter((i) => i.resolution_status !== "resolved").map((i) => <SelectItem key={`i${i.id}`} value={`i:${i.id}`}>{i.code} · {i.service_area_name}</SelectItem>)}
                </SelectContent>
              </Select>
            </Field>
          </div>
          <Field label="Recipients by service area" error={errors.area_ids}>
            <div className={cn("grid gap-1.5 rounded-lg border p-2 sm:grid-cols-2", errors.area_ids && "border-destructive")}>
              {areas.data?.map((a) => (
                <label key={a.id} className="flex cursor-pointer items-center gap-2 rounded px-2 py-1 text-sm hover:bg-accent">
                  <Checkbox checked={areaIds.includes(a.id)} onCheckedChange={(c) => setAreaIds(c ? [...areaIds, a.id] : areaIds.filter((x) => x !== a.id))} />
                  <span className="flex-1">{a.name}</span>
                  <span className="text-xs text-muted-foreground">{a.customer_count}</span>
                </label>
              ))}
            </div>
          </Field>
          {needed.map((k) => (
            <Field key={k} label={LABELS[k] ?? k} htmlFor={`v-${k}`} error={errors[k]}>
              {k === "message" ? <Textarea id={`v-${k}`} rows={3} value={vars[k] ?? ""} invalid={!!errors[k]} onChange={(e) => setVars({ ...vars, [k]: e.target.value })} />
                : <Input id={`v-${k}`} value={vars[k] ?? ""} invalid={!!errors[k]} onChange={(e) => setVars({ ...vars, [k]: e.target.value })} />}
            </Field>
          ))}
          <fieldset className="space-y-2">
            <Label>Delivery</Label>
            <div className="grid gap-2 sm:grid-cols-3">
              {([["send_now", "Send now", Send], ["schedule", "Schedule", CalendarClock], ["draft", "Save draft", PenSquare]] as const).map(([v, l, Icon]) => (
                <label key={v} className={cn("flex cursor-pointer items-center gap-2 rounded-lg border p-3 text-sm transition", mode === v && "border-primary bg-brand-soft")}>
                  <input type="radio" name="mode" value={v} checked={mode === v} onChange={() => setMode(v)} className="accent-[#2563EB]" />
                  <Icon className="h-4 w-4 text-muted-foreground" /> {l}
                </label>
              ))}
            </div>
            {mode === "schedule" && (
              <Field label="Send at" htmlFor="n-at" error={errors.send_at} className="max-w-xs">
                <Input id="n-at" type="datetime-local" value={sendAt} invalid={!!errors.send_at} onChange={(e) => setSendAt(e.target.value)} />
              </Field>
            )}
          </fieldset>
          <div className="flex justify-end gap-2 border-t pt-4">
            <Button disabled={submit.isPending} onClick={() => validate() && (mode === "send_now" ? setConfirm(true) : submit.mutate())}>
              {submit.isPending && <Loader2 className="animate-spin" />}
              {mode === "send_now" ? <><FlaskConical /> Simulate send</> : mode === "schedule" ? "Schedule notification" : "Save draft"}
            </Button>
          </div>
        </CardContent>
      </Card>
      <div className="space-y-2">
        <p className="text-sm font-medium">Preview</p>
        {previewErr && <p className="text-xs text-destructive">{previewErr}</p>}
        <WhatsAppPreview preview={preview} title={tpl?.name} />
      </div>
      <ConfirmDialog open={confirm} onOpenChange={setConfirm} title="Send this notification now?" confirmLabel="Simulate send"
        description={<>The message will be generated for <b>{preview?.recipients.eligible ?? 0} customers</b> and recorded as <i>simulated sent</i>. No real WhatsApp message is delivered.</>}
        onConfirm={() => { submit.mutate(); setConfirm(false); }} />
    </div>
  );
}

/* --------------------------------------------------------------- job detail */
function JobDetail({ id, onClose }: { id: number | null; onClose: () => void }) {
  const q = useJob(id);
  const j = q.data;
  const names = useAreaNames();
  const [filter, setFilter] = useState<"all" | "failed">("all");
  const retry = useAction(() => api.post<Job>(`/notifications/${id}/retry`), { success: (r) => `Retry complete: ${r.sent_count} sent, ${r.failed_count} still failing` });
  const msgs = (j?.messages ?? []).filter((m) => filter === "all" || m.status === "failed");
  return (
    <Dialog open={id != null} onOpenChange={(v) => !v && onClose()}>
      <SheetContent className="sm:max-w-2xl">
        {!j ? <div className="p-6"><TableSkeleton rows={6} cols={2} /></div> : (
          <>
            <div className="border-b p-6 pr-12">
              <div className="flex flex-wrap items-center gap-2"><span className="font-mono text-xs text-muted-foreground">{j.code}</span><JobStatusBadge status={j.status} failed={j.failed_count} /><Badge tone="warning">Simulated</Badge></div>
              <DialogTitle className="mt-2 text-xl font-semibold">{j.kind_label}</DialogTitle>
              <DialogDescription className="mt-1 text-sm text-muted-foreground">
                {j.linked ? <Link className="text-primary hover:underline" to={j.linked.type === "incident" ? `/incidents?id=${j.linked.id}` : `/scheduled?id=${j.linked.id}`}>{j.linked.code} · {j.linked.title}</Link> : "Manual announcement"}
              </DialogDescription>
              {j.failed_count > 0 && <Button size="sm" className="mt-4" disabled={retry.isPending} onClick={() => retry.mutate()}><RefreshCw className={cn(retry.isPending && "animate-spin")} /> Retry {j.failed_count} failed</Button>}
            </div>
            <div className="space-y-6 p-6">
              <dl className="grid grid-cols-2 gap-4 sm:grid-cols-3">
                <KeyValue label={j.status === "scheduled" || j.status === "draft" ? "Scheduled for" : "Processed"}>{formatDateTime(j.processed_at ?? j.send_at)}</KeyValue>
                <KeyValue label="Service areas">{names(j.area_ids)}</KeyValue>
                <KeyValue label="Template">{j.template_key.replace(/_/g, " ")}</KeyValue>
                <KeyValue label="Recipients">{j.recipients_count}</KeyValue>
                <KeyValue label="Simulated sent">{j.sent_count}</KeyValue>
                <KeyValue label="Failed">{j.failed_count}</KeyValue>
              </dl>
              {j.note && <p className="rounded-lg bg-muted/50 p-3 text-sm">{j.note}</p>}
              {j.preview && (
                <div className="rounded-xl bg-[#efeae2] p-3 text-[13px] dark:bg-[#0b141a]"><div className="rounded-lg bg-white p-3 text-slate-800 dark:bg-[#202c33] dark:text-slate-100"><WhatsAppText text={j.preview} /></div></div>
              )}
              {!!j.messages?.length && (
                <div>
                  <div className="mb-3 flex items-center justify-between">
                    <h4 className="text-sm font-semibold">Recipients ({j.messages.length})</h4>
                    <Tabs value={filter} onValueChange={(v) => setFilter(v as "all" | "failed")}><TabsList><TabsTrigger value="all">All</TabsTrigger><TabsTrigger value="failed">Failed ({j.failed_count})</TabsTrigger></TabsList></Tabs>
                  </div>
                  <div className="divide-y rounded-lg border">
                    {msgs.map((m) => (
                      <details key={m.id} className="group px-3 py-2 text-sm">
                        <summary className="flex cursor-pointer list-none items-center justify-between gap-2">
                          <span className="min-w-0"><span className="font-medium">{m.customer_name}</span><span className="ml-2 font-mono text-xs text-muted-foreground">{m.phone}</span></span>
                          <span className="flex items-center gap-2">
                            {m.attempts > 1 && <span className="text-xs text-muted-foreground">attempt {m.attempts}</span>}
                            {m.status === "simulated_sent" ? <Badge tone="success"><Check /> Simulated sent</Badge> : <Badge tone="danger"><XCircle /> Failed</Badge>}
                          </span>
                        </summary>
                        {m.error && <p className="mt-1 text-xs text-destructive">{m.error}</p>}
                        <div className="mt-2 rounded-lg bg-muted/50 p-2 text-xs leading-relaxed"><WhatsAppText text={m.body} /></div>
                      </details>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </>
        )}
      </SheetContent>
    </Dialog>
  );
}

/* -------------------------------------------------------------- jobs tables */
function JobsTable({ jobs, pending, onOpen }: { jobs: Job[]; pending?: boolean; onOpen: (j: Job) => void }) {
  const now = useNow(5000);
  const names = useAreaNames();
  const [action, setAction] = useState<{ type: "send" | "cancel"; job: Job } | null>(null);
  const [scheduleJob, setScheduleJob] = useState<Job | null>(null);
  const [at, setAt] = useState("");
  const send = useAction((j: Job) => api.post<Job>("/notifications/simulate", { job_id: j.id }), { success: (j) => `${j.code} sent in simulation to ${j.sent_count} customers` });
  const cancel = useAction((j: Job) => api.post<Job>(`/notifications/${j.id}/cancel`), { success: (j) => `${j.code} cancelled` });
  const schedule = useAction(() => api.post<Job>(`/notifications/${scheduleJob!.id}/schedule`, { send_at: localInputToIso(at) }), {
    success: (j) => `${j.code} scheduled for ${formatDateTime(j.send_at)}`, onSuccess: () => setScheduleJob(null),
  });
  const retry = useAction((j: Job) => api.post<Job>(`/notifications/${j.id}/retry`), { success: (r) => `Retry complete: ${r.sent_count} sent, ${r.failed_count} still failing` });
  if (!jobs.length) return <div className="p-6"><EmptyState icon={pending ? Inbox : History} title={pending ? "Queue is empty" : "No notifications found"} description={pending ? "Scheduled reminders and drafts will appear here." : undefined} /></div>;
  return (
    <>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Notification</TableHead>
            <TableHead>Related to</TableHead>
            <TableHead>Areas</TableHead>
            <TableHead>{pending ? "Send time" : "Processed"}</TableHead>
            <TableHead className="text-right">{pending ? "Recipients" : "Sent / total"}</TableHead>
            <TableHead>Status</TableHead>
            <TableHead className="text-right">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {jobs.map((j) => (
            <TableRow key={j.id} className="cursor-pointer" onClick={() => onOpen(j)}>
              <TableCell><p className="font-medium">{j.kind_label}</p><p className="font-mono text-xs text-muted-foreground">{j.code}</p></TableCell>
              <TableCell className="max-w-[220px] truncate text-sm">{j.linked ? `${j.linked.code} · ${j.linked.title}` : <span className="text-muted-foreground">Manual</span>}</TableCell>
              <TableCell className="max-w-[200px] truncate text-sm text-muted-foreground">{names(j.area_ids)}</TableCell>
              <TableCell className="whitespace-nowrap text-sm">
                {formatDateTime(pending ? j.send_at : j.processed_at ?? j.send_at)}
                {pending && <p className="text-xs text-muted-foreground">{j.status === "draft" ? "not scheduled" : relative(j.send_at, now)}</p>}
              </TableCell>
              <TableCell className="text-right tabular">{pending ? j.recipients_count : `${j.sent_count} / ${j.recipients_count}`}</TableCell>
              <TableCell><JobStatusBadge status={j.status} failed={j.failed_count} />{j.note && !pending && <p className="mt-0.5 max-w-[200px] truncate text-[11px] text-muted-foreground" title={j.note}>{j.note}</p>}</TableCell>
              <TableCell className="text-right" onClick={(e) => e.stopPropagation()}>
                <div className="flex justify-end gap-1">
                  {pending && <Button size="sm" variant="outline" onClick={() => setAction({ type: "send", job: j })}><Send /> Send now</Button>}
                  {j.status === "draft" && <Button size="sm" variant="outline" onClick={() => { setAt(""); setScheduleJob(j); }}><Clock /> Schedule</Button>}
                  {pending && <Button size="sm" variant="ghost" className="text-destructive" onClick={() => setAction({ type: "cancel", job: j })}><Ban /> Cancel</Button>}
                  {!pending && j.failed_count > 0 && <Button size="sm" variant="outline" disabled={retry.isPending} onClick={() => retry.mutate(j)}><RefreshCw /> Retry failed</Button>}
                </div>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      <ConfirmDialog open={action?.type === "send"} onOpenChange={(v) => !v && setAction(null)} title={`Send ${action?.job.code} now?`} confirmLabel="Simulate send"
        description={<>{action?.job.kind_label} will be generated for {action?.job.recipients_count} customers ahead of its scheduled time. Delivery is simulated.</>}
        onConfirm={() => { send.mutate(action!.job); setAction(null); }} />
      <ConfirmDialog open={action?.type === "cancel"} onOpenChange={(v) => !v && setAction(null)} title={`Cancel ${action?.job.code}?`} destructive confirmLabel="Cancel notification"
        description="This notification will not be sent. This cannot be undone." onConfirm={() => { cancel.mutate(action!.job); setAction(null); }} />
      <Dialog open={!!scheduleJob} onOpenChange={(v) => !v && setScheduleJob(null)}>
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle>Schedule {scheduleJob?.code}</DialogTitle><DialogDescription>Choose when the simulated message should be sent.</DialogDescription></DialogHeader>
          <Field label="Send at" htmlFor="sched-at" error={schedule.fieldErrors.send_at}><Input id="sched-at" type="datetime-local" value={at} onChange={(e) => setAt(e.target.value)} /></Field>
          <DialogFooter><Button variant="outline" onClick={() => setScheduleJob(null)}>Cancel</Button><Button disabled={!at || schedule.isPending} onClick={() => schedule.mutate()}>Schedule</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

/* ------------------------------------------------------------------ message log */
function MessageLog() {
  const msgs = useMessages();
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("all");
  const list = (msgs.data ?? []).filter((m) => (status === "all" || m.status === status) && (!q || m.customer_name.toLowerCase().includes(q.toLowerCase()) || m.service_area_name.toLowerCase().includes(q.toLowerCase())));
  return (
    <Card>
      <div className="flex flex-wrap items-center gap-2 border-b p-4">
        <div className="relative"><Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" /><Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Customer or area" className="w-56 pl-8" aria-label="Search messages" /></div>
        <Select value={status} onValueChange={setStatus}><SelectTrigger className="w-44" aria-label="Status"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">All outcomes</SelectItem><SelectItem value="simulated_sent">Simulated sent</SelectItem><SelectItem value="failed">Failed</SelectItem></SelectContent></Select>
        <span className="ml-auto text-xs text-muted-foreground">Showing the latest {list.length} messages · outcomes are simulated, not real deliveries</span>
      </div>
      <CardContent className="p-0">
        {msgs.isLoading ? <div className="p-4"><TableSkeleton /></div> : !list.length ? <div className="p-6"><EmptyState title="No messages" /></div> : (
          <Table>
            <TableHeader><TableRow><TableHead>Time</TableHead><TableHead>Recipient</TableHead><TableHead>Area</TableHead><TableHead>Message</TableHead><TableHead>Outcome</TableHead></TableRow></TableHeader>
            <TableBody>
              {list.slice(0, 200).map((m) => (
                <TableRow key={m.id}>
                  <TableCell className="whitespace-nowrap text-xs">{formatDateTime(m.created_at)}</TableCell>
                  <TableCell><p className="text-sm font-medium">{m.customer_name}</p><p className="font-mono text-xs text-muted-foreground">{m.phone}</p></TableCell>
                  <TableCell className="text-sm text-muted-foreground">{m.service_area_name}</TableCell>
                  <TableCell className="max-w-md"><p className="line-clamp-2 text-xs text-muted-foreground">{m.body.replace(/\*/g, "")}</p></TableCell>
                  <TableCell>{m.status === "simulated_sent" ? <Badge tone="success">Simulated sent</Badge> : <Badge tone="danger" title={m.error}>Failed</Badge>}{m.error && <p className="mt-0.5 max-w-[220px] truncate text-[11px] text-destructive">{m.error}</p>}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}

/* ----------------------------------------------------------------- channels */
function Channels() {
  const scheduled = useScheduled();
  const incidents = useIncidents("all");
  const [source, setSource] = useState("custom");
  const [custom, setCustom] = useState("");
  const [text, setText] = useState("");
  const [err, setErr] = useState("");
  const [copied, setCopied] = useState(false);
  const generate = async () => {
    setErr(""); setCopied(false);
    const [t, id] = source.split(":");
    try {
      const r = await api.post<{ text: string }>("/channels/announcement", t === "o" ? { scheduled_outage_id: Number(id) } : t === "i" ? { incident_id: Number(id) } : { custom_text: custom });
      setText(r.text);
    } catch (e) { setErr(errorMessage(e)); setText(""); }
  };
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><Megaphone className="h-5 w-5 text-primary" /> WhatsApp Channel announcement</CardTitle>
          <CardDescription>Public community updates. WhatsApp Channels have no documented publishing API, so PowerChat generates the text and an operator posts it manually. Customer names and numbers are never included.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Field label="Announcement source" htmlFor="ch-src">
            <Select value={source} onValueChange={(v) => { setSource(v); setText(""); }}>
              <SelectTrigger id="ch-src"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="custom">Custom text</SelectItem>
                {scheduled.data?.filter((o) => o.status !== "draft").slice(0, 15).map((o) => <SelectItem key={o.id} value={`o:${o.id}`}>{o.code} · {o.title}</SelectItem>)}
                {incidents.data?.filter((i) => i.verification_status === "confirmed").slice(0, 10).map((i) => <SelectItem key={i.id} value={`i:${i.id}`}>{i.code} · {i.service_area_name}</SelectItem>)}
              </SelectContent>
            </Select>
          </Field>
          {source === "custom" && (
            <Field label="Announcement text" htmlFor="ch-text" hint="Do not include personal information such as phone numbers.">
              <Textarea id="ch-text" rows={4} value={custom} onChange={(e) => setCustom(e.target.value)} />
            </Field>
          )}
          {err && <p className="text-sm text-destructive">{err}</p>}
          <Button onClick={generate} disabled={source === "custom" && !custom.trim()}>Generate announcement</Button>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>Channel-ready text</CardTitle><CardDescription>Copy and paste into your WhatsApp Channel.</CardDescription></CardHeader>
        <CardContent className="space-y-3">
          <div className="min-h-[160px] rounded-lg bg-[#efeae2] p-4 text-[13px] leading-relaxed text-slate-800 dark:bg-[#0b141a] dark:text-slate-100">
            {text ? <WhatsAppText text={text} /> : <p className="pt-10 text-center text-xs text-slate-500">Generate an announcement to see it here.</p>}
          </div>
          <Button variant="outline" disabled={!text} onClick={async () => { if (await copyText(text)) { setCopied(true); toast.success("Copied to clipboard"); } }}>{copied ? <Check /> : <Copy />} {copied ? "Copied" : "Copy text"}</Button>
        </CardContent>
      </Card>
    </div>
  );
}

/* --------------------------------------------------------------------- page */
export default function Notifications() {
  const [params, setParams] = useSearchParams();
  const jobs = useJobs();
  const [tab, setTab] = useState(params.get("tab") ?? "queue");
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("all");
  const jobId = params.get("job") ? Number(params.get("job")) : null;
  useEffect(() => { const t = params.get("tab"); if (t) setTab(t); }, [params]);
  const all = jobs.data ?? [];
  const pending = all.filter((j) => ["draft", "scheduled", "processing"].includes(j.status)).sort((a, b) => a.send_at.localeCompare(b.send_at));
  const history = all.filter((j) => !["draft", "scheduled", "processing"].includes(j.status) && (status === "all" || j.status === status)
    && (!q || j.kind_label.toLowerCase().includes(q.toLowerCase()) || j.code.toLowerCase().includes(q.toLowerCase()) || (j.linked?.title.toLowerCase().includes(q.toLowerCase()) ?? false)))
    .sort((a, b) => (b.processed_at ?? b.send_at).localeCompare(a.processed_at ?? a.send_at));
  const open = (j: Job) => { params.set("job", String(j.id)); setParams(params); };
  const changeTab = (t: string) => { setTab(t); params.set("tab", t); setParams(params, { replace: true }); };

  return (
    <div className="animate-fade-in">
      <PageHeader title="Notifications" description={<>WhatsApp communication for planned and unexpected interruptions. <Badge tone="warning" className="ml-1 align-middle">Simulation: no real customer is contacted</Badge></>}
        actions={<Button onClick={() => changeTab("compose")}><PenSquare /> New notification</Button>} />
      <Tabs value={tab} onValueChange={changeTab}>
        <TabsList>
          <TabsTrigger value="queue"><Inbox /> Queue {pending.length > 0 && <Badge tone="brand" className="ml-1 px-1.5">{pending.length}</Badge>}</TabsTrigger>
          <TabsTrigger value="history"><History /> History</TabsTrigger>
          <TabsTrigger value="messages"><ListChecks /> Message log</TabsTrigger>
          <TabsTrigger value="compose"><PenSquare /> Compose</TabsTrigger>
          <TabsTrigger value="templates"><FlaskConical /> Templates</TabsTrigger>
          <TabsTrigger value="channels"><Megaphone /> Channels</TabsTrigger>
        </TabsList>
        <TabsContent value="queue">
          <Card><CardContent className="p-0">{jobs.isLoading ? <div className="p-4"><TableSkeleton /></div> : <JobsTable jobs={pending} pending onOpen={open} />}</CardContent></Card>
        </TabsContent>
        <TabsContent value="history">
          <Card>
            <div className="flex flex-wrap items-center gap-2 border-b p-4">
              <div className="relative"><Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" /><Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search notifications" className="w-56 pl-8" aria-label="Search notifications" /></div>
              <Select value={status} onValueChange={setStatus}>
                <SelectTrigger className="w-44" aria-label="Status"><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="all">All outcomes</SelectItem>{(["simulated_sent", "failed", "cancelled"] as JobStatus[]).map((s) => <SelectItem key={s} value={s}>{JOB_STATUS[s].label}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <CardContent className="p-0">{jobs.isLoading ? <div className="p-4"><TableSkeleton /></div> : <JobsTable jobs={history} onOpen={open} />}</CardContent>
          </Card>
        </TabsContent>
        <TabsContent value="messages"><MessageLog /></TabsContent>
        <TabsContent value="compose"><Compose onDone={() => changeTab("history")} /></TabsContent>
        <TabsContent value="templates"><TemplateEditor /></TabsContent>
        <TabsContent value="channels"><Channels /></TabsContent>
      </Tabs>
      <JobDetail id={jobId} onClose={() => { params.delete("job"); setParams(params); }} />
    </div>
  );
}
