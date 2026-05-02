"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Sparkles, AlertTriangle, Hospital, ShieldAlert, UserRound } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { listReflections } from "@/lib/api";
import { openAgentsStream } from "@/lib/sse";
import type { MemoryHit, MemoryKind } from "@/lib/types";
import { formatRelative } from "@/lib/format";

const ICONS: Record<MemoryKind, React.ComponentType<{ className?: string }>> = {
  reflection: Sparkles,
  incident: ShieldAlert,
  regulation: AlertTriangle,
  facility_intel: Hospital,
  weather_class: AlertTriangle,
  operator_pref: UserRound,
};

const FILTER_KINDS: MemoryKind[] = [
  "reflection",
  "incident",
  "regulation",
  "facility_intel",
  "operator_pref",
];

interface Props {
  limit?: number;
  filterChips?: boolean;
}

export function ReflectionFeed({ limit = 30, filterChips = true }: Props) {
  const [items, setItems] = useState<MemoryHit[]>([]);
  const [filter, setFilter] = useState<MemoryKind | "all">("all");
  const [selected, setSelected] = useState<MemoryHit | null>(null);

  useEffect(() => {
    let cancelled = false;
    listReflections().then((rs) => {
      if (cancelled) return;
      // Dedupe by id in case the backend returns the same doc twice.
      const seen = new Set<string>();
      const unique = rs.filter((r) => (seen.has(r.id) ? false : (seen.add(r.id), true)));
      setItems(unique.slice(0, limit));
    });
    const off = openAgentsStream({ kind: "reflection" }, (msg) => {
      const synth: MemoryHit = {
        id: msg.id,
        kind: "reflection",
        text: msg.text,
        score: 0.85,
        metadata: {
          mission_id: msg.mission_id,
          created_at: msg.ts,
        },
        created_at: msg.ts,
      };
      setItems((prev) => {
        if (prev.some((p) => p.id === synth.id)) return prev;
        return [synth, ...prev].slice(0, limit);
      });
    });
    return () => {
      cancelled = true;
      off();
    };
  }, [limit]);

  const visible = filter === "all" ? items : items.filter((i) => i.kind === filter);

  return (
    <Card className="flex h-full flex-col">
      <CardHeader className="flex-row items-center justify-between gap-3 pb-2">
        <CardTitle>Reflection feed</CardTitle>
        <Badge variant="outline">{items.length} lessons</Badge>
      </CardHeader>
      {filterChips && (
        <div className="flex flex-wrap gap-1.5 px-5 pb-2">
          <FilterChip
            active={filter === "all"}
            onClick={() => setFilter("all")}
            label="all"
          />
          {FILTER_KINDS.map((k) => (
            <FilterChip
              key={k}
              active={filter === k}
              onClick={() => setFilter(k)}
              label={k.replace("_", " ")}
            />
          ))}
        </div>
      )}
      <CardContent className="thin-scrollbar flex-1 overflow-y-auto pt-2" data-testid="reflection-feed">
        <AnimatePresence initial={false}>
          {visible.length === 0 ? (
            <p className="rounded-md border border-dashed border-[var(--color-border)] p-3 text-sm text-[var(--color-fg-muted)]">
              No lessons yet. Run a mission and the system will start learning.
            </p>
          ) : (
            <ul className="space-y-3">
              {visible.map((item, i) => {
                const Icon = ICONS[item.kind] ?? Sparkles;
                return (
                  <motion.li
                    key={item.id}
                    layout
                    initial={{ opacity: 0, y: 6, boxShadow: "var(--shadow-2)" }}
                    animate={{ opacity: 1, y: 0, boxShadow: "var(--shadow-1)" }}
                    transition={{ delay: Math.min(i * 0.04, 0.2), duration: 0.2 }}
                  >
                    <button
                      type="button"
                      onClick={() => setSelected(item)}
                      aria-label={`Open reflection ${item.id}`}
                      className="w-full rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] p-3 text-left transition-colors hover:border-[var(--color-accent)] hover:bg-[var(--color-surface-2)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
                    >
                      <header className="mb-1.5 flex items-center gap-2">
                        <span className="grid h-6 w-6 place-items-center rounded-md bg-[var(--color-success-soft)] text-[var(--color-success)]">
                          <Icon className="h-3.5 w-3.5" />
                        </span>
                        <span className="text-[11px] uppercase tracking-wider text-[var(--color-fg-muted)]">
                          {item.kind.replace("_", " ")}
                        </span>
                        <span className="ml-auto text-[11px] text-[var(--color-fg-subtle)]">
                          {formatRelative(item.created_at)}
                        </span>
                      </header>
                      <p className="line-clamp-3 text-sm leading-snug text-[var(--color-fg)]">
                        {item.text}
                      </p>
                    </button>
                  </motion.li>
                );
              })}
            </ul>
          )}
        </AnimatePresence>
      </CardContent>

      <Dialog open={selected !== null} onOpenChange={(open) => !open && setSelected(null)}>
        <DialogContent className="max-w-xl">
          {selected && (
            <>
              <DialogHeader>
                <DialogTitle className="flex items-center gap-2">
                  {(() => {
                    const Icon = ICONS[selected.kind] ?? Sparkles;
                    return (
                      <span className="grid h-7 w-7 place-items-center rounded-md bg-[var(--color-success-soft)] text-[var(--color-success)]">
                        <Icon className="h-3.5 w-3.5" />
                      </span>
                    );
                  })()}
                  <span className="capitalize">{selected.kind.replace("_", " ")}</span>
                </DialogTitle>
                <DialogDescription className="mt-1 text-xs">
                  {formatRelative(selected.created_at)} · score{" "}
                  {selected.score.toFixed(3)}
                </DialogDescription>
              </DialogHeader>

              <div className="space-y-4 text-sm">
                <section>
                  <h3 className="mb-1 text-xs font-semibold uppercase tracking-wider text-[var(--color-fg-muted)]">
                    Lesson
                  </h3>
                  <p className="whitespace-pre-wrap leading-relaxed text-[var(--color-fg)]">
                    {selected.text}
                  </p>
                </section>

                {selected.metadata && Object.keys(selected.metadata).length > 0 && (
                  <section>
                    <h3 className="mb-1 text-xs font-semibold uppercase tracking-wider text-[var(--color-fg-muted)]">
                      Metadata
                    </h3>
                    <div className="flex flex-wrap gap-1.5">
                      {Object.entries(selected.metadata)
                        .filter(
                          ([k]) =>
                            !["embedding", "embedding_model", "use_count", "score_ema"].includes(k),
                        )
                        .slice(0, 12)
                        .map(([k, v]) => (
                          <Badge key={k} variant="outline" className="font-mono text-[10px]">
                            {k}: {typeof v === "object" ? JSON.stringify(v) : String(v)}
                          </Badge>
                        ))}
                    </div>
                  </section>
                )}

                <section className="grid grid-cols-2 gap-3 rounded-md border border-[var(--color-border)] bg-[var(--color-surface-2)] p-3 text-xs">
                  <div>
                    <p className="text-[var(--color-fg-muted)]">ID</p>
                    <p className="truncate font-mono text-[11px]">{selected.id}</p>
                  </div>
                  <div>
                    <p className="text-[var(--color-fg-muted)]">Kind</p>
                    <p className="capitalize">{selected.kind.replace("_", " ")}</p>
                  </div>
                  <div>
                    <p className="text-[var(--color-fg-muted)]">Score</p>
                    <p>{selected.score.toFixed(3)}</p>
                  </div>
                  <div>
                    <p className="text-[var(--color-fg-muted)]">Written</p>
                    <p>{formatRelative(selected.created_at)}</p>
                  </div>
                </section>
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>
    </Card>
  );
}

function FilterChip({ active, onClick, label }: { active: boolean; onClick: () => void; label: string }) {
  return (
    <Button
      variant={active ? "soft" : "ghost"}
      size="sm"
      onClick={onClick}
      className="h-7 px-2.5 text-[11px] capitalize"
    >
      {label}
    </Button>
  );
}
