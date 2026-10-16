import { AlertTriangle, BellRing, CalendarCheck, CheckCircle2, Loader2, Plus, X, XCircle } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { WhatsAppPreview } from "@/components/shared/WhatsAppPreview";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Checkbox, Field, Label, Switch } from "@/components/ui/form-bits";
import { Input, Textarea } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/menus";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useAction, useMiniGrids, useSettings } from "@/hooks/queries";
import { api, errorMessage } from "@/lib/api";
import { PRESET_OFFSETS, REASONS } from "@/lib/constants";
import { formatDateTime, isoToLocalInput, localDateKey, localInputToIso, offsetLabel } from "@/lib/format";
import type { AudienceRow, PlanPreview, Priority, Reason, ScheduledOutage } from "@/lib/types";
import { useQuery } from "@tanstack/react-query";
import { cn } from "@/lib/utils";

export type FormMode = "create" | "edit" | "reschedule";

interface State {
  title: string;
  reason: Reason;
  reason_detail: string;
  mini_grid_id: string;
  area_ids: number[];
  start: string;
  end: string;
  description: string;
  priority: Priority;
  offsets: number[];
  send_notice: boolean;
  notify_customers: boolean;
}

function tomorrowAt(hour: number, plusHours = 0): string {
  const key = localDateKey(new Date(Date.now() + 86400000));
  const h = String(hour + plusHours).padStart(2, "0");
  return `${key}T${h}:00`;
}

function RecipientList({ areaIds }: { areaIds: number[] }) {
  const [open, setOpen] = useState(false);
  const audience = useQuery({
    queryKey: ["audience", areaIds],
    queryFn: () => api.get<{ customers: AudienceRow[]; eligible: number; total_in_areas: number }>(`/audience?detail=true&area_ids=${areaIds.join(",")}`),
    enabled: open && areaIds.length > 0,
  });
  if (!areaIds.length) return null;
  return (
    <div className="rounded-xl border bg-card">
      <button type="button" onClick={() => setOpen((v) => !v)} className="flex w-full items-center justify-between px-3 py-2 text-sm font-medium">
        Affected customers {audience.data && <span className="text-muted-foreground">({audience.data.eligible} of {audience.data.total_in_areas} notified)</span>}
        <span className="text-xs text-primary">{open ? "Hide" : "Show"}</span>
      </button>
      {open && (
        <ul className="max-h-56 divide-y overflow-y-auto border-t text-xs scrollbar-thin">
          {audience.isLoading && <li className="p-3 text-muted-foreground">Loading…</li>}
          {audience.data?.customers.map((c) => (
            <li key={c.id} className={cn("flex items-center justify-between gap-2 px-3 py-1.5", !c.included && "text-muted-foreground")}>
              <span className="min-w-0 truncate">{c.name} <span className="font-mono text-[10px]">{c.phone}</span>{c.source === "mpm" && <Badge tone="brand" className="ml-1 px-1 text-[9px]">MPM</Badge>}</span>
              <span className="shrink-0">{c.included ? <>{c.channel === "sms" ? "SMS" : "WhatsApp"}{c.simulated && " (sim)"}{c.reason && <span className="text-amber-600"> · {c.reason}</span>}</> : c.reason}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function OutageForm({ open, onOpenChange, mode, outage, preset, onSaved }: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  mode: FormMode;
  outage?: ScheduledOutage | null;
  preset?: "demo" | null;
  onSaved?: (o: ScheduledOutage) => void;
}) {
  const grids = useMiniGrids();
  const settings = useSettings();
  const [s, setS] = useState<State | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [custom, setCustom] = useState({ value: "30", unit: "minutes" });
  const [preview, setPreview] = useState<PlanPreview | null>(null);
  const [previewError, setPreviewError] = useState("");
  const [previewLoading, setPreviewLoading] = useState(false);
  const [msgTab, setMsgTab] = useState("notice");

  // Initialise the form when opened.
  useEffect(() => {
    if (!open || !grids.data) return;
    setErrors({});
    setPreview(null);
    if (outage) {
      setS({
        title: outage.title, reason: outage.reason, reason_detail: outage.reason_detail, mini_grid_id: String(outage.mini_grid_id),
        area_ids: outage.service_areas.map((a) => a.id), start: isoToLocalInput(outage.start_at), end: isoToLocalInput(outage.end_at),
        description: outage.description, priority: outage.priority, offsets: outage.reminder_offsets, send_notice: outage.send_notice_on_publish,
        notify_customers: true,
      });
      setMsgTab(mode === "reschedule" ? "reschedule" : "notice");
    } else {
      const kivu = grids.data.find((g) => g.service_areas.some((a) => a.code === "B")) ?? grids.data[0];
      const demo = preset === "demo";
      setS({
        title: demo ? "Feeder maintenance – Hillside" : "",
        reason: "planned_maintenance",
        reason_detail: "",
        mini_grid_id: demo ? String(kivu.id) : "",
        area_ids: demo ? kivu.service_areas.filter((a) => a.code === "B").map((a) => a.id) : [],
        start: tomorrowAt(9),
        end: tomorrowAt(9, 2),
        description: demo ? "Replacement of worn conductors and insulators on the Hillside feeder." : "",
        priority: demo ? "high" : "medium",
        offsets: demo ? [60] : settings.data?.notifications.default_reminder_offsets ?? [1440, 60],
        send_notice: settings.data?.notifications.send_notice_on_publish ?? true,
        notify_customers: true,
      });
      setMsgTab("notice");
    }
  }, [open, outage, preset, mode, grids.data, settings.data]);

  const grid = grids.data?.find((g) => String(g.id) === s?.mini_grid_id);
  const published = !!outage && outage.status !== "draft";
  const timesChanged = !!outage && !!s && (localInputToIso(s.start) !== new Date(outage.start_at).toISOString() || localInputToIso(s.end) !== new Date(outage.end_at).toISOString());

  // Debounced live preview of the notification schedule and messages.
  const previewKey = s ? JSON.stringify([s.start, s.end, s.area_ids, s.offsets, s.send_notice, s.title, s.reason, s.reason_detail]) : "";
  useEffect(() => {
    if (!open || !s || !s.start || !s.end) return;
    const id = setTimeout(async () => {
      setPreviewLoading(true);
      try {
        const r = await api.post<PlanPreview>("/outages/scheduled/preview", {
          title: s.title, reason: s.reason, reason_detail: s.reason_detail, service_area_ids: s.area_ids,
          start_at: localInputToIso(s.start), end_at: localInputToIso(s.end), reminder_offsets: s.offsets,
          send_notice_on_publish: s.send_notice, outage_id: outage?.id,
        });
        setPreview(r);
        setPreviewError("");
      } catch (e) {
        setPreviewError(errorMessage(e));
      } finally {
        setPreviewLoading(false);
      }
    }, 350);
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [previewKey, open]);

  const set = <K extends keyof State>(k: K, v: State[K]) => setS((p) => (p ? { ...p, [k]: v } : p));

  function validate(): Record<string, string> {
    const e: Record<string, string> = {};
    if (!s) return e;
    if (s.title.trim().length < 3) e.title = "Enter a title of at least 3 characters.";
    if (!s.mini_grid_id) e.mini_grid_id = "Select the affected mini-grid.";
    if (!s.area_ids.length) e.service_area_ids = "Select at least one affected service area.";
    if (!s.start) e.start_at = "Choose a start date and time.";
    if (!s.end) e.end_at = "Choose the expected restoration time.";
    if (s.start && s.end && localInputToIso(s.end) <= localInputToIso(s.start)) e.end_at = "Restoration must be after the start time.";
    // The server preview evaluates "past" against the demo clock, so rely on it.
    if (s.start && (!outage || timesChanged) && outage?.status !== "in_progress" && preview?.start_in_past) {
      e.start_at = "The start time must be in the future.";
    }
    if (s.reason === "other" && !s.reason_detail.trim()) e.reason_detail = "Describe the reason so customers understand the interruption.";
    return e;
  }

  const save = useAction(async ({ publish }: { publish: boolean }) => {
    const body: Record<string, unknown> = {
      title: s!.title.trim(), reason: s!.reason, reason_detail: s!.reason_detail.trim(), mini_grid_id: Number(s!.mini_grid_id),
      service_area_ids: s!.area_ids, start_at: localInputToIso(s!.start), end_at: localInputToIso(s!.end), description: s!.description.trim(),
      priority: s!.priority, reminder_offsets: s!.offsets, send_notice_on_publish: s!.send_notice,
    };
    if (!outage) return { data: await api.post<ScheduledOutage>("/outages/scheduled", { ...body, publish }), meta: undefined };
    const patch = mode === "reschedule"
      ? { start_at: body.start_at, end_at: body.end_at, reminder_offsets: body.reminder_offsets, notify_customers: s!.notify_customers }
      : outage.status === "in_progress" ? { end_at: body.end_at, description: body.description } : { ...body, notify_customers: s!.notify_customers };
    const r = await api.patch<ScheduledOutage>(`/outages/scheduled/${outage.id}`, patch);
    if (publish && r.data.status === "draft") return { data: await api.post<ScheduledOutage>(`/outages/scheduled/${outage.id}/publish`), meta: r.meta };
    return r;
  }, {
    success: (r: any) => {
      const c = r.meta?.changes;
      if (c) {
        const parts = [];
        if (c.reminders_updated) parts.push(`${c.reminders_updated} reminder(s) re-timed`);
        if (c.reminders_cancelled) parts.push(`${c.reminders_cancelled} cancelled`);
        if (c.reminders_created) parts.push(`${c.reminders_created} created`);
        if (c.announcement_job_ids?.length) parts.push("customer update sent in simulation");
        return `${r.data.code} updated${parts.length ? `: ${parts.join(", ")}` : ""}`;
      }
      return r.data.status === "draft" ? `${r.data.code} saved as draft` : `${r.data.code} scheduled. The notice was sent in simulation and reminders are queued.`;
    },
    onSuccess: (r: any) => { onSaved?.(r.data); onOpenChange(false); },
  });

  useEffect(() => setErrors((e) => ({ ...e, ...save.fieldErrors })), [save.fieldErrors]);

  function submit(publish: boolean) {
    const e = validate();
    setErrors(e);
    if (Object.keys(e).length === 0) save.mutate({ publish });
  }

  const addCustom = () => {
    const v = Number(custom.value);
    if (!Number.isFinite(v) || v <= 0) {
      setErrors((e) => ({ ...e, reminder_offsets: "Enter a positive number." }));
      return;
    }
    const minutes = Math.round(custom.unit === "hours" ? v * 60 : custom.unit === "days" ? v * 1440 : v);
    if (minutes > 14 * 1440) {
      setErrors((e) => ({ ...e, reminder_offsets: "Reminders can be at most 14 days before the start." }));
      return;
    }
    set("offsets", Array.from(new Set([...(s?.offsets ?? []), minutes])).sort((a, b) => b - a));
    setErrors(({ reminder_offsets: _, ...rest }) => rest);
  };

  const messages = preview?.messages ?? {};
  const msgOptions = useMemo(() => (["notice", "reminder", "reschedule"] as const).filter((k) => messages[k]), [messages]);
  const title = mode === "create" ? "Schedule a planned interruption" : mode === "reschedule" ? `Reschedule ${outage?.code}` : `Edit ${outage?.code}`;
  const onlyTimes = mode === "reschedule";
  const inProgress = outage?.status === "in_progress";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-5xl gap-0 p-0">
        <DialogHeader className="border-b p-5">
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>
            {mode === "create" ? "Customers in the selected areas are notified in advance (WhatsApp messages are simulated)." :
              onlyTimes ? "Pending reminders are recalculated automatically. Customers who were already notified can receive a rescheduling notice." :
              inProgress ? "This interruption is in progress. Only the restoration time and description can change." : "Update the event details."}
          </DialogDescription>
        </DialogHeader>
        {!s ? (
          <div className="flex h-64 items-center justify-center"><Loader2 className="animate-spin text-muted-foreground" /></div>
        ) : (
          <div className="grid lg:grid-cols-[1fr_400px]">
            <form className="space-y-4 p-5" onSubmit={(e) => { e.preventDefault(); submit(true); }} noValidate>
              {!onlyTimes && (
                <>
                  <Field label="Event title" htmlFor="title" error={errors.title}>
                    <Input id="title" value={s.title} disabled={inProgress} invalid={!!errors.title} onChange={(e) => set("title", e.target.value)} placeholder="e.g. Transformer maintenance – Market Centre" />
                  </Field>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <Field label="Reason for interruption" htmlFor="reason">
                      <Select value={s.reason} disabled={inProgress} onValueChange={(v) => set("reason", v as Reason)}>
                        <SelectTrigger id="reason"><SelectValue /></SelectTrigger>
                        <SelectContent>{Object.entries(REASONS).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}</SelectContent>
                      </Select>
                    </Field>
                    <Field label="Priority level" htmlFor="priority">
                      <Select value={s.priority} disabled={inProgress} onValueChange={(v) => set("priority", v as Priority)}>
                        <SelectTrigger id="priority"><SelectValue /></SelectTrigger>
                        <SelectContent>{["low", "medium", "high", "critical"].map((p) => <SelectItem key={p} value={p} className="capitalize">{p[0].toUpperCase() + p.slice(1)}</SelectItem>)}</SelectContent>
                      </Select>
                    </Field>
                  </div>
                  {s.reason === "other" && (
                    <Field label="Describe the reason" htmlFor="reason_detail" error={errors.reason_detail} hint="Shown to customers, e.g. “tree trimming near the lines”.">
                      <Input id="reason_detail" value={s.reason_detail} invalid={!!errors.reason_detail} onChange={(e) => set("reason_detail", e.target.value)} />
                    </Field>
                  )}
                  <div className="grid gap-4 sm:grid-cols-2">
                    <Field label="Affected mini-grid" htmlFor="grid" error={errors.mini_grid_id}>
                      <Select value={s.mini_grid_id} disabled={inProgress} onValueChange={(v) => setS((p) => p && { ...p, mini_grid_id: v, area_ids: [] })}>
                        <SelectTrigger id="grid" invalid={!!errors.mini_grid_id}><SelectValue placeholder="Select mini-grid" /></SelectTrigger>
                        <SelectContent>{grids.data?.map((g) => <SelectItem key={g.id} value={String(g.id)}>{g.name}</SelectItem>)}</SelectContent>
                      </Select>
                    </Field>
                    <Field label="Affected service areas" error={errors.service_area_ids}>
                      <div className={cn("min-h-9 space-y-1.5 rounded-lg border bg-card p-2", errors.service_area_ids && "border-destructive")}>
                        {!grid ? <p className="px-1 text-xs text-muted-foreground">Select a mini-grid first.</p> : grid.service_areas.map((a) => (
                          <label key={a.id} className="flex cursor-pointer items-center gap-2 rounded px-1 py-0.5 text-sm hover:bg-accent">
                            <Checkbox checked={s.area_ids.includes(a.id)} disabled={inProgress}
                                      onCheckedChange={(c) => set("area_ids", c ? [...s.area_ids, a.id] : s.area_ids.filter((x) => x !== a.id))} />
                            {a.name}
                          </label>
                        ))}
                      </div>
                    </Field>
                  </div>
                </>
              )}
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Scheduled start" htmlFor="start" error={errors.start_at}>
                  <Input id="start" type="datetime-local" value={s.start} disabled={inProgress} invalid={!!errors.start_at} onChange={(e) => set("start", e.target.value)} />
                </Field>
                <Field label="Expected restoration" htmlFor="end" error={errors.end_at}>
                  <Input id="end" type="datetime-local" value={s.end} invalid={!!errors.end_at} onChange={(e) => set("end", e.target.value)} />
                </Field>
              </div>
              {!onlyTimes && (
                <Field label="Maintenance description" htmlFor="desc" hint="Internal notes for the field team (not sent to customers).">
                  <Textarea id="desc" rows={2} value={s.description} onChange={(e) => set("description", e.target.value)} />
                </Field>
              )}

              {!inProgress && (
                <fieldset className="space-y-3 rounded-xl border p-4">
                  <legend className="flex items-center gap-1.5 px-1 text-sm font-medium"><BellRing className="h-4 w-4 text-primary" /> Notification schedule</legend>
                  {!published && (
                    <label className="flex items-center justify-between gap-3 text-sm">
                      <span>Send the initial notice as soon as the event is published</span>
                      <Switch checked={s.send_notice} onCheckedChange={(v) => set("send_notice", v)} />
                    </label>
                  )}
                  <div>
                    <Label className="text-xs text-muted-foreground">Reminders before the interruption</Label>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {PRESET_OFFSETS.map((p) => (
                        <label key={p.minutes} className={cn("flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-1.5 text-sm transition", s.offsets.includes(p.minutes) && "border-primary bg-brand-soft")}>
                          <Checkbox checked={s.offsets.includes(p.minutes)} onCheckedChange={(c) => set("offsets", c ? [...s.offsets, p.minutes].sort((a, b) => b - a) : s.offsets.filter((o) => o !== p.minutes))} />
                          {p.label}
                        </label>
                      ))}
                      {s.offsets.filter((o) => !PRESET_OFFSETS.some((p) => p.minutes === o)).map((o) => (
                        <Badge key={o} tone="brand" className="py-1 text-sm">
                          {offsetLabel(o)} before
                          <button type="button" aria-label={`Remove ${offsetLabel(o)} reminder`} onClick={() => set("offsets", s.offsets.filter((x) => x !== o))}><X className="!size-3.5" /></button>
                        </Badge>
                      ))}
                    </div>
                  </div>
                  <div className="flex flex-wrap items-end gap-2">
                    <Field label="Custom reminder" htmlFor="custom" className="w-36">
                      <Input id="custom" type="number" min={1} value={custom.value} onChange={(e) => setCustom({ ...custom, value: e.target.value })} />
                    </Field>
                    <Select value={custom.unit} onValueChange={(v) => setCustom({ ...custom, unit: v })}>
                      <SelectTrigger className="w-28" aria-label="Unit"><SelectValue /></SelectTrigger>
                      <SelectContent><SelectItem value="minutes">minutes</SelectItem><SelectItem value="hours">hours</SelectItem><SelectItem value="days">days</SelectItem></SelectContent>
                    </Select>
                    <span className="pb-2 text-sm text-muted-foreground">before</span>
                    <Button type="button" variant="outline" onClick={addCustom}><Plus /> Add</Button>
                  </div>
                  {errors.reminder_offsets && <p className="text-xs font-medium text-destructive">{errors.reminder_offsets}</p>}
                  {published && (
                    <label className={cn("flex items-start justify-between gap-3 rounded-lg p-3 text-sm", timesChanged && outage?.customers_notified ? "bg-warning-soft" : "bg-muted/50")}>
                      <span>
                        <span className="font-medium">Send a rescheduling notice to customers already notified</span>
                        <span className="block text-xs text-muted-foreground">{outage?.customers_notified ? timesChanged ? "The time has changed. Customers will be informed of the new schedule." : "Only sent if the date or time changes." : "No customer has been notified yet."}</span>
                      </span>
                      <Switch checked={s.notify_customers} disabled={!outage?.customers_notified} onCheckedChange={(v) => set("notify_customers", v)} />
                    </label>
                  )}
                </fieldset>
              )}
              <button type="submit" className="hidden" />
            </form>

            <aside className="space-y-4 border-t bg-muted/30 p-5 lg:border-l lg:border-t-0">
              <div>
                <p className="mb-2 flex items-center gap-2 text-sm font-medium"><CalendarCheck className="h-4 w-4 text-primary" /> When messages will be sent {previewLoading && <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />}</p>
                {previewError ? <p className="text-xs text-destructive">{previewError}</p> : (
                  <ul className="space-y-1.5">
                    {preview?.schedule.length === 0 && <li className="text-xs text-muted-foreground">No advance notifications selected. Customers will not be warned.</li>}
                    {preview?.schedule.map((p, i) => (
                      <li key={i} className={cn("flex items-start gap-2 rounded-lg border bg-card px-3 py-2 text-xs", !p.valid && "opacity-70")}>
                        {p.valid ? <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-success" /> : <XCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-danger" />}
                        <span className="min-w-0 flex-1">
                          <span className="block font-medium">{p.label}</span>
                          <span className="text-muted-foreground">{p.valid ? (p.kind === "notice" ? "Immediately on publish" : formatDateTime(p.send_at)) : p.reason}</span>
                        </span>
                      </li>
                    ))}
                    {published && timesChanged && outage?.customers_notified && s.notify_customers && (
                      <li className="flex items-start gap-2 rounded-lg border border-warning/50 bg-warning-soft px-3 py-2 text-xs">
                        <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-600" />
                        <span><span className="block font-medium">Rescheduling notice</span><span className="text-muted-foreground">Sent immediately when you save</span></span>
                      </li>
                    )}
                  </ul>
                )}
              </div>
              {msgOptions.length > 1 && (
                <Tabs value={msgOptions.includes(msgTab as never) ? msgTab : msgOptions[0]} onValueChange={setMsgTab}>
                  <TabsList className="w-full">{msgOptions.map((k) => <TabsTrigger key={k} value={k} className="flex-1 capitalize">{k}</TabsTrigger>)}</TabsList>
                </Tabs>
              )}
              <WhatsAppPreview
                preview={messages[(msgOptions.includes(msgTab as never) ? msgTab : msgOptions[0]) as "notice"] ?? null}
                loading={previewLoading}
                title={s.title || "Planned interruption"}
              />
              <RecipientList areaIds={s.area_ids} />
            </aside>
          </div>
        )}
        <DialogFooter className="border-t p-4">
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          {mode === "create" && <Button variant="secondary" disabled={save.isPending} onClick={() => submit(false)}>Save as draft</Button>}
          {outage?.status === "draft" && mode === "edit" && <Button variant="secondary" disabled={save.isPending} onClick={() => submit(false)}>Save draft</Button>}
          <Button disabled={save.isPending || !s} onClick={() => submit(true)}>
            {save.isPending && <Loader2 className="animate-spin" />}
            {mode === "create" || outage?.status === "draft" ? "Schedule & queue notifications" : mode === "reschedule" ? "Reschedule event" : "Save changes"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
