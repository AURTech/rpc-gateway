import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SwapLabel } from "./swap-label";

describe("SwapLabel", () => {
  it("renders the current label", () => {
    render(<SwapLabel swapKey="idle">Save</SwapLabel>);

    expect(screen.getByText("Save")).toBeInTheDocument();
  });

  it("replaces the label when the key changes", async () => {
    const { rerender } = render(<SwapLabel swapKey="idle">Save</SwapLabel>);

    rerender(<SwapLabel swapKey="submitting">Saving…</SwapLabel>);

    expect(await screen.findByText("Saving…")).toBeInTheDocument();
    // mode="wait" — the old label leaves before the new one arrives, so both
    // are never in the accessible name at once.
    await waitFor(() =>
      expect(screen.queryByText("Save")).not.toBeInTheDocument(),
    );
  });

  it("keeps the label unchanged when the key is stable", () => {
    const { rerender } = render(<SwapLabel swapKey="idle">Save</SwapLabel>);
    rerender(<SwapLabel swapKey="idle">Save</SwapLabel>);

    expect(screen.getAllByText("Save")).toHaveLength(1);
  });
});
