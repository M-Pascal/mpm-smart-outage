import { FlaskConical, Power, RadioTower, Zap, ZapOff, Unplug } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/form-bits";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useAction, useAreas, useMeters } from "@/hooks/queries";
import { api } from "@/lib/api";

type Scenario = "voltage_loss" | "multi_meter_loss" | "comm_failure" | "low_voltage";

export function SimulationControls({ compact = false }: { compact?: boolean }) {
  const areas = useAreas();
  const meters = useMeters();
  const [areaId, setAreaId] = useState<string>("");
  const [meterId, setMeterId] = useState<string>("any");
  const selectedArea = areaId || String(areas.data?.find((a) => a.code === "D")?.id ?? areas.data?.[0]?.id ?? "");
  const areaMeters = (meters.data ?? []).filter((m) => String(m.service_area_id) === selectedArea);

  const simulate = useAction((scenario: Scenario) => api.post<{ target: string }>("/simulation/outage", {
    scenario,
    service_area_id: Number(selectedArea),
    meter_id: meterId !== "any" && scenario !== "multi_meter_loss" ? Number(meterId) : undefined,
  }), { success: (r) => `Simulation applied to ${r.target}` });
  const restore = useAction(() => api.post("/simulation/restore", { service_area_id: Number(selectedArea) }), { success: "Power restored in simulation" });
  const normal = useAction(() => api.post("/simulation/normal"), { success: "All simulated meters back to normal supply" });
  const busy = simulate.isPending || restore.isPending || normal.isPending;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="flex items-center gap-2"><FlaskConical className="h-4 w-4 text-amber-500" /> Outage simulation</CardTitle>
        </div>
        {!compact && <CardDescription>Inject events into the simulated meters. Detection reacts within a few seconds.</CardDescription>}
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Service area" htmlFor="sim-area">
            <Select value={selectedArea} onValueChange={(v) => { setAreaId(v); setMeterId("any"); }}>
              <SelectTrigger id="sim-area"><SelectValue placeholder="Choose area" /></SelectTrigger>
              <SelectContent>
                {areas.data?.map((a) => <SelectItem key={a.id} value={String(a.id)}>{a.name}</SelectItem>)}
              </SelectContent>
            </Select>
          </Field>
          <Field label="Meter" htmlFor="sim-meter">
            <Select value={meterId} onValueChange={setMeterId}>
              <SelectTrigger id="sim-meter"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="any">First meter in area</SelectItem>
                {areaMeters.map((m) => <SelectItem key={m.id} value={String(m.id)}>{m.serial} · {m.customer_name}</SelectItem>)}
              </SelectContent>
            </Select>
          </Field>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <Button variant="outline" disabled={busy} onClick={() => normal.mutate()}><Zap className="text-success" /> Normal supply</Button>
          <Button variant="outline" disabled={busy || !selectedArea} onClick={() => simulate.mutate("voltage_loss")}><ZapOff className="text-danger" /> Voltage loss</Button>
          <Button variant="destructive" disabled={busy || !selectedArea} onClick={() => simulate.mutate("multi_meter_loss")}><Unplug /> Multiple meters</Button>
          <Button variant="outline" disabled={busy || !selectedArea} onClick={() => simulate.mutate("comm_failure")}><RadioTower className="text-slate-500" /> Comm. failure</Button>
          <Button variant="outline" disabled={busy || !selectedArea} onClick={() => simulate.mutate("low_voltage")}><Power className="text-amber-500" /> Low voltage</Button>
          <Button variant="success" disabled={busy || !selectedArea} onClick={() => restore.mutate()}><Zap /> Restore power</Button>
        </div>
      </CardContent>
    </Card>
  );
}
