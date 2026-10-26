import { cn } from "cn";

// Default pixel avatar from the mockups, drawn on a 16x16 grid. Decorative.
export function PixelAvatar({ className }: { className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={cn(
        "size-32 overflow-hidden rounded-full border-4 border-accent bg-panel shadow-pixel",
        className,
      )}
    >
      <svg viewBox="0 0 16 16" className="size-full" shapeRendering="crispEdges">
        <rect x="0" y="0" width="16" height="16" className="fill-frame" />
        <rect x="5" y="3" width="6" height="1" className="fill-label" />
        <rect x="5" y="4" width="6" height="7" className="fill-text" />
        <rect x="6" y="6" width="1" height="1" className="fill-outline" />
        <rect x="9" y="6" width="1" height="1" className="fill-outline" />
        <rect x="6" y="8" width="4" height="1" className="fill-outline" />
        <rect x="4" y="11" width="8" height="5" className="fill-accent" />
      </svg>
    </div>
  );
}
