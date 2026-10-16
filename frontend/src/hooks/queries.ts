import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/api";
import type {
  Analytics, Customer, Dashboard, DemoClock, Incident, Integrations, Job, Message, Meter, MiniGrid, ScheduledOutage, SeriesPoint, ServiceArea, Settings, Template,
} from "@/lib/types";

const LIVE = 3000;

export const useDashboard = () => useQuery({ queryKey: ["dashboard"], queryFn: () => api.get<Dashboard>("/dashboard"), refetchInterval: LIVE });
export const useAreas = () => useQuery({ queryKey: ["areas"], queryFn: () => api.get<ServiceArea[]>("/areas"), refetchInterval: LIVE });
export const useMiniGrids = () => useQuery({ queryKey: ["mini-grids"], queryFn: () => api.get<MiniGrid[]>("/mini-grids"), staleTime: 60_000 });
export const useMeters = () => useQuery({ queryKey: ["meters"], queryFn: () => api.get<Meter[]>("/meters"), refetchInterval: LIVE });
export const useSeries = (range: string, areaId?: number | null) =>
  useQuery({
    queryKey: ["series", range, areaId ?? "all"],
    queryFn: () => api.get<SeriesPoint[]>(`/monitoring/series?range=${range}${areaId ? `&area_id=${areaId}` : ""}`),
    refetchInterval: range === "1h" || range === "6h" ? LIVE : 30_000,
    placeholderData: (prev) => prev,
  });
export const useMeterReadings = (id: number | null, range: string) =>
  useQuery({
    queryKey: ["meter-readings", id, range],
    queryFn: () => api.get<SeriesPoint[]>(`/meters/${id}/readings?range=${range}`),
    enabled: id != null,
    refetchInterval: 10_000,
    placeholderData: (prev) => prev,
  });
export const useScheduled = () =>
  useQuery({ queryKey: ["scheduled"], queryFn: () => api.get<ScheduledOutage[]>("/outages/scheduled"), refetchInterval: LIVE });
export const useScheduledOne = (id: number | null) =>
  useQuery({ queryKey: ["scheduled", id], queryFn: () => api.get<ScheduledOutage>(`/outages/scheduled/${id}`), enabled: id != null, refetchInterval: LIVE });
export const useIncidents = (status = "all") =>
  useQuery({ queryKey: ["incidents", status], queryFn: () => api.get<Incident[]>(`/incidents?status=${status}`), refetchInterval: LIVE });
export const useIncident = (id: number | null) =>
  useQuery({ queryKey: ["incident", id], queryFn: () => api.get<Incident>(`/incidents/${id}`), enabled: id != null, refetchInterval: LIVE });
export const useJobs = () => useQuery({ queryKey: ["jobs"], queryFn: () => api.get<Job[]>("/notifications"), refetchInterval: LIVE });
export const useJob = (id: number | null) =>
  useQuery({ queryKey: ["job", id], queryFn: () => api.get<Job>(`/notifications/${id}`), enabled: id != null, refetchInterval: LIVE });
export const useMessages = () =>
  useQuery({ queryKey: ["messages"], queryFn: () => api.get<Message[]>("/notifications/messages?limit=500"), refetchInterval: 5000 });
export const useTemplates = () =>
  useQuery({ queryKey: ["templates"], queryFn: () => api.getWithMeta<Template[]>("/templates") });
export const useCustomers = () => useQuery({ queryKey: ["customers"], queryFn: () => api.get<Customer[]>("/customers"), refetchInterval: 10_000 });
export const useCustomer = (id: number | null) =>
  useQuery({ queryKey: ["customer", id], queryFn: () => api.get<Customer>(`/customers/${id}`), enabled: id != null });
export const useSettings = () => useQuery({ queryKey: ["settings"], queryFn: () => api.get<Settings>("/settings") });
export const useAnalytics = (days: number) =>
  useQuery({ queryKey: ["analytics", days], queryFn: () => api.get<Analytics>(`/analytics?days=${days}`), refetchInterval: 15_000 });
export const useIntegrations = () =>
  useQuery({ queryKey: ["integrations"], queryFn: () => api.get<Integrations>("/integrations"), staleTime: 30_000 });
export const useDemoClock = () => useQuery({ queryKey: ["clock"], queryFn: () => api.get<DemoClock>("/demo/clock"), refetchInterval: 5000 });

/**
 * Wraps an API call: shows a success/error toast, refreshes every query so all
 * pages reflect the change, and exposes field-level validation errors.
 */
export function useAction<TArgs = void, TResult = unknown>(
  fn: (args: TArgs) => Promise<TResult>,
  opts: { success?: string | ((r: TResult) => string); silent?: boolean; onSuccess?: (r: TResult) => void } = {},
) {
  const qc = useQueryClient();
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const m = useMutation({
    mutationFn: fn,
    onMutate: () => setFieldErrors({}),
    onSuccess: (r) => {
      qc.invalidateQueries();
      const msg = typeof opts.success === "function" ? opts.success(r) : opts.success;
      if (msg) toast.success(msg);
      opts.onSuccess?.(r);
    },
    onError: (e) => {
      if (e instanceof ApiError) setFieldErrors(e.fieldErrors());
      if (!opts.silent) toast.error(e instanceof Error ? e.message : String(e));
    },
  });
  return { ...m, fieldErrors, setFieldErrors };
}
