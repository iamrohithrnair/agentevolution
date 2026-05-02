"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { openMissionSocket, openDashboardSocket } from "@/lib/ws";
import { getMission, listMissions } from "@/lib/api";
import { clockTime } from "@/lib/format";
import type { FlightLog as FlightLogT } from "@/lib/types";

const EVENT_VARIANT: Partial<Record<FlightLogT["event"], "info" | "success" | "warning" | "danger" | "accent" | "outline">> = {
  mission_created: "outline",
  preflight_ok: "success",
  takeoff: "accent",
  waypoint_reached: "info",
  reroute: "warning",
  delivery_handover: "success",
  landing: "info",
  anomaly: "danger",
  weather_alert: "warning",
  obstacle_detected: "danger",
  mission_complete: "success",
  operator_override: "warning",
};

interface Props {
  missionId?: string;
  height?: number | string;
}

export function FlightLog({ missionId, height = 320 }: Props) {
  const [logs, setLogs] = useState<FlightLogT[]>([]);

  useEffect(() => {
    let cancelled = false;
    async function bootstrap() {
      if (missionId) {
        const r = await getMission(missionId);
        if (!cancelled) setLogs(r.flight_logs ?? []);
      } else {
        const ms = await listMissions();
        const all: FlightLogT[] = [];
        for (const m of ms.slice(0, 5)) {
          const detail = await getMission(m.id);
          all.push(...(detail.flight_logs ?? []));
        }
        all.sort((a, b) => b.ts - a.ts);
        if (!cancelled) setLogs(all.slice(0, 80));
      }
    }
    void bootstrap();

    const sock = missionId ? openMissionSocket(missionId) : openDashboardSocket();
    const off = sock.on("flight_log", (log: FlightLogT) =>
      setLogs((prev) => [log, ...prev].slice(0, 200)),
    );
    return () => {
      cancelled = true;
      off();
      sock.close();
    };
  }, [missionId]);

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between pb-2">
        <CardTitle>Flight log</CardTitle>
        <Badge variant="outline">{logs.length} events</Badge>
      </CardHeader>
      <CardContent className="p-0">
        <ScrollArea style={{ height }}>
          <ol className="divide-y divide-dashed divide-[var(--color-border)] px-5 py-1" data-testid="flight-log">
            <AnimatePresence initial={false}>
              {logs.length === 0 ? (
                <li className="py-4 text-sm text-[var(--color-fg-muted)]">
                  No flight events yet. Dispatch a mission to see takeoff → reroute → handover.
                </li>
              ) : (
                logs.map((log) => (
                  <motion.li
                    key={log.id}
                    layout
                    initial={{ opacity: 0, y: 4 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0 }}
                    className="grid grid-cols-[5.5rem_8rem_1fr] items-start gap-3 py-2 text-xs"
                  >
                    <span className="font-mono text-[var(--color-fg-subtle)]">
                      {clockTime(log.ts)}
                    </span>
                    <Badge variant={EVENT_VARIANT[log.event] ?? "outline"} className="justify-self-start capitalize">
                      {log.event.replace("_", " ")}
                    </Badge>
                    <span className="leading-snug text-[var(--color-fg)]">{log.message}</span>
                  </motion.li>
                ))
              )}
            </AnimatePresence>
          </ol>
        </ScrollArea>
      </CardContent>
    </Card>
  );
}
