"use client";

import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  type CreateProviderInput,
  createProvider,
  type DeleteProviderInput,
  deleteProvider,
  getProviderDeleteImpact,
  getProviderSyncRun,
  type ListProvidersParams,
  listProviderEndpoints,
  listProviderSyncRuns,
  listProviders,
  syncProvider,
  type UpdateProviderInput,
  updateProvider,
} from "@/api/providers/client";

const keys = {
  all: ["providers"] as const,
  list: (params: ListProvidersParams) => ["providers", "list", params] as const,
  endpoints: (id: string) => ["providers", "endpoints", id] as const,
  runs: (id: string) => ["providers", "runs", id] as const,
  run: (id: string, runId: string) => ["providers", "run", id, runId] as const,
  impact: (id: string) => ["providers", "impact", id] as const,
};

export function useProviders(params: ListProvidersParams = {}) {
  return useQuery({
    queryKey: keys.list(params),
    queryFn: () => listProviders({ size: 20, ...params }),
    placeholderData: keepPreviousData,
    refetchInterval: (query) =>
      query.state.data?.items.some((provider) => provider.syncing)
        ? 2000
        : false,
  });
}

export function useProviderEndpoints(id: string, page = 1, size = 5) {
  return useQuery({
    queryKey: [...keys.endpoints(id), page, size],
    queryFn: () => listProviderEndpoints(id, { page, size }),
    placeholderData: keepPreviousData,
  });
}

export function useProviderRuns(id: string, page = 1, size = 5) {
  return useQuery({
    queryKey: [...keys.runs(id), page, size],
    queryFn: () => listProviderSyncRuns(id, { page, size }),
    placeholderData: keepPreviousData,
    refetchInterval: (query) =>
      query.state.data?.items.some(
        (run) => run.state === "queued" || run.state === "running",
      )
        ? 2000
        : false,
  });
}

export function useProviderRun(id: string, runId: string | null) {
  return useQuery({
    queryKey: keys.run(id, runId ?? "pending"),
    queryFn: () => getProviderSyncRun(id, runId ?? ""),
    enabled: runId !== null,
    refetchInterval: (query) =>
      query.state.data?.state === "queued" ||
      query.state.data?.state === "running"
        ? 1000
        : false,
  });
}

export function useProviderDeleteImpact(id: string, enabled: boolean) {
  return useQuery({
    queryKey: keys.impact(id),
    queryFn: () => getProviderDeleteImpact(id),
    enabled,
  });
}

function refresh(qc: ReturnType<typeof useQueryClient>, id?: string) {
  qc.invalidateQueries({ queryKey: keys.all });
  qc.invalidateQueries({ queryKey: ["endpoints"] });
  if (id) {
    qc.invalidateQueries({
      queryKey: ["providers", "endpoints", id],
    });
    qc.invalidateQueries({ queryKey: keys.runs(id) });
    qc.invalidateQueries({ queryKey: keys.impact(id) });
  }
}

export function useCreateProvider() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateProviderInput) => createProvider(input),
    onSuccess: () => refresh(qc),
  });
}

export function useUpdateProvider(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: UpdateProviderInput) => updateProvider(id, input),
    onSuccess: () => refresh(qc, id),
  });
}

export function useDeleteProvider(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: DeleteProviderInput) => deleteProvider(id, input),
    onSuccess: () => refresh(qc),
  });
}

export function useStartProviderSync(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => syncProvider(id),
    onSuccess: () => {
      refresh(qc, id);
    },
  });
}

export { keys as providerKeys };
