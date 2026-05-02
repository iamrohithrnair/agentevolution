"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Plus, Send, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { listFacilities, createMission } from "@/lib/api";
import { SUPPLY_LABELS, type Facility, type Priority, type Supply } from "@/lib/types";

interface DraftDelivery {
  destination_id: string;
  supply: Supply;
  payload_weight_kg: number;
  priority: Priority;
  cold_chain_required: boolean;
}

const PRIORITIES: Priority[] = ["low", "normal", "high", "critical"];
const SUPPLIES: Supply[] = Object.keys(SUPPLY_LABELS) as Supply[];

const DEFAULT_DELIVERY: DraftDelivery = {
  destination_id: "fac_royal_london",
  supply: "o_neg_blood",
  payload_weight_kg: 1.2,
  priority: "high",
  cold_chain_required: true,
};

export function DispatchForm() {
  const router = useRouter();
  const [facilities, setFacilities] = useState<Facility[]>([]);
  const [items, setItems] = useState<DraftDelivery[]>([DEFAULT_DELIVERY]);
  const [scenario, setScenario] = useState<string>("Whitechapel Trauma");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    listFacilities().then(setFacilities);
  }, []);

  const facilitiesNotDepot = facilities.filter((f) => f.type !== "depot");

  function addItem() {
    setItems((s) => [...s, DEFAULT_DELIVERY]);
  }

  function updateItem(i: number, patch: Partial<DraftDelivery>) {
    setItems((s) => s.map((x, idx) => (idx === i ? { ...x, ...patch } : x)));
  }

  function removeItem(i: number) {
    setItems((s) => (s.length === 1 ? s : s.filter((_, idx) => idx !== i)));
  }

  async function submit() {
    setSubmitting(true);
    try {
      const r = await createMission({
        deliveries: items,
        scenario,
        origin_id: "fac_depot_canary",
      });
      toast.success(
        `Mission ${r.mission_id.slice(-6)} dispatched · drone ${r.drone_id} · ETA ${r.eta_seconds}s.`,
      );
      router.push(`/missions/${r.mission_id}`);
    } catch (e) {
      toast.error(`Dispatch failed: ${(e as Error).message}`);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card data-testid="dispatch-form">
      <CardHeader className="flex-row items-center justify-between gap-3 pb-2">
        <CardTitle>Compose mission</CardTitle>
        <Badge variant="accent">{items.length} cargo</Badge>
      </CardHeader>
      <CardContent className="space-y-4">
        <label className="block text-xs">
          <span className="mb-1 block text-[var(--color-fg-muted)]">Scenario name</span>
          <input
            value={scenario}
            onChange={(e) => setScenario(e.target.value)}
            className="h-9 w-full rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 text-sm focus:outline-none focus-visible:shadow-[var(--shadow-focus)]"
            aria-label="Scenario name"
          />
        </label>

        <ul className="space-y-3">
          {items.map((d, i) => (
            <li
              key={i}
              className="grid grid-cols-12 items-end gap-2 rounded-md border border-[var(--color-border)] bg-[var(--color-surface-2)] p-3 text-xs"
            >
              <div className="col-span-12 sm:col-span-4">
                <span className="mb-1 block text-[var(--color-fg-muted)]">Destination</span>
                <Select
                  value={d.destination_id}
                  onValueChange={(v) => updateItem(i, { destination_id: v })}
                >
                  <SelectTrigger aria-label={`Destination ${i + 1}`}>
                    <SelectValue placeholder="Pick…" />
                  </SelectTrigger>
                  <SelectContent>
                    {facilitiesNotDepot.map((f) => (
                      <SelectItem key={f.id} value={f.id}>
                        {f.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="col-span-6 sm:col-span-3">
                <span className="mb-1 block text-[var(--color-fg-muted)]">Supply</span>
                <Select
                  value={d.supply}
                  onValueChange={(v) => updateItem(i, { supply: v as Supply })}
                >
                  <SelectTrigger aria-label={`Supply ${i + 1}`}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {SUPPLIES.map((s) => (
                      <SelectItem key={s} value={s}>
                        {SUPPLY_LABELS[s]}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="col-span-3 sm:col-span-2">
                <span className="mb-1 block text-[var(--color-fg-muted)]">Weight (kg)</span>
                <input
                  type="number"
                  min={0.1}
                  max={5}
                  step={0.1}
                  value={d.payload_weight_kg}
                  onChange={(e) =>
                    updateItem(i, { payload_weight_kg: Number(e.target.value || 0) })
                  }
                  className="h-9 w-full rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-2 text-xs"
                  aria-label={`Weight ${i + 1}`}
                />
              </div>

              <div className="col-span-3 sm:col-span-2">
                <span className="mb-1 block text-[var(--color-fg-muted)]">Priority</span>
                <Select
                  value={d.priority}
                  onValueChange={(v) => updateItem(i, { priority: v as Priority })}
                >
                  <SelectTrigger aria-label={`Priority ${i + 1}`}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {PRIORITIES.map((p) => (
                      <SelectItem key={p} value={p}>
                        {p}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="col-span-9 sm:col-span-1 flex items-center justify-between gap-2 sm:flex-col sm:items-stretch">
                <label className="flex items-center justify-between gap-2 sm:justify-center">
                  <span className="text-[var(--color-fg-muted)] sm:hidden">Cold</span>
                  <Switch
                    checked={d.cold_chain_required}
                    onCheckedChange={(v) => updateItem(i, { cold_chain_required: v })}
                    aria-label={`Cold-chain ${i + 1}`}
                  />
                </label>
              </div>
              <div className="col-span-3 sm:col-span-12 sm:flex sm:justify-end">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => removeItem(i)}
                  disabled={items.length === 1}
                  aria-label={`Remove cargo ${i + 1}`}
                  className="text-[var(--color-fg-muted)] hover:text-[var(--color-danger)]"
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            </li>
          ))}
        </ul>

        <div className="flex flex-wrap items-center justify-between gap-2">
          <Button variant="outline" size="sm" onClick={addItem} className="gap-1.5">
            <Plus className="h-3.5 w-3.5" /> Add cargo
          </Button>
          <Button
            type="button"
            disabled={submitting}
            onClick={submit}
            className="gap-1.5"
            data-testid="dispatch-submit"
          >
            <Send className="h-4 w-4" />
            {submitting ? "Dispatching…" : "Dispatch mission"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
