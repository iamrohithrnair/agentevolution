"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip as RTooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { listExperiments } from "@/lib/api";
import type { ExperimentPoint } from "@/lib/types";
import { formatDuration } from "@/lib/format";

export default function AnalyticsPage() {
  const [points, setPoints] = useState<ExperimentPoint[] | null>(null);

  useEffect(() => {
    listExperiments().then(setPoints);
  }, []);

  const scenarios = useMemo(() => {
    if (!points) return [] as Array<{ scenario: string; takes: ExperimentPoint[] }>;
    const map = new Map<string, ExperimentPoint[]>();
    for (const p of points) {
      if (!map.has(p.scenario)) map.set(p.scenario, []);
      map.get(p.scenario)!.push(p);
    }
    return Array.from(map.entries()).map(([scenario, takes]) => ({
      scenario,
      takes: [...takes].sort((a, b) => a.take_n - b.take_n),
    }));
  }, [points]);

  const improvementSummary = useMemo(() => {
    if (!points || points.length === 0) return null;
    const byScenario = scenarios.map((s) => {
      const first = s.takes[0]?.actual_time_s ?? 0;
      const last = s.takes[s.takes.length - 1]?.actual_time_s ?? first;
      const delta = first - last;
      const deltaPct = first === 0 ? 0 : delta / first;
      return { scenario: s.scenario, delta, deltaPct };
    });
    return byScenario;
  }, [points, scenarios]);

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Self-evolution</h1>
        <p className="text-sm text-[var(--color-fg-muted)]">
          Take-over-take improvement on the same scenario. Lessons are extracted by
          ReflectionAgent and embedded back into mission_memory for the next run.
        </p>
      </header>

      {!points ? (
        <Skeleton className="h-72 w-full" />
      ) : (
        <>
          <div className="grid gap-3 md:grid-cols-3">
            {improvementSummary?.map((s) => (
              <Card key={s.scenario}>
                <CardHeader className="pb-2">
                  <CardDescription className="text-[11px] uppercase tracking-wider">
                    {s.scenario}
                  </CardDescription>
                  <CardTitle className="font-mono text-2xl tabular-nums tracking-tight">
                    −{formatDuration(s.delta)}
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <Badge variant={s.delta > 0 ? "success" : "outline"}>
                    {(s.deltaPct * 100).toFixed(1)}% faster after 3 takes
                  </Badge>
                </CardContent>
              </Card>
            ))}
          </div>

          <div className="grid gap-5 lg:grid-cols-2">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle>Mission time per take</CardTitle>
                <CardDescription>Lower is better — same scenario re-run with growing memory.</CardDescription>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={260}>
                  <LineChart data={pivot(scenarios)}>
                    <CartesianGrid stroke="var(--color-border)" strokeDasharray="3 3" />
                    <XAxis
                      dataKey="take_n"
                      tickLine={false}
                      stroke="var(--color-fg-muted)"
                      label={{ value: "Take", position: "insideBottom", offset: -2, fill: "var(--color-fg-muted)" }}
                    />
                    <YAxis tickLine={false} stroke="var(--color-fg-muted)" />
                    <RTooltip
                      contentStyle={{
                        background: "var(--color-elevated)",
                        border: "1px solid var(--color-border)",
                        borderRadius: 8,
                        fontSize: 12,
                      }}
                    />
                    <Legend />
                    {scenarios.map((s, i) => (
                      <Line
                        key={s.scenario}
                        type="monotone"
                        dataKey={s.scenario}
                        stroke={i % 2 === 0 ? "var(--color-accent)" : "var(--color-info)"}
                        strokeWidth={2}
                        dot={{ r: 3 }}
                        activeDot={{ r: 5 }}
                      />
                    ))}
                  </LineChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle>Reroutes per take</CardTitle>
                <CardDescription>How the planner&rsquo;s confidence grew with experience.</CardDescription>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={260}>
                  <BarChart data={pivot(scenarios, "reroutes")}>
                    <CartesianGrid stroke="var(--color-border)" strokeDasharray="3 3" />
                    <XAxis dataKey="take_n" tickLine={false} stroke="var(--color-fg-muted)" />
                    <YAxis tickLine={false} stroke="var(--color-fg-muted)" allowDecimals={false} />
                    <RTooltip
                      contentStyle={{
                        background: "var(--color-elevated)",
                        border: "1px solid var(--color-border)",
                        borderRadius: 8,
                        fontSize: 12,
                      }}
                    />
                    <Legend />
                    {scenarios.map((s, i) => (
                      <Bar
                        key={s.scenario}
                        dataKey={s.scenario}
                        fill={i % 2 === 0 ? "var(--color-accent)" : "var(--color-info)"}
                        radius={[6, 6, 0, 0]}
                      />
                    ))}
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle>Lessons extracted</CardTitle>
              <CardDescription>These reflections are now part of mission_memory.</CardDescription>
            </CardHeader>
            <CardContent>
              <ul className="space-y-2 text-sm">
                {points
                  .filter((p) => p.lesson)
                  .map((p, i) => (
                    <li
                      key={i}
                      className="flex items-start gap-3 rounded-md border border-[var(--color-border)] bg-[var(--color-surface-2)] p-3"
                    >
                      <span className="mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full bg-[var(--color-success-soft)] text-[10px] font-semibold text-[var(--color-success)]">
                        T{p.take_n}
                      </span>
                      <p className="leading-snug">
                        <span className="font-medium text-[var(--color-fg)]">{p.scenario}</span>
                        <span className="px-1.5 text-[var(--color-fg-muted)]">·</span>
                        {p.lesson}
                      </p>
                    </li>
                  ))}
              </ul>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}

type Row = { take_n: number } & Record<string, number | string>;

function pivot(
  scenarios: Array<{ scenario: string; takes: ExperimentPoint[] }>,
  field: keyof ExperimentPoint = "actual_time_s",
): Row[] {
  const takes = new Set<number>();
  for (const s of scenarios) for (const t of s.takes) takes.add(t.take_n);
  const sorted = Array.from(takes).sort((a, b) => a - b);
  return sorted.map((take_n) => {
    const row: Row = { take_n };
    for (const s of scenarios) {
      const point = s.takes.find((t) => t.take_n === take_n);
      if (point && typeof point[field] === "number") row[s.scenario] = point[field] as number;
    }
    return row;
  });
}
