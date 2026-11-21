"use client";

import { useEffect, useRef } from "react";

import { isAnalyticsEventType, trackEvent } from "@/lib/api";

// Views and clicks of a public page (ADR-0029). The view is sent after the mount, so
// SSR, prefetch and bots without JavaScript count nothing. Clicks are found by one
// listener: a link or a button inside an element with data-analytics="<type>" counts,
// and its project is the nearest data-analytics-project, else the page's project.
// The pages stay server components; the navigation never waits for the request.

export function AnalyticsTracker({ slug, projectId = null }: { slug: string; projectId?: string | null }) {
  // Strict Mode runs the effect twice on the same instance in development.
  const viewed = useRef(false);

  useEffect(() => {
    if (!viewed.current) {
      viewed.current = true;
      trackEvent(projectId ? "PROJECT_VIEW" : "PROFILE_VIEW", slug, projectId);
    }

    function onClick(event: MouseEvent) {
      // auxclick: the middle button, a link opened in a new tab.
      if (event.type === "auxclick" && event.button !== 1) {
        return;
      }
      const control = event.target instanceof Element ? event.target.closest("a[href], button") : null;
      const marked = control?.closest<HTMLElement>("[data-analytics]");
      const type = marked?.dataset.analytics;
      if (!control || !isAnalyticsEventType(type)) {
        return;
      }
      const project = control.closest<HTMLElement>("[data-analytics-project]")?.dataset.analyticsProject;
      trackEvent(type, slug, project ?? projectId);
    }

    document.addEventListener("click", onClick);
    document.addEventListener("auxclick", onClick);
    return () => {
      document.removeEventListener("click", onClick);
      document.removeEventListener("auxclick", onClick);
    };
  }, [slug, projectId]);

  return null;
}
