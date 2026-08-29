import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ChainIcon, chainIconUrl } from "./chain-icon";

const MARK = '[data-slot="chain-testnet-mark"]';

describe("chainIconUrl", () => {
  it("uses the cryptocurrency symbol CDN path with the chain slug", () => {
    expect(chainIconUrl("solana")).toBe(
      "https://cdn.aurpay.net/cryptocurrency-symbol/sol.svg",
    );
    expect(chainIconUrl("ethereum")).toBe(
      "https://cdn.aurpay.net/cryptocurrency-symbol/eth.svg",
    );
  });
});

describe("ChainIcon", () => {
  // The chain-only branch must stay byte-identical: it is what every filter,
  // chain card header and ChainGroup renders, and a testnet mark there would
  // claim something about a network the icon doesn't stand for.
  it("renders a bare image with no wrapper when no network is given", () => {
    const { container } = render(<ChainIcon chain="ethereum" />);

    expect(container.firstElementChild?.tagName).toBe("IMG");
    expect(screen.getByAltText("Ethereum")).toBeInTheDocument();
    expect(container.querySelector(MARK)).toBeNull();
  });

  it("stays unmarked on a mainnet", () => {
    const { container } = render(
      <ChainIcon chain="ethereum" network="mainnet" />,
    );

    expect(container.firstElementChild?.tagName).toBe("IMG");
    expect(container.querySelector(MARK)).toBeNull();
  });

  // Solana's production network is `mainnet-beta`, not `mainnet` — the second
  // alias the testnet predicate has to know about.
  it("treats solana mainnet-beta as a mainnet", () => {
    const { container } = render(
      <ChainIcon chain="solana" network="mainnet-beta" />,
    );

    expect(container.firstElementChild?.tagName).toBe("IMG");
    expect(container.querySelector(MARK)).toBeNull();
  });

  it("wraps the logo with a mark on a testnet", () => {
    const { container } = render(
      <ChainIcon chain="ethereum" network="sepolia" />,
    );

    // The logo keeps its own colour, so the chain stays recognisable inside
    // the testnet outline.
    const image = screen.getByAltText("Ethereum");
    expect(image.className).not.toContain("saturate");
    expect(container.querySelector(MARK)).toBeInTheDocument();
  });

  // The alt stays chain-only whatever the network: the chain·network dropdowns
  // build their option name from this alt plus the visible network text, so a
  // network in here would be announced twice.
  it("keeps the alt chain-only and the mark out of the a11y tree", () => {
    const { container } = render(<ChainIcon chain="tron" network="nile" />);

    expect(screen.getByAltText("TRON")).toBeInTheDocument();
    expect(screen.queryByAltText("TRON Nile")).not.toBeInTheDocument();
    expect(container.querySelector(MARK)).toHaveAttribute("aria-hidden");
  });

  // The caller's className sizes whichever element is outermost. On the
  // testnet branch that's the wrapper, and the image just fills it — merging
  // the two would let tailwind-merge drop `size-full` for the caller's size.
  it("puts the caller's classes on the outermost element", () => {
    const mainnet = render(
      <ChainIcon chain="base" network="mainnet" className="size-4 shrink-0" />,
    );
    expect(mainnet.container.firstElementChild).toHaveClass(
      "size-4",
      "shrink-0",
    );

    const testnet = render(
      <ChainIcon chain="base" network="sepolia" className="size-4 shrink-0" />,
    );
    const wrapper = testnet.container.firstElementChild;
    expect(wrapper?.tagName).toBe("SPAN");
    expect(wrapper).toHaveClass("size-4", "shrink-0");
    expect(wrapper).not.toHaveClass("size-5");
    expect(wrapper?.querySelector("img")?.className).toContain("size-full");
  });
});
