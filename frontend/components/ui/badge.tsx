import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset",
  {
    variants: {
      variant: {
        default:
          "bg-[var(--color-surface-2)] text-[var(--color-fg)] ring-[var(--color-border)]",
        outline:
          "bg-transparent text-[var(--color-fg-muted)] ring-[var(--color-border)]",
        accent:
          "bg-[var(--color-accent-soft)] text-[var(--color-accent-fg)] ring-transparent",
        success:
          "bg-[var(--color-success-soft)] text-[var(--color-success)] ring-transparent",
        warning:
          "bg-[var(--color-warning-soft)] text-[var(--color-warning)] ring-transparent",
        danger:
          "bg-[var(--color-danger-soft)] text-[var(--color-danger)] ring-transparent",
        info:
          "bg-[var(--color-info-soft)] text-[var(--color-info)] ring-transparent",
      },
    },
    defaultVariants: { variant: "default" },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { badgeVariants };
