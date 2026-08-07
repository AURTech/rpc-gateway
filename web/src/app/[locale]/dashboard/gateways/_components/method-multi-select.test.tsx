import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { MethodMultiSelect } from "./method-multi-select";

vi.mock("next-intl", async () => (await import("@/test/intl")).nextIntlMock());

vi.mock("@/hooks/use-rpc-methods", () => ({
  useRpcMethodsQuery: () => ({
    data: {
      items: [
        {
          protocol: "evm",
          protocol_label: "EVM",
          sources: [],
          methods: [
            {
              value: "eth_getBalance",
              label: "eth_getBalance",
              namespace: "eth",
              namespace_label: "Ethereum",
              risk: "read",
              risk_label: "Read",
              deprecated: false,
            },
            {
              value: "eth_getBlockByNumber",
              label: "eth_getBlockByNumber",
              namespace: "eth",
              namespace_label: "Ethereum",
              risk: "read",
              risk_label: "Read",
              deprecated: false,
            },
          ],
        },
      ],
    },
    isLoading: false,
    isError: false,
  }),
}));

describe("MethodMultiSelect", () => {
  it("completes the highlighted method with Tab", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <MethodMultiSelect
        protocol="evm"
        value={[]}
        assigned={new Set()}
        onChange={onChange}
      />,
    );

    const input = screen.getByPlaceholderText(
      "methodRoutes.form.searchPlaceholder",
    );
    await user.type(input, "eth_getBal");
    expect(
      await screen.findByRole("option", { name: /eth_getBalance/ }),
    ).toHaveAttribute("data-highlighted");

    await user.tab();

    expect(onChange).toHaveBeenCalledWith(["eth_getBalance"]);
    expect(input).toHaveFocus();
  });

  it("keeps normal Tab navigation when the search is empty", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <MethodMultiSelect
        protocol="evm"
        value={[]}
        assigned={new Set()}
        onChange={onChange}
      />,
    );

    const input = screen.getByPlaceholderText(
      "methodRoutes.form.searchPlaceholder",
    );
    await user.click(input);
    await user.tab();

    expect(onChange).not.toHaveBeenCalled();
    expect(input).not.toHaveFocus();
  });
});
