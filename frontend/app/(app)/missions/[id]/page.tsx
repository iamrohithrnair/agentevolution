"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { MapView } from "@/components/dashboard/MapView";
import { ReasoningStream } from "@/components/dashboard/ReasoningStream";
import { FlightLog } from "@/components/dashboard/FlightLog";
import { RouteTimeline } from "@/components/dashboard/RouteTimeline";
import { PayloadStatus } from "@/components/dashboard/PayloadStatus";
import { MemoryInspector } from "@/components/dashboard/MemoryInspector";
import { RiskBadge } from "@/components/dashboard/RiskBadge";
import { ChatPanel } from "@/components/dashboard/ChatPanel";
import { getMission } from "@/lib/api";
import { openMissionSocket } from "@/lib/ws";
import { formatDuration, formatRelative } from "@/lib/format";
import type { Mission } from "@/lib/types";

export default function MissionDetailPage() {
  const params = useParams<{ id: string }>();
  const missionId = params.id;
  const [mission, setMission] = useState<Mission | null>(null);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    if (!missionId) return;
    let cancelled = false;
    async function refresh() {
      const r = await getMission(missionId);
      if (cancelled) return;
      if (!r.mission) {
        setNotFound(true);
        return;
      }
      setMission(r.mission);
    }
    void refresh();

    const sock = openMissionSocket(missionId);
    const off = sock.on("mission_update", (m: Mission) => {
      if (m.id === missionId) setMission(m);
    });
    return () => {
      cancelled = true;
      off();
      sock.close();
    };
  }, [missionId]);

  if (notFound) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Mission not found</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-[var(--color-fg-muted)]">
            That mission ID isn&rsquo;t in our system. It may have been pruned or the link is stale.
          </p>
        </CardContent>
      </Card>
    );
  }

  if (!mission) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-72" />
        <Skeleton className="h-72 w-full" />
        <div className="grid gap-3 md:grid-cols-3">
          <Skeleton className="h-40 w-full" />
          <Skeleton className="h-40 w-full" />
          <Skeleton className="h-40 w-full" />
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-5" data-testid="mission-detail">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-[11px] uppercase tracking-wider text-[var(--color-fg-muted)]">Mission</p>
          <h1 className="font-mono text-2xl font-semibold tracking-tight">
            {mission.id.slice(-12)}
          </h1>
          <p className="text-sm text-[var(--color-fg-muted)]">
            {mission.scenario ?? "Ad-hoc dispatch"} · drone {mission.drone_id} · created{" "}
            {formatRelative(mission.created_at)}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="accent" className="capitalize">
            {mission.status.replace("_", " ")}
          </Badge>
          <Badge variant="outline">ETA {formatDuration(mission.eta_seconds)}</Badge>
          {mission.actual_seconds && (
            <Badge variant="success">actual {formatDuration(mission.actual_seconds)}</Badge>
          )}
          <RiskBadge mission={mission} />
        </div>
      </header>

      <section className="grid gap-5 xl:grid-cols-[minmax(0,_3fr)_minmax(0,_2fr)]">
        <div className="space-y-5">
          <MapView missionId={mission.id} followDrone={mission.drone_id} height={420} />
          <FlightLog missionId={mission.id} />
        </div>
        <div className="space-y-5">
          <RouteTimeline mission={mission} />
          <PayloadStatus missionId={mission.id} />
          <ChatPanel missionId={mission.id} compact />
        </div>
      </section>

      <section className="grid gap-5 lg:grid-cols-2">
        <ReasoningStream missionId={mission.id} height={360} />
        <MemoryInspector
          missionId={mission.id}
          initialQuery={`mission ${mission.scenario ?? "dispatch"} reflections`}
        />
      </section>
    </div>
  );
}
