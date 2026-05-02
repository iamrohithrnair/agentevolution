"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Send,
  ListChecks,
  Brain,
  Sparkles,
  Bot,
  ScrollText,
  LineChart,
  Settings,
  Plane,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { DemoMenu } from "@/components/demo/DemoMenu";

const NAV: Array<{ href: string; label: string; icon: React.ComponentType<{ className?: string }> }> = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/deploy", label: "Deploy", icon: Send },
  { href: "/missions", label: "Missions", icon: ListChecks },
  { href: "/memory", label: "Memory", icon: Brain },
  { href: "/reflections", label: "Reflections", icon: Sparkles },
  { href: "/agents", label: "Agents", icon: Bot },
  { href: "/logs", label: "Logs", icon: ScrollText },
  { href: "/analytics", label: "Analytics", icon: LineChart },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <nav
      aria-label="Primary"
      className="flex h-full flex-col gap-1 overflow-y-auto thin-scrollbar"
    >
      <div className="flex items-center gap-2 px-5 pt-5 pb-4">
        <span className="grid h-8 w-8 place-items-center rounded-md bg-[var(--color-accent)] text-[var(--color-fg-inverse)] shadow-[var(--shadow-1)]">
          <Plane className="h-4 w-4 -rotate-12" />
        </span>
        <div className="leading-tight">
          <p className="text-sm font-semibold tracking-tight">Dronan</p>
          <p className="text-[11px] uppercase tracking-wider text-[var(--color-fg-muted)]">
            Mission Control
          </p>
        </div>
      </div>

      <div className="flex flex-1 flex-col gap-0.5 px-2">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active =
            pathname === href || (href !== "/" && pathname.startsWith(href));
          return (
            <Link
              key={href}
              href={href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "group inline-flex h-9 items-center gap-2.5 rounded-md px-3 text-sm font-medium",
                "transition-colors duration-[var(--duration-quick)] ease-[var(--ease-out-soft)]",
                active
                  ? "bg-[var(--color-accent-soft)] text-[var(--color-accent-fg)]"
                  : "text-[var(--color-fg-muted)] hover:bg-[var(--color-surface-2)] hover:text-[var(--color-fg)]",
              )}
            >
              <Icon
                className={cn(
                  "h-4 w-4",
                  active ? "text-[var(--color-accent)]" : "text-[var(--color-fg-subtle)] group-hover:text-[var(--color-fg-muted)]",
                )}
              />
              {label}
            </Link>
          );
        })}
      </div>

      <DemoMenu />
    </nav>
  );
}
