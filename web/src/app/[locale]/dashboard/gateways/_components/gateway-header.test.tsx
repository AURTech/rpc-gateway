import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { RpcGatewayDetail } from "@/api/gateways/client";
import { copyToClipboard } from "@/lib/clipboard";
import { makeGateway } from "@/test/fixtures";

import { GatewayHeader } from "./gateway-header";

vi.mock("next-intl", async () => (await import("@/test/intl")).nextIntlMock());
vi.mock("sonner", async () => (await import("@/test/mocks")).sonnerMock());
vi.mock("@/lib/clipboard", async () =>
  (await import("@/test/mocks")).clipboardMock(),
);
vi.mock("@/hooks/use-gateways", () => ({
  useUpdateGatewayMutation: () => ({ isPending: false, mutate: vi.fn() }),
}));

const gateway = makeGateway({
  chain: "solana",
  network: "mainnet-beta",
  access_points: [
    {
      transport: "jsonrpc",
      url: "https://sol-jsonrpc.example.test/{api_key}",
    },
  ],
}) as RpcGatewayDetail;

describe("GatewayHeader", () => {
  it("shows and copies the complete gateway URL with the active API key", async () => {
    render(
      <GatewayHeader
        gateway={gateway}
        transport="jsonrpc"
        pathKey="ak_complete_value"
        pathKeyStatus="available"
      />,
    );

    const completeUrl = "https://sol-jsonrpc.example.test/ak_complete_value";
    const url = screen.getByText(completeUrl);
    expect(url).toBeInTheDocument();
    expect(url).toHaveClass("break-all", "whitespace-normal");
    expect(screen.queryByText(/\{api_key\}/)).not.toBeInTheDocument();

    await userEvent.click(
      screen.getByRole("button", { name: "table.copyEndpoint" }),
    );
    expect(copyToClipboard).toHaveBeenCalledWith(completeUrl);
  });
});
