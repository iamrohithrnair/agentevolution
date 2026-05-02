"use client";

import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  Brain,
  Cloud,
  Hospital,
  ShieldAlert,
  UserRound,
  Search,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { memorySearch } from "@/lib/api";
import type { MemoryHit, MemoryKind } from "@/lib/types";
import { formatRelative } from "@/lib/format";

const ICONS: Record<MemoryKind, React.ComponentType<{ className?: string }>> = {
  reflection: Brain,
  incident: ShieldAlert,
  regulation: ShieldAlert,
  facility_intel: Hospital,
  weather_class: Cloud,
  operator_pref: UserRound,
};

interface Props {
  /**
   * Reserved for future per-mission memory namespacing — currently the
   * inspector queries cross-mission memory.  Accepting it now lets callers be
   * future-proof.
   */
  missionId?: string;
  initialQuery?: string;
}

export function MemoryInspector({ initialQuery }: Props) {
  const [query, setQuery] = useState(initialQuery ?? "storm corridor near Homerton");
  const [hits, setHits] = useState<MemoryHit[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [active, setActive] = useState<MemoryHit | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    const t = setTimeout(() => {
      memorySearch(query, 5).then(({ hits }) => {
        if (!cancelled) {
          setHits(hits);
          setLoading(false);
        }
      });
    }, 250);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [query]);

  const headerHint = useMemo(() => {
    if (loading) return "Embedding…";
    if (!hits) return "Idle";
    if (hits.length === 0) return "No memories matched";
    return `Top score ${(hits[0]?.score ?? 0).toFixed(3)}`;
  }, [loading, hits]);

  return (
    <Card className="flex h-full flex-col">
      <CardHeader className="flex-row items-center justify-between gap-3 pb-2">
        <CardTitle>Memory inspector</CardTitle>
        <Badge variant="outline">{headerHint}</Badge>
      </CardHeader>
      <CardContent className="flex-1 space-y-3">
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--color-fg-subtle)]" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Query mission_memory…"
            aria-label="Memory query"
            className="h-9 w-full rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] pl-9 pr-3 text-sm placeholder:text-[var(--color-fg-subtle)] focus:outline-none focus-visible:shadow-[var(--shadow-focus)]"
          />
        </div>

        <div className="space-y-2.5" data-testid="memory-cards" aria-busy={loading}>
          {loading && !hits
            ? Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-20 w-full" />
              ))
            : (hits ?? []).map((hit) => {
                const Icon = ICONS[hit.kind];
                return (
                  <motion.article
                    key={hit.id}
                    role="button"
                    tabIndex={0}
                    onClick={() => setActive(hit)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        setActive(hit);
                      }
                    }}
                    layout
                    initial={{ opacity: 0, y: 4 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.18 }}
                    className="cursor-pointer rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] p-3 shadow-[var(--shadow-1)] transition-shadow hover:shadow-[var(--shadow-2)]"
                  >
                    <header className="mb-1.5 flex items-center gap-2">
                      <Icon className="h-4 w-4 text-[var(--color-accent)]" />
                      <span className="text-[11px] uppercase tracking-wider text-[var(--color-fg-muted)]">
                        {hit.kind.replace("_", " ")}
                      </span>
                      <span className="ml-auto font-mono text-[11px] text-[var(--color-fg-subtle)]">
                        {hit.score.toFixed(3)}
                      </span>
                    </header>
                    <p className="line-clamp-3 text-sm leading-snug text-[var(--color-fg)]">{hit.text}</p>
                    <footer className="mt-2 flex flex-wrap items-center gap-1.5">
                      {hit.metadata.region && (
                        <Badge variant="outline">{String(hit.metadata.region)}</Badge>
                      )}
                      {hit.metadata.weather_class && (
                        <Badge variant="info">{String(hit.metadata.weather_class)}</Badge>
                      )}
                      {hit.metadata.success !== undefined && (
                        <Badge variant={hit.metadata.success ? "success" : "danger"}>
                          {hit.metadata.success ? "succeeded" : "failed"}
                        </Badge>
                      )}
                      <span className="ml-auto text-[11px] text-[var(--color-fg-subtle)]">
                        {formatRelative(hit.created_at)}
                      </span>
                    </footer>
                    <div
                      className="mt-2 h-1 overflow-hidden rounded bg-[var(--color-surface-2)]"
                      aria-label={`similarity ${hit.score.toFixed(2)}`}
                    >
                      <div
                        className="h-1 rounded bg-[var(--color-accent)]"
                        style={{ width: `${Math.round(hit.score * 100)}%` }}
                      />
                    </div>
                  </motion.article>
                );
              })}

          {hits && hits.length === 0 && !loading && (
            <p className="rounded-md border border-dashed border-[var(--color-border)] p-3 text-center text-sm text-[var(--color-fg-muted)]">
              No memories matched. Try a broader query like &ldquo;storm&rdquo; or
              &ldquo;handover&rdquo;.
            </p>
          )}
        </div>

        <Sheet open={Boolean(active)} onOpenChange={(o) => !o && setActive(null)}>
          <SheetContent>
            {active && (
              <>
                <SheetHeader>
                  <SheetTitle className="flex items-center gap-2">
                    <Brain className="h-4 w-4 text-[var(--color-accent)]" />
                    {active.kind.replace("_", " ")}
                  </SheetTitle>
                </SheetHeader>
                <div className="space-y-4 overflow-y-auto p-5">
                  <p className="text-sm leading-relaxed text-[var(--color-fg)]">{active.text}</p>
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <Stat label="similarity" value={active.score.toFixed(3)} />
                    <Stat label="created" value={formatRelative(active.created_at)} />
                    {Object.entries(active.metadata).map(([k, v]) => (
                      <Stat key={k} label={k} value={String(v)} />
                    ))}
                  </div>
                  <pre className="overflow-x-auto rounded-md border border-[var(--color-border)] bg-[var(--color-surface-2)] p-3 font-mono text-[11px] leading-relaxed">
                    {JSON.stringify(active, null, 2)}
                  </pre>
                </div>
              </>
            )}
          </SheetContent>
        </Sheet>
      </CardContent>
    </Card>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface-2)] p-2">
      <p className="text-[10px] uppercase tracking-wider text-[var(--color-fg-subtle)]">{label}</p>
      <p className="font-mono text-[11px] text-[var(--color-fg)]">{value}</p>
    </div>
  );
}
