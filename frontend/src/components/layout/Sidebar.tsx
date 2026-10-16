import { Activity, BarChart3, Bell, CalendarClock, ChevronsLeft, ChevronsRight, LayoutDashboard, MonitorPlay, Settings, ShieldAlert, Users, Zap } from "lucide-react";
import { NavLink } from "react-router-dom";
import { Tip } from "@/components/ui/menus";
import { useApp } from "@/hooks/app-context";
import { useDashboard } from "@/hooks/queries";
import { cn } from "@/lib/utils";

export const NAV = [
  { to: "/", label: "Overview", icon: LayoutDashboard },
  { to: "/monitoring", label: "Power Monitoring", icon: Activity },
  { to: "/scheduled", label: "Scheduled Outages", icon: CalendarClock },
  { to: "/incidents", label: "Incident Management", icon: ShieldAlert },
  { to: "/customers", label: "Customer Management", icon: Users },
  { to: "/notifications", label: "Notifications", icon: Bell },
  { to: "/analytics", label: "Analytics", icon: BarChart3 },
  { to: "/settings", label: "Settings", icon: Settings },
];

export function Brand({ collapsed }: { collapsed?: boolean }) {
  return (
    <div className="flex items-center gap-2.5 px-1">
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-brand shadow-lg shadow-blue-900/40">
        <Zap className="h-5 w-5 text-white" fill="currentColor" />
      </div>
      {!collapsed && (
        <div className="min-w-0 leading-tight">
          <p className="text-[15px] font-semibold text-white">PowerChat</p>
          <p className="truncate text-[10.5px] text-sidebar-muted">Smarter Power Monitoring. Timely Communication.</p>
        </div>
      )}
    </div>
  );
}

export function NavList({ collapsed, onNavigate }: { collapsed?: boolean; onNavigate?: () => void }) {
  const dash = useDashboard();
  const counts: Record<string, number | undefined> = {
    "/incidents": dash.data?.summary.unexpected_outages || undefined,
    "/scheduled": dash.data?.summary.scheduled_interruptions || undefined,
  };
  return (
    <nav className="flex flex-col gap-0.5" aria-label="Main">
      {NAV.map(({ to, label, icon: Icon }) => {
        const link = (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            onClick={onNavigate}
            className={({ isActive }) =>
              cn(
                "group flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-sidebar-muted transition-colors hover:bg-sidebar-accent hover:text-white",
                isActive && "bg-sidebar-accent text-white shadow-[inset_3px_0_0_0_#2563EB]",
                collapsed && "justify-center px-2",
              )
            }
          >
            <Icon className="h-[18px] w-[18px] shrink-0" aria-hidden />
            {!collapsed && <span className="flex-1 truncate">{label}</span>}
            {!collapsed && counts[to] != null && (
              <span className={cn("rounded-full px-1.5 text-[11px] font-semibold", to === "/incidents" ? "bg-danger text-white" : "bg-white/10 text-white")}>
                {counts[to]}
              </span>
            )}
          </NavLink>
        );
        return collapsed ? <Tip key={to} content={label} side="right">{link}</Tip> : link;
      })}
    </nav>
  );
}

export function Sidebar({ collapsed, onToggle }: { collapsed: boolean; onToggle: () => void }) {
  const { setDemoOpen } = useApp();
  return (
    <aside className={cn("sticky top-0 hidden h-screen shrink-0 flex-col bg-sidebar p-3 text-sidebar-foreground transition-[width] duration-200 lg:flex", collapsed ? "w-[68px]" : "w-64")}>
      <div className="py-2"><Brand collapsed={collapsed} /></div>
      <div className="mt-6 flex-1 overflow-y-auto scrollbar-thin"><NavList collapsed={collapsed} /></div>
      <div className="space-y-2 border-t border-white/10 pt-3">
        <button
          onClick={() => setDemoOpen(true)}
          className={cn("flex w-full items-center gap-3 rounded-lg bg-amber-400/10 px-3 py-2 text-sm font-medium text-amber-300 ring-1 ring-amber-400/30 transition hover:bg-amber-400/20", collapsed && "justify-center px-2")}
        >
          <MonitorPlay className="h-[18px] w-[18px]" />
          {!collapsed && "Guided demo"}
        </button>
        {!collapsed && (
          <p className="px-1 text-[10.5px] leading-snug text-sidebar-muted">
            Prototype · simulated meters & WhatsApp. Not connected to MPM or real customers.
          </p>
        )}
        <button
          onClick={onToggle}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          className="flex w-full items-center justify-center rounded-lg py-1.5 text-sidebar-muted hover:bg-sidebar-accent hover:text-white"
        >
          {collapsed ? <ChevronsRight className="h-4 w-4" /> : <ChevronsLeft className="h-4 w-4" />}
        </button>
      </div>
    </aside>
  );
}
