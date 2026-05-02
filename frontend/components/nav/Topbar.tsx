"use client";

import { useEffect, useState } from "react";
import { Bell, Headphones, Search } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { listMissions } from "@/lib/api";
import { openDashboardSocket } from "@/lib/ws";

export function Topbar() {
  const [missionCount, setMissionCount] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    listMissions()
      .then((ms) => {
        if (cancelled) return;
        setMissionCount(
          ms.filter((m) => m.status === "in_transit" || m.status === "assigned" || m.status === "queued").length,
        );
      })
      .catch(() => setMissionCount(0));
    const sock = openDashboardSocket();
    const off = sock.on("mission_update", () => {
      // Refresh on any mission change.
      listMissions()
        .then((ms) =>
          setMissionCount(
            ms.filter(
              (m) =>
                m.status === "in_transit" || m.status === "assigned" || m.status === "queued",
            ).length,
          ),
        )
        .catch(() => undefined);
    });
    return () => {
      cancelled = true;
      off();
      sock.close();
    };
  }, []);

  return (
    <div
      className="flex h-full items-center gap-3 px-4"
      data-testid="topbar"
    >
      <div className="hidden flex-1 items-center md:flex">
        <div className="relative w-full max-w-sm">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--color-fg-subtle)]" />
          <input
            placeholder="Jump to mission, drone, facility…"
            aria-label="Quick search"
            className="h-8 w-full rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] pl-8 pr-3 text-sm placeholder:text-[var(--color-fg-subtle)] focus:outline-none focus-visible:shadow-[var(--shadow-focus)]"
          />
        </div>
      </div>

      <div className="ml-auto flex items-center gap-2">
        <Badge variant="success" className="gap-1.5">
          <span
            className="h-1.5 w-1.5 rounded-full bg-[var(--color-success)] animate-dronan-pulse"
            aria-hidden
          />
          live
        </Badge>
        {missionCount !== null && (
          <Badge variant="accent" className="gap-1.5">
            {missionCount} active mission{missionCount === 1 ? "" : "s"}
          </Badge>
        )}
        <Button variant="ghost" size="icon" aria-label="Notifications" className="relative">
          <Bell className="h-4 w-4" />
        </Button>
        <Button variant="soft" size="sm" className="gap-1.5">
          <Headphones className="h-4 w-4" />
          <span className="hidden md:inline">Join voice room</span>
        </Button>
        <div className="ml-2 flex items-center gap-2 rounded-full border border-[var(--color-border)] bg-[var(--color-surface)] px-2.5 py-1">
          <span className="grid h-6 w-6 place-items-center rounded-full bg-[var(--color-accent-soft)] text-[10px] font-semibold tracking-tight text-[var(--color-accent-fg)]">
            RD
          </span>
          <span className="text-xs font-medium text-[var(--color-fg)]">R. Daniels</span>
        </div>
      </div>
    </div>
  );
}
