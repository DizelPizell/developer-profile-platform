import * as React from "react"
import { cn } from "cn"

// Restyled for DESIGN.md: an error block with a 4px error border. Only the
// parts in use are kept (shadcn also generates title, description and action).
function Alert({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="alert"
      role="alert"
      className={cn(
        "w-full border-4 border-error bg-bg px-4 py-3 text-left text-base text-error",
        className
      )}
      {...props}
    />
  )
}

export { Alert }
