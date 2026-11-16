import type { ReactNode } from "react";

import type { PublicContact } from "@/lib/api";

import { ContactReveal } from "./contact-reveal";

// The same classes as in contact-reveal.tsx: a server file cannot read a constant
// of a "use client" module, it gets a reference instead of the string.
const CONTACT_LINK = "break-all text-text-muted underline underline-offset-4";

// The «Контакты» section of the public page (ADR-020, profile-contacts.png). Server
// rendered except the email and the phone, which ContactReveal asks for on a click.
// Every value is React text; a link is rendered only after its check, by type.

const TYPE_LABEL: Record<PublicContact["type"], string> = {
  EMAIL: "Email",
  TELEGRAM: "Telegram",
  LINKEDIN: "LinkedIn",
  PHONE: "Телефон",
  OTHER: "Другое",
};

/** The host of an http(s) URL (IDN in punycode); null for anything else. */
function httpHost(url: string): string | null {
  try {
    const { protocol, host } = new URL(url);
    return protocol === "http:" || protocol === "https:" ? host : null;
  } catch {
    return null;
  }
}

/** A link in a new tab when `safe`, the same text without a link otherwise. */
function External({ url, safe, children }: { url: string; safe: boolean; children: ReactNode }) {
  if (!safe) {
    return <span className="break-all">{children}</span>;
  }
  return (
    <a href={url} target="_blank" rel="noopener noreferrer nofollow ugc" className={CONTACT_LINK}>
      {children}
    </a>
  );
}

function ContactValue({ contact, slug }: { contact: PublicContact; slug: string }) {
  if (contact.type === "EMAIL" || contact.type === "PHONE") {
    return <ContactReveal type={contact.type} slug={slug} />;
  }
  // The reader lets through TELEGRAM, LINKEDIN and OTHER only with both strings.
  const url = contact.url ?? "";
  if (contact.type === "TELEGRAM") {
    return (
      <External url={url} safe={url.startsWith("https://t.me/")}>
        @{contact.value}
      </External>
    );
  }
  if (contact.type === "LINKEDIN") {
    return (
      <External url={url} safe={url.startsWith("https://www.linkedin.com/in/")}>
        in/{contact.value}
      </External>
    );
  }
  // The host stands next to the name, so the name cannot hide where the link leads.
  const host = httpHost(url);
  return (
    <>
      <External url={url} safe={host !== null}>
        {contact.label}
      </External>
      {host !== null && <span className="text-base break-all text-text-muted"> · {host}</span>}
    </>
  );
}

export function ProfileContacts({
  contacts,
  slug,
  className,
  mark,
}: {
  contacts: PublicContact[];
  slug: string;
  className?: string;
  /** «От автора», owned by the page. */
  mark: ReactNode;
}) {
  return (
    <section
      id="contacts"
      aria-labelledby="contacts-title"
      className={`flex scroll-mt-6 flex-col gap-4 bg-panel px-8 py-8 shadow-panel ${className ?? ""}`}
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="contacts-title" className="font-heading text-base leading-normal uppercase">
          Контакты
        </h2>
        {mark}
      </div>
      <dl className="flex flex-col gap-4">
        {contacts.map((contact, index) => (
          <div key={index} className="flex min-w-0 flex-col gap-1">
            <dt className="text-sm text-text-muted">{TYPE_LABEL[contact.type]}</dt>
            <dd className="text-lg">
              <ContactValue contact={contact} slug={slug} />
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
