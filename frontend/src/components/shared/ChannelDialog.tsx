import { Check, Copy, Megaphone } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { api, errorMessage } from "@/lib/api";
import { WhatsAppText } from "./WhatsAppPreview";

export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    const ta = document.createElement("textarea");
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand("copy");
    ta.remove();
    return ok;
  }
}

/** Generates Channel-ready public text (no private data) for manual posting to a WhatsApp Channel. */
export function ChannelDialog({ open, onOpenChange, source }: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  source: { scheduled_outage_id?: number; incident_id?: number; custom_text?: string } | null;
}) {
  const [text, setText] = useState<string>("");
  const [error, setError] = useState<string>("");
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    if (!open || !source) return;
    setText("");
    setError("");
    setCopied(false);
    api.post<{ text: string }>("/channels/announcement", source).then((r) => setText(r.text)).catch((e) => setError(errorMessage(e)));
  }, [open, source]);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><Megaphone className="h-5 w-5 text-primary" /> WhatsApp Channel announcement</DialogTitle>
          <DialogDescription>Public, Channel-ready text with no customer names or numbers. WhatsApp Channels have no official publishing API, so copy it and post it manually.</DialogDescription>
        </DialogHeader>
        <div className="rounded-lg bg-[#efeae2] p-3 text-[13px] leading-relaxed text-slate-800 dark:bg-[#0b141a] dark:text-slate-100">
          {error ? <p className="text-destructive">{error}</p> : text ? <WhatsAppText text={text} /> : <div className="h-20 animate-pulse rounded bg-white/50" />}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Close</Button>
          <Button disabled={!text} onClick={async () => { if (await copyText(text)) { setCopied(true); toast.success("Announcement copied. Paste it into your WhatsApp Channel."); } }}>
            {copied ? <Check /> : <Copy />} {copied ? "Copied" : "Copy text"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
