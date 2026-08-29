import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { RoutingModeCards } from "./routing-mode-cards";

describe("RoutingModeCards", () => {
  it("uses the xl radius for each routing mode card", () => {
    render(
      <RoutingModeCards
        value="priority_failover"
        onChange={vi.fn()}
        ariaLabel="Route"
        options={[
          {
            value: "priority_failover",
            label: "Priority failover",
            hint: "Try endpoints in priority order.",
          },
          {
            value: "load_balance",
            label: "Load balancing",
            hint: "Distribute requests by weight.",
          },
        ]}
      />,
    );

    for (const radio of screen.getAllByRole("radio")) {
      expect(radio.nextElementSibling).toHaveClass("rounded-xl");
      expect(radio.nextElementSibling).not.toHaveClass("rounded-lg");
    }
  });
});
