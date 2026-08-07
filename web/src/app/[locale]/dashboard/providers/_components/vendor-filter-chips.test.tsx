import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { RpcProviderVendor } from "@/api/providers/client";

import { VendorFilterChips } from "./vendor-filter-chips";

const OPTIONS: readonly RpcProviderVendor[] = ["alchemy", "quicknode"];
const LABELS: Record<RpcProviderVendor, string> = {
  alchemy: "Alchemy",
  quicknode: "QuickNode",
  chainstack: "Chainstack",
  drpc: "dRPC",
  tenderly: "Tenderly",
};

function setup(value: readonly RpcProviderVendor[]) {
  const onValueChange = vi.fn();
  const user = userEvent.setup();
  render(
    <VendorFilterChips
      options={OPTIONS}
      optionLabels={LABELS}
      allLabel="All vendors"
      value={value}
      onValueChange={onValueChange}
    />,
  );
  return { onValueChange, user };
}

describe("VendorFilterChips", () => {
  it("marks the all-chip pressed and vendors unpressed when nothing is selected", () => {
    setup([]);

    expect(screen.getByRole("button", { name: "All vendors" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("button", { name: /Alchemy/ })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
  });

  it("adds a vendor on click", async () => {
    const { onValueChange, user } = setup([]);

    await user.click(screen.getByRole("button", { name: /QuickNode/ }));

    expect(onValueChange).toHaveBeenCalledWith(["quicknode"]);
  });

  it("removes an already-selected vendor on click", async () => {
    const { onValueChange, user } = setup(["alchemy", "quicknode"]);

    await user.click(screen.getByRole("button", { name: /Alchemy/ }));

    expect(onValueChange).toHaveBeenCalledWith(["quicknode"]);
  });

  it("clears the selection via the all-chip", async () => {
    const { onValueChange, user } = setup(["alchemy"]);

    await user.click(screen.getByRole("button", { name: "All vendors" }));

    expect(onValueChange).toHaveBeenCalledWith([]);
  });

  it("does not emit when the all-chip is already active", async () => {
    const { onValueChange, user } = setup([]);

    await user.click(screen.getByRole("button", { name: "All vendors" }));

    expect(onValueChange).not.toHaveBeenCalled();
  });
});
