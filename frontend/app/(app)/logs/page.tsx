"use client";

import { useEffect, useState } from "react";
import { ScrollText, Wrench, ShieldCheck } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import env from "@/lib/env";

type FlightLog = {
  _id?: string;
  mission_id?: string;
  drone_id?: string;
  event?: string;
  ts?: string;
  payload?: Record<string, unknown>;
};

type AuditEntry = {
  _id?: string;
  mission_id?: string;
  step?: string;
  digest?: string;
  signature_id?: string;
  ts?: string;
};

type ToolCall = {
  _id?: string;
  tool?: string;
  agent?: string;
  status?: string;
  started_at?: string;
  completed_at?: string;
};

async function fetchJSON<T>(path: string): Promise<T[]> {
  try {
    const r = await fetch(`${env.apiBase}${path}`, { cache: "no-store" });
    if (!r.ok) return [];
    return (await r.json()) as T[];
  } catch {
    return [];
  }
}

function fmtTs(ts?: string): string {
  if (!ts) return "—";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts;
  return d.toLocaleString();
}

export default function LogsPage() {
  const [flight, setFlight] = useState<FlightLog[] | null>(null);
  const [audit, setAudit] = useState<AuditEntry[] | null>(null);
  const [tools, setTools] = useState<ToolCall[] | null>(null);

  useEffect(() => {
    fetchJSON<FlightLog>("/api/logs/flight").then(setFlight);
    fetchJSON<AuditEntry>("/api/logs/audit").then(setAudit);
    fetchJSON<ToolCall>("/api/logs/tool-calls").then(setTools);
    const id = setInterval(() => {
      fetchJSON<FlightLog>("/api/logs/flight").then(setFlight);
      fetchJSON<AuditEntry>("/api/logs/audit").then(setAudit);
      fetchJSON<ToolCall>("/api/logs/tool-calls").then(setTools);
    }, 5_000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="space-y-5">
      <header>
        <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
          <ScrollText className="h-5 w-5 text-[var(--color-accent)]" />
          Logs
        </h1>
        <p className="text-sm text-[var(--color-fg-muted)]">
          Flight events, the append-only audit trail, and recent tool invocations. Refreshes every
          five seconds.
        </p>
      </header>

      <Tabs defaultValue="flight">
        <TabsList>
          <TabsTrigger value="flight">Flight events</TabsTrigger>
          <TabsTrigger value="audit">Audit trail</TabsTrigger>
          <TabsTrigger value="tools">Tool calls</TabsTrigger>
        </TabsList>

        <TabsContent value="flight" className="mt-4">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">flight_logs</CardTitle>
              <CardDescription className="text-xs">
                Live events from the flight loop. Source: MongoDB Atlas change streams.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {flight === null ? (
                <Skeleton className="h-40 w-full" />
              ) : flight.length === 0 ? (
                <p className="text-sm text-[var(--color-fg-muted)]">
                  No flight events yet. Run a mission and they'll show up here.
                </p>
              ) : (
                <ul className="divide-y divide-[var(--color-border)]">
                  {flight.map((f, i) => (
                    <li
                      key={f._id ?? i}
                      className="flex flex-wrap items-baseline gap-3 py-2 text-sm"
                    >
                      <span className="font-mono text-xs text-[var(--color-fg-muted)]">
                        {fmtTs(f.ts)}
                      </span>
                      <Badge variant="outline" className="text-[10px]">
                        {f.event ?? "event"}
                      </Badge>
                      {f.mission_id ? (
                        <span className="font-mono text-xs">{f.mission_id}</span>
                      ) : null}
                      {f.drone_id ? (
                        <span className="text-xs text-[var(--color-fg-muted)]">
                          drone {f.drone_id}
                        </span>
                      ) : null}
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="audit" className="mt-4">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-sm">
                <ShieldCheck className="h-4 w-4" />
                audit_trail
              </CardTitle>
              <CardDescription className="text-xs">
                Append-only signature record. Each row carries a SHA-256 digest plus the SIG-####
                short id.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {audit === null ? (
                <Skeleton className="h-40 w-full" />
              ) : audit.length === 0 ? (
                <p className="text-sm text-[var(--color-fg-muted)]">No audit entries yet.</p>
              ) : (
                <ul className="divide-y divide-[var(--color-border)]">
                  {audit.map((a, i) => (
                    <li key={a._id ?? i} className="flex flex-wrap items-baseline gap-3 py-2 text-sm">
                      <span className="font-mono text-xs text-[var(--color-fg-muted)]">
                        {fmtTs(a.ts)}
                      </span>
                      <Badge variant="outline" className="font-mono text-[10px]">
                        {a.signature_id ?? "SIG-?"}
                      </Badge>
                      {a.mission_id ? (
                        <span className="font-mono text-xs">{a.mission_id}</span>
                      ) : null}
                      {a.step ? <span className="text-xs">{a.step}</span> : null}
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="tools" className="mt-4">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-sm">
                <Wrench className="h-4 w-4" />
                tool_call_log
              </CardTitle>
              <CardDescription className="text-xs">
                Every @mongo_tool invocation, with status and timing. Idempotency keys live here.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {tools === null ? (
                <Skeleton className="h-40 w-full" />
              ) : tools.length === 0 ? (
                <p className="text-sm text-[var(--color-fg-muted)]">
                  No tool calls recorded yet.
                </p>
              ) : (
                <ul className="divide-y divide-[var(--color-border)]">
                  {tools.map((t, i) => (
                    <li key={t._id ?? i} className="flex flex-wrap items-baseline gap-3 py-2 text-sm">
                      <span className="font-mono text-xs text-[var(--color-fg-muted)]">
                        {fmtTs(t.started_at)}
                      </span>
                      <Badge
                        variant={t.status === "completed" ? "default" : "outline"}
                        className="text-[10px]"
                      >
                        {t.status ?? "pending"}
                      </Badge>
                      <span className="font-mono text-xs">{t.tool}</span>
                      {t.agent ? (
                        <span className="text-xs text-[var(--color-fg-muted)]">{t.agent}</span>
                      ) : null}
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
