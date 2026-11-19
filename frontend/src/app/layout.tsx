import type { Metadata } from "next";
import Link from "next/link";

import { pressStart2P, tektur } from "./fonts";
import "./globals.css";

export const metadata: Metadata = {
  title: "Developer Profile Platform",
  description: "Профиль разработчика, подтверждённый реальными проектами.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="ru" className={`${pressStart2P.variable} ${tektur.variable}`}>
      <body>
        {children}
        <footer className="mx-auto w-full max-w-4xl px-6 pb-6 text-sm text-text-muted">
          <Link href="/privacy" className="underline underline-offset-4">
            Политика данных
          </Link>
        </footer>
      </body>
    </html>
  );
}
