import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useAuthStore } from "@/stores/auth-store";

import { PersonalAccessTokenCard } from "./personal-access-token-card";

const { createMock, revokeMock, tokenLimit } = vi.hoisted(() => ({
  createMock: vi.fn(),
  revokeMock: vi.fn(),
  tokenLimit: { active: 1, maxActive: 20 },
}));

vi.mock("next-intl", async () => (await import("@/test/intl")).nextIntlMock());

vi.mock("sonner", async () => (await import("@/test/mocks")).sonnerMock());

vi.mock("@/lib/clipboard", async () =>
  (await import("@/test/mocks")).clipboardMock(),
);

vi.mock("@/hooks/use-personal-access-tokens", () => ({
  usePersonalAccessTokens: () => ({
    isPending: false,
    isError: false,
    data: {
      total: 1,
      ...tokenLimit,
      items: [
        {
          id: "token-1",
          name: "Codex",
          token_prefix: "rg_pat_example",
          scopes: ["overview:read"],
          state: "active",
          expires_at: "2026-11-01T00:00:00Z",
          last_used_at: null,
          revoked_at: null,
          created_at: "2026-08-03T00:00:00Z",
        },
      ],
    },
  }),
  useCreatePersonalAccessToken: () => ({
    isPending: false,
    mutate: createMock,
  }),
  useRevokePersonalAccessToken: () => ({
    isPending: false,
    mutate: revokeMock,
  }),
}));

afterEach(() => {
  useAuthStore.setState({ authIdentity: null });
  tokenLimit.active = 1;
  tokenLimit.maxActive = 20;
  vi.clearAllMocks();
});

describe("PersonalAccessTokenCard", () => {
  it("shows token metadata without revealing a stored secret", () => {
    render(<PersonalAccessTokenCard />);

    expect(screen.getByText("Codex")).toBeInTheDocument();
    expect(screen.getByText("rg_pat_example…")).toBeInTheDocument();
    expect(screen.queryByText("rg_pat_example-secret")).toBeNull();
    expect(screen.getByRole("button", { name: "revoke" })).toBeInTheDocument();
    expect(screen.getByText("activeCount")).toBeInTheDocument();
  });

  it("disables creation when the active token limit is reached", () => {
    tokenLimit.active = 20;
    render(<PersonalAccessTokenCard />);

    expect(screen.getByRole("button", { name: "create" })).toBeDisabled();
    expect(screen.getByText(/limitReached/)).toBeInTheDocument();
  });

  it("shows admin scopes only to admins", async () => {
    const user = userEvent.setup();
    useAuthStore.setState({
      authIdentity: {
        identity_type: "user",
        id: "user-1",
        email: "member@example.com",
      },
    });
    const { unmount } = render(<PersonalAccessTokenCard />);
    await user.click(screen.getByRole("button", { name: "create" }));
    expect(screen.queryByText("accounts:read")).toBeNull();
    unmount();

    useAuthStore.setState({
      authIdentity: {
        identity_type: "admin",
        id: "admin-1",
        email: "admin@example.com",
      },
    });
    render(<PersonalAccessTokenCard />);
    await user.click(screen.getByRole("button", { name: "create" }));
    expect(screen.getByText("accounts:read")).toBeInTheDocument();
    expect(screen.getByText("policies:write")).toBeInTheDocument();
  });

  it("reveals a newly created secret once", async () => {
    createMock.mockImplementation(
      (
        _input: unknown,
        options: { onSuccess: (value: Record<string, unknown>) => void },
      ) =>
        options.onSuccess({
          id: "new-token",
          name: "Local agent",
          token_prefix: "rg_pat_new",
          token: "rg_pat_new-secret",
          scopes: ["overview:read"],
          state: "active",
          expires_at: "2026-11-01T00:00:00Z",
          last_used_at: null,
          revoked_at: null,
          created_at: "2026-08-03T00:00:00Z",
        }),
    );
    const user = userEvent.setup();
    render(<PersonalAccessTokenCard />);
    await user.click(screen.getByRole("button", { name: "create" }));
    const dialog = screen.getByRole("dialog");
    await user.type(within(dialog).getByLabelText("name"), "Local agent");
    await user.click(within(dialog).getByRole("button", { name: "create" }));

    expect(screen.getByText("rg_pat_new-secret")).toBeInTheDocument();
    expect(screen.getByText("secretDescription")).toBeInTheDocument();
  });
});
