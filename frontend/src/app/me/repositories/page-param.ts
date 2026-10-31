import { REPOSITORY_PAGE_MAX } from "@/lib/api";

/**
 * The page number from ?page= (DESIGN.md): 1..100 written plainly, so "2" but
 * not "02", "2.0" or "1e1". Anything else, a repeated parameter included, is
 * page 1, the same as no parameter.
 */
export function parsePage(value: string | string[] | undefined): number {
  if (typeof value !== "string" || !/^[1-9][0-9]{0,2}$/.test(value)) {
    return 1;
  }
  const page = Number(value);
  return page <= REPOSITORY_PAGE_MAX ? page : 1;
}
