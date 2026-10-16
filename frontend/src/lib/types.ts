export type MeterStatus = "normal" | "low_voltage" | "no_supply" | "offline";
export type OutageStatus = "draft" | "scheduled" | "notification_queued" | "in_progress" | "completed" | "cancelled";
export type JobStatus = "draft" | "scheduled" | "processing" | "simulated_sent" | "failed" | "cancelled";
export type Severity = "low" | "medium" | "high" | "critical";
export type Reason = "planned_maintenance" | "equipment_replacement" | "network_upgrade" | "load_shedding" | "safety_inspection" | "other";
export type Priority = "low" | "medium" | "high" | "critical";

export interface AreaRef { id: number; code: string; name: string }

export interface ServiceArea extends AreaRef {
  description: string;
  mini_grid_id: number;
  mini_grid_name: string;
  sim_scenario: string | null;
  customer_count: number;
  meter_count: number;
  meters_online: number;
  meters_offline: number;
  meters_no_supply: number;
  meters_low_voltage: number;
  avg_voltage: number | null;
  total_power_kw: number;
  planned_outage: { id: number; code: string; title: string } | null;
  open_incident: { id: number; code: string; severity: Severity; verification_status: string } | null;
}

export interface MiniGrid { id: number; name: string; district: string; capacity_kw: number; service_areas: AreaRef[] }

export interface Meter {
  id: number;
  serial: string;
  service_area_id: number;
  service_area_name: string;
  customer_id: number | null;
  customer_name: string | null;
  status: MeterStatus;
  voltage: number | null;
  current: number | null;
  power_kw: number | null;
  last_reading_at: string | null;
  status_since: string | null;
  pending_status: MeterStatus | null;
  pending_count: number;
  sim_scenario: string | null;
}

export interface Customer {
  id: number;
  code: string;
  name: string;
  phone: string;
  service_area_id: number;
  service_area_name: string;
  customer_type: string;
  notification_preference: "whatsapp" | "sms" | "none";
  whatsapp_opt_in: boolean;
  account_status: "active" | "suspended" | "inactive";
  notes: string;
  meter_id: number | null;
  meter_serial: string | null;
  whatsapp_eligible: boolean;
  ineligible_reason: string | null;
  created_at: string;
  updated_at: string;
  recent_messages?: Message[];
}

export interface Job {
  id: number;
  code: string;
  kind: string;
  kind_label: string;
  template_key: string;
  area_ids: number[];
  context: Record<string, string>;
  send_at: string;
  offset_minutes: number | null;
  status: JobStatus;
  recipients_count: number;
  sent_count: number;
  failed_count: number;
  note: string;
  created_by: string;
  created_at: string;
  processed_at: string | null;
  linked: { type: "scheduled_outage" | "incident"; id: number; code: string; title: string } | null;
  simulated: boolean;
  messages?: Message[];
  preview?: string | null;
}

export interface Message {
  id: number;
  job_id: number;
  customer_id: number;
  customer_name: string;
  service_area_name: string;
  phone: string;
  body: string;
  status: "simulated_sent" | "failed";
  attempts: number;
  error: string;
  simulated_message_id: string;
  created_at: string;
  updated_at: string;
}

export interface ScheduledOutage {
  id: number;
  code: string;
  title: string;
  reason: Reason;
  reason_label: string;
  reason_detail: string;
  mini_grid_id: number;
  mini_grid_name: string;
  service_areas: AreaRef[];
  start_at: string;
  end_at: string;
  description: string;
  priority: Priority;
  status: OutageStatus;
  reminder_offsets: number[];
  send_notice_on_publish: boolean;
  customers_notified: boolean;
  published_at: string | null;
  cancelled_at: string | null;
  cancel_reason: string;
  reschedule_count: number;
  affected_customers: number;
  eligible_recipients: number;
  notifications_pending: number;
  notifications_sent: number;
  next_notification_at: string | null;
  created_at: string;
  updated_at: string;
  notifications?: Job[];
}

export interface IncidentEvent { id: number; ts: string; type: string; message: string; actor: string }

export interface Incident {
  id: number;
  code: string;
  service_area_id: number;
  service_area_name: string;
  mini_grid_name: string;
  scope: "meter" | "area";
  severity: Severity;
  verification_status: "potential" | "confirmed" | "rejected";
  resolution_status: "open" | "investigating" | "resolved";
  confirmation_method: "auto" | "manual" | null;
  first_evidence_at: string | null;
  detected_at: string;
  confirmed_at: string | null;
  acknowledged_at: string | null;
  acknowledged_by: string | null;
  power_restored_at: string | null;
  resolved_at: string | null;
  affected_meters: number;
  peak_affected_meters: number;
  area_meter_count: number;
  estimated_customers: number;
  resolution_note: string;
  restoration_suggested: boolean;
  events?: IncidentEvent[];
  notifications?: Job[];
  affected_meter_list?: Meter[];
}

export interface Activity {
  id: number;
  ts: string;
  type: string;
  severity: "info" | "success" | "warning" | "critical";
  message: string;
  entity_type: string | null;
  entity_id: number | null;
  operator_alert: boolean;
  read: boolean;
}

export interface Dashboard {
  generated_at: string;
  summary: {
    total_meters: number;
    active_meters: number;
    offline_meters: number;
    meters_no_supply: number;
    scheduled_interruptions: number;
    planned_in_progress: number;
    unexpected_outages: number;
    unconfirmed_incidents: number;
    customers_affected: number;
    notifications_scheduled: number;
    avg_voltage: number | null;
    total_power_kw: number;
    total_customers: number;
  };
  areas: ServiceArea[];
  upcoming_maintenance: ScheduledOutage[];
  active_incidents: Incident[];
  recent_activity: Activity[];
}

export interface SeriesPoint { ts: string; voltage: number | null; power_kw: number; current?: number }

export interface Template { id: number; key: string; name: string; category: string; description: string; body: string; updated_at: string }

export interface PreviewResult {
  body: string;
  missing_placeholders: string[];
  recipients: { eligible: number; total_in_areas: number; excluded: Record<string, number> };
}

export interface PlanItem { kind: "notice" | "reminder"; offset_minutes: number | null; send_at: string; valid: boolean; label: string; reason: string }

export interface PlanPreview {
  schedule: PlanItem[];
  messages: { notice?: PreviewResult; reminder?: PreviewResult; reschedule?: PreviewResult };
  recipients: PreviewResult["recipients"];
  start_in_past: boolean;
}

export interface Settings {
  general: { organization_name: string; timezone: string; operator_name: string; date_format: string };
  notifications: { default_reminder_offsets: number[]; send_notice_on_publish: boolean; auto_notify_unexpected: boolean; restoration_min_customers: number; simulated_failure_rate: number };
  detection: { outage_voltage_max: number; low_voltage_max: number; restore_voltage_min: number; confirm_readings: number; verification_seconds: number; min_meters_for_area_outage: number; stale_after_seconds: number; auto_confirm: boolean; auto_resolve_on_restore: boolean };
  demo: { clock_offset_seconds: number; auto_tick: boolean };
  environment: { whatsapp: IntegrationStatus; mpm: IntegrationStatus };
}

export interface IntegrationStatus { name: string; configured: boolean; connected: boolean; mode: string; note: string; [k: string]: unknown }

export interface DemoClock { now: string; offset_seconds: number; auto_tick: boolean; next_notification: Job | null }

export interface SearchResult { type: "customer" | "meter" | "scheduled_outage" | "service_area" | "incident"; id: number; title: string; subtitle: string }

export interface Analytics {
  simulated: boolean;
  period_days: number;
  kpis: {
    planned_interruptions: number;
    cancelled_interruptions: number;
    unexpected_outages: number;
    confirmed_outages: number;
    avg_unexpected_duration_min: number | null;
    avg_planned_duration_min: number | null;
    avg_detection_seconds: number | null;
    avg_confirmation_seconds: number | null;
    avg_notification_prep_seconds: number | null;
    avg_advance_notice_hours: number | null;
    messages_sent: number;
    messages_failed: number;
    failure_rate: number;
  };
  weekly: { week_start: string; planned: number; unexpected: number }[];
  areas: { service_area_id: number; name: string; code: string; unexpected: number; planned: number; customer_hours_lost: number }[];
  messages_by_kind: { kind: string; sent: number; failed: number }[];
  severity: { severity: Severity; count: number }[];
  durations: { code: string; area: string; minutes: number; detected_at: string }[];
}
