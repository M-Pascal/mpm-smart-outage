import type { JobStatus, MeterStatus, OutageStatus, Reason, Severity } from "./types";

type Tone = "neutral" | "brand" | "success" | "warning" | "danger" | "violet" | "muted";

export const OUTAGE_STATUS: Record<OutageStatus, { label: string; tone: Tone; dot: string }> = {
  draft: { label: "Draft", tone: "muted", dot: "#94a3b8" },
  scheduled: { label: "Scheduled", tone: "brand", dot: "#2563EB" },
  notification_queued: { label: "Notification queued", tone: "warning", dot: "#F59E0B" },
  in_progress: { label: "In progress", tone: "violet", dot: "#7c3aed" },
  completed: { label: "Completed", tone: "success", dot: "#10B981" },
  cancelled: { label: "Cancelled", tone: "neutral", dot: "#64748b" },
};

export const JOB_STATUS: Record<JobStatus, { label: string; tone: Tone }> = {
  draft: { label: "Draft", tone: "muted" },
  scheduled: { label: "Scheduled", tone: "brand" },
  processing: { label: "Processing", tone: "violet" },
  simulated_sent: { label: "Simulated sent", tone: "success" },
  failed: { label: "Failed", tone: "danger" },
  cancelled: { label: "Cancelled", tone: "neutral" },
};

export const METER_STATUS: Record<MeterStatus, { label: string; tone: Tone; color: string }> = {
  normal: { label: "Normal", tone: "success", color: "#10B981" },
  low_voltage: { label: "Low voltage", tone: "warning", color: "#F59E0B" },
  no_supply: { label: "No supply", tone: "danger", color: "#EF4444" },
  offline: { label: "Offline", tone: "neutral", color: "#64748b" },
};

export const SEVERITY: Record<Severity, { label: string; tone: Tone }> = {
  low: { label: "Low", tone: "neutral" },
  medium: { label: "Medium", tone: "warning" },
  high: { label: "High", tone: "danger" },
  critical: { label: "Critical", tone: "danger" },
};

export const VERIFICATION: Record<string, { label: string; tone: Tone }> = {
  potential: { label: "Potential", tone: "warning" },
  confirmed: { label: "Confirmed", tone: "danger" },
  rejected: { label: "Rejected", tone: "neutral" },
};

export const RESOLUTION: Record<string, { label: string; tone: Tone }> = {
  open: { label: "Open", tone: "danger" },
  investigating: { label: "Investigating", tone: "warning" },
  resolved: { label: "Resolved", tone: "success" },
};

export const REASONS: Record<Reason, string> = {
  planned_maintenance: "Planned maintenance",
  equipment_replacement: "Equipment replacement",
  network_upgrade: "Network upgrade",
  load_shedding: "Planned load shedding",
  safety_inspection: "Safety inspection",
  other: "Other",
};

export const PRIORITY: Record<string, { label: string; tone: Tone }> = {
  low: { label: "Low", tone: "neutral" },
  medium: { label: "Medium", tone: "brand" },
  high: { label: "High", tone: "warning" },
  critical: { label: "Critical", tone: "danger" },
};

export const CUSTOMER_TYPES: Record<string, string> = {
  residential: "Residential",
  commercial: "Commercial",
  productive_use: "Productive use",
  public_institution: "Public institution",
  essential_service: "Essential service",
};

export const PRESET_OFFSETS = [
  { minutes: 1440, label: "24 hours before" },
  { minutes: 360, label: "6 hours before" },
  { minutes: 60, label: "1 hour before" },
];

export const CHART = {
  power: "#2563EB",
  voltage: "#10B981",
  planned: "#F59E0B",
  unexpected: "#EF4444",
  sent: "#10B981",
  failed: "#EF4444",
};
