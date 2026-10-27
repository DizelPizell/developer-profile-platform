import type { Metadata } from "next";

import { ProjectEditScreen } from "../project-edit-screen";

export const metadata: Metadata = {
  title: "Проект — Developer Profile Platform",
};

export default async function EditProjectPage({ params }: PageProps<"/me/projects/[id]">) {
  const { id } = await params;
  return <ProjectEditScreen projectId={id} />;
}
