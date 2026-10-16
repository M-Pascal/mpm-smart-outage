import { AlertCircle, CheckCheck, Inbox, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/table";
import { JOB_STATUS, METER_STATUS, OUTAGE_STATUS, PRIORITY, RESOLUTION, SEVERITY, VERIFICATION } from "@/lib/constants";
import type { JobStatus, MeterStatus, OutageStatus, Severity } from "@/lib/types";
import { cn } from "@/lib/utils";

export function PageHeader({ title, description, actions }: { title: string; description?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

const TONES = {
  brand: "bg-brand-soft text-brand",
  success: "bg-success-soft text-success",
  warning: "bg-warning-soft text-amber-600 dark:text-warning",
  danger: "bg-danger-soft text-danger",
  neutral: "bg-muted text-muted-foreground",
};

export function StatCard({ label, value, hint, icon: Icon, tone = "brand", loading, highlight, onClick }: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  icon: LucideIcon;
  tone?: keyof typeof TONES;
  loading?: boolean;
  highlight?: boolean;
  onClick?: () => void;
}) {
  return (
    <Card
      className={cn("p-4 transition-shadow", onClick && "cursor-pointer hover:shadow-md", highlight && "border-danger/50 ring-1 ring-danger/30")}
      onClick={onClick}
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={onClick ? (e) => (e.key === "Enter" || e.key === " ") && onClick() : undefined}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-medium text-muted-foreground">{label}</p>
          {loading ? <Skeleton className="mt-2 h-8 w-16" /> : <p className="mt-1 text-[1.75rem] font-semibold leading-tight tracking-tight">{value}</p>}
        </div>
        <div className={cn("flex h-9 w-9 shrink-0 items-center justify-center rounded-lg", TONES[tone])}>
          <Icon className="h-[18px] w-[18px]" aria-hidden />
        </div>
      </div>
      {hint && <p className="mt-2 truncate text-xs text-muted-foreground">{hint}</p>}
    </Card>
  );
}

export function EmptyState({ icon: Icon = Inbox, title, description, action, className }: {
  icon?: LucideIcon;
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center justify-center rounded-xl border border-dashed px-6 py-10 text-center", className)}>
      <div className="mb-3 flex h-11 w-11 items-center justify-center rounded-full bg-muted">
        <Icon className="h-5 w-5 text-muted-foreground" aria-hidden />
      </div>
      <p className="text-sm font-medium">{title}</p>
      {description && <p className="mt-1 max-w-sm text-sm text-muted-foreground">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-danger/40 bg-danger-soft p-4 text-sm" role="alert">
      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-danger" />
      <div className="flex-1">
        <p className="font-medium">Could not load data</p>
        <p className="text-muted-foreground">{message}</p>
      </div>
      {onRetry && <Button size="sm" variant="outline" onClick={onRetry}>Retry</Button>}
    </div>
  );
}

export function TableSkeleton({ rows = 5, cols = 5 }: { rows?: number; cols?: number }) {
  return (
    <div className="space-y-2 p-1" aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex gap-3">
          {Array.from({ length: cols }).map((__, j) => <Skeleton key={j} className="h-8 flex-1" />)}
        </div>
      ))}
    </div>
  );
}

export const OutageStatusBadge = ({ status }: { status: OutageStatus }) => {
  const s = OUTAGE_STATUS[status];
  return (
    <Badge tone={s.tone}>
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: s.dot }} aria-hidden />
      {s.label}
    </Badge>
  );
};

export const JobStatusBadge = ({ status, failed }: { status: JobStatus; failed?: number }) => {
  const s = JOB_STATUS[status];
  return (
    <span className="inline-flex items-center gap-1">
      <Badge tone={s.tone}>
        {status === "simulated_sent" && <CheckCheck aria-hidden />}
        {s.label}
      </Badge>
      {status === "simulated_sent" && !!failed && <Badge tone="danger">{failed} failed</Badge>}
    </span>
  );
};

export const MeterStatusBadge = ({ status }: { status: MeterStatus }) => {
  const s = METER_STATUS[status];
  return (
    <Badge tone={s.tone}>
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: s.color }} aria-hidden />
      {s.label}
    </Badge>
  );
};

export const SeverityBadge = ({ severity }: { severity: Severity }) => (
  <Badge tone={SEVERITY[severity].tone} className={cn(severity === "critical" && "border-red-600 bg-red-600 text-white dark:bg-red-600 dark:text-white")}>
    {SEVERITY[severity].label}
  </Badge>
);
export const VerificationBadge = ({ status }: { status: string }) => <Badge tone={VERIFICATION[status]?.tone}>{VERIFICATION[status]?.label ?? status}</Badge>;
export const ResolutionBadge = ({ status }: { status: string }) => <Badge tone={RESOLUTION[status]?.tone}>{RESOLUTION[status]?.label ?? status}</Badge>;
export const PriorityBadge = ({ priority }: { priority: string }) => <Badge tone={PRIORITY[priority]?.tone}>{PRIORITY[priority]?.label ?? priority}</Badge>;

export function SimulatedTag({ className }: { className?: string }) {
  return (
    <Badge tone="warning" className={cn("uppercase tracking-wide", className)}>
      Simulated
    </Badge>
  );
}

export function KeyValue({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="mt-0.5 text-sm font-medium">{children}</dd>
    </div>
  );
}
