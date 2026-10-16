import { CheckCheck, FlaskConical, Users } from "lucide-react";
import { Fragment, type ReactNode } from "react";
import type { PreviewResult } from "@/lib/types";
import { cn } from "@/lib/utils";

/** Renders WhatsApp-style *bold* and _italic_ markup. */
export function WhatsAppText({ text }: { text: string }) {
  const lines = text.split("\n");
  return (
    <>
      {lines.map((line, i) => (
        <Fragment key={i}>
          {line.split(/(\*[^*]+\*|_[^_]+_|\{[a-z_]+\})/g).map((part, j) => {
            if (/^\*[^*]+\*$/.test(part)) return <strong key={j}>{part.slice(1, -1)}</strong>;
            if (/^_[^_]+_$/.test(part)) return <em key={j}>{part.slice(1, -1)}</em>;
            if (/^\{[a-z_]+\}$/.test(part)) return <mark key={j} className="rounded bg-amber-200/80 px-0.5 text-amber-900">{part}</mark>;
            return <Fragment key={j}>{part}</Fragment>;
          })}
          {i < lines.length - 1 && <br />}
        </Fragment>
      ))}
    </>
  );
}

export function WhatsAppBubble({ body, time, status, className }: { body: string; time?: string; status?: ReactNode; className?: string }) {
  return (
    <div className={cn("relative max-w-[95%] rounded-lg rounded-tl-none bg-white px-3 py-2 text-[13px] leading-relaxed text-slate-800 shadow-sm dark:bg-[#202c33] dark:text-slate-100", className)}>
      <WhatsAppText text={body} />
      <div className="mt-1 flex items-center justify-end gap-1 text-[10px] text-slate-400">
        {time}
        {status ?? <CheckCheck className="h-3 w-3" aria-hidden />}
      </div>
    </div>
  );
}

export function WhatsAppPreview({ preview, title = "Message preview", time, loading, className }: {
  preview?: PreviewResult | null;
  title?: string;
  time?: string;
  loading?: boolean;
  className?: string;
}) {
  return (
    <div className={cn("overflow-hidden rounded-xl border", className)}>
      <div className="flex items-center justify-between gap-2 bg-[#075e54] px-3 py-2 text-white dark:bg-[#1f2c34]">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-full bg-white/20 text-[10px] font-bold">PC</div>
          <div className="leading-tight">
            <p className="text-sm font-medium">{title}</p>
            <p className="text-[10px] text-white/70">WhatsApp Business · template message</p>
          </div>
        </div>
        <span className="inline-flex items-center gap-1 rounded bg-amber-400 px-1.5 py-0.5 text-[10px] font-bold uppercase text-amber-950">
          <FlaskConical className="h-3 w-3" /> Simulated
        </span>
      </div>
      <div className="min-h-[120px] bg-[#efeae2] p-3 dark:bg-[#0b141a]">
        {loading && !preview ? (
          <div className="h-24 w-4/5 animate-pulse rounded-lg bg-white/70 dark:bg-white/10" />
        ) : preview ? (
          <WhatsAppBubble body={preview.body} time={time} />
        ) : (
          <p className="pt-8 text-center text-xs text-slate-500">Select service areas to preview the message.</p>
        )}
      </div>
      {preview && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t bg-card px-3 py-2 text-xs">
          <span className="inline-flex items-center gap-1 font-medium">
            <Users className="h-3.5 w-3.5 text-muted-foreground" />
            {preview.recipients.eligible} of {preview.recipients.total_in_areas} customers will receive this
          </span>
          {Object.entries(preview.recipients.excluded).map(([reason, n]) => (
            <span key={reason} className="text-muted-foreground">· {n} excluded ({reason})</span>
          ))}
          {preview.missing_placeholders.length > 0 && (
            <span className="font-medium text-amber-600">· Missing values: {preview.missing_placeholders.join(", ")}</span>
          )}
        </div>
      )}
    </div>
  );
}
