import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import {
  INITIAL_PROVIDER_FORM,
  ProviderFormFields,
} from "./provider-form-fields";

vi.mock("next-intl", async () => (await import("@/test/intl")).nextIntlMock());

describe("ProviderFormFields", () => {
  it("shows the accepted dRPC credential formats", () => {
    const props = {
      values: { ...INITIAL_PROVIDER_FORM, vendor: "drpc" as const },
      onChange: vi.fn(),
      busy: false,
      idPrefix: "provider-test",
    };
    const { rerender } = render(<ProviderFormFields {...props} />);

    expect(screen.getByText("form.drpcSecretHint")).toBeInTheDocument();
    expect(
      screen.getByRole("textbox", { name: /form\.secret/ }),
    ).toHaveAttribute("placeholder", "form.drpcSecretPlaceholder");

    rerender(
      <ProviderFormFields {...props} secretHint="form.secretKeepHint" />,
    );

    expect(screen.getByText("form.drpcSecretKeepHint")).toBeInTheDocument();
  });
});
