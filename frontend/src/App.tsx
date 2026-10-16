import { useState } from "react";
import { Route, Routes } from "react-router-dom";
import { Toaster } from "sonner";
import { DemoPanel } from "@/components/layout/DemoPanel";
import { Sidebar } from "@/components/layout/Sidebar";
import { Topbar } from "@/components/layout/Topbar";
import { EmptyState } from "@/components/shared";
import { TooltipProvider } from "@/components/ui/menus";
import { AppProvider, useApp } from "@/hooks/app-context";
import Analytics from "@/pages/Analytics";
import Customers from "@/pages/Customers";
import Incidents from "@/pages/Incidents";
import Monitoring from "@/pages/Monitoring";
import Notifications from "@/pages/Notifications";
import Overview from "@/pages/Overview";
import ScheduledOutages from "@/pages/ScheduledOutages";
import SettingsPage from "@/pages/Settings";

function Shell() {
  const { theme } = useApp();
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return localStorage.getItem("pc-sidebar") === "collapsed";
    } catch {
      return false;
    }
  });
  const toggle = () =>
    setCollapsed((c) => {
      try {
        localStorage.setItem("pc-sidebar", c ? "open" : "collapsed");
      } catch {
        /* ignore */
      }
      return !c;
    });
  return (
    <div className="flex min-h-screen">
      <Sidebar collapsed={collapsed} onToggle={toggle} />
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar />
        <main className="mx-auto w-full max-w-[1500px] flex-1 px-4 py-6 sm:px-6 lg:py-8">
          <Routes>
            <Route path="/" element={<Overview />} />
            <Route path="/monitoring" element={<Monitoring />} />
            <Route path="/scheduled" element={<ScheduledOutages />} />
            <Route path="/incidents" element={<Incidents />} />
            <Route path="/customers" element={<Customers />} />
            <Route path="/notifications" element={<Notifications />} />
            <Route path="/analytics" element={<Analytics />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="*" element={<EmptyState title="Page not found" description="Use the navigation to pick a section." />} />
          </Routes>
        </main>
      </div>
      <DemoPanel />
      <Toaster theme={theme} position="bottom-right" richColors closeButton />
    </div>
  );
}

export default function App() {
  return (
    <TooltipProvider>
      <AppProvider>
        <Shell />
      </AppProvider>
    </TooltipProvider>
  );
}
