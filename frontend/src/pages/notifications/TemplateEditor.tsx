import { RotateCcw, Save } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { TableSkeleton } from "@/components/shared";
import { WhatsAppPreview } from "@/components/shared/WhatsAppPreview";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Field } from "@/components/ui/form-bits";
import { Textarea } from "@/components/ui/input";
import { Tip } from "@/components/ui/menus";
import { useAction, useAreas, useTemplates } from "@/hooks/queries";
import { api, errorMessage } from "@/lib/api";
import type { PreviewResult, Template } from "@/lib/types";
import { cn } from "@/lib/utils";

const SAMPLE_CONTEXT = {
  title: "Transformer maintenance", reason: "planned maintenance", date: "20 October 2026", start_time: "9:00 AM", end_time: "11:00 AM",
  end_date: "20 October 2026", time_until: "24 hours", old_date: "19 October 2026", old_start_time: "8:00 AM", old_end_time: "10:00 AM",
  eta: "around 6:00 PM today", message: "Our office will be closed on Friday.",
};
const CATEGORY_TONE = { planned: "warning", unplanned: "danger", general: "brand" } as const;

export function TemplateEditor() {
  const templates = useTemplates();
  const areas = useAreas();
  const [key, setKey] = useState<string | null>(null);
  const [body, setBody] = useState("");
  const [preview, setPreview] = useState<PreviewResult | null>(null);
  const [err, setErr] = useState("");
  const [confirmReset, setConfirmReset] = useState(false);
  const ref = useRef<HTMLTextAreaElement>(null);
  const list = templates.data?.data ?? [];
  const placeholders = (templates.data?.meta?.placeholders ?? {}) as Record<string, string>;
  const current: Template | undefined = list.find((t) => t.key === key) ?? list[0];

  useEffect(() => {
    if (current) setBody(current.body);
  }, [current?.key, current?.body]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!body || !areas.data?.length) return;
    const id = setTimeout(() => {
      api.post<PreviewResult>("/notifications/preview", { body, area_ids: [areas.data![0].id], context: SAMPLE_CONTEXT })
        .then((p) => { setPreview(p); setErr(""); })
        .catch((e) => setErr(errorMessage(e)));
    }, 300);
    return () => clearTimeout(id);
  }, [body, areas.data]);

  const save = useAction(() => api.put<Template>(`/templates/${current!.key}`, { body }), { success: "Template saved" });
  const reset = useAction(() => api.post<Template>(`/templates/${current!.key}/reset`), { success: "Template restored to default" });
  const dirty = current && body !== current.body;

  const insert = (p: string) => {
    const el = ref.current;
    if (!el) return setBody((b) => `${b}{${p}}`);
    const { selectionStart: s, selectionEnd: e } = el;
    const next = `${body.slice(0, s)}{${p}}${body.slice(e)}`;
    setBody(next);
    requestAnimationFrame(() => { el.focus(); el.selectionStart = el.selectionEnd = s + p.length + 2; });
  };

  if (templates.isLoading) return <TableSkeleton rows={6} cols={2} />;
  return (
    <div className="grid gap-4 lg:grid-cols-[260px_1fr_360px]">
      <Card className="p-2">
        <ul className="space-y-0.5">
          {list.map((t) => (
            <li key={t.key}>
              <button onClick={() => setKey(t.key)} className={cn("w-full rounded-lg px-3 py-2 text-left text-sm transition", current?.key === t.key ? "bg-accent font-medium" : "hover:bg-muted/60")}>
                <span className="block truncate">{t.name}</span>
                <Badge tone={CATEGORY_TONE[t.category as keyof typeof CATEGORY_TONE]} className="mt-1 capitalize">{t.category}</Badge>
              </button>
            </li>
          ))}
        </ul>
      </Card>
      {current && (
        <Card className="space-y-3 p-4">
          <div>
            <h3 className="font-semibold">{current.name}</h3>
            <p className="text-sm text-muted-foreground">{current.description}</p>
          </div>
          <Field label="Message body" htmlFor="tpl-body" error={err || undefined} hint="Use *bold* and _italic_ like WhatsApp. Click a placeholder to insert it.">
            <Textarea id="tpl-body" ref={ref} rows={12} value={body} onChange={(e) => setBody(e.target.value)} className="font-mono text-[13px]" invalid={!!err} />
          </Field>
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(placeholders).map(([p, desc]) => (
              <Tip key={p} content={desc}><button type="button" onClick={() => insert(p)} className="rounded-md border bg-muted/50 px-2 py-0.5 font-mono text-[11px] hover:border-primary hover:text-primary">{`{${p}}`}</button></Tip>
            ))}
          </div>
          <div className="flex flex-wrap justify-end gap-2 border-t pt-3">
            <Button variant="ghost" onClick={() => setConfirmReset(true)}><RotateCcw /> Restore default</Button>
            {dirty && <Button variant="outline" onClick={() => setBody(current.body)}>Discard changes</Button>}
            <Button disabled={!dirty || !!err || save.isPending} onClick={() => save.mutate()}><Save /> Save template</Button>
          </div>
        </Card>
      )}
      <div className="space-y-2">
        <p className="text-sm font-medium">Live preview <span className="font-normal text-muted-foreground">(sample values)</span></p>
        <WhatsAppPreview preview={preview} title={current?.name} />
      </div>
      <ConfirmDialog open={confirmReset} onOpenChange={setConfirmReset} title="Restore the default template?" description="Your edits to this template will be replaced by the original text." confirmLabel="Restore default" destructive
        onConfirm={() => { reset.mutate(); setConfirmReset(false); }} />
    </div>
  );
}
