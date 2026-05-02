"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { listMissions } from "@/lib/api";
import { openDashboardSocket } from "@/lib/ws";
import { MissionCard } from "@/components/dashboard/MissionCard";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import type { Mission } from "@/lib/types";

export default function MissionsPage() {
  const [missions, setMissions] = useState<Mission[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function refresh() {
      const m = await listMissions();
      if (!cancelled) setMissions(m);
    }
    void refresh();
    const sock = openDashboardSocket();
    const off = sock.on("mission_update", refresh);
    return () => {
      cancelled = true;
      off();
      sock.close();
    };
  }, []);

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Missions</h1>
          <p className="text-sm text-[var(--color-fg-muted)]">
            Every dispatched, in-flight, and completed mission. Click through for telemetry,
            reasoning, and reflection.
          </p>
        </div>
        <Button asChild className="gap-1.5">
          <Link href="/deploy">
            New mission <ArrowRight className="h-4 w-4" />
          </Link>
        </Button>
      </header>

      {!missions ? (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-36 w-full" />
          ))}
        </div>
      ) : missions.length === 0 ? (
        <p className="rounded-md border border-dashed border-[var(--color-border)] p-6 text-center text-sm text-[var(--color-fg-muted)]">
          No missions yet. Dispatch one from the
          <Link href="/deploy" className="px-1 text-[var(--color-accent)] underline-offset-2 hover:underline">
            Deploy
          </Link>
          tab.
        </p>
      ) : (
        <ul className="grid gap-3 md:grid-cols-2 xl:grid-cols-3" data-testid="mission-list">
          {missions.map((m) => (
            <li key={m.id}>
              <MissionCard mission={m} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
