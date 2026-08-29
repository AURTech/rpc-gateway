import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { renderWithQuery } from "@/test/query";

import LoginPage from "./page";

const { getAurPayLoginUrlMock, getGoogleLoginUrlMock } = vi.hoisted(() => ({
  getAurPayLoginUrlMock: vi.fn(
    (options?: { prompt?: "login" | "select_account" }) =>
      options?.prompt ? `#aurpay-${options.prompt}` : "#aurpay-login",
  ),
  getGoogleLoginUrlMock: vi.fn(() => "#google-login"),
}));

vi.mock("next-intl", async () => (await import("@/test/intl")).nextIntlMock());

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@/i18n/navigation", async () =>
  (await import("@/test/navigation")).navigationMock(),
);

vi.mock("@/api/auth/actions", () => ({
  getAurPayLoginUrl: getAurPayLoginUrlMock,
  getGoogleLoginUrl: getGoogleLoginUrlMock,
}));

describe("LoginPage", () => {
  it("places Google and Aurpay sign-in before the email-password form", () => {
    renderWithQuery(<LoginPage />);

    const googleButton = screen.getByRole("button", {
      name: "continue_with_google_aria",
    });
    const aurpayButton = screen.getByRole("button", {
      name: "sign_in_with_aurpay_aria",
    });
    const emailInput = screen.getByRole("textbox", { name: "email_label" });

    expect(googleButton.compareDocumentPosition(aurpayButton)).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    );
    expect(aurpayButton.compareDocumentPosition(emailInput)).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    );
    expect(aurpayButton).toBeEnabled();
    expect(aurpayButton).not.toHaveAttribute("onclick");
  });

  it("keeps the existing Google sign-in action", async () => {
    renderWithQuery(<LoginPage />);

    await userEvent.click(
      screen.getByRole("button", { name: "continue_with_google_aria" }),
    );

    expect(getGoogleLoginUrlMock).toHaveBeenCalledOnce();
  });

  it("asks AurPay to select an account from the primary action", async () => {
    renderWithQuery(<LoginPage />);

    await userEvent.click(
      screen.getByRole("button", { name: "sign_in_with_aurpay_aria" }),
    );

    expect(getAurPayLoginUrlMock).toHaveBeenCalledWith({
      prompt: "select_account",
    });
    expect(screen.getAllByRole("button", { name: /aurpay/i })).toHaveLength(1);
  });
});
