import type { Metadata } from "next";

import { ProjectsScreen } from "./projects-screen";

export const metadata: Metadata = {
  title: "Мои проекты — Developer Profile Platform",
};

export default function ProjectsPage() {
  return <ProjectsScreen />;
}
