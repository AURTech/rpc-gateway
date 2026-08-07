import {
  defaultShouldDehydrateQuery,
  isServer,
  MutationCache,
  QueryClient,
} from "@tanstack/react-query";
import { toast } from "sonner";

import { isApiError } from "@/api/client";
import { getApiErrorMessage } from "@/lib/api-error";

/** English fallbacks used before the i18n provider mounts (rare). */
const FALLBACK_MESSAGES: Record<string, string> = {
  offline: "Can't reach the server. Check your connection and retry.",
  timeout: "The request timed out. Please retry.",
  server: "The service is temporarily unavailable. Please retry shortly.",
  unauthorized: "Your session expired. Please sign in again.",
  forbidden: "You don't have permission to do that.",
  notFound: "We couldn't find what you were looking for.",
  generic: "Something went wrong. Please retry.",
};

function translate(key: string): string {
  return FALLBACK_MESSAGES[key] ?? key;
}

type MutationMeta = { skipGlobalErrorToast?: boolean };

function makeQueryClient() {
  return new QueryClient({
    mutationCache: new MutationCache({
      onError: (error, _vars, _ctx, mutation) => {
        const meta = mutation.options.meta as MutationMeta | undefined;
        if (meta?.skipGlobalErrorToast) return;
        toast.error(getApiErrorMessage(error, translate));
      },
    }),
    defaultOptions: {
      queries: {
        staleTime: 60 * 1000,
        refetchOnWindowFocus: false,
        // Don't retry deterministic client errors (400/401/403/404/422);
        // retry transient network / timeout / 5xx up to twice.
        retry: (failureCount, error) => {
          if (isApiError(error) && error.isClient) return false;
          return failureCount < 2;
        },
        retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 8000),
      },
      dehydrate: {
        shouldDehydrateQuery: (query) =>
          defaultShouldDehydrateQuery(query) ||
          query.state.status === "pending",
      },
    },
  });
}

let browserQueryClient: QueryClient | undefined;

export function getQueryClient() {
  if (isServer) {
    return makeQueryClient();
  }

  if (!browserQueryClient) {
    browserQueryClient = makeQueryClient();
  }
  return browserQueryClient;
}
