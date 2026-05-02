"use client";

import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Bot,
  Brain,
  Cloud,
  Compass,
  GaugeCircle,
  Mic,
  Radio,
  ShieldAlert,
  Sparkles,
  User,
  Wand2,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { openAgentsStream } from "@/lib/sse";
import { clockTime } from "@/lib/format";
import type { AgentMessage, AgentMessageKind } from "@/lib/types";

const ICONS: Partial<Record<AgentMessageKind, React.ComponentType<{ className?: string }>>> = {
  user: User,
  supervisor: Bot,
  interpreter: Wand2,
  memory: Brain,
  memory_query: Brain,
  planner: Compass,
  weather: Cloud,
  geofence: ShieldAlert,
  preflight: GaugeCircle,
  payload: GaugeCircle,
  dispatch: Radio,
  vision: Compass,
  replanner: Compass,
  anomaly: ShieldAlert,
  deconfliction: ShieldAlert,
  narrator: Mic,
  reflection: Sparkles,
  retrieval_critic: Brain,
  agent_activity: Bot,
};

const ACCENTS: Partial<Record<AgentMessageKind, string>> = {
  user: "var(--color-info)",
  supervisor: "var(--color-accent)",
  planner: "var(--color-accent)",
  memory: "var(--color-info)",
  memory_query: "var(--color-info)",
  weather: "var(--color-info)",
  geofence: "var(--color-danger)",
  anomaly: "var(--color-danger)",
  reflection: "var(--color-success)",
  narrator: "var(--color-accent-2)",
  replanner: "var(--color-warning)",
  preflight: "var(--color-success)",
  dispatch: "var(--color-accent)",
};

interface Props {
  missionId?: string;
  limit?: number;
  height?: number | string;
  title?: string;
}

export function ReasoningStream({
  missionId,
  limit = 60,
  height = 360,
  title = "Reasoning stream",
}: Props) {
  const [items, setItems] = useState<AgentMessage[]>([]);
  const stickyRef = useRef(true);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const off = openAgentsStream(missionId ? { mission_id: missionId } : {}, (m) => {
      setItems((prev) => {
        if (prev.find((p) => p.id === m.id)) return prev;
        const next = [...prev, m].slice(-limit);
        return next;
      });
    });
    return () => off();
  }, [missionId, limit]);

  // Sticky-bottom scroll: only auto-stick if user is near the bottom.
  useEffect(() => {
    const el = scrollRef.current;
    if (!el || !stickyRef.current) return;
    el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [items]);

  return (
    <Card className="flex h-full flex-col overflow-hidden">
      <CardHeader className="flex-row items-center justify-between gap-3 pb-2">
        <CardTitle>{title}</CardTitle>
        <Badge variant="accent">{items.length} events</Badge>
      </CardHeader>
      <CardContent className="flex-1 px-0 pb-0">
        <div
          ref={scrollRef}
          onScroll={(e) => {
            const el = e.currentTarget;
            stickyRef.current = el.scrollTop + el.clientHeight >= el.scrollHeight - 24;
          }}
          className="thin-scrollbar overflow-y-auto px-5"
          style={{ height }}
          data-testid="reasoning-stream"
        >
          <AnimatePresence initial={false}>
            {items.length === 0 ? (
              <p className="py-6 text-sm text-[var(--color-fg-muted)]">
                Standing by. Speak or dispatch a mission to see Supervisor → Planner → Dispatch in
                real time.
              </p>
            ) : (
              items.map((m) => {
                const Icon = ICONS[m.kind] ?? Bot;
                const accent = ACCENTS[m.kind] ?? "var(--color-fg-muted)";
                return (
                  <motion.article
                    key={m.id}
                    layout
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: 4 }}
                    transition={{ duration: 0.2, ease: "easeOut" }}
                    className="border-b border-dashed border-[var(--color-border)] py-3 last:border-b-0"
                  >
                    <header className="mb-1 flex items-center gap-2">
                      <span
                        className="grid h-6 w-6 place-items-center rounded-md border border-[var(--color-border)]"
                        style={{ color: accent }}
                      >
                        <Icon className="h-3.5 w-3.5" />
                      </span>
                      <span className="text-xs font-semibold tracking-tight">{m.agent ?? m.kind}</span>
                      <span className="ml-auto font-mono text-[11px] text-[var(--color-fg-subtle)]">
                        {clockTime(m.ts)}
                      </span>
                    </header>
                    <p className="pl-8 text-sm leading-snug text-[var(--color-fg)]">{m.text}</p>
                  </motion.article>
                );
              })
            )}
          </AnimatePresence>
        </div>
      </CardContent>
    </Card>
  );
}
