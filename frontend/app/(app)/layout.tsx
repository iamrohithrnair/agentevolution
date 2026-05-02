import { Sidebar } from "@/components/nav/Sidebar";
import { Topbar } from "@/components/nav/Topbar";
import { TooltipProvider } from "@/components/ui/tooltip";

export const dynamic = "force-dynamic";

export default function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <TooltipProvider delayDuration={120}>
      <div className="grid min-h-dvh w-full grid-cols-[240px_1fr] bg-[var(--color-canvas)]">
        <aside
          className="sticky top-0 h-dvh border-r border-[var(--color-border)] bg-[var(--color-surface)]"
          data-testid="sidebar"
        >
          <Sidebar />
        </aside>
        <div className="flex min-h-dvh flex-col">
          <header
            className="sticky top-0 z-30 h-14 border-b border-[var(--color-border)] bg-[var(--color-surface)]/95 backdrop-blur-sm"
          >
            <Topbar />
          </header>
          <main className="flex-1 overflow-x-hidden p-5 lg:p-6">{children}</main>
        </div>
      </div>
    </TooltipProvider>
  );
}
