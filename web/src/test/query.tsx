import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { type RenderResult, render } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";

/** A QueryClient with retries off, so failed queries surface immediately. */
export function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
}

/** `renderHook` wrapper that provides `client`. */
export function queryWrapper(client: QueryClient) {
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
}

/** Render `ui` under a QueryClientProvider, returning the client alongside the view. */
export function renderWithQuery(
  ui: ReactElement,
  client: QueryClient = createTestQueryClient(),
): RenderResult & { client: QueryClient } {
  return {
    client,
    ...render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>),
  };
}
