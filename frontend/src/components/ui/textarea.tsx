import * as React from "react"
import { cn } from "cn"

// Restyled for DESIGN.md; same rules as Input.
function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return (
    <textarea
      data-slot="textarea"
      className={cn(
        "min-h-24 w-full resize-y border-4 border-text-muted bg-bg px-3 py-2 font-sans text-base text-text placeholder:text-text-muted focus-visible:outline-4 focus-visible:outline-offset-2 focus-visible:outline-label disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-error",
        className
      )}
      {...props}
    />
  )
}

export { Textarea }
