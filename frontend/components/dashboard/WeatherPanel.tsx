"use client";

import { Cloud, Wind, Eye, Thermometer } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export function WeatherPanel() {
  // Phase 5 mock — in Phase 4 the WeatherAgent publishes a weather doc per
  // facility region every 5 minutes; we render a stable representative reading.
  const stats: Array<{
    label: string;
    value: string;
    icon: React.ComponentType<{ className?: string }>;
    accent?: string;
  }> = [
    { label: "Cloud cover", value: "scattered", icon: Cloud },
    { label: "Wind", value: "8 kt @ 240°", icon: Wind },
    { label: "Visibility", value: ">10 km", icon: Eye },
    { label: "Temp", value: "14 °C", icon: Thermometer },
  ];
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between pb-2">
        <CardTitle>Weather · East London</CardTitle>
        <Badge variant="success">stable</Badge>
      </CardHeader>
      <CardContent>
        <ul className="grid grid-cols-2 gap-2 text-xs">
          {stats.map(({ label, value, icon: Icon }) => (
            <li
              key={label}
              className="flex items-center gap-2 rounded-md border border-[var(--color-border)] bg-[var(--color-surface-2)] px-2.5 py-2"
            >
              <Icon className="h-3.5 w-3.5 text-[var(--color-info)]" />
              <span className="text-[var(--color-fg-muted)]">{label}</span>
              <span className="ml-auto font-mono text-[var(--color-fg)]">{value}</span>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
