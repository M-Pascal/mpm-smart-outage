import { CheckCircle2, Cpu, Info, Loader2, MapPin, MessageSquare, Plug, Plus, RotateCcw, Save, Settings2, ShieldAlert, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { ErrorState, PageHeader, TableSkeleton } from "@/components/shared";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Checkbox, Field, Switch } from "@/components/ui/form-bits";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/menus";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useAction, useAreas, useMiniGrids, useSettings } from "@/hooks/queries";
import { api } from "@/lib/api";
import { PRESET_OFFSETS } from "@/lib/constants";
import { offsetLabel } from "@/lib/format";
import type { IntegrationStatus, ServiceArea, Settings } from "@/lib/types";
import { TemplateEditor } from "./notifications/TemplateEditor";

const TIMEZONES = ["Africa/Kigali", "Africa/Nairobi", "Africa/Lagos", "Africa/Johannesburg", "Africa/Dar_es_Salaam", "Africa/Kampala", "UTC"];

/** Generic section form: edits a copy of one settings section and PUTs it. */
function useSection<K extends "general" | "notifications" | "detection">(section: K, data: Settings | undefined) {
  const [v, setV] = useState<Settings[K] | null>(null);
  useEffect(() => { if (data) setV(data[section]); }, [data, section]);
  const save = useAction(() => api.put(`/settings/${section}`, v), { success: "Settings saved" });
  const dirty = !!data && !!v && JSON.stringify(v) !== JSON.stringify(data[section]);
  const set = <F extends keyof Settings[K]>(k: F, val: Settings[K][F]) => setV((p) => (p ? { ...p, [k]: val } : p));
  return { v, set, save, dirty, reset: () => data && setV(data[section]) };
}

function SaveBar({ s }: { s: { dirty: boolean; save: { isPending: boolean; mutate: () => void }; reset: () => void } }) {
  return (
    <CardFooter className="justify-end gap-2 border-t pt-4">
      {s.dirty && <Button variant="outline" onClick={s.reset}>Discard</Button>}
      <Button disabled={!s.dirty || s.save.isPending} onClick={() => s.save.mutate()}>{s.save.isPending ? <Loader2 className="animate-spin" /> : <Save />} Save changes</Button>
    </CardFooter>
  );
}

function General({ data }: { data?: Settings }) {
  const s = useSection("general", data);
  if (!s.v) return <TableSkeleton rows={3} cols={2} />;
  return (
    <Card>
      <CardHeader><CardTitle>Application preferences</CardTitle><CardDescription>Used in the interface and in customer messages.</CardDescription></CardHeader>
      <CardContent className="grid gap-4 sm:grid-cols-2">
        <Field label="Organisation name" htmlFor="org" error={s.save.fieldErrors.organization_name} hint="Shown in message headers, e.g. “PowerChat Energy Notice”.">
          <Input id="org" value={s.v.organization_name} onChange={(e) => s.set("organization_name", e.target.value)} />
        </Field>
        <Field label="Operator name" htmlFor="op" error={s.save.fieldErrors.operator_name} hint="Recorded on acknowledgements and actions.">
          <Input id="op" value={s.v.operator_name} onChange={(e) => s.set("operator_name", e.target.value)} />
        </Field>
        <Field label="Time zone" htmlFor="tz" error={s.save.fieldErrors.timezone} hint="All times in the app and in messages use this zone.">
          <Select value={s.v.timezone} onValueChange={(v) => s.set("timezone", v)}>
            <SelectTrigger id="tz"><SelectValue /></SelectTrigger>
            <SelectContent>{TIMEZONES.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent>
          </Select>
        </Field>
      </CardContent>
      <SaveBar s={s} />
    </Card>
  );
}

function NotificationTiming({ data }: { data?: Settings }) {
  const s = useSection("notifications", data);
  if (!s.v) return <TableSkeleton rows={3} cols={2} />;
  const offsets = s.v.default_reminder_offsets;
  return (
    <Card>
      <CardHeader><CardTitle>Notification timing</CardTitle><CardDescription>Defaults applied to new planned interruptions and unexpected outages.</CardDescription></CardHeader>
      <CardContent className="space-y-5">
        <Field label="Default reminders before planned work" error={s.save.fieldErrors.default_reminder_offsets}>
          <div className="flex flex-wrap gap-2">
            {[...PRESET_OFFSETS, { minutes: 2880, label: "2 days before" }].map((p) => (
              <label key={p.minutes} className="flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-1.5 text-sm">
                <Checkbox checked={offsets.includes(p.minutes)} onCheckedChange={(c) => s.set("default_reminder_offsets", c ? [...offsets, p.minutes].sort((a, b) => b - a) : offsets.filter((o) => o !== p.minutes))} />
                {p.label}
              </label>
            ))}
          </div>
        </Field>
        <p className="text-xs text-muted-foreground">Current default: {offsets.length ? offsets.map((o) => offsetLabel(o)).join(", ") + " before" : "no reminders"}.</p>
        <div className="space-y-3">
          {([
            ["send_notice_on_publish", "Send the initial notice when an event is published"],
            ["auto_notify_unexpected", "Automatically alert customers when an unexpected outage is confirmed"],
          ] as const).map(([k, l]) => (
            <label key={k} className="flex items-center justify-between gap-3 rounded-lg border p-3 text-sm"><span>{l}</span><Switch checked={s.v![k]} onCheckedChange={(v) => s.set(k, v)} /></label>
          ))}
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Suggest restoration message at (customers)" htmlFor="rmin" error={s.save.fieldErrors.restoration_min_customers} hint="Restoration messages are never sent automatically.">
            <Input id="rmin" type="number" min={0} value={s.v.restoration_min_customers} onChange={(e) => s.set("restoration_min_customers", Number(e.target.value))} />
          </Field>
          <Field label="Simulated failure rate (%)" htmlFor="fail" error={s.save.fieldErrors.simulated_failure_rate} hint="Demo only: share of simulated messages that fail, to exercise retries.">
            <Input id="fail" type="number" min={0} max={50} step={1} value={Math.round(s.v.simulated_failure_rate * 100)} onChange={(e) => s.set("simulated_failure_rate", Number(e.target.value) / 100)} />
          </Field>
        </div>
      </CardContent>
      <SaveBar s={s} />
    </Card>
  );
}

function Detection({ data }: { data?: Settings }) {
  const s = useSection("detection", data);
  if (!s.v) return <TableSkeleton rows={3} cols={2} />;
  const num = (k: "outage_voltage_max" | "low_voltage_max" | "restore_voltage_min" | "confirm_readings" | "verification_seconds" | "min_meters_for_area_outage" | "stale_after_seconds", label: string, hint: string, unit = "") => (
    <Field label={`${label}${unit ? ` (${unit})` : ""}`} htmlFor={k} error={s.save.fieldErrors[k]} hint={hint}>
      <Input id={k} type="number" value={s.v![k]} onChange={(e) => s.set(k, Number(e.target.value))} />
    </Field>
  );
  return (
    <Card>
      <CardHeader><CardTitle>Outage detection thresholds</CardTitle><CardDescription>Rule-based detection applied to every meter reading. Changes take effect on the next reading.</CardDescription></CardHeader>
      <CardContent className="space-y-5">
        {s.save.error && <ErrorState message={(s.save.error as Error).message} />}
        <div className="grid gap-4 sm:grid-cols-3">
          {num("outage_voltage_max", "No-supply below", "Near-zero voltage means no supply.", "V")}
          {num("low_voltage_max", "Low voltage below", "Brown-out warning threshold.", "V")}
          {num("restore_voltage_min", "Restored at or above", "Hysteresis to avoid flapping.", "V")}
          {num("confirm_readings", "Consecutive readings", "Readings needed to accept a change.")}
          {num("verification_seconds", "Verification period", "Evidence must persist this long before auto-confirmation.", "s")}
          {num("min_meters_for_area_outage", "Meters for an area outage", "A single meter never triggers a community alert.")}
          {num("stale_after_seconds", "Offline after", "No data = communication problem, not an outage.", "s")}
        </div>
        <div className="space-y-3">
          {([
            ["auto_confirm", "Auto-confirm area outages when evidence persists through the verification period"],
            ["auto_resolve_on_restore", "Close incidents automatically when power returns (no customer message)"],
          ] as const).map(([k, l]) => (
            <label key={k} className="flex items-center justify-between gap-3 rounded-lg border p-3 text-sm"><span>{l}</span><Switch checked={s.v![k]} onCheckedChange={(v) => s.set(k, v)} /></label>
          ))}
        </div>
      </CardContent>
      <SaveBar s={s} />
    </Card>
  );
}

function Areas() {
  const areas = useAreas();
  const grids = useMiniGrids();
  const [edit, setEdit] = useState<{ area?: ServiceArea } | null>(null);
  const [f, setF] = useState({ code: "", name: "", description: "", mini_grid_id: "" });
  useEffect(() => {
    if (edit) setF(edit.area ? { code: edit.area.code, name: edit.area.name, description: edit.area.description, mini_grid_id: String(edit.area.mini_grid_id) } : { code: "", name: "", description: "", mini_grid_id: String(grids.data?.[0]?.id ?? "") });
  }, [edit, grids.data]);
  const save = useAction(async () => edit?.area
    ? (await api.patch(`/areas/${edit.area.id}`, { name: f.name, description: f.description })).data
    : api.post("/areas", { ...f, mini_grid_id: Number(f.mini_grid_id) }), { success: edit?.area ? "Service area updated" : "Service area added", onSuccess: () => setEdit(null) });
  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between space-y-0">
        <div><CardTitle>Service areas</CardTitle><CardDescription>Areas used to target notifications and group meters.</CardDescription></div>
        <Button size="sm" onClick={() => setEdit({})}><Plus /> Add area</Button>
      </CardHeader>
      <CardContent className="p-0">
        {areas.isLoading ? <div className="p-4"><TableSkeleton /></div> : (
          <Table>
            <TableHeader><TableRow><TableHead>Code</TableHead><TableHead>Name</TableHead><TableHead>Mini-grid</TableHead><TableHead className="text-right">Customers</TableHead><TableHead className="text-right">Meters</TableHead><TableHead /></TableRow></TableHeader>
            <TableBody>
              {areas.data?.map((a) => (
                <TableRow key={a.id}>
                  <TableCell className="font-mono">{a.code}</TableCell>
                  <TableCell><p className="font-medium">{a.name}</p><p className="text-xs text-muted-foreground">{a.description}</p></TableCell>
                  <TableCell className="text-sm">{a.mini_grid_name}</TableCell>
                  <TableCell className="text-right tabular">{a.customer_count}</TableCell>
                  <TableCell className="text-right tabular">{a.meter_count}</TableCell>
                  <TableCell className="text-right"><Button size="sm" variant="ghost" onClick={() => setEdit({ area: a })}>Edit</Button></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
      <Dialog open={!!edit} onOpenChange={(v) => !v && setEdit(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>{edit?.area ? `Edit ${edit.area.name}` : "Add service area"}</DialogTitle><DialogDescription>Customers and meters are assigned to service areas.</DialogDescription></DialogHeader>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Code" htmlFor="a-code" error={save.fieldErrors.code}><Input id="a-code" value={f.code} disabled={!!edit?.area} onChange={(e) => setF({ ...f, code: e.target.value })} /></Field>
            <Field label="Mini-grid" htmlFor="a-grid" error={save.fieldErrors.mini_grid_id}>
              <Select value={f.mini_grid_id} disabled={!!edit?.area} onValueChange={(v) => setF({ ...f, mini_grid_id: v })}>
                <SelectTrigger id="a-grid"><SelectValue /></SelectTrigger>
                <SelectContent>{grids.data?.map((g) => <SelectItem key={g.id} value={String(g.id)}>{g.name}</SelectItem>)}</SelectContent>
              </Select>
            </Field>
            <Field label="Name" htmlFor="a-name" error={save.fieldErrors.name} className="sm:col-span-2"><Input id="a-name" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
            <Field label="Description" htmlFor="a-desc" className="sm:col-span-2"><Input id="a-desc" value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></Field>
          </div>
          <DialogFooter><Button variant="outline" onClick={() => setEdit(null)}>Cancel</Button><Button disabled={save.isPending || f.name.trim().length < 2 || !f.code.trim()} onClick={() => save.mutate()}>Save</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

function IntegrationCard({ s, icon: Icon, children }: { s: IntegrationStatus; icon: typeof Plug; children?: React.ReactNode }) {
  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-3 space-y-0">
        <div className="flex items-start gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-muted"><Icon className="h-5 w-5" /></div>
          <div><CardTitle>{s.name}</CardTitle><CardDescription>{s.note}</CardDescription></div>
        </div>
        <Badge tone={s.connected ? "success" : "neutral"}>{s.connected ? "Connected" : "Not connected"}</Badge>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        <p className="flex items-center gap-2">{s.configured ? <CheckCircle2 className="h-4 w-4 text-success" /> : <XCircle className="h-4 w-4 text-muted-foreground" />} Credentials {s.configured ? "present in environment" : "not configured"}</p>
        <p className="text-xs text-muted-foreground">Mode: <b>{s.mode.replace("_", " ")}</b>. Secrets are read from backend environment variables (<code>backend/.env</code>) and are never exposed to the browser.</p>
        {children}
      </CardContent>
    </Card>
  );
}

function Integrations({ data }: { data?: Settings }) {
  const [result, setResult] = useState<{ ok: boolean; message: string } | null>(null);
  const test = useAction(() => api.post<{ ok: boolean; message: string }>("/integrations/mpm/test"), { silent: true, onSuccess: setResult });
  if (!data) return <TableSkeleton rows={3} cols={2} />;
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <IntegrationCard s={data.environment.whatsapp} icon={MessageSquare}>
        <ul className="list-disc space-y-1 pl-4 text-xs text-muted-foreground">
          <li>Env: <code>WHATSAPP_ACCESS_TOKEN</code>, <code>WHATSAPP_PHONE_NUMBER_ID</code>, <code>WHATSAPP_BUSINESS_ACCOUNT_ID</code></li>
          <li>Templates must be approved in WhatsApp Manager before live use.</li>
          <li>The prototype only simulates delivery, even when credentials are set.</li>
        </ul>
      </IntegrationCard>
      <IntegrationCard s={data.environment.mpm} icon={Cpu}>
        <ul className="list-disc space-y-1 pl-4 text-xs text-muted-foreground">
          <li>Env: <code>MPM_BASE_URL</code>, <code>MPM_API_TOKEN</code></li>
          <li>REST adapter prepared for MPM’s Laravel plugin architecture. The endpoint mapping must be verified.</li>
        </ul>
        <Button size="sm" variant="outline" disabled={test.isPending} onClick={() => test.mutate()}>{test.isPending ? <Loader2 className="animate-spin" /> : <Plug />} Test connection</Button>
        {result && <p className={`text-xs ${result.ok ? "text-success" : "text-destructive"}`}>{result.message}</p>}
      </IntegrationCard>
    </div>
  );
}

function Demo({ data }: { data?: Settings }) {
  const [confirm, setConfirm] = useState(false);
  const auto = useAction((enabled: boolean) => api.post("/demo/auto-tick", { enabled }), { success: "Saved" });
  const clock = useAction(() => api.post("/demo/clock/reset"), { success: "Demo clock reset" });
  const reset = useAction(() => api.post("/demo/reset"), { success: "Demo data restored" });
  return (
    <Card>
      <CardHeader><CardTitle>Demonstration mode</CardTitle><CardDescription>Controls for presenting the prototype.</CardDescription></CardHeader>
      <CardContent className="space-y-3">
        <label className="flex items-center justify-between gap-3 rounded-lg border p-3 text-sm"><span>Live simulated meter feed (new readings every few seconds)</span><Switch checked={data?.demo.auto_tick ?? true} onCheckedChange={(v) => auto.mutate(v)} /></label>
        <div className="flex items-center justify-between gap-3 rounded-lg border p-3 text-sm">
          <span>Demo clock offset: <b>{((data?.demo.clock_offset_seconds ?? 0) / 3600).toFixed(1)} h</b> ahead of real time</span>
          <Button size="sm" variant="outline" disabled={!data?.demo.clock_offset_seconds} onClick={() => clock.mutate()}><RotateCcw /> Reset clock</Button>
        </div>
        <div className="flex items-center justify-between gap-3 rounded-lg border border-danger/40 p-3 text-sm">
          <span>Restore all demo data to its initial state</span>
          <Button size="sm" variant="destructive" disabled={reset.isPending} onClick={() => setConfirm(true)}>Reset demo data</Button>
        </div>
      </CardContent>
      <ConfirmDialog open={confirm} onOpenChange={setConfirm} title="Reset all demo data?" destructive confirmLabel="Reset demo data"
        description="All events, incidents, notifications and customer changes will be replaced by the original sample data."
        onConfirm={() => { reset.mutate(); setConfirm(false); }} />
    </Card>
  );
}

export default function SettingsPage() {
  const settings = useSettings();
  return (
    <div className="animate-fade-in">
      <PageHeader title="Settings" description="Preferences, notification timing, detection rules, templates, areas and integrations." />
      {settings.error && <ErrorState message={(settings.error as Error).message} onRetry={() => settings.refetch()} />}
      <Tabs defaultValue="general">
        <TabsList>
          <TabsTrigger value="general"><Settings2 /> General</TabsTrigger>
          <TabsTrigger value="timing"><MessageSquare /> Notification timing</TabsTrigger>
          <TabsTrigger value="detection"><ShieldAlert /> Detection</TabsTrigger>
          <TabsTrigger value="templates"><MessageSquare /> Templates</TabsTrigger>
          <TabsTrigger value="areas"><MapPin /> Service areas</TabsTrigger>
          <TabsTrigger value="integrations"><Plug /> Integrations</TabsTrigger>
          <TabsTrigger value="demo"><Info /> Demo</TabsTrigger>
        </TabsList>
        <TabsContent value="general"><General data={settings.data} /></TabsContent>
        <TabsContent value="timing"><NotificationTiming data={settings.data} /></TabsContent>
        <TabsContent value="detection"><Detection data={settings.data} /></TabsContent>
        <TabsContent value="templates"><TemplateEditor /></TabsContent>
        <TabsContent value="areas"><Areas /></TabsContent>
        <TabsContent value="integrations"><Integrations data={settings.data} /></TabsContent>
        <TabsContent value="demo"><Demo data={settings.data} /></TabsContent>
      </Tabs>
    </div>
  );
}
