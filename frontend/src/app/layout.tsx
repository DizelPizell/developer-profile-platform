import type { Metadata } from "next";

import { pressStart2P, tektur } from "./fonts";
import "./globals.css";

export const metadata: Metadata = {
  title: "Developer Profile Platform",
  description: "Профиль разработчика, подтверждённый реальными проектами.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="ru" className={`${pressStart2P.variable} ${tektur.variable}`}>
      <body>{children}</body>
    </html>
  );
}
