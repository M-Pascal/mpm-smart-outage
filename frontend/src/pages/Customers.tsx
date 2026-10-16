import { CheckCircle2, MessageCircleOff, Pencil, Plus, Search, ShieldCheck, UserPlus, Users, XCircle } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { EmptyState, ErrorState, KeyValue, PageHeader, StatCard, TableSkeleton } from "@/components/shared";
import { WhatsAppBubble } from "@/components/shared/WhatsAppPreview";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, SheetContent } from "@/components/ui/dialog";
import { Checkbox, Field, Switch } from "@/components/ui/form-bits";
import { Input, Textarea } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useAction, useAreas, useCustomer, useCustomers } from "@/hooks/queries";
import { api } from "@/lib/api";
import { CUSTOMER_TYPES } from "@/lib/constants";
import { formatDate, formatDateTime } from "@/lib/format";
import type { Customer } from "@/lib/types";

const ACCOUNT_TONE = { active: "success", suspended: "warning", inactive: "neutral" } as const;
const PREF_LABEL = { whatsapp: "WhatsApp", sms: "SMS", none: "No messages" };

interface FormState {
  name: string; phone: string; service_area_id: string; customer_type: string; notification_preference: "whatsapp" | "sms" | "none";
  whatsapp_opt_in: boolean; account_status: "active" | "suspended" | "inactive"; notes: string; create_meter: boolean;
}

function CustomerForm({ open, onOpenChange, customer, onSaved }: { open: boolean; onOpenChange: (v: boolean) => void; customer?: Customer | null; onSaved: (c: Customer) => void }) {
  const areas = useAreas();
  const [f, setF] = useState<FormState | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  useEffect(() => {
    if (!open) return;
    setErrors({});
    setF(customer ? {
      name: customer.name, phone: customer.phone, service_area_id: String(customer.service_area_id), customer_type: customer.customer_type,
      notification_preference: customer.notification_preference, whatsapp_opt_in: customer.whatsapp_opt_in, account_status: customer.account_status, notes: customer.notes, create_meter: false,
    } : { name: "", phone: "+250", service_area_id: "", customer_type: "residential", notification_preference: "whatsapp", whatsapp_opt_in: false, account_status: "active", notes: "", create_meter: true });
  }, [open, customer]);
  const save = useAction(async (form: FormState) => {
    const body = { ...form, service_area_id: Number(form.service_area_id) };
    if (customer) {
      const { create_meter: _, ...patch } = body;
      return (await api.patch<Customer>(`/customers/${customer.id}`, patch)).data;
    }
    return api.post<Customer>("/customers", body);
  }, { success: (c) => `${c.name} ${customer ? "updated" : "added"}`, onSuccess: (c) => { onSaved(c); onOpenChange(false); } });
  useEffect(() => setErrors((e) => ({ ...e, ...save.fieldErrors })), [save.fieldErrors]);

  const submit = () => {
    if (!f) return;
    const e: Record<string, string> = {};
    if (f.name.trim().length < 2) e.name = "Enter the customer's name.";
    if (!/^\+[1-9]\d{7,14}$/.test(f.phone.replace(/\s/g, ""))) e.phone = "Use international format, e.g. +250700100001.";
    if (!f.service_area_id) e.service_area_id = "Select a service area.";
    setErrors(e);
    if (!Object.keys(e).length) save.mutate({ ...f, phone: f.phone.replace(/\s/g, "") });
  };
  const set = <K extends keyof FormState>(k: K, v: FormState[K]) => setF((p) => (p ? { ...p, [k]: v } : p));

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>{customer ? `Edit ${customer.name}` : "Add customer"}</DialogTitle>
          <DialogDescription>Only customers with WhatsApp consent, an active account and the WhatsApp preference receive messages.</DialogDescription>
        </DialogHeader>
        {f && (
          <form className="grid gap-4 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); submit(); }} noValidate>
            <Field label="Full name" htmlFor="c-name" error={errors.name} className="sm:col-span-2">
              <Input id="c-name" value={f.name} invalid={!!errors.name} onChange={(e) => set("name", e.target.value)} />
            </Field>
            <Field label="Phone number" htmlFor="c-phone" error={errors.phone} hint="International (E.164) format">
              <Input id="c-phone" value={f.phone} invalid={!!errors.phone} onChange={(e) => set("phone", e.target.value)} inputMode="tel" />
            </Field>
            <Field label="Service area" htmlFor="c-area" error={errors.service_area_id}>
              <Select value={f.service_area_id} onValueChange={(v) => set("service_area_id", v)}>
                <SelectTrigger id="c-area" invalid={!!errors.service_area_id}><SelectValue placeholder="Select area" /></SelectTrigger>
                <SelectContent>{areas.data?.map((a) => <SelectItem key={a.id} value={String(a.id)}>{a.name}</SelectItem>)}</SelectContent>
              </Select>
            </Field>
            <Field label="Customer type" htmlFor="c-type">
              <Select value={f.customer_type} onValueChange={(v) => set("customer_type", v)}>
                <SelectTrigger id="c-type"><SelectValue /></SelectTrigger>
                <SelectContent>{Object.entries(CUSTOMER_TYPES).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}</SelectContent>
              </Select>
            </Field>
            <Field label="Account status" htmlFor="c-status">
              <Select value={f.account_status} onValueChange={(v) => set("account_status", v as FormState["account_status"])}>
                <SelectTrigger id="c-status"><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="active">Active</SelectItem><SelectItem value="suspended">Suspended</SelectItem><SelectItem value="inactive">Inactive</SelectItem></SelectContent>
              </Select>
            </Field>
            <Field label="Notification preference" htmlFor="c-pref">
              <Select value={f.notification_preference} onValueChange={(v) => set("notification_preference", v as FormState["notification_preference"])}>
                <SelectTrigger id="c-pref"><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="whatsapp">WhatsApp</SelectItem><SelectItem value="sms">SMS (not in prototype)</SelectItem><SelectItem value="none">No messages</SelectItem></SelectContent>
              </Select>
            </Field>
            <label className="flex items-center justify-between gap-3 rounded-lg border p-3 text-sm sm:col-span-1">
              <span><span className="font-medium">WhatsApp consent</span><span className="block text-xs text-muted-foreground">Customer agreed to receive messages</span></span>
              <Switch checked={f.whatsapp_opt_in} onCheckedChange={(v) => set("whatsapp_opt_in", v)} aria-label="WhatsApp consent" />
            </label>
            {!customer && (
              <label className="flex items-center gap-2 text-sm sm:col-span-2">
                <Checkbox checked={f.create_meter} onCheckedChange={(v) => set("create_meter", !!v)} /> Link a new simulated smart meter
              </label>
            )}
            <Field label="Notes" htmlFor="c-notes" className="sm:col-span-2">
              <Textarea id="c-notes" rows={2} value={f.notes} onChange={(e) => set("notes", e.target.value)} />
            </Field>
            <button type="submit" className="hidden" />
          </form>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button disabled={save.isPending} onClick={submit}>{customer ? "Save changes" : "Add customer"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function CustomerDetail({ id, onClose, onEdit }: { id: number | null; onClose: () => void; onEdit: (c: Customer) => void }) {
  const q = useCustomer(id);
  const c = q.data;
  return (
    <Dialog open={id != null} onOpenChange={(v) => !v && onClose()}>
      <SheetContent>
        {!c ? <div className="p-6"><TableSkeleton rows={6} cols={2} /></div> : (
          <>
            <div className="border-b p-6 pr-12">
              <p className="font-mono text-xs text-muted-foreground">{c.code}</p>
              <DialogTitle className="mt-1 text-xl font-semibold">{c.name}</DialogTitle>
              <DialogDescription className="mt-1 text-sm text-muted-foreground">{CUSTOMER_TYPES[c.customer_type]} · {c.service_area_name}</DialogDescription>
              <Button size="sm" variant="outline" className="mt-4" onClick={() => onEdit(c)}><Pencil /> Edit customer</Button>
            </div>
            <div className="space-y-6 p-6">
              <div className={`flex items-start gap-3 rounded-lg p-3 text-sm ${c.whatsapp_eligible ? "bg-success-soft" : "bg-muted"}`}>
                {c.whatsapp_eligible ? <ShieldCheck className="mt-0.5 h-4 w-4 text-success" /> : <MessageCircleOff className="mt-0.5 h-4 w-4 text-muted-foreground" />}
                <p>{c.whatsapp_eligible ? "Included in WhatsApp notifications for this service area." : <>Excluded from WhatsApp notifications: <b>{c.ineligible_reason}</b>.</>}</p>
              </div>
              <dl className="grid grid-cols-2 gap-4">
                <KeyValue label="Phone">{c.phone}</KeyValue>
                <KeyValue label="Linked meter">{c.meter_serial ?? "No smart meter"}</KeyValue>
                <KeyValue label="Preference">{PREF_LABEL[c.notification_preference]}</KeyValue>
                <KeyValue label="WhatsApp consent">{c.whatsapp_opt_in ? "Given" : "Not given"}</KeyValue>
                <KeyValue label="Account">{c.account_status}</KeyValue>
                <KeyValue label="Customer since">{formatDate(c.created_at)}</KeyValue>
              </dl>
              {c.notes && <p className="rounded-lg bg-muted/50 p-3 text-sm">{c.notes}</p>}
              <div>
                <h4 className="mb-3 text-sm font-semibold">Recent messages (simulated)</h4>
                {!c.recent_messages?.length ? <EmptyState title="No messages yet" /> : (
                  <div className="space-y-3 rounded-xl bg-[#efeae2] p-3 dark:bg-[#0b141a]">
                    {c.recent_messages.map((m) => (
                      <WhatsAppBubble key={m.id} body={m.body} time={formatDateTime(m.created_at)}
                        status={m.status === "failed" ? <XCircle className="h-3 w-3 text-danger" aria-label="failed" /> : undefined} />
                    ))}
                  </div>
                )}
              </div>
            </div>
          </>
        )}
      </SheetContent>
    </Dialog>
  );
}

export default function Customers() {
  const [params, setParams] = useSearchParams();
  const customers = useCustomers();
  const areas = useAreas();
  const [q, setQ] = useState("");
  const [area, setArea] = useState("all");
  const [consent, setConsent] = useState("all");
  const [account, setAccount] = useState("all");
  const [form, setForm] = useState<{ customer?: Customer | null } | null>(null);
  const selected = params.get("id") ? Number(params.get("id")) : null;
  const data = customers.data ?? [];
  const list = useMemo(() => data.filter((c) => {
    const ql = q.toLowerCase();
    return (!ql || c.name.toLowerCase().includes(ql) || c.phone.includes(ql) || c.code.toLowerCase().includes(ql) || (c.meter_serial ?? "").toLowerCase().includes(ql))
      && (area === "all" || String(c.service_area_id) === area)
      && (consent === "all" || (consent === "eligible" ? c.whatsapp_eligible : consent === "opted_in" ? c.whatsapp_opt_in : !c.whatsapp_opt_in))
      && (account === "all" || c.account_status === account);
  }), [data, q, area, consent, account]);

  return (
    <div className="animate-fade-in">
      <PageHeader title="Customer management" description="Customers, linked meters and notification consent." actions={<Button onClick={() => setForm({})}><UserPlus /> Add customer</Button>} />
      <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard label="Customers" value={data.length} icon={Users} loading={customers.isLoading} />
        <StatCard label="Reachable on WhatsApp" value={data.filter((c) => c.whatsapp_eligible).length} hint="Consent + active + WhatsApp preference" icon={CheckCircle2} tone="success" loading={customers.isLoading} />
        <StatCard label="No WhatsApp consent" value={data.filter((c) => !c.whatsapp_opt_in).length} icon={MessageCircleOff} tone="neutral" loading={customers.isLoading} />
        <StatCard label="Without smart meter" value={data.filter((c) => !c.meter_serial).length} icon={Plus} tone="warning" loading={customers.isLoading} />
      </div>
      <Card>
        <div className="flex flex-wrap items-center gap-2 border-b p-4">
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Name, phone, CUS-… or meter" className="w-60 pl-8" aria-label="Search customers" />
          </div>
          <Select value={area} onValueChange={setArea}>
            <SelectTrigger className="w-48" aria-label="Service area"><SelectValue /></SelectTrigger>
            <SelectContent><SelectItem value="all">All service areas</SelectItem>{areas.data?.map((a) => <SelectItem key={a.id} value={String(a.id)}>{a.name}</SelectItem>)}</SelectContent>
          </Select>
          <Select value={consent} onValueChange={setConsent}>
            <SelectTrigger className="w-44" aria-label="Consent"><SelectValue /></SelectTrigger>
            <SelectContent><SelectItem value="all">Any consent</SelectItem><SelectItem value="eligible">WhatsApp reachable</SelectItem><SelectItem value="opted_in">Opted in</SelectItem><SelectItem value="opted_out">Not opted in</SelectItem></SelectContent>
          </Select>
          <Select value={account} onValueChange={setAccount}>
            <SelectTrigger className="w-36" aria-label="Account status"><SelectValue /></SelectTrigger>
            <SelectContent><SelectItem value="all">Any account</SelectItem><SelectItem value="active">Active</SelectItem><SelectItem value="suspended">Suspended</SelectItem><SelectItem value="inactive">Inactive</SelectItem></SelectContent>
          </Select>
          <span className="ml-auto text-xs text-muted-foreground">{list.length} of {data.length}</span>
        </div>
        <CardContent className="p-0">
          {customers.error ? <div className="p-4"><ErrorState message={(customers.error as Error).message} /></div> : customers.isLoading ? <div className="p-4"><TableSkeleton rows={8} cols={7} /></div> : list.length === 0 ? (
            <div className="p-6"><EmptyState icon={Users} title="No customers match" description="Adjust the filters or add a customer." /></div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Customer</TableHead>
                  <TableHead>Phone</TableHead>
                  <TableHead>Service area</TableHead>
                  <TableHead>Meter</TableHead>
                  <TableHead>Preference</TableHead>
                  <TableHead>WhatsApp</TableHead>
                  <TableHead>Account</TableHead>
                  <TableHead className="w-10"><span className="sr-only">Edit</span></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {list.map((c) => (
                  <TableRow key={c.id} className="cursor-pointer" onClick={() => setParams({ id: String(c.id) })}>
                    <TableCell><p className="font-medium">{c.name}</p><p className="text-xs text-muted-foreground"><span className="font-mono">{c.code}</span> · {CUSTOMER_TYPES[c.customer_type]}</p></TableCell>
                    <TableCell className="font-mono text-xs">{c.phone}</TableCell>
                    <TableCell className="text-sm">{c.service_area_name}</TableCell>
                    <TableCell className="font-mono text-xs">{c.meter_serial ?? <span className="font-sans text-muted-foreground">—</span>}</TableCell>
                    <TableCell className="text-sm">{PREF_LABEL[c.notification_preference]}</TableCell>
                    <TableCell>{c.whatsapp_eligible ? <Badge tone="success"><CheckCircle2 /> Opted in</Badge> : <Badge tone="neutral" title={c.ineligible_reason ?? ""}>{c.whatsapp_opt_in ? c.ineligible_reason : "No consent"}</Badge>}</TableCell>
                    <TableCell><Badge tone={ACCOUNT_TONE[c.account_status]} className="capitalize">{c.account_status}</Badge></TableCell>
                    <TableCell onClick={(e) => e.stopPropagation()}><Button variant="ghost" size="icon" aria-label={`Edit ${c.name}`} onClick={() => setForm({ customer: c })}><Pencil /></Button></TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
      <CustomerDetail id={selected} onClose={() => setParams({})} onEdit={(c) => setForm({ customer: c })} />
      <CustomerForm open={!!form} onOpenChange={(v) => !v && setForm(null)} customer={form?.customer} onSaved={(c) => setParams({ id: String(c.id) })} />
    </div>
  );
}
