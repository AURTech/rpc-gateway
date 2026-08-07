import { describe, expect, it } from "vitest";

import { providerSupportsNetwork } from "@/api/providers/capabilities";

describe("provider network capabilities", () => {
  it("matches vendor-specific catalog support", () => {
    expect(
      providerSupportsNetwork("alchemy", {
        chain: "litecoin",
        network: "testnet",
      }),
    ).toBe(true);
    expect(
      providerSupportsNetwork("chainstack", {
        chain: "litecoin",
        network: "testnet",
      }),
    ).toBe(false);
    expect(
      providerSupportsNetwork("drpc", {
        chain: "bitcoin",
        network: "testnet",
      }),
    ).toBe(false);
    expect(
      providerSupportsNetwork("tenderly", {
        chain: "bsc",
        network: "mainnet",
      }),
    ).toBe(false);
  });
});
