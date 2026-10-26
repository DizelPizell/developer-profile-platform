import type { Metadata } from "next";

import { CabinetScreen } from "./cabinet-screen";

export const metadata: Metadata = {
  title: "Кабинет — Developer Profile Platform",
};

export default function MePage() {
  return <CabinetScreen />;
}
