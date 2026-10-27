import type { Metadata } from "next";

import { ProjectEditScreen } from "../project-edit-screen";

export const metadata: Metadata = {
  title: "Новый проект — Developer Profile Platform",
};

export default function NewProjectPage() {
  return <ProjectEditScreen />;
}
