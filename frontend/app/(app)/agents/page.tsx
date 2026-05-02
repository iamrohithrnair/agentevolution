"use client";

import { useEffect, useState } from "react";
import { Bot } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { ReasoningStream } from "@/components/dashboard/ReasoningStream";
import { listSkills } from "@/lib/api";
import type { Skill } from "@/lib/types";
import { formatPercent } from "@/lib/format";

export default function AgentsPage() {
  const [skills, setSkills] = useState<Skill[] | null>(null);
  const [selected, setSelected] = useState<Skill | null>(null);

  useEffect(() => {
    listSkills().then(setSkills);
  }, []);

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Agents & skills</h1>
        <p className="text-sm text-[var(--color-fg-muted)]">
          Every agent registered in the supervisor graph plus the reusable skills indexed for
          peer-to-peer recall. Click a card for the full capability record.
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
                  <button
                    type="button"
                    onClick={() => setSelected(s)}
                    className="group w-full text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] focus-visible:ring-offset-2 rounded-lg"
                    aria-label={`Open details for ${s.name}`}
                  >
                    <Card className="h-full cursor-pointer transition-shadow hover:shadow-[var(--shadow-2)] group-focus:shadow-[var(--shadow-2)]">
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
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <ReasoningStream title="Live agent activity" height={520} />
      </section>

      <Dialog open={selected !== null} onOpenChange={(open) => !open && setSelected(null)}>
        <DialogContent className="max-w-xl">
          {selected && (
            <>
              <DialogHeader>
                <DialogTitle className="flex items-center gap-2">
                  <span className="grid h-7 w-7 place-items-center rounded-md bg-[var(--color-accent-soft)] text-[var(--color-accent-fg)]">
                    <Bot className="h-3.5 w-3.5" />
                  </span>
                  {selected.name}
                </DialogTitle>
                <DialogDescription className="mt-1">
                  {selected.agent} · {selected.invocations} invocations ·{" "}
                  {formatPercent(selected.win_rate)} win rate
                </DialogDescription>
              </DialogHeader>

              <div className="space-y-4 text-sm">
                <section>
                  <h3 className="mb-1 text-xs font-semibold uppercase tracking-wider text-[var(--color-fg-muted)]">
                    Capability
                  </h3>
                  <p className="leading-relaxed text-[var(--color-fg)]">{selected.summary}</p>
                </section>

                {selected.parameters.length > 0 && (
                  <section>
                    <h3 className="mb-1 text-xs font-semibold uppercase tracking-wider text-[var(--color-fg-muted)]">
                      Tools / parameters
                    </h3>
                    <div className="flex flex-wrap gap-1.5">
                      {selected.parameters.map((p) => (
                        <Badge key={p} variant="outline" className="font-mono text-[10px]">
                          {p}
                        </Badge>
                      ))}
                    </div>
                  </section>
                )}

                <section className="grid grid-cols-2 gap-3 rounded-md border border-[var(--color-border)] bg-[var(--color-surface-2)] p-3 text-xs">
                  <div>
                    <p className="text-[var(--color-fg-muted)]">Skill id</p>
                    <p className="font-mono text-[11px]">{selected.skill_id}</p>
                  </div>
                  <div>
                    <p className="text-[var(--color-fg-muted)]">Invocations</p>
                    <p>{selected.invocations}</p>
                  </div>
                  <div>
                    <p className="text-[var(--color-fg-muted)]">Win rate</p>
                    <p>{formatPercent(selected.win_rate)}</p>
                  </div>
                  {selected.score !== undefined && (
                    <div>
                      <p className="text-[var(--color-fg-muted)]">Last score</p>
                      <p>{selected.score.toFixed(3)}</p>
                    </div>
                  )}
                </section>
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
