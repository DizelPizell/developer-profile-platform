import type { Metadata } from "next";
import { headers } from "next/headers";
import { notFound, permanentRedirect } from "next/navigation";

import { getPublicProfile, type PublicProfile } from "@/lib/api";

import { ProfileView } from "./profile-view";

// The slug format of the database CHECK ck_profiles_slug_format (3–39
// characters, ADR-012). Anything else is a 404 without asking the API, which
// would answer 404 anyway (ADR-013).
const SLUG_PATTERN = /^[a-z0-9][a-z0-9-]{1,37}[a-z0-9]$/;

const SITE = "Developer Profile Platform";

// One API call per request, shared by generateMetadata and the page.
// React cache() is not enough: after an error Next renders the error page in a
// second pass with a fresh cache, and generateMetadata would call the API
// again (two requests to a failing API, two timeouts in a row). The headers()
// object lives for the whole request, so it keys the call instead. If Next
// changes that, this degrades to a second call, never to another request's data.
const callsByRequest = new WeakMap<object, Map<string, Promise<PublicProfile | null>>>();

async function loadProfile(slug: string): Promise<PublicProfile | null> {
  const request = await headers();
  let calls = callsByRequest.get(request);
  if (!calls) {
    calls = new Map();
    callsByRequest.set(request, calls);
  }
  let call = calls.get(slug);
  if (!call) {
    call = getPublicProfile(slug);
    calls.set(slug, call);
  }
  return call;
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
