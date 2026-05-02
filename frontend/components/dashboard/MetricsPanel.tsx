"use client";

import { useEffect, useState } from "react";
import { Activity, BatteryCharging, Compass, Sparkles } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { listDrones, listMissions, listReflections } from "@/lib/api";
import { openDashboardSocket } from "@/lib/ws";
import type { Drone, MemoryHit, Mission } from "@/lib/types";

interface Metrics {
  active: number;
  online: number;
  reroutes: number;
  reflections: number;
  fleetBattery: number;
}

const METRIC_DEFS: Array<{
  key: keyof Metrics;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  suffix?: string;
}> = [
  { key: "active", label: "Active missions", icon: Activity },
  { key: "online", label: "Drones online", icon: Compass },
  { key: "fleetBattery", label: "Fleet battery", icon: BatteryCharging, suffix: "%" },
  { key: "reflections", label: "Reflections today", icon: Sparkles },
];

function compute(missions: Mission[], drones: Drone[], reflections: MemoryHit[]): Metrics {
  const active = missions.filter(
    (m) => m.status === "in_transit" || m.status === "assigned" || m.status === "queued",
  ).length;
  const reroutes = missions.reduce((acc, m) => acc + (m.reroutes?.length ?? 0), 0);
  const online = drones.filter((d) => d.status !== "fault").length;
  const fleetBattery = drones.length
    ? Math.round(drones.reduce((acc, d) => acc + d.battery, 0) / drones.length)
    : 0;
  const dayAgo = Date.now() - 1000 * 60 * 60 * 24;
  const reflectionsToday = reflections.filter((r) => r.created_at >= dayAgo).length;
  return { active, online, reroutes, reflections: reflectionsToday || reflections.length, fleetBattery };
}

export function MetricsPanel() {
  const [metrics, setMetrics] = useState<Metrics | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function refresh() {
      const [m, d, r] = await Promise.all([listMissions(), listDrones(), listReflections()]);
      if (!cancelled) setMetrics(compute(m, d, r));
    }
    refresh();
    const sock = openDashboardSocket();
    const offM = sock.on("mission_update", refresh);
    const offD = sock.on("drone_update", refresh);
    return () => {
      cancelled = true;
      offM();
      offD();
      sock.close();
    };
  }, []);

  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      {METRIC_DEFS.map(({ key, label, icon: Icon, suffix }) => (
        <Card key={key} className="overflow-hidden">
          <CardContent className="flex items-center justify-between gap-3 p-4">
            <div>
              <p className="text-[11px] font-medium uppercase tracking-wider text-[var(--color-fg-muted)]">
                {label}
              </p>
              {metrics ? (
                <p className="mt-1 font-mono text-2xl font-semibold tabular-nums tracking-tight text-[var(--color-fg)]">
                  {metrics[key]}
                  {suffix && <span className="ml-0.5 text-base text-[var(--color-fg-muted)]">{suffix}</span>}
                </p>
              ) : (
                <Skeleton className="mt-1 h-8 w-16" />
              )}
            </div>
            <span className="grid h-9 w-9 place-items-center rounded-md bg-[var(--color-accent-soft)] text-[var(--color-accent-fg)]">
              <Icon className="h-4 w-4" />
            </span>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
