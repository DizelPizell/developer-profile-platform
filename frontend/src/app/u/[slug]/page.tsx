import type { Metadata } from "next";
import { notFound, permanentRedirect } from "next/navigation";

import { getPublicProfile, type PublicProfile } from "@/lib/api";
import { perRequest } from "@/lib/per-request";

import { SITE, SLUG_PATTERN } from "./address";
import { ProfileView } from "./profile-view";

function loadProfile(slug: string): Promise<PublicProfile | null> {
  return perRequest(`profile:${slug}`, () => getPublicProfile(slug));
}

function profileTitle(profile: PublicProfile): string {
  const name = profile.display_name ?? `@${profile.github_login}`;
  return profile.headline ? `${name} — ${profile.headline}` : name;
}

export async function generateMetadata({ params }: PageProps<"/u/[slug]">): Promise<Metadata> {
  const { slug } = await params;
  // 404 and errors get the neutral site title. Next ignores this for the 404
  // render anyway (only the root not-found may set metadata), so the profile
  // 404 shows the root layout title too.
  if (!SLUG_PATTERN.test(slug)) {
    return { title: SITE };
  }
  try {
    const profile = await loadProfile(slug);
    if (!profile) {
      return { title: SITE };
    }
    return { title: profileTitle(profile), description: profile.headline ?? undefined };
  } catch {
    // The page throws the same error and renders error.tsx.
    return { title: SITE };
  }
}

export default async function PublicProfilePage({ params }: PageProps<"/u/[slug]">) {
  const { slug } = await params;
  const lower = slug.toLowerCase();
  if (!SLUG_PATTERN.test(lower)) {
    notFound();
  }
  if (lower !== slug) {
    // The API ignores case; one address per profile.
    permanentRedirect(`/u/${lower}`);
  }

  const profile = await loadProfile(slug);
  if (!profile) {
    notFound();
  }
  return <ProfileView profile={profile} />;
}
