/**
 * Helpers for the weighted endpoint pools used by the gateway JSON-RPC routing
 * editor. The v2 API models a load-balance weight as a plain integer 1–1000 per
 * target (no fixed pool total — a target's share is its weight over the sum of
 * weights). Users edit the raw weights; the normalized expected traffic share is
 * a read-only preview derived from them.
 */

/** Inclusive bounds of a single load-balance target weight (matches the API). */
export const WEIGHT_MIN = 1;
export const WEIGHT_MAX = 1000;

/** Per-endpoint weight map, keyed by endpoint id. */
export type EndpointWeights = Record<string, number>;

/** A single weight is valid when it's an integer in [1, 1000]. */
export function isValidWeight(value: number | undefined): boolean {
  return (
    Number.isInteger(value) &&
    (value as number) >= WEIGHT_MIN &&
    (value as number) <= WEIGHT_MAX
  );
}

/** A weighted pool is submittable when it has ≥1 endpoint, each with a valid weight. */
export function weightsValid(
  ids: readonly string[],
  weights: EndpointWeights,
): boolean {
  return ids.length > 0 && ids.every((id) => isValidWeight(weights[id]));
}

/** Clamp an arbitrary number to a valid integer weight (defaulting empties to 100). */
export function clampWeight(value: number | undefined): number {
  if (!Number.isFinite(value)) return 100;
  return Math.min(
    WEIGHT_MAX,
    Math.max(WEIGHT_MIN, Math.round(value as number)),
  );
}

/** Seed every endpoint with an equal weight of 1 (an even split). */
export function evenWeights(ids: readonly string[]): EndpointWeights {
  return Object.fromEntries(ids.map((id) => [id, 1]));
}

/** Sum of weights across the given ids; missing/NaN entries count as 0. */
export function weightsSum(
  ids: readonly string[],
  weights: EndpointWeights,
): number {
  return ids.reduce((acc, id) => {
    const w = weights[id];
    return acc + (Number.isFinite(w) ? w : 0);
  }, 0);
}

/**
 * Normalize the given weights to integer percentages that total exactly 100,
 * for a read-only expected-share preview. Uses the largest-remainder method so
 * the parts sum to 100 without drift. Returns `{}` when the pool is empty or invalid.
 */
export function sharePercents(
  ids: readonly string[],
  weights: EndpointWeights,
): EndpointWeights {
  if (!weightsValid(ids, weights)) return {};
  const total = weightsSum(ids, weights);
  if (total <= 0) return {};

  const shares = ids.map((id, index) => {
    const exact = ((weights[id] ?? 0) / total) * 100;
    const floor = Math.floor(exact);
    return { id, index, floor, fraction: exact - floor };
  });
  const out: EndpointWeights = Object.fromEntries(
    shares.map((share) => [share.id, share.floor]),
  );

  let remainder = 100 - shares.reduce((acc, share) => acc + share.floor, 0);
  const byFraction = [...shares].sort(
    (a, b) => b.fraction - a.fraction || a.index - b.index,
  );
  for (const share of byFraction) {
    if (remainder <= 0) break;
    out[share.id] += 1;
    remainder -= 1;
  }
  return out;
}
