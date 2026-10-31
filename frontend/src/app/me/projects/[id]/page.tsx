import type { Metadata } from "next";

import { isImportedMarker } from "../imported-marker";
import { ProjectEditScreen } from "../project-edit-screen";

export const metadata: Metadata = {
  title: "Проект — Developer Profile Platform",
};

export default async function EditProjectPage({
  params,
  searchParams,
}: PageProps<"/me/projects/[id]">) {
  const [{ id }, { imported }] = await Promise.all([params, searchParams]);
  return <ProjectEditScreen projectId={id} imported={isImportedMarker(imported)} />;
}
