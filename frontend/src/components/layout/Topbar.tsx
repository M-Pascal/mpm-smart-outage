import { useQuery } from "@tanstack/react-query";
import { Bell, CalendarClock, Clock, Gauge, Menu, Moon, Search, ShieldAlert, Sun, User, Users, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, SheetContent, DialogTitle } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger, Tip } from "@/components/ui/menus";
import { useApp, useNow } from "@/hooks/app-context";
import { useAction } from "@/hooks/queries";
import { api } from "@/lib/api";
import { formatLongDate, formatTimeSec, relative } from "@/lib/format";
import type { Activity, SearchResult } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Brand, NAV, NavList } from "./Sidebar";

const SEARCH_ICONS = { customer: Users, meter: Gauge, scheduled_outage: CalendarClock, service_area: Gauge, incident: ShieldAlert };

export function searchTarget(r: { type: string; id: number }): string {
  switch (r.type) {
    case "customer": return `/customers?id=${r.id}`;
    case "meter": return `/monitoring?meter=${r.id}`;
    case "scheduled_outage": return `/scheduled?id=${r.id}`;
    case "incident": return `/incidents?id=${r.id}`;
    case "service_area": return `/monitoring?area=${r.id}`;
    case "notification": return `/notifications?job=${r.id}`;
    default: return "/";
  }
}

function GlobalSearch() {
  const [q, setQ] = useState("");
  const [debounced, setDebounced] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const navigate = useNavigate();
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(q.trim()), 200);
    return () => clearTimeout(id);
  }, [q]);
  const results = useQuery({
    queryKey: ["search", debounced],
    queryFn: () => api.get<SearchResult[]>(`/search?q=${encodeURIComponent(debounced)}`),
    enabled: debounced.length > 0,
  });
  useEffect(() => {
    const close = (e: MouseEvent) => !box.current?.contains(e.target as Node) && setOpen(false);
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);
  const items = results.data ?? [];
  const go = (r: SearchResult) => {
    navigate(searchTarget(r));
    setOpen(false);
    setQ("");
  };
  return (
    <div ref={box} className="relative w-full max-w-md">
      <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
      <input
        value={q}
        onChange={(e) => { setQ(e.target.value); setOpen(true); setActive(0); }}
        onFocus={() => setOpen(true)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(a + 1, items.length - 1)); }
          if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
          if (e.key === "Enter" && items[active]) go(items[active]);
          if (e.key === "Escape") setOpen(false);
        }}
        placeholder="Search customers, meters, events, INC-0001…"
        aria-label="Search"
        className="h-9 w-full rounded-lg border bg-background pl-9 pr-3 text-sm outline-none transition placeholder:text-muted-foreground focus:border-primary focus:ring-2 focus:ring-primary/20"
      />
      {open && debounced && (
        <div className="absolute left-0 right-0 top-11 z-50 overflow-hidden rounded-lg border bg-popover shadow-xl" role="listbox">
          {results.isLoading ? (
            <p className="p-3 text-sm text-muted-foreground">Searching…</p>
          ) : items.length === 0 ? (
            <p className="p-3 text-sm text-muted-foreground">No results for “{debounced}”.</p>
          ) : (
            items.map((r, i) => {
              const Icon = SEARCH_ICONS[r.type];
              return (
                <button key={`${r.type}-${r.id}`} role="option" aria-selected={i === active} onMouseEnter={() => setActive(i)} onClick={() => go(r)}
                        className={cn("flex w-full items-center gap-3 px-3 py-2 text-left text-sm", i === active && "bg-accent")}>
                  <Icon className="h-4 w-4 shrink-0 text-muted-foreground" />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium">{r.title}</span>
                    <span className="block truncate text-xs text-muted-foreground">{r.subtitle}</span>
                  </span>
                  <span className="text-[10px] uppercase text-muted-foreground">{r.type.replace("_", " ")}</span>
                </button>
              );
            })
          )}
        </div>
      )}
    </div>
  );
}

function NotificationBell() {
  const navigate = useNavigate();
  const alerts = useQuery({ queryKey: ["alerts"], queryFn: () => api.getWithMeta<Activity[]>("/activity?alerts_only=true&limit=12"), refetchInterval: 3000 });
  const markRead = useAction(() => api.post("/activity/read-all"), { silent: true });
  const now = useNow(10_000);
  const unread = (alerts.data?.meta?.unread_alerts as number | undefined) ?? 0;
  const target = (a: Activity) => (a.entity_type === "incident" ? `/incidents?id=${a.entity_id}` : a.entity_type === "scheduled_outage" ? `/scheduled?id=${a.entity_id}` : "/");
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" aria-label={`Operator alerts${unread ? `, ${unread} unread` : ""}`} className="relative">
          <Bell />
          {unread > 0 && (
            <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 animate-pulse-ring items-center justify-center rounded-full bg-danger px-1 text-[10px] font-bold text-white">{unread > 9 ? "9+" : unread}</span>
          )}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-80 p-0">
        <div className="flex items-center justify-between px-3 py-2.5">
          <DropdownMenuLabel className="p-0 text-sm text-foreground">Operator alerts</DropdownMenuLabel>
          {unread > 0 && <button className="text-xs font-medium text-primary hover:underline" onClick={() => markRead.mutate()}>Mark all read</button>}
        </div>
        <DropdownMenuSeparator className="mx-0 my-0" />
        <div className="max-h-80 overflow-y-auto scrollbar-thin">
          {(alerts.data?.data ?? []).length === 0 ? (
            <p className="px-3 py-6 text-center text-sm text-muted-foreground">No alerts. All quiet.</p>
          ) : (
            alerts.data!.data.map((a) => (
              <DropdownMenuItem key={a.id} className="items-start rounded-none px-3 py-2.5" onSelect={() => navigate(target(a))}>
                <span className={cn("mt-1.5 h-2 w-2 shrink-0 rounded-full", a.severity === "critical" ? "bg-danger" : "bg-warning", a.read && "opacity-30")} />
                <span className="min-w-0 flex-1">
                  <span className={cn("block text-[13px] leading-snug", !a.read && "font-medium")}>{a.message}</span>
                  <span className="text-[11px] text-muted-foreground">{relative(a.ts, now)}</span>
                </span>
              </DropdownMenuItem>
            ))
          )}
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function LiveClock() {
  const now = useNow(1000);
  const { offsetMs, setDemoOpen, timezone } = useApp();
  return (
    <div className="hidden items-center gap-2 xl:flex">
      <Clock className="h-4 w-4 text-muted-foreground" />
      <div className="text-right leading-tight">
        <p className="text-xs font-medium tabular">{formatTimeSec(new Date(now))}</p>
        <p className="text-[10.5px] text-muted-foreground">{formatLongDate(new Date(now))}</p>
      </div>
      {offsetMs >= 60_000 && (
        <Tip content={`The demo clock is ahead of real time (${timezone}). Reset it in the guided demo panel.`}>
          <button onClick={() => setDemoOpen(true)}><Badge tone="warning">Demo time +{offsetMs < 3600000 ? `${Math.round(offsetMs / 60000)} min` : `${(offsetMs / 3600000).toFixed(1)} h`}</Badge></button>
        </Tip>
      )}
    </div>
  );
}

export function Topbar() {
  const { theme, toggleTheme, operator } = useApp();
  const location = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);
  const title = NAV.find((n) => (n.to === "/" ? location.pathname === "/" : location.pathname.startsWith(n.to)))?.label ?? "PowerChat";
  return (
    <header className="sticky top-0 z-30 border-b bg-background/85 backdrop-blur supports-[backdrop-filter]:bg-background/70">
      <div className="flex h-16 items-center gap-3 px-4 sm:px-6">
        <Button variant="ghost" size="icon" className="lg:hidden" aria-label="Open navigation" onClick={() => setMobileOpen(true)}><Menu /></Button>
        <h2 className="hidden min-w-[10rem] text-[15px] font-semibold md:block">{title}</h2>
        <div className="flex flex-1 justify-center"><GlobalSearch /></div>
        <div className="flex items-center gap-1 sm:gap-2">
          <LiveClock />
          <NotificationBell />
          <Tip content={theme === "dark" ? "Light mode" : "Dark mode"}>
            <Button variant="ghost" size="icon" onClick={toggleTheme} aria-label="Toggle theme">{theme === "dark" ? <Sun /> : <Moon />}</Button>
          </Tip>
          <div className="hidden items-center gap-2 rounded-lg border bg-card py-1 pl-1 pr-3 sm:flex">
            <div className="flex h-7 w-7 items-center justify-center rounded-md bg-brand text-white"><User className="h-4 w-4" /></div>
            <div className="leading-tight">
              <p className="text-xs font-medium">{operator}</p>
              <p className="text-[10.5px] text-muted-foreground">Administrator</p>
            </div>
          </div>
        </div>
      </div>
      <Dialog open={mobileOpen} onOpenChange={setMobileOpen}>
        <SheetContent side="left" className="bg-sidebar p-4 text-sidebar-foreground">
          <DialogTitle className="sr-only">Navigation</DialogTitle>
          <div className="flex items-center justify-between"><Brand /><button onClick={() => setMobileOpen(false)} aria-label="Close" className="hidden"><X /></button></div>
          <div className="mt-6"><NavList onNavigate={() => setMobileOpen(false)} /></div>
        </SheetContent>
      </Dialog>
    </header>
  );
}
