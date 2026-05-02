import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  [
    "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium",
    "transition-[background,color,box-shadow,transform] duration-[var(--duration-quick)] ease-[var(--ease-out-soft)]",
    "disabled:pointer-events-none disabled:opacity-50",
    "[&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  ].join(" "),
  {
    variants: {
      variant: {
        default:
          "bg-[var(--color-accent)] text-[var(--color-fg-inverse)] shadow-[var(--shadow-1)] hover:bg-[var(--color-accent-2)] active:translate-y-px",
        outline:
          "border border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-fg)] hover:bg-[var(--color-surface-2)]",
        ghost:
          "text-[var(--color-fg)] hover:bg-[var(--color-surface-2)]",
        soft:
          "bg-[var(--color-accent-soft)] text-[var(--color-accent-fg)] hover:bg-[#E0E7FF]",
        danger:
          "bg-[var(--color-danger)] text-[var(--color-fg-inverse)] hover:opacity-90",
        success:
          "bg-[var(--color-success)] text-[var(--color-fg-inverse)] hover:opacity-90",
        link:
          "text-[var(--color-accent)] underline-offset-4 hover:underline",
      },
      size: {
        sm: "h-8 px-3 text-xs",
        md: "h-9 px-4",
        lg: "h-10 px-5 text-base",
        icon: "h-9 w-9",
      },
    },
    defaultVariants: { variant: "default", size: "md" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp
        ref={ref}
        className={cn(buttonVariants({ variant, size }), className)}
        {...props}
      />
    );
  },
);
Button.displayName = "Button";

export { buttonVariants };
