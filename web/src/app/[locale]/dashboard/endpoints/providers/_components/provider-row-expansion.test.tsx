import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { AnchorHTMLAttributes } from "react";
import { describe, expect, it, vi } from "vitest";

import type { ProviderEndpoint } from "@/api/providers/client";

import type { ProviderRecord } from "./provider-model";
import { ProviderRowExpansion } from "./provider-row-expansion";

const mocks = vi.hoisted(() => ({
  getProviderCredential: vi.fn(),
  useProviderEndpoints: vi.fn(),
  useProviderRuns: vi.fn(),
}));

vi.mock("next-intl", async () =>
  (await import("@/test/intl")).nextIntlMock({ separator: ":" }),
);

vi.mock("@/i18n/navigation", () => ({
  Link: ({
    href,
    ...props
  }: AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
    <a href={href} {...props} />
  ),
}));

vi.mock("@/api/providers/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/api/providers/client")>()),
  getProviderCredential: mocks.getProviderCredential,
}));

vi.mock("./use-providers", () => ({
  useProviderEndpoints: mocks.useProviderEndpoints,
  useProviderRuns: mocks.useProviderRuns,
}));

const provider: ProviderRecord = {
  id: "provider-1",
  name: "Production Alchemy",
  vendor: "alchemy",
  enabled: true,
  sync_enabled: true,
  credential: { has_secret: true },
  networks: [{ chain: "ethereum", network: "mainnet" }],
  last_sync_at: "2026-08-19T09:00:00.000Z",
  last_sync_status: "success",
  version: 1,
  endpoint_counts: { present: 5, missing: 1 },
  connected_app_count: 2,
  syncing: false,
};

function endpoint(index: number): ProviderEndpoint {
  return {
    endpoint: {
      id: `endpoint-${index}`,
      account_id: "account-1",
      name: `Endpoint ${index}`,
      origin_type: "provider",
      provider: {
        id: provider.id,
        name: provider.name,
        vendor: provider.vendor,
        vendor_label: "Alchemy",
      },
      provider_external_id: `external-${index}`,
      provider_sync_status: "available",
      provider_last_seen_at: "2026-08-19T09:00:00.000Z",
      chain: "ethereum",
      network: "mainnet",
      protocol: "jsonrpc",
      url: `https://example.com/${index}`,
      effective_url: null,
      enabled: true,
      auth: { type: "none", has_secret: false },
      version: 1,
      created_at: "2026-08-19T09:00:00.000Z",
      modified_at: "2026-08-19T09:00:00.000Z",
    },
    sync_status: "available",
    discovery_status: "present",
    registry_state: "active",
    retained_by_routes: false,
    external_id: `external-${index}`,
    last_seen_at: "2026-08-19T09:00:00.000Z",
    missing_since: null,
    archived_at: null,
  };
}

describe("ProviderRowExpansion", () => {
  it("keeps visited panels mounted and pages endpoints in place", async () => {
    const user = userEvent.setup();
    mocks.useProviderEndpoints.mockImplementation(
      (_id: string, page: number, size: number) => ({
        data: {
          page,
          size,
          total: 6,
          max_page: 2,
          items: page === 1 ? [1, 2, 3, 4, 5].map(endpoint) : [endpoint(6)],
        },
        isLoading: false,
        isError: false,
        isPlaceholderData: false,
        refetch: vi.fn(),
      }),
    );
    mocks.useProviderRuns.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
      isPlaceholderData: false,
      refetch: vi.fn(),
    });

    render(<ProviderRowExpansion provider={provider} />);
    await user.click(
      screen.getByRole("tab", { name: "rowExpansion.tabs.endpointsCount:6" }),
    );

    expect(mocks.useProviderEndpoints).toHaveBeenLastCalledWith(
      provider.id,
      1,
      5,
    );
    expect(screen.getByText("Endpoint 1")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "next" }));

    expect(mocks.useProviderEndpoints).toHaveBeenLastCalledWith(
      provider.id,
      2,
      5,
    );
    expect(screen.getByText("Endpoint 6")).toBeVisible();

    await user.click(
      screen.getByRole("tab", { name: "rowExpansion.tabs.provider" }),
    );
    expect(
      document.querySelector("#provider-provider-1-expansion-panel-endpoints"),
    ).toHaveAttribute("aria-hidden", "true");
    expect(mocks.useProviderEndpoints).toHaveBeenLastCalledWith(
      provider.id,
      2,
      5,
    );
  });

  it("masks a revealed credential when leaving the provider tab", async () => {
    const user = userEvent.setup();
    mocks.getProviderCredential.mockResolvedValue({ secret: "secret-value" });
    mocks.useProviderEndpoints.mockReturnValue({
      data: { page: 1, size: 5, total: 0, max_page: 1, items: [] },
      isLoading: false,
      isError: false,
      isPlaceholderData: false,
      refetch: vi.fn(),
    });

    render(<ProviderRowExpansion provider={provider} />);
    await user.click(
      screen.getByRole("button", {
        name: "rowExpansion.provider.showCredential",
      }),
    );
    expect(await screen.findByText("secret-value")).toBeVisible();

    await user.click(
      screen.getByRole("tab", { name: "rowExpansion.tabs.endpointsCount:6" }),
    );
    await user.click(
      screen.getByRole("tab", { name: "rowExpansion.tabs.provider" }),
    );

    await waitFor(() =>
      expect(screen.queryByText("secret-value")).not.toBeInTheDocument(),
    );
    expect(
      screen.getByRole("button", {
        name: "rowExpansion.provider.showCredential",
      }),
    ).toHaveAttribute("aria-pressed", "false");
  });
});
