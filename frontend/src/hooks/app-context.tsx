import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { setTimeZone } from "@/lib/format";
import { useDemoClock, useSettings } from "./queries";

interface AppState {
  offsetMs: number;
  operator: string;
  organization: string;
  timezone: string;
  theme: "light" | "dark";
  toggleTheme: () => void;
  demoOpen: boolean;
  setDemoOpen: (v: boolean) => void;
}

const Ctx = createContext<AppState | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const clock = useDemoClock();
  const settings = useSettings();
  const [theme, setTheme] = useState<"light" | "dark">(() => (document.documentElement.classList.contains("dark") ? "dark" : "light"));
  const [demoOpen, setDemoOpen] = useState(false);
  const tz = settings.data?.general.timezone ?? "Africa/Kigali";
  setTimeZone(tz);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    try {
      localStorage.setItem("pc-theme", theme);
    } catch {
      /* storage unavailable */
    }
  }, [theme]);

  const value: AppState = {
    offsetMs: (clock.data?.offset_seconds ?? 0) * 1000,
    operator: settings.data?.general.operator_name ?? "Admin Operator",
    organization: settings.data?.general.organization_name ?? "PowerChat Energy",
    timezone: tz,
    theme,
    toggleTheme: () => setTheme((t) => (t === "dark" ? "light" : "dark")),
    demoOpen,
    setDemoOpen,
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useApp(): AppState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useApp outside AppProvider");
  return v;
}

/** Current *demo* time in ms, re-rendering every `intervalMs`. */
export function useNow(intervalMs = 1000): number {
  const { offsetMs } = useApp();
  const [tick, setTick] = useState(Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setTick(Date.now()), intervalMs);
    return () => window.clearInterval(id);
  }, [intervalMs]);
  return tick + offsetMs;
}
