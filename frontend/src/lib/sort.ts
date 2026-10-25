/** Sorting a list that is already complete in the browser, such as the raid counters. */

export type SortValue = number | string | null | undefined;

/**
 * Sort on one column, with '-' for descending. Unknown values always come last and equal
 * values keep their original order. An unknown column leaves the list as it is.
 */
export function sortRows<T>(rows: readonly T[], sort: string, columns: Record<string, (row: T) => SortValue>): T[] {
  const descending = sort.startsWith("-");
  const value = columns[sort.replace(/^-/, "")];
  if (!value) return [...rows];
  const known = rows.filter((row) => value(row) !== null && value(row) !== undefined);
  const unknown = rows.filter((row) => value(row) === null || value(row) === undefined);
  const compare = (a: T, b: T) => {
    const x = value(a) as number | string;
    const y = value(b) as number | string;
    const order = typeof x === "string" && typeof y === "string" ? x.localeCompare(y, "nl") : Number(x) - Number(y);
    return descending ? -order : order;
  };
  return [...known].sort(compare).concat(unknown);
}
