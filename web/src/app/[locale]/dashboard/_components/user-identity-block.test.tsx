import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useAuthStore } from "@/stores/auth-store";

import { UserIdentityBlock } from "./user-identity-block";

vi.mock("next-intl", async () => (await import("@/test/intl")).nextIntlMock());

vi.mock("@/hooks/use-auth", () => ({
  useLogout: () => ({ isPending: false, mutate: vi.fn() }),
}));

vi.mock("@/i18n/navigation", async () =>
  (await import("@/test/navigation")).navigationMock({
    pathname: "/dashboard",
  }),
);

describe("UserIdentityBlock", () => {
  beforeEach(() => {
    useAuthStore.setState({
      authIdentity: {
        identity_type: "user",
        id: "user-1",
        email: "member@example.com",
        name: "Member",
      },
    });
  });

  it("opens the external documentation site from the user menu", async () => {
    const user = userEvent.setup();
    render(<UserIdentityBlock />);

    await user.click(await screen.findByRole("button", { name: "Member" }));

    const docsLink = await screen.findByRole("menuitem", { name: "docs" });
    expect(docsLink).toHaveAttribute("href", "https://rpc.aurpay.net");
    expect(docsLink).toHaveAttribute("target", "_blank");
    expect(docsLink).toHaveAttribute("rel", "noreferrer");
  });
});
