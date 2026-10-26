import type { ReactNode } from "react";

import { BrandMark } from "@/components/brand-mark";

// Centered panel for 404 and error screens (mockup not-found.png).
export function MessageScreen({
  code,
  title,
  text,
  children,
}: {
  /** Large status number above the title, such as 404. */
  code?: string;
  title: string;
  text?: string;
  /** Buttons under the text. */
  children: ReactNode;
}) {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-8 p-6">
      <BrandMark />
      <section className="flex w-full max-w-2xl flex-col items-center gap-6 bg-panel px-8 py-10 text-center shadow-panel">
        {code && (
          <p
            aria-hidden="true"
            className="font-heading text-6xl text-accent text-shadow-[4px_4px_0_var(--color-outline)]"
          >
            {code}
          </p>
        )}
        <h1 className="font-heading text-xl leading-relaxed uppercase">{title}</h1>
        {text && <p className="text-xl leading-relaxed">{text}</p>}
        <div className="flex flex-wrap justify-center gap-4">{children}</div>
      </section>
    </main>
  );
}
