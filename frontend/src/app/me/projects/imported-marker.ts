// After an import the project form shows «Проект создан» once (DESIGN.md). The
// marker travels in the address and the form removes it at once, so a reload
// or a later visit does not show the panel again.

export const IMPORTED_PARAM = "imported";

export function importedProjectHref(projectId: string): string {
  return `/me/projects/${encodeURIComponent(projectId)}?${IMPORTED_PARAM}=1`;
}

export function isImportedMarker(value: string | string[] | undefined): boolean {
  return value === "1";
}
