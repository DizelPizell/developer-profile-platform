import * as React from "react"
import { cn } from "cn"

// Restyled for DESIGN.md: 4px border in text-muted (frame is too low-contrast
// for an interactive boundary), visible focus, error border on aria-invalid.
function Input({ className, type, ...props }: React.ComponentProps<"input">) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        "h-10 w-full min-w-0 border-4 border-text-muted bg-bg px-3 py-1 font-sans text-base text-text placeholder:text-text-muted focus-visible:outline-4 focus-visible:outline-offset-2 focus-visible:outline-label disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-error",
        className
      )}
      {...props}
    />
  )
}

export { Input }
