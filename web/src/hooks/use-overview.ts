import { useQuery } from "@tanstack/react-query";

import { getOverview, type Overview } from "@/api/overview/client";

const root = ["overview"] as const;

export const overviewKeys = {
  all: root,
  overview: () => [...root, "overview"] as const,
};

export function useOverviewQuery() {
  return useQuery<Overview>({
    queryKey: overviewKeys.overview(),
    queryFn: () => getOverview(),
    staleTime: 30_000,
  });
}
