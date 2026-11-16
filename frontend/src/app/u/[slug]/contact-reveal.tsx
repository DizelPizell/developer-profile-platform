"use client";

import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { revealContact, type RevealedContact } from "@/lib/api";

// «Показать email» / «Показать телефон» (ADR-020, profile-contacts.png). The props
// are the type and the slug only: a prop of a client component is serialized into
// the HTML, so the value is requested on a click and lives in state.

const CONTACT_LINK = "break-all text-text-muted underline underline-offset-4";

const TEXT = {
  EMAIL: { show: "Показать email", failed: "Не удалось получить email." },
  PHONE: { show: "Показать телефон", failed: "Не удалось получить телефон." },
};

export function ContactReveal({ type, slug }: { type: RevealedContact["type"]; slug: string }) {
  const [state, setState] = useState<"idle" | "loading" | "error" | RevealedContact>("idle");
  const link = useRef<HTMLAnchorElement>(null);
  const shown = typeof state === "object";

  // The button is gone once the value is shown, so the focus goes to the link.
  useEffect(() => {
    if (shown) {
      link.current?.focus();
    }
  }, [shown]);

  async function reveal() {
    setState("loading");
    try {
      setState(await revealContact(slug, type));
    } catch {
      // Only the field: the log never holds a value (ADR-020).
      console.warn(`Contact ${type}: request failed`);
      setState("error");
    }
  }

  if (shown) {
    // mailto: and tel: open no tab; revealContact checked the link against the value.
    return (
      <a ref={link} href={state.url} className={CONTACT_LINK}>
        {state.value}
      </a>
    );
  }

  const failed = state === "error";
  return (
    <div className="flex flex-col items-start gap-2">
      {!failed && (
        <Button
          type="button"
          variant="secondary"
          disabled={state === "loading"}
          onClick={() => void reveal()}
        >
          {state === "loading" ? "Загрузка…" : TEXT[type].show}
        </Button>
      )}
      <p role="status" className={failed ? "text-base text-error" : "sr-only"}>
        {state === "loading" && "Загрузка…"}
        {failed && TEXT[type].failed}
      </p>
      {failed && (
        <button type="button" className={CONTACT_LINK} onClick={() => void reveal()}>
          Повторить
        </button>
      )}
    </div>
  );
}
