import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { logout } from "@/api/auth/client";
import { ApiError } from "@/api/client";
import { getQueryClient } from "@/lib/query-client";
import { useAuthStore } from "@/stores/auth-store";
import { renderWithQuery } from "@/test/query";

import { DangerSection } from "./danger-section";

const { replaceMock } = vi.hoisted(() => ({ replaceMock: vi.fn() }));

vi.mock("next-intl", async () => (await import("@/test/intl")).nextIntlMock());

vi.mock("@/i18n/navigation", async () =>
  (await import("@/test/navigation")).navigationMock({ replace: replaceMock }),
);

vi.mock("@/api/auth/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/auth/client")>();
  return { ...actual, logout: vi.fn() };
});

vi.mock("sonner", async () => (await import("@/test/mocks")).sonnerMock());

const logoutMock = vi.mocked(logout);

afterEach(() => {
  getQueryClient().clear();
  useAuthStore.setState({ authIdentity: null });
  vi.clearAllMocks();
});

describe("DangerSection", () => {
  it("keeps the session on failure, shows the server error, and allows retry", async () => {
    const { toast } = await import("sonner");
    const queryClient = getQueryClient();
    const identity = {
      identity_type: "user" as const,
      id: "user-1",
      email: "member@example.com",
      name: "Member",
    };
    const error = new ApiError({
      kind: "http",
      status: 503,
      data: {
        success: false,
        msg: "Sign-out service is unavailable. Please retry.",
      },
    });
    useAuthStore.setState({ authIdentity: identity });
    logoutMock.mockRejectedValueOnce(error).mockResolvedValueOnce();
    const user = userEvent.setup();

    renderWithQuery(<DangerSection />, queryClient);

    const button = screen.getByRole("button", { name: "sign_out" });
    await user.click(button);

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        "Sign-out service is unavailable. Please retry.",
      ),
    );
    expect(replaceMock).not.toHaveBeenCalled();
    expect(useAuthStore.getState().authIdentity).toEqual(identity);
    expect(button).toBeEnabled();

    await user.click(button);

    await waitFor(() => expect(replaceMock).toHaveBeenCalledWith("/login"));
    expect(useAuthStore.getState().authIdentity).toBeNull();
  });
});
