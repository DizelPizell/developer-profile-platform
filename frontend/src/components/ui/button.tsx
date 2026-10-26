import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "cn"
import { Slot } from "radix-ui"

// Restyled for DESIGN.md: 4px outline, hard shadow, stepped hover, visible focus.
// Movement is skipped with prefers-reduced-motion; only the brightness changes.
const buttonVariants = cva(
  "inline-flex shrink-0 items-center justify-center gap-2 border-4 border-outline font-sans whitespace-nowrap shadow-pixel select-none transition-steps hover:brightness-110 motion-safe:hover:-translate-x-0.5 motion-safe:hover:-translate-y-0.5 motion-safe:hover:shadow-pixel-lg motion-safe:active:translate-x-0.5 motion-safe:active:translate-y-0.5 motion-safe:active:shadow-pixel-sm focus-visible:outline-4 focus-visible:outline-offset-2 focus-visible:outline-label disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default: "bg-accent text-text",
        secondary: "bg-panel text-text",
      },
      size: {
        default: "h-10 px-4 text-base",
        // Important actions such as sign-in: large, normal case (DESIGN.md).
        lg: "h-14 px-6 text-xl",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

function Button({
  className,
  variant = "default",
  size = "default",
  asChild = false,
  ...props
}: React.ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean
  }) {
  const Comp = asChild ? Slot.Root : "button"

  return (
    <Comp
      data-slot="button"
      data-variant={variant}
      data-size={size}
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
}

export { Button, buttonVariants }
