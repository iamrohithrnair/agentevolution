import type { Metadata } from "next";
import { MetricsPanel } from "@/components/dashboard/MetricsPanel";
import { MapView } from "@/components/dashboard/MapView";
import { ReasoningStream } from "@/components/dashboard/ReasoningStream";
import { MemoryInspector } from "@/components/dashboard/MemoryInspector";
import { ChatPanel } from "@/components/dashboard/ChatPanel";
import { VoiceHUD } from "@/components/dashboard/VoiceHUD";
import { ReflectionFeed } from "@/components/dashboard/ReflectionFeed";
import { WeatherPanel } from "@/components/dashboard/WeatherPanel";
import { FlightLog } from "@/components/dashboard/FlightLog";

export const metadata: Metadata = { title: "Dashboard · Dronan" };

export default function DashboardPage() {
  return (
    <div className="space-y-5" data-testid="dashboard-root">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Mission Control</h1>
          <p className="text-sm text-[var(--color-fg-muted)]">
            Voice-first, memory-augmented, self-evolving multi-agent control tower for medical drones.
          </p>
        </div>
      </header>

      <MetricsPanel />

      <section className="grid gap-5 xl:grid-cols-[minmax(0,_3fr)_minmax(0,_2fr)]">
        <div className="space-y-5">
          <MapView height={520} />
          <FlightLog height={260} />
        </div>
        <div className="grid gap-5 lg:grid-cols-2 xl:grid-cols-1">
          <ChatPanel />
          <VoiceHUD />
          <WeatherPanel />
        </div>
      </section>

      <section className="grid gap-5 lg:grid-cols-3">
        <ReasoningStream height={360} />
        <MemoryInspector />
        <ReflectionFeed />
      </section>
    </div>
  );
}
