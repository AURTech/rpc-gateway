import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { toast } from "sonner";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { copyToClipboard } from "@/lib/clipboard";

import { GatewayApiKeyCopy } from "./gateway-api-key-copy";

vi.mock("next-intl", async () => (await import("@/test/intl")).nextIntlMock());

vi.mock("sonner", async () => (await import("@/test/mocks")).sonnerMock());

vi.mock("@/lib/clipboard", async () =>
  (await import("@/test/mocks")).clipboardMock(),
);

const copyMock = vi.mocked(copyToClipboard);
const successToastMock = vi.mocked(toast.success);
const errorToastMock = vi.mocked(toast.error);

beforeEach(() => {
  vi.clearAllMocks();
});

describe("GatewayApiKeyCopy", () => {
  it("renders and copies the complete key", async () => {
    render(
      <GatewayApiKeyCopy
        pathKeyState={{
          pathKey: "ak_complete_secret",
          status: "available",
          refetchKeys: vi.fn(),
          isRefetchingKeys: false,
        }}
      />,
    );

    expect(screen.getByText("label")).toBeInTheDocument();
    const key = screen.getByText("ak_complete_secret");
    const copyButton = screen.getByRole("button", {
      name: "actions.copyPathKey",
    });
    expect(key).toHaveClass("truncate", "text-xs");
    expect(key).toHaveAttribute("title", "ak_complete_secret");
    expect(key.parentElement).toHaveClass("sm:w-80", "bg-ink-wash");
    expect(copyButton).toHaveClass("size-9");

    await userEvent.click(copyButton);

    await waitFor(() =>
      expect(copyMock).toHaveBeenCalledWith("ak_complete_secret"),
    );
    expect(screen.getByText("ak_complete_secret")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "copied" })).toBeInTheDocument();
    expect(successToastMock).not.toHaveBeenCalled();
  });

  it("shows an explicit loading state and disables copying", () => {
    render(
      <GatewayApiKeyCopy
        pathKeyState={{
          pathKey: null,
          status: "metadata-loading",
          refetchKeys: vi.fn(),
          isRefetchingKeys: true,
        }}
      />,
    );

    expect(screen.getByText("loading")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "actions.copyPathKey" }),
    ).toBeDisabled();
  });

  it("keeps metadata errors actionable and retries from the copy control", async () => {
    const refetchKeys = vi.fn();
    render(
      <GatewayApiKeyCopy
        pathKeyState={{
          pathKey: null,
          status: "metadata-error",
          refetchKeys,
          isRefetchingKeys: false,
        }}
      />,
    );

    expect(screen.getByText("metadataError")).toBeInTheDocument();
    await userEvent.click(
      screen.getByRole("button", { name: "actions.copyPathKey" }),
    );

    expect(errorToastMock).toHaveBeenCalledWith("metadataError");
    expect(refetchKeys).toHaveBeenCalledOnce();
  });
});
