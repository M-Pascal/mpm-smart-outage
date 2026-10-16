/** Date formatting in the operator's configured time zone (Settings → General). */
let TZ = "Africa/Kigali";

export function setTimeZone(tz: string) {
  TZ = tz;
}
export function getTimeZone() {
  return TZ;
}

const fmtCache = new Map<string, Intl.DateTimeFormat>();
function fmt(opts: Intl.DateTimeFormatOptions): Intl.DateTimeFormat {
  const key = TZ + JSON.stringify(opts);
  let f = fmtCache.get(key);
  if (!f) {
    f = new Intl.DateTimeFormat("en-GB", { timeZone: TZ, ...opts });
    fmtCache.set(key, f);
  }
  return f;
}

const d = (v: string | Date) => (typeof v === "string" ? new Date(v) : v);

export const formatDate = (v: string | Date) => fmt({ day: "numeric", month: "short", year: "numeric" }).format(d(v));
export const formatLongDate = (v: string | Date) => fmt({ weekday: "short", day: "numeric", month: "long", year: "numeric" }).format(d(v));
export const formatTime = (v: string | Date) =>
  new Intl.DateTimeFormat("en-US", { timeZone: TZ, hour: "numeric", minute: "2-digit" }).format(d(v));
export const formatTimeSec = (v: string | Date) =>
  new Intl.DateTimeFormat("en-US", { timeZone: TZ, hour: "numeric", minute: "2-digit", second: "2-digit" }).format(d(v));
export const formatDateTime = (v: string | Date) => `${formatDate(v)}, ${formatTime(v)}`;
export const formatDay = (v: string | Date) => fmt({ weekday: "short", day: "numeric", month: "short" }).format(d(v));

export function formatRange(start: string, end: string): string {
  const sameDay = localDateKey(start) === localDateKey(end);
  return sameDay ? `${formatDate(start)}, ${formatTime(start)} – ${formatTime(end)}` : `${formatDateTime(start)} – ${formatDateTime(end)}`;
}

/** YYYY-MM-DD of an instant in the configured zone. */
export function localDateKey(v: string | Date): string {
  const parts = fmt({ year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(d(v));
  const get = (t: string) => parts.find((p) => p.type === t)!.value;
  return `${get("year")}-${get("month")}-${get("day")}`;
}

function zoneOffsetMinutes(at: Date): number {
  const parts = fmt({ year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" }).formatToParts(at);
  const get = (t: string) => Number(parts.find((p) => p.type === t)!.value);
  const asUtc = Date.UTC(get("year"), get("month") - 1, get("day"), get("hour"), get("minute"), get("second"));
  return Math.round((asUtc - at.getTime()) / 60000);
}

/** "2026-10-20T09:00" (wall clock in TZ) -> ISO UTC string. */
export function localInputToIso(value: string): string {
  const [date, time] = value.split("T");
  const [y, m, day] = date.split("-").map(Number);
  const [hh, mm] = time.split(":").map(Number);
  const guess = new Date(Date.UTC(y, m - 1, day, hh, mm));
  const offset = zoneOffsetMinutes(guess);
  return new Date(guess.getTime() - offset * 60000).toISOString();
}

/** ISO UTC -> "YYYY-MM-DDTHH:mm" in TZ (for <input type="datetime-local">). */
export function isoToLocalInput(iso: string): string {
  const parts = fmt({ year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).formatToParts(new Date(iso));
  const get = (t: string) => parts.find((p) => p.type === t)!.value;
  return `${get("year")}-${get("month")}-${get("day")}T${get("hour")}:${get("minute")}`;
}

export function relative(iso: string | null | undefined, now: number = Date.now()): string {
  if (!iso) return "never";
  const diff = (new Date(iso).getTime() - now) / 1000;
  const abs = Math.abs(diff);
  const unit = abs < 60 ? [Math.round(abs), "s"] : abs < 3600 ? [Math.round(abs / 60), "min"] : abs < 86400 ? [Math.round(abs / 3600), "h"] : [Math.round(abs / 86400), "d"];
  if (abs < 5) return "just now";
  return diff < 0 ? `${unit[0]} ${unit[1]} ago` : `in ${unit[0]} ${unit[1]}`;
}

export function duration(fromIso: string, toIso?: string | null, now: number = Date.now()): string {
  const ms = (toIso ? new Date(toIso).getTime() : now) - new Date(fromIso).getTime();
  const s = Math.max(0, Math.floor(ms / 1000));
  const days = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (days) return `${days}d ${h}h`;
  if (h) return `${h}h ${m}m`;
  if (m) return `${m}m ${s % 60}s`;
  return `${s}s`;
}

export function offsetLabel(minutes: number): string {
  if (minutes % 1440 === 0) return `${minutes / 1440} day${minutes === 1440 ? "" : "s"}`;
  if (minutes % 60 === 0) return `${minutes / 60} hour${minutes === 60 ? "" : "s"}`;
  if (minutes > 60) return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
  return `${minutes} min`;
}

export function secondsLabel(s: number | null | undefined): string {
  if (s == null) return "—";
  if (s < 90) return `${Math.round(s)} s`;
  if (s < 5400) return `${(s / 60).toFixed(1)} min`;
  return `${(s / 3600).toFixed(1)} h`;
}

export const number = (n: number | null | undefined, digits = 0) =>
  n == null ? "—" : n.toLocaleString("en-US", { maximumFractionDigits: digits, minimumFractionDigits: digits });
