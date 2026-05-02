"use client";

import { Check, Circle, Plane } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { Mission } from "@/lib/types";

interface Props {
  mission: Mission;
}

export function RouteTimeline({ mission }: Props) {
  const stops = mission.route;
  const totalLegs = stops.length - 1;
  // Assume the simulator's progress matches the number of legs flown so far
  // by checking arrived_at; we don't have it in the mock yet, so derive from
  // mission status.
  const flown =
    mission.status === "completed"
      ? totalLegs
      : mission.status === "in_transit"
        ? Math.max(1, Math.round(totalLegs / 2))
        : 0;

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between gap-3 pb-2">
        <CardTitle>Route timeline</CardTitle>
        <Badge variant="outline">{stops.length} waypoints</Badge>
      </CardHeader>
      <CardContent>
        <ol className="space-y-3">
          {stops.map((wp, i) => {
            const done = i <= flown;
            const active = i === flown && mission.status !== "completed";
            return (
              <li key={`${i}-${wp.label}`} className="relative flex gap-3 pl-6">
                <span
                  className={
                    "absolute left-0 top-1.5 grid h-4 w-4 place-items-center rounded-full ring-2 " +
                    (done
                      ? "bg-[var(--color-success)] ring-[var(--color-success-soft)]"
                      : "bg-[var(--color-surface-2)] ring-[var(--color-border)]")
                  }
                >
                  {done ? (
                    <Check className="h-2.5 w-2.5 text-white" />
                  ) : active ? (
                    <Plane className="h-2.5 w-2.5 text-[var(--color-accent)] animate-dronan-pulse" />
                  ) : (
                    <Circle className="h-2 w-2 text-[var(--color-fg-subtle)]" />
                  )}
                </span>
                {i < stops.length - 1 && (
                  <span
                    className={
                      "absolute left-[7px] top-5 h-[calc(100%-0.25rem)] w-0.5 " +
                      (done
                        ? "bg-[var(--color-success)]"
                        : "bg-[var(--color-border)]")
                    }
                    aria-hidden
                  />
                )}
                <div>
                  <p className="text-sm font-medium text-[var(--color-fg)]">{wp.label}</p>
                  <p className="text-[11px] text-[var(--color-fg-subtle)]">
                    {wp.position[1].toFixed(4)}, {wp.position[0].toFixed(4)}
                  </p>
                </div>
              </li>
            );
          })}
        </ol>
      </CardContent>
    </Card>
  );
}
