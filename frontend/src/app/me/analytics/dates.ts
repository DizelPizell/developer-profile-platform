// The API's UTC days ("YYYY-MM-DD") as text. The string is split, never passed to
// Date: a Date would shift the day to the browser's time zone (DESIGN.md, Analytics).

/** "2026-11-14" → "14.11" */
export function dayMonth(day: string): string {
  const [, month, date] = day.split("-");
  return `${date}.${month}`;
}

/** "2026-11-14" → "14.11.2026" */
export function fullDate(day: string): string {
  const [year] = day.split("-");
  return `${dayMonth(day)}.${year}`;
}
