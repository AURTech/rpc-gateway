import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { NewEndpointButton } from "./new-endpoint-button";

vi.mock("@/hooks/use-is-admin", async () =>
  (await import("@/test/mocks")).useIsAdminMock(),
);

vi.mock("./edit-endpoint-sheet", () => ({
  EditEndpointSheet: ({
    initialChain,
    initialNetwork,
    initialProtocol,
    open,
    presentation,
  }: {
    initialChain?: string;
    initialNetwork?: string;
    initialProtocol?: string;
    open: boolean;
    presentation?: "dialog" | "sheet";
  }) => (
    <div
      data-testid="create-endpoint-sheet"
      data-open={open}
      data-chain={initialChain}
      data-network={initialNetwork}
      data-protocol={initialProtocol}
      data-presentation={presentation}
    />
  ),
}));

describe("NewEndpointButton", () => {
  it("opens the requested create overlay with gateway defaults", async () => {
    render(
      <NewEndpointButton
        label="Create endpoint"
        size="sm"
        variant="soft"
        showIcon={false}
        className="rounded-xl"
        initialChain="tron"
        initialNetwork="nile"
        initialProtocol="jsonrpc"
        presentation="dialog"
      />,
    );

    const button = screen.getByRole("button", { name: "Create endpoint" });
    expect(button).toHaveAttribute("data-size", "sm");
    expect(button).toHaveAttribute("data-variant", "soft");
    expect(button).toHaveClass("rounded-xl");
    expect(button.querySelector("svg")).not.toBeInTheDocument();
    expect(screen.getByTestId("create-endpoint-sheet")).toHaveAttribute(
      "data-open",
      "false",
    );

    await userEvent.click(button);

    const sheet = screen.getByTestId("create-endpoint-sheet");
    expect(sheet).toHaveAttribute("data-open", "true");
    expect(sheet).toHaveAttribute("data-chain", "tron");
    expect(sheet).toHaveAttribute("data-network", "nile");
    expect(sheet).toHaveAttribute("data-protocol", "jsonrpc");
    expect(sheet).toHaveAttribute("data-presentation", "dialog");
  });

  it("keeps the endpoints-page presentation as a sheet by default", () => {
    render(<NewEndpointButton label="New endpoint" />);

    expect(screen.getByTestId("create-endpoint-sheet")).toHaveAttribute(
      "data-presentation",
      "sheet",
    );
  });
});
