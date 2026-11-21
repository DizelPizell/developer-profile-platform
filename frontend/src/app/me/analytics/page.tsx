import type { Metadata } from "next";

import { AnalyticsScreen } from "./analytics-screen";

export const metadata: Metadata = {
  title: "Аналитика — Developer Profile Platform",
};

export default function AnalyticsPage() {
  return <AnalyticsScreen />;
}
