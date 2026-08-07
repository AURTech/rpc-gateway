import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { Endpoint, EndpointDetail } from "@/api/endpoints/client";

import { EditEndpointSheet } from "./edit-endpoint-sheet";
import { EndpointDetailSheet } from "./endpoint-detail-sheet";

vi.mock("next-intl", async () => (await import("@/test/intl")).nextIntlMock());

vi.mock("@/i18n/navigation", async () =>
  (await import("@/test/navigation")).navigationMock(),
);

vi.mock("sonner", async () => (await import("@/test/mocks")).sonnerMock());

const detail: EndpointDetail = {
  id: "endpoint-1",
  account_id: "account-1",
  name: "primary",
  origin_type: "manual",
  provider: null,
  provider_external_id: null,
  provider_sync_status: null,
  provider_last_seen_at: null,
  chain: "ethereum",
  network: "mainnet",
  protocol: "jsonrpc",
  configured_url: "https://rpc.example.com/base",
  url: "https://rpc.example.com/base",
  enabled: true,
  auth: {
    type: "header_api_key",
    header_name: "x-api-key",
    has_secret: true,
    secret: "endpoint-secret",
  },
  version: 1,
  created_at: "2026-06-01T00:00:00Z",
  modified_at: "2026-06-01T00:00:00Z",
};

const summary: Endpoint = {
  ...detail,
  auth: {
    type: "header_api_key",
    header_name: "x-api-key",
    has_secret: true,
  },
};

vi.mock("@/hooks/use-endpoints", () => ({
  useEndpointQuery: () => ({ data: detail, refetch: vi.fn() }),
  useCreateEndpointMutation: () => ({ isPending: false, mutate: vi.fn() }),
  useUpdateEndpointMutation: () => ({ isPending: false, mutate: vi.fn() }),
}));

describe("endpoint credential surfaces", () => {
  it("shows the authentication secret in the detail sheet", () => {
    render(
      <EndpointDetailSheet
        endpoint={summary}
        open
        onOpenChange={vi.fn()}
        onEdit={vi.fn()}
        onAudit={vi.fn()}
        onDelete={vi.fn()}
      />,
    );

    expect(screen.getByText(/endpoint-secret/)).toBeInTheDocument();
  });

  it("prefills visible URL and credential fields in the edit sheet", async () => {
    render(
      <EditEndpointSheet endpoint={summary} open onOpenChange={vi.fn()} />,
    );

    expect(
      await screen.findByDisplayValue("https://rpc.example.com/base"),
    ).toBeInTheDocument();
    expect(screen.getByDisplayValue("endpoint-secret")).toHaveAttribute(
      "type",
      "text",
    );
  });
});
