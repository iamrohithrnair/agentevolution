"use client";

import { useEffect, useMemo, useState } from "react";
import { ThermometerSnowflake, Boxes, ShieldCheck, AlertTriangle } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { openMissionSocket } from "@/lib/ws";
import { formatTemp } from "@/lib/format";
import type { TelemetryFrame } from "@/lib/types";

interface Props {
  missionId?: string;
}

export function PayloadStatus({ missionId }: Props) {
  const [frame, setFrame] = useState<TelemetryFrame | null>(null);

  useEffect(() => {
    if (!missionId) return;
    const sock = openMissionSocket(missionId);
    const off = sock.on("telemetry", (f: TelemetryFrame) => setFrame(f));
    return () => {
      off();
      sock.close();
    };
  }, [missionId]);

  const integrity = useMemo(() => {
    const t = frame?.payload_temp_c;
    if (t === null || t === undefined) return null;
    if (t < 8) return { label: "nominal", variant: "success" as const, Icon: ShieldCheck };
    if (t < 12) return { label: "drifting", variant: "warning" as const, Icon: AlertTriangle };
    return { label: "breach", variant: "danger" as const, Icon: AlertTriangle };
  }, [frame]);

  const cardStyle = "rounded-md border border-[var(--color-border)] bg-[var(--color-surface-2)] p-2.5";

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between pb-2">
        <CardTitle>Payload</CardTitle>
        {integrity && (
          <Badge variant={integrity.variant} className="capitalize">
            <integrity.Icon className="mr-1 h-3 w-3" />
            {integrity.label}
          </Badge>
        )}
      </CardHeader>
      <CardContent className="grid grid-cols-2 gap-2 text-xs">
        <div className={cardStyle}>
          <p className="flex items-center gap-1.5 text-[var(--color-fg-muted)]">
            <ThermometerSnowflake className="h-3.5 w-3.5 text-[var(--color-info)]" /> Temp
          </p>
          <p className="mt-1 font-mono text-base text-[var(--color-fg)]">
            {formatTemp(frame?.payload_temp_c ?? null)}
          </p>
        </div>
        <div className={cardStyle}>
          <p className="flex items-center gap-1.5 text-[var(--color-fg-muted)]">
            <Boxes className="h-3.5 w-3.5 text-[var(--color-info)]" /> Cargo
          </p>
          <p className="mt-1 font-mono text-base text-[var(--color-fg)]">2 items</p>
        </div>
      </CardContent>
    </Card>
  );
}
