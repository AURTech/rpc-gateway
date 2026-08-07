/**
 * Build the page list with `…` placeholders the HeroUI / shadcn way:
 *   1 2 3 4 5 6 7      (≤ 7 pages — show all)
 *   1 2 3 4 5 … 20     (active near the start)
 *   1 … 16 17 18 19 20 (active near the end)
 *   1 … 9 10 11 … 20   (active in the middle)
 *
 * Lives in its own module (not in `pagination.tsx`) so the component file only
 * exports components — keeps React Fast Refresh happy.
 */
export function buildPaginationRange(
  page: number,
  total: number,
  siblings = 1,
): Array<number | "ellipsis-left" | "ellipsis-right"> {
  // window = 1 (first) + 1 (last) + 2*siblings + 1 (active) + 2 (ellipses)
  const window = siblings * 2 + 5;
  if (total <= window) {
    return Array.from({ length: total }, (_, i) => i + 1);
  }

  const leftSibling = Math.max(page - siblings, 1);
  const rightSibling = Math.min(page + siblings, total);
  const showLeftEllipsis = leftSibling > 2;
  const showRightEllipsis = rightSibling < total - 1;

  if (!showLeftEllipsis && showRightEllipsis) {
    const leftCount = 3 + 2 * siblings;
    const range = Array.from({ length: leftCount }, (_, i) => i + 1);
    return [...range, "ellipsis-right" as const, total];
  }
  if (showLeftEllipsis && !showRightEllipsis) {
    const rightCount = 3 + 2 * siblings;
    const range = Array.from(
      { length: rightCount },
      (_, i) => total - rightCount + 1 + i,
    );
    return [1, "ellipsis-left" as const, ...range];
  }
  const middle = Array.from(
    { length: rightSibling - leftSibling + 1 },
    (_, i) => leftSibling + i,
  );
  return [
    1,
    "ellipsis-left" as const,
    ...middle,
    "ellipsis-right" as const,
    total,
  ];
}
