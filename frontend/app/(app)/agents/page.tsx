"use client";

import { useEffect, useState } from "react";
import { Bot } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ReasoningStream } from "@/components/dashboard/ReasoningStream";
import { listSkills } from "@/lib/api";
import type { Skill } from "@/lib/types";
import { formatPercent } from "@/lib/format";

export default function AgentsPage() {
  const [skills, setSkills] = useState<Skill[] | null>(null);

  useEffect(() => {
    listSkills().then(setSkills);
  }, []);

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Agents & skills</h1>
        <p className="text-sm text-[var(--color-fg-muted)]">
          Every agent registered in the supervisor graph plus the reusable skills indexed for
          peer-to-peer recall.
        </p>
      </header>

      <section className="grid gap-5 lg:grid-cols-[minmax(0,_3fr)_minmax(0,_2fr)]">
        <div>
          <h2 className="mb-2 text-sm font-semibold tracking-tight">Skills registry</h2>
          {!skills ? (
            <div className="grid gap-3 sm:grid-cols-2">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-32 w-full" />
              ))}
            </div>
          ) : (
            <ul className="grid gap-3 sm:grid-cols-2">
              {skills.map((s) => (
                <li key={s.skill_id}>
                  <Card className="h-full">
                    <CardHeader className="flex-row items-start justify-between gap-2 pb-2">
                      <div>
                        <CardTitle className="text-sm">{s.name}</CardTitle>
                        <CardDescription className="mt-0.5 text-xs">{s.agent}</CardDescription>
                      </div>
                      <span className="grid h-7 w-7 place-items-center rounded-md bg-[var(--color-accent-soft)] text-[var(--color-accent-fg)]">
                        <Bot className="h-3.5 w-3.5" />
                      </span>
                    </CardHeader>
                    <CardContent className="space-y-2 pt-0 text-xs">
                      <p className="line-clamp-2 text-[var(--color-fg)]">{s.summary}</p>
                      <div className="flex flex-wrap gap-1.5">
                        {s.parameters.map((p) => (
                          <Badge key={p} variant="outline" className="font-mono text-[10px]">
                            {p}
                          </Badge>
                        ))}
                      </div>
                      <div className="flex items-center justify-between border-t border-dashed border-[var(--color-border)] pt-2 text-[var(--color-fg-muted)]">
                        <span>{s.invocations} invocations</span>
                        <Badge variant={s.win_rate >= 0.9 ? "success" : "info"}>
                          {formatPercent(s.win_rate)} win rate
                        </Badge>
                      </div>
                    </CardContent>
                  </Card>
                </li>
              ))}
            </ul>
          )}
        </div>

        <ReasoningStream title="Live agent activity" height={520} />
      </section>
    </div>
  );
}
