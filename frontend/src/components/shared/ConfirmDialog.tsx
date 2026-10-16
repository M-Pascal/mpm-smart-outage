import { useEffect, useState, type ReactNode } from "react";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Field } from "@/components/ui/form-bits";
import { Textarea } from "@/components/ui/input";

/** Confirmation for destructive / outward-facing actions, with an optional text input (e.g. a reason). */
export function ConfirmDialog({ open, onOpenChange, title, description, confirmLabel = "Confirm", destructive, input, onConfirm, children }: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  title: string;
  description?: ReactNode;
  confirmLabel?: string;
  destructive?: boolean;
  input?: { label: string; placeholder?: string; required?: boolean };
  onConfirm: (value: string) => void;
  children?: ReactNode;
}) {
  const [value, setValue] = useState("");
  useEffect(() => {
    if (open) setValue("");
  }, [open]);
  const blocked = !!input?.required && !value.trim();
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          {description && <AlertDialogDescription asChild><div>{description}</div></AlertDialogDescription>}
        </AlertDialogHeader>
        {input && (
          <Field label={input.label} htmlFor="confirm-input">
            <Textarea id="confirm-input" rows={2} value={value} placeholder={input.placeholder} onChange={(e) => setValue(e.target.value)} />
          </Field>
        )}
        {children}
        <AlertDialogFooter>
          <AlertDialogCancel>Go back</AlertDialogCancel>
          <AlertDialogAction destructive={destructive} disabled={blocked} onClick={() => onConfirm(value.trim())}>
            {confirmLabel}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
