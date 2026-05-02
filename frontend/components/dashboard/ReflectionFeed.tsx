"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Sparkles, AlertTriangle, Hospital, ShieldAlert, UserRound } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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
                    className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] p-3"
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
                    <p className="text-sm leading-snug text-[var(--color-fg)]">{item.text}</p>
                  </motion.li>
                );
              })}
            </ul>
          )}
        </AnimatePresence>
      </CardContent>
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
