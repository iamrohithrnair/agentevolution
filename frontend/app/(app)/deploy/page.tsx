import type { Metadata } from "next";
import { DispatchForm } from "@/components/dashboard/DispatchForm";
import { MapView } from "@/components/dashboard/MapView";
import { MemoryInspector } from "@/components/dashboard/MemoryInspector";
import { WeatherPanel } from "@/components/dashboard/WeatherPanel";

export const metadata: Metadata = { title: "Deploy · Dronan" };

export default function DeployPage() {
  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Compose & dispatch</h1>
        <p className="text-sm text-[var(--color-fg-muted)]">
          Stage cargo, pick destinations, and let Dronan plan the route. Memory recall surfaces
          lessons from prior runs as you compose.
        </p>
      </header>
      <div className="grid gap-5 xl:grid-cols-[minmax(0,_3fr)_minmax(0,_2fr)]">
        <div className="space-y-5">
          <DispatchForm />
          <MapView height={420} />
        </div>
        <div className="space-y-5">
          <WeatherPanel />
          <MemoryInspector initialQuery="cold chain handover storm" />
        </div>
      </div>
    </div>
  );
}
