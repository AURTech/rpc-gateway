import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ChainGroup } from "./chain-group";

describe("ChainGroup", () => {
  it("renders one logo per chain with alt text", () => {
    render(<ChainGroup chains={["ethereum", "solana"]} />);

    expect(screen.getByAltText("Ethereum")).toBeInTheDocument();
    expect(screen.getByAltText("Solana")).toBeInTheDocument();
  });

  it("dedupes repeated chains", () => {
    render(<ChainGroup chains={["ethereum", "ethereum", "base"]} />);

    expect(screen.getAllByAltText("Ethereum")).toHaveLength(1);
  });

  it("collapses chains past `max` into a +N pill that names the overflow", () => {
    render(
      <ChainGroup
        chains={["ethereum", "polygon", "bsc", "arbitrum"]}
        max={2}
      />,
    );

    // Only the first two render as logos.
    expect(screen.getByAltText("Ethereum")).toBeInTheDocument();
    expect(screen.getByAltText("Polygon")).toBeInTheDocument();
    expect(screen.queryByAltText("BNB Smart Chain")).not.toBeInTheDocument();

    // The rest collapse into a labelled +2 pill.
    const pill = screen.getByLabelText("+2: BNB Smart Chain, Arbitrum");
    expect(pill).toHaveTextContent("+2");
  });

  it("renders an em dash when there are no chains", () => {
    const { container } = render(<ChainGroup chains={[]} />);

    expect(container.querySelector("img")).toBeNull();
    expect(container.textContent).toBe("—");
  });
});
