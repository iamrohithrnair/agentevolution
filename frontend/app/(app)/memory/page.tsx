import type { Metadata } from "next";
import { MemoryInspector } from "@/components/dashboard/MemoryInspector";

export const metadata: Metadata = { title: "Memory · Dronan" };

export default function MemoryPage() {
  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Memory</h1>
        <p className="text-sm text-[var(--color-fg-muted)]">
          Vector-search every reflection, incident, regulation, and operator preference. Powered by
          Voyage-3 embeddings + Atlas $vectorSearch.
        </p>
      </header>
      <MemoryInspector />
    </div>
  );
}
