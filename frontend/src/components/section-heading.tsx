import { cn } from "cn";
import type { ReactNode } from "react";

/**
 * A section heading of the mockups: a square marker, the title, a rule and an
 * optional mark on the right (the public page puts «От автора» there).
 */
export function SectionHeading({
  id,
  marker,
  aside,
  children,
}: {
  id: string;
  marker: "label" | "muted";
  aside?: ReactNode;
  children: string;
}) {
  return (
    <div className="flex items-center gap-4">
      <span
        aria-hidden="true"
        className={cn("size-4 shrink-0", marker === "label" ? "bg-label" : "bg-text-muted")}
      />
      <h2 id={id} className="font-heading text-sm leading-normal uppercase">
        {children}
      </h2>
      <span aria-hidden="true" className="h-1 grow bg-frame" />
      {aside}
    </div>
  );
}
