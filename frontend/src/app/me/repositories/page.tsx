import type { Metadata } from "next";

import { parsePage } from "./page-param";
import { RepositoriesScreen } from "./repositories-screen";

export const metadata: Metadata = {
  title: "Репозитории GitHub — Developer Profile Platform",
};

export default async function RepositoriesPage({
  searchParams,
}: PageProps<"/me/repositories">) {
  const { page } = await searchParams;
  return <RepositoriesScreen page={parsePage(page)} />;
}
