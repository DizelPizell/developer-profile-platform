import type { Metadata } from "next";
import { notFound, permanentRedirect } from "next/navigation";

import { getPublicProject, type PublicProjectPage } from "@/lib/api";
import { perRequest } from "@/lib/per-request";

import { PROJECT_ID_PATTERN, SITE, SLUG_PATTERN } from "../../address";
import { ProjectView } from "./project-view";

type Props = PageProps<"/u/[slug]/projects/[id]">;

function loadProject(slug: string, id: string): Promise<PublicProjectPage | null> {
  return perRequest(`project:${slug}/${id}`, () => getPublicProject(slug, id));
}

/** Both parts are well-formed; the API is not asked otherwise. */
function isValid(slug: string, id: string): boolean {
  return SLUG_PATTERN.test(slug) && PROJECT_ID_PATTERN.test(id);
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug, id } = await params;
  if (!isValid(slug, id)) {
    return { title: SITE };
  }
  try {
    const project = await loadProject(slug, id);
    if (!project) {
      return { title: SITE };
    }
    return { title: `${project.title} — ${project.owner.display_name}`, description: project.summary };
  } catch {
    // The page throws the same error and renders error.tsx.
    return { title: SITE };
  }
}

export default async function PublicProjectRoute({ params }: Props) {
  const { slug, id } = await params;
  const lowerSlug = slug.toLowerCase();
  const lowerId = id.toLowerCase();
  if (!isValid(lowerSlug, lowerId)) {
    notFound();
  }
  if (lowerSlug !== slug || lowerId !== id) {
    // The API ignores the case of both; one address per project.
    permanentRedirect(`/u/${lowerSlug}/projects/${lowerId}`);
  }

  const project = await loadProject(slug, id);
  if (!project) {
    notFound();
  }
  return <ProjectView project={project} />;
}
