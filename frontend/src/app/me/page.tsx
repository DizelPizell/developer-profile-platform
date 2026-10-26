import type { Metadata } from "next";

import { SessionScreen } from "./session-screen";

export const metadata: Metadata = {
  title: "Кабинет — Developer Profile Platform",
};

export default function MePage() {
  return <SessionScreen />;
}
