"use client";

import { useState } from "react";
import { AlertTriangle, Cloud, RotateCcw, Zap } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { simulateWeather, injectObstacle, createMission } from "@/lib/api";

export function DemoMenu() {
  const [busy, setBusy] = useState<string | null>(null);

  async function withBusy(label: string, fn: () => Promise<unknown>) {
    setBusy(label);
    try {
      await fn();
    } catch (e) {
      toast.error(`${label} failed: ${(e as Error).message}`);
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="mt-auto space-y-1.5 border-t border-[var(--color-border)] p-3">
      <p className="px-1 pt-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--color-fg-subtle)]">
        Demo affordances
      </p>
      <Button
        variant="outline"
        size="sm"
        className="w-full justify-start"
        disabled={busy === "storm"}
        onClick={() =>
          withBusy("storm", async () => {
            await simulateWeather("high");
            toast.success("Storm injected — Atlas Trigger fanning out.");
          })
        }
      >
        <Cloud className="mr-2 h-4 w-4 text-[var(--color-info)]" />
        Inject Storm
      </Button>
      <Button
        variant="outline"
        size="sm"
        className="w-full justify-start"
        disabled={busy === "obstacle"}
        onClick={() =>
          withBusy("obstacle", async () => {
            await injectObstacle("crane");
            toast.info("Obstacle injected (crane).");
          })
        }
      >
        <AlertTriangle className="mr-2 h-4 w-4 text-[var(--color-warning)]" />
        Inject Obstacle
      </Button>
      <Button
        variant="outline"
        size="sm"
        className="w-full justify-start"
        disabled={busy === "encore"}
        onClick={() =>
          withBusy("encore", async () => {
            const r = await createMission({
              deliveries: [
                { destination_id: "fac_kings", supply: "defib", payload_weight_kg: 1.8, priority: "high" },
                {
                  destination_id: "fac_royal_london",
                  supply: "o_neg_blood",
                  payload_weight_kg: 0.6,
                  priority: "critical",
                  cold_chain_required: true,
                },
              ],
              scenario: "Whitechapel Trauma · encore",
            });
            toast.success(`Encore queued · ${r.mission_id.slice(-6)} (${r.eta_seconds}s ETA)`);
          })
        }
      >
        <Zap className="mr-2 h-4 w-4 text-[var(--color-accent)]" />
        Run Encore
      </Button>
      <Button
        variant="ghost"
        size="sm"
        className="w-full justify-start text-[var(--color-fg-muted)]"
        disabled
      >
        <RotateCcw className="mr-2 h-4 w-4" />
        Replay Mission
      </Button>
    </div>
  );
}
