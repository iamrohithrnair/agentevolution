import type { Metadata } from "next";
import { ReflectionFeed } from "@/components/dashboard/ReflectionFeed";

export const metadata: Metadata = { title: "Reflections · Dronan" };

export default function ReflectionsPage() {
  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Reflections</h1>
        <p className="text-sm text-[var(--color-fg-muted)]">
          Every lesson the system has learned from past missions, scored and tagged for retrieval
          on the next dispatch.
        </p>
      </header>
      <ReflectionFeed limit={120} />
    </div>
  );
}
