"use client";

import Link from "next/link";
import { ArrowRight, Plane, Timer } from "lucide-react";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { Mission, MissionStatus } from "@/lib/types";
import { formatDuration, formatRelative } from "@/lib/format";

const STATUS_VARIANT: Record<MissionStatus, "outline" | "info" | "success" | "warning" | "danger" | "accent" | "default"> = {
  draft: "outline",
  queued: "info",
  assigned: "info",
  planned: "info",
  executing: "accent",
  in_transit: "accent",
  delivered: "success",
  returning: "warning",
  completed: "success",
  aborted: "danger",
  failed: "danger",
};

interface Props {
  mission: Mission;
  href?: string;
}

export function MissionCard({ mission, href = `/missions/${mission.id}` }: Props) {
  const stops = mission.route.length - 2; // exclude origin + return
  const variant = STATUS_VARIANT[mission.status];
  return (
    <Card className="transition-shadow hover:shadow-[var(--shadow-2)]">
      <CardHeader className="flex-row items-center justify-between gap-3 pb-2">
        <CardTitle className="font-mono text-sm tracking-tight">{mission.id.slice(-8)}</CardTitle>
        <Badge variant={variant} className="capitalize">
          {mission.status.replace("_", " ")}
        </Badge>
      </CardHeader>
      <CardContent className="space-y-2 pt-0">
        <p className="line-clamp-1 text-sm text-[var(--color-fg-muted)]">
          {mission.scenario ?? `${stops} stop${stops === 1 ? "" : "s"} · drone ${mission.drone_id.slice(-6)}`}
        </p>
        <div className="flex flex-wrap gap-3 text-[11px] text-[var(--color-fg-muted)]">
          <span className="inline-flex items-center gap-1">
            <Plane className="h-3 w-3" />
            {mission.drone_id}
          </span>
          <span className="inline-flex items-center gap-1">
            <Timer className="h-3 w-3" />
            ETA {formatDuration(mission.eta_seconds)}
          </span>
          {mission.actual_seconds && (
            <span className="inline-flex items-center gap-1">
              <Timer className="h-3 w-3" />
              actual {formatDuration(mission.actual_seconds)}
            </span>
          )}
          {mission.reroutes.length > 0 && (
            <span className="text-[var(--color-warning)]">
              {mission.reroutes.length} reroute{mission.reroutes.length === 1 ? "" : "s"}
            </span>
          )}
        </div>
      </CardContent>
      <CardFooter className="text-[11px] text-[var(--color-fg-muted)]">
        <span>created {formatRelative(mission.created_at)}</span>
        <Button asChild variant="ghost" size="sm" className="gap-1">
          <Link href={href}>
            Open <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </Button>
      </CardFooter>
    </Card>
  );
}
