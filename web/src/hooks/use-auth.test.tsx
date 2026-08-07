import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { logout } from "@/api/auth/client";
import { useAuthStore } from "@/stores/auth-store";
import { createTestQueryClient, queryWrapper } from "@/test/query";

import { authIdentityQueryKey, useLogout } from "./use-auth";

vi.mock("@/api/auth/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/auth/client")>();
  return { ...actual, logout: vi.fn() };
});

const logoutMock = vi.mocked(logout);
const identity = {
  identity_type: "user" as const,
  id: "user-1",
  email: "member@example.com",
  name: "Member",
};

function setup() {
  const queryClient = createTestQueryClient();
  queryClient.setQueryData(authIdentityQueryKey, identity);
  queryClient.setQueryData(["accounts"], [{ id: "account-1" }]);
  useAuthStore.setState({ authIdentity: identity });

  const wrapper = queryWrapper(queryClient);
  const hook = renderHook(() => useLogout(), { wrapper });
  return { queryClient, ...hook };
}

afterEach(() => {
  useAuthStore.setState({ authIdentity: null });
  vi.clearAllMocks();
});

describe("useLogout", () => {
  it("clears identity state and its query only after success", async () => {
    logoutMock.mockResolvedValue();
    const { queryClient, result } = setup();

    await act(async () => {
      await result.current.mutateAsync();
    });

    expect(useAuthStore.getState().authIdentity).toBeNull();
    expect(queryClient.getQueryData(authIdentityQueryKey)).toBeUndefined();
    expect(queryClient.getQueryData(["accounts"])).toBeUndefined();
  });

  it("preserves identity state and its query when logout fails", async () => {
    const error = new Error("logout failed");
    logoutMock.mockRejectedValue(error);
    const { queryClient, result } = setup();

    await act(async () => {
      await expect(result.current.mutateAsync()).rejects.toBe(error);
    });

    expect(useAuthStore.getState().authIdentity).toEqual(identity);
    expect(queryClient.getQueryData(authIdentityQueryKey)).toEqual(identity);
    expect(queryClient.getQueryData(["accounts"])).toEqual([
      { id: "account-1" },
    ]);
  });
});
